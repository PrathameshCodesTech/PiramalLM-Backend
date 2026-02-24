"""
Billing Rules Engine
====================
Called after specific user actions to evaluate active rules and produce
PendingAction records (MANUAL mode) or fire immediately (AUTO mode).

Entry points:
  RulesEngine.check_credit_rules(credit_note, scope, user)
      → called after CreditNote is created

  RulesEngine.check_dispute_rules(invoice, scope, user)
      → called after Invoice is marked DISPUTED
"""

from decimal import Decimal
from django.utils import timezone
from . import models


# ---------------------------------------------------------------------------
# Operator helpers
# ---------------------------------------------------------------------------

_OP = {
    "GT":  lambda a, b: a > b,
    "LT":  lambda a, b: a < b,
    "EQ":  lambda a, b: a == b,
    "GTE": lambda a, b: a >= b,
    "LTE": lambda a, b: a <= b,
    "NE":  lambda a, b: a != b,
}


def _evaluate(condition_type, operator, threshold, invoice):
    """
    Evaluate a single DisputeRule condition against an Invoice.
    Returns True if the condition matches.
    """
    fn = _OP.get(operator)
    if not fn:
        return False

    threshold = Decimal(str(threshold))

    if condition_type in ("INVOICE_AMOUNT", "DISPUTE_AMOUNT"):
        return fn(invoice.total_amount, threshold)

    if condition_type == "INVOICE_AGE":
        age = Decimal((timezone.now().date() - invoice.invoice_date).days)
        return fn(age, threshold)

    if condition_type == "DISPUTE_COUNT":
        count = Decimal(
            models.Invoice.objects.filter(
                agreement__tenant=invoice.agreement.tenant,
                is_disputed=True,
            ).count()
        )
        return fn(count, threshold)

    # CUSTOMER_TYPE and unknown — skip
    return False


def _create_pending(scope, user, rule_type_val, rule_kwargs,
                    obj_type_val, obj_id, desc,
                    status_val=None, applied_at=None, applied_by=None):
    """
    Shared helper to create a PendingAction record.
    rule_kwargs: dict with ONE of billing_rule/credit_rule/dispute_rule set.
    """
    if status_val is None:
        status_val = models.PendingAction.Status.PENDING

    models.PendingAction.objects.create(
        scope=scope,
        rule_type=rule_type_val,
        object_type=obj_type_val,
        object_id=obj_id,
        action_description=desc,
        status=status_val,
        applied_at=applied_at,
        applied_by=applied_by,
        created_by=user,
        **rule_kwargs,
    )


# ---------------------------------------------------------------------------
# Credit Rule evaluation
# ---------------------------------------------------------------------------

# Map CreditNote.reason → CreditRule.trigger_type
_REASON_TO_TRIGGER = {
    "BILLING_ERROR":     "BILLING_ERROR",
    "PAYMENT_VARIANCE":  "PAYMENT_VARIANCE",
    "GOODWILL":          "GOODWILL",
    "SERVICE_ISSUE":     "SERVICE_CREDIT",
    "RATE_ADJUSTMENT":   "DISCOUNT_REQUEST",
    "EARLY_TERMINATION": "RETURN_REQUEST",
}


def _credit_rule_matches(rule, credit_note):
    """Return True if this CreditRule applies to the given CreditNote."""
    if rule.variance_threshold:
        if rule.variance_basis == "PERCENTAGE":
            inv_amount = credit_note.invoice.total_amount
            if inv_amount:
                pct = (credit_note.amount / inv_amount) * 100
                if pct <= rule.variance_threshold:
                    return False
        elif rule.variance_basis == "FIXED_AMOUNT":
            if credit_note.amount < rule.variance_threshold:
                return False

    if rule.max_credit_amount and credit_note.amount > rule.max_credit_amount:
        return False

    return True


class RulesEngine:

    @staticmethod
    def check_credit_rules(credit_note, scope, user):
        """
        Called after a CreditNote is created.
        Finds the first matching ACTIVE CreditRule and either:
          - AUTO: sets status/approval on the CN and logs an APPLIED action
          - MANUAL: creates a PENDING action for the user to review
        """
        trigger_type = _REASON_TO_TRIGGER.get(credit_note.reason)
        if not trigger_type:
            return  # No mapping — nothing to check

        rules = models.CreditRule.objects.filter(
            scope=scope,
            status=models.CreditRule.RuleStatus.ACTIVE,
            trigger_type=trigger_type,
        )

        for rule in rules:
            if not _credit_rule_matches(rule, credit_note):
                continue

            if rule.trigger_mode == models.CreditRule.TriggerMode.AUTO:
                # Fire immediately
                if rule.auto_approve:
                    credit_note.status = models.CreditNote.CreditNoteStatus.APPROVED
                    credit_note.approved_at = timezone.now()
                else:
                    credit_note.status = models.CreditNote.CreditNoteStatus.PENDING_APPROVAL
                credit_note.credit_rule = rule
                credit_note.save(update_fields=["status", "approved_at", "credit_rule"])

                _create_pending(
                    scope=scope, user=user,
                    rule_type_val=models.PendingAction.RuleType.CREDIT,
                    rule_kwargs={"credit_rule": rule},
                    obj_type_val=models.PendingAction.ObjectType.CREDIT_NOTE,
                    obj_id=credit_note.id,
                    desc=(
                        f"[AUTO] Credit Rule '{rule.name}' applied to "
                        f"CN {credit_note.credit_note_number} (₹{credit_note.amount}) — "
                        f"{'auto-approved' if rule.auto_approve else (rule.approval_role.name if rule.approval_role_id else 'requires approval')}"
                    ),
                    status_val=models.PendingAction.Status.APPLIED,
                    applied_at=timezone.now(),
                    applied_by=user,
                )
            else:
                # MANUAL — create alert
                desc = (
                    f"Credit Rule '{rule.name}' matched CN {credit_note.credit_note_number} "
                    f"(₹{credit_note.amount}, reason: {credit_note.get_reason_display()}) — "
                    f"requires {rule.approval_role.name if rule.approval_role_id else 'role'} approval"
                )
                _create_pending(
                    scope=scope, user=user,
                    rule_type_val=models.PendingAction.RuleType.CREDIT,
                    rule_kwargs={"credit_rule": rule},
                    obj_type_val=models.PendingAction.ObjectType.CREDIT_NOTE,
                    obj_id=credit_note.id,
                    desc=desc,
                )

            break  # Only apply the first matching rule

    @staticmethod
    def check_dispute_rules(invoice, scope, user):
        """
        Called when an Invoice is disputed.
        Finds the first matching ACTIVE DisputeRule (by priority) and either:
          - AUTO: applies hold/SLA immediately and logs an APPLIED action
          - MANUAL: creates a PENDING action for the user to review
        """
        rules = models.DisputeRule.objects.filter(
            scope=scope,
            status=models.DisputeRule.RuleStatus.ACTIVE,
        ).order_by("priority")

        for rule in rules:
            if not _evaluate(rule.condition_type, rule.operator, rule.threshold_value, invoice):
                continue

            if rule.trigger_mode == models.DisputeRule.TriggerMode.AUTO:
                # Apply immediately — enforce dispute hold via AR rules
                try:
                    ar = invoice.agreement.ar_rules
                    ar.dispute_hold = True
                    ar.stop_interest_on_dispute = True
                    ar.stop_reminders_on_dispute = True
                    ar.save(update_fields=[
                        "dispute_hold",
                        "stop_interest_on_dispute",
                        "stop_reminders_on_dispute",
                    ])
                except Exception:
                    pass  # AR rules may not exist; don't block the dispute

                _create_pending(
                    scope=scope, user=user,
                    rule_type_val=models.PendingAction.RuleType.DISPUTE,
                    rule_kwargs={"dispute_rule": rule},
                    obj_type_val=models.PendingAction.ObjectType.DISPUTE,
                    obj_id=invoice.id,
                    desc=(
                        f"[AUTO] Dispute Rule '{rule.name}' fired on Invoice "
                        f"{invoice.invoice_number} (₹{invoice.total_amount}): "
                        f"{rule.action_description}"
                        + (f" → Route to: {rule.route_to_role}" if rule.route_to_role else "")
                    ),
                    status_val=models.PendingAction.Status.APPLIED,
                    applied_at=timezone.now(),
                    applied_by=user,
                )
            else:
                # MANUAL — create alert
                desc = (
                    f"Dispute Rule '{rule.name}' matched Invoice "
                    f"{invoice.invoice_number} (₹{invoice.total_amount}): "
                    f"{rule.action_description}"
                    + (f" → Route to: {rule.route_to_role}" if rule.route_to_role else "")
                )
                _create_pending(
                    scope=scope, user=user,
                    rule_type_val=models.PendingAction.RuleType.DISPUTE,
                    rule_kwargs={"dispute_rule": rule},
                    obj_type_val=models.PendingAction.ObjectType.DISPUTE,
                    obj_id=invoice.id,
                    desc=desc,
                )

            break  # Only the highest-priority matching rule fires
