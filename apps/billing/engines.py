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

  RulesEngine.check_billing_rules(invoice, scope, user=None)
      → called by the nightly process_overdue_invoices management command
        for each invoice that is currently OVERDUE
"""

from datetime import timedelta
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
        Only evaluates credit rules explicitly attached to the agreement.
        No implicit fallback to scope-level rules.
        Finds the first matching ACTIVE CreditRule and either:
          - AUTO: sets status/approval on the CN and logs an APPLIED action
          - MANUAL: creates a PENDING action for the user to review
        """
        trigger_type = _REASON_TO_TRIGGER.get(credit_note.reason)
        if not trigger_type:
            return  # No mapping — nothing to check

        agreement = getattr(credit_note, "agreement", None) or getattr(
            credit_note.invoice, "agreement", None
        )
        if not agreement:
            return  # No agreement attached — no rules to evaluate

        rules = models.CreditRule.objects.filter(
            agreement=agreement,
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
        Only evaluates dispute rules explicitly attached to the agreement.
        No implicit fallback to scope-level rules.
        Finds the first matching ACTIVE DisputeRule (by priority) and either:
          - AUTO: applies hold/SLA immediately and logs an APPLIED action
          - MANUAL: creates a PENDING action for the user to review
        """
        if not invoice.agreement_id:
            return  # No agreement attached — no rules to evaluate

        rules = models.DisputeRule.objects.filter(
            agreement=invoice.agreement,
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

    @staticmethod
    def check_billing_rules(invoice, scope, user=None):
        """
        Called by the nightly process_overdue_invoices command for each OVERDUE invoice.
        Only evaluates billing rules explicitly attached to the agreement.
        No implicit fallback to scope-level rules.

        Finds all ACTIVE BillingRules with trigger_event=OVERDUE and:
          - Skips rules whose grace_period_days haven't elapsed yet
          - AUTO: creates a new LATE_FEE Invoice and logs an APPLIED action
          - MANUAL: creates a PENDING action for the user to review

        Only the first matching rule fires per invoice.
        """
        today = timezone.now().date()
        overdue_days = (today - invoice.due_date).days

        if not invoice.agreement_id:
            return  # No agreement attached — no rules to evaluate

        rules = models.BillingRule.objects.filter(
            agreement=invoice.agreement,
            status=models.BillingRule.RuleStatus.ACTIVE,
            trigger_event=models.BillingRule.TriggerEvent.OVERDUE,
        )

        for rule in rules:
            # Respect grace period
            if overdue_days < rule.grace_period_days:
                continue

            charge = _calculate_billing_charge(rule, invoice, overdue_days)
            if charge <= 0:
                continue

            # Apply cap
            if rule.max_cap_amount and charge > rule.max_cap_amount:
                charge = rule.max_cap_amount

            desc = (
                f"Billing Rule '{rule.name}' [{rule.get_charge_type_display()}]: "
                f"₹{charge:.2f} on Invoice {invoice.invoice_number} "
                f"({overdue_days} days overdue)"
            )

            if rule.trigger_mode == models.BillingRule.TriggerMode.AUTO:
                _create_late_fee_invoice(invoice, rule, charge, today)
                _create_pending(
                    scope=scope, user=user,
                    rule_type_val=models.PendingAction.RuleType.BILLING,
                    rule_kwargs={"billing_rule": rule},
                    obj_type_val=models.PendingAction.ObjectType.INVOICE,
                    obj_id=invoice.id,
                    desc=f"[AUTO] {desc}",
                    status_val=models.PendingAction.Status.APPLIED,
                    applied_at=timezone.now(),
                    applied_by=user,
                )
            else:
                _create_pending(
                    scope=scope, user=user,
                    rule_type_val=models.PendingAction.RuleType.BILLING,
                    rule_kwargs={"billing_rule": rule},
                    obj_type_val=models.PendingAction.ObjectType.INVOICE,
                    obj_id=invoice.id,
                    desc=desc,
                )

            break  # Only the first matching billing rule fires per invoice


# ---------------------------------------------------------------------------
# Billing Rule evaluation helpers
# ---------------------------------------------------------------------------

def _calculate_billing_charge(rule, invoice, overdue_days):
    """
    Calculate the late-fee / penalty charge for a BillingRule.
    Returns a Decimal charge amount (>= 0).
    """
    balance = invoice.balance_due

    if rule.calculation_method == models.BillingRule.CalculationMethod.FLAT:
        return rule.amount or Decimal("0")

    if rule.calculation_method == models.BillingRule.CalculationMethod.PERCENTAGE_OF_OUTSTANDING:
        if rule.rate:
            return balance * (rule.rate / 100)
        return Decimal("0")

    if rule.calculation_method == models.BillingRule.CalculationMethod.PERCENTAGE_OF_RENT:
        rent = Decimal("0")
        try:
            rent = invoice.agreement.financials.base_rent_monthly or Decimal("0")
        except Exception:
            pass
        if rule.rate:
            return rent * (rule.rate / 100)
        return Decimal("0")

    if rule.calculation_method == models.BillingRule.CalculationMethod.PER_DAY:
        if rule.amount:
            return rule.amount * Decimal(str(overdue_days))
        return Decimal("0")

    return Decimal("0")


_CHARGE_TYPE_TO_LINE_ITEM_TYPE = {
    "LATE_PAYMENT_FEE":    models.InvoiceLineItem.LineItemType.LATE_FEE,
    "INTEREST":            models.InvoiceLineItem.LineItemType.INTEREST,
    "PENALTY":             models.InvoiceLineItem.LineItemType.OTHER,
    "ADMINISTRATIVE_FEE":  models.InvoiceLineItem.LineItemType.ADJUSTMENT,
    "CAM_RECONCILIATION":  models.InvoiceLineItem.LineItemType.CAM,
    "OTHER":               models.InvoiceLineItem.LineItemType.OTHER,
}


def _create_late_fee_invoice(invoice, rule, charge, today):
    """
    Create a new LATE_FEE Invoice linked to the same agreement.
    Also adds a single InvoiceLineItem whose type reflects the rule's charge_type.
    """
    new_number = f"LF-{invoice.invoice_number}-{today.strftime('%Y%m%d')}"

    due_date = today
    try:
        site = invoice.agreement.site
        config = models.SiteBillingConfig.objects.get(site=site, scope=invoice.scope)
        term_days_map = {
            "DUE_ON_RECEIPT": 0, "NET_7": 7, "NET_15": 15,
            "NET_30": 30, "NET_45": 45, "NET_60": 60,
        }
        due_date = today + timedelta(days=term_days_map.get(config.default_payment_term, 0))
    except Exception:
        pass

    late_inv = models.Invoice.objects.create(
        scope=invoice.scope,
        agreement=invoice.agreement,
        invoice_number=new_number,
        invoice_type=models.Invoice.InvoiceType.LATE_FEE,
        status=models.Invoice.InvoiceStatus.PENDING,
        invoice_date=today,
        due_date=due_date,
        subtotal=charge,
        tax_amount=Decimal("0"),
        total_amount=charge,
        amount_paid=Decimal("0"),
        balance_due=charge,
        notes=(
            f"Auto-generated by Billing Rule '{rule.name}' "
            f"for overdue Invoice {invoice.invoice_number}"
        ),
    )

    line_item_type = _CHARGE_TYPE_TO_LINE_ITEM_TYPE.get(
        rule.charge_type,
        models.InvoiceLineItem.LineItemType.LATE_FEE,
    )
    models.InvoiceLineItem.objects.create(
        invoice=late_inv,
        scope=invoice.scope,
        item_type=line_item_type,
        description=f"{rule.get_charge_type_display()} – {rule.name}",
        quantity=Decimal("1"),
        unit_price=charge,
        tax_rate=Decimal("0"),
    )

    return late_inv
