"""
Approval Matrices — models for lease approval workflow rules.

Structure:
  ApprovalRule  — the rule definition with conditions + SLA settings
  ApprovalLevel — L1/L2/L3 approver tiers attached to a rule
  ApprovalRuleLog — audit trail of rule changes
"""

from django.conf import settings
from django.db import models

from apps.core.models import AuditModel


class ApprovalRule(AuditModel):
    """
    Defines when a lease requires approval and who approves it.
    Conditions: lease value range, tenant types, lease term range.
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"

    class TenantType(models.TextChoices):
        CORPORATE = "CORPORATE", "Corporate"
        RETAIL = "RETAIL", "Retail"
        INDUSTRIAL = "INDUSTRIAL", "Industrial"
        RESIDENTIAL = "RESIDENTIAL", "Residential"

    scope = models.ForeignKey(
        "accounts.TenantScope",
        on_delete=models.CASCADE,
        related_name="approval_rules",
    )
    name = models.CharField(max_length=200)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )

    # ── Conditions ───────────────────────────────────────────────────────────
    lease_value_min = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text="Minimum lease value (INR) to trigger this rule",
    )
    lease_value_max = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text="Maximum lease value (INR) to trigger this rule (null = no upper limit)",
    )
    tenant_types = models.JSONField(
        default=list,
        blank=True,
        help_text="List of TenantType values; empty = applies to all",
    )
    lease_term_min_months = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Minimum lease term in months",
    )
    lease_term_max_months = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Maximum lease term in months (null = no upper limit)",
    )

    # ── SLA ──────────────────────────────────────────────────────────────────
    overall_sla_hours = models.PositiveIntegerField(
        default=48,
        help_text="Total SLA in hours across all approval levels",
    )

    # ── Escalation ───────────────────────────────────────────────────────────
    enable_escalations = models.BooleanField(default=False)
    escalate_after_hours = models.PositiveIntegerField(
        default=24,
        help_text="Hours of inaction before escalation triggers",
    )
    escalate_to_role = models.ForeignKey(
        "accounts.Role",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="escalation_rules",
        help_text="Role to escalate to if no action within escalate_after_hours",
    )
    send_escalation_notification = models.BooleanField(default=False)

    # ── Options ──────────────────────────────────────────────────────────────
    parallel_approvals_same_level = models.BooleanField(
        default=False,
        help_text="If True, all approvers at same level can approve in parallel",
    )

    class Meta:
        ordering = ["lease_value_min", "name"]

    def __str__(self):
        return f"ApprovalRule({self.name})"

    def activate(self):
        self.status = self.Status.ACTIVE
        self.save(update_fields=["status", "updated_at"])
        ApprovalRuleLog.objects.create(
            rule=self,
            action=ApprovalRuleLog.Action.ACTIVATED,
            detail=f"Rule activated.",
        )

    def deactivate(self):
        self.status = self.Status.INACTIVE
        self.save(update_fields=["status", "updated_at"])
        ApprovalRuleLog.objects.create(
            rule=self,
            action=ApprovalRuleLog.Action.DEACTIVATED,
            detail=f"Rule deactivated.",
        )

    def get_label(self):
        """Human-readable threshold label like '<₹50L'."""
        def fmt(v):
            if v is None:
                return None
            v = float(v)
            if v >= 1e7:
                return f"₹{v/1e7:.1f}Cr".rstrip("0").rstrip(".")
            if v >= 1e5:
                return f"₹{v/1e5:.0f}L"
            return f"₹{v:,.0f}"

        lo = fmt(self.lease_value_min)
        hi = fmt(self.lease_value_max)
        if lo and hi:
            return f"{lo}–{hi}"
        if lo:
            return f">{lo}"
        if hi:
            return f"<{hi}"
        return self.name

    def matches(self, lease_value=None, tenant_type=None, lease_term_months=None):
        """Check if given parameters trigger this rule."""
        if self.status != self.Status.ACTIVE:
            return False
        if lease_value is not None:
            if self.lease_value_min is not None and lease_value < float(self.lease_value_min):
                return False
            if self.lease_value_max is not None and lease_value > float(self.lease_value_max):
                return False
        if tenant_type and self.tenant_types:
            if tenant_type not in self.tenant_types:
                return False
        if lease_term_months is not None:
            if self.lease_term_min_months is not None and lease_term_months < self.lease_term_min_months:
                return False
            if self.lease_term_max_months is not None and lease_term_months > self.lease_term_max_months:
                return False
        return True


class ApprovalLevel(AuditModel):
    """A single approver tier (L1, L2, L3) within an ApprovalRule."""

    rule = models.ForeignKey(
        ApprovalRule,
        on_delete=models.CASCADE,
        related_name="levels",
    )
    level = models.PositiveSmallIntegerField(
        help_text="1 = L1 (first approver), 2 = L2, etc.",
    )
    role = models.ForeignKey(
        "accounts.Role",
        on_delete=models.PROTECT,
        related_name="approval_levels",
    )
    approval_required = models.BooleanField(
        default=True,
        help_text="If False, this level is informational only (notify but don't block)",
    )
    sla_hours = models.PositiveIntegerField(
        default=24,
        help_text="SLA for this individual level in hours",
    )
    allow_auto_skip_if_vacant = models.BooleanField(
        default=False,
        help_text="Skip this level automatically if no user has this role",
    )

    class Meta:
        ordering = ["rule", "level"]
        constraints = [
            models.UniqueConstraint(
                fields=["rule", "level"],
                name="uq_approval_rule_level",
            ),
        ]

    def __str__(self):
        return f"L{self.level} – {self.role_id} (Rule {self.rule_id})"


class ApprovalRuleLog(models.Model):
    """Immutable audit trail for approval rule changes."""

    class Action(models.TextChoices):
        CREATED = "CREATED", "Created"
        UPDATED = "UPDATED", "Updated"
        ACTIVATED = "ACTIVATED", "Activated"
        DEACTIVATED = "DEACTIVATED", "Deactivated"
        DELETED = "DELETED", "Deleted"

    rule = models.ForeignKey(
        ApprovalRule,
        on_delete=models.CASCADE,
        related_name="logs",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approval_rule_logs",
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    detail = models.TextField(blank=True, default="")
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"[{self.action}] Rule {self.rule_id} @ {self.timestamp}"
