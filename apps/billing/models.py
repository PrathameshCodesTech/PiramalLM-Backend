from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from decimal import Decimal
from apps.core.models import TenantModel


# =============================================================================
# AGEING BUCKET CONFIGURATION (Tab 4)
# =============================================================================

class AgeingBucket(TenantModel):
    """
    Defines ageing buckets for AR aging reports.
    Scope-level configuration.

    UI: Ageing Bucket Configuration tab - Bucket list
    """

    label = models.CharField(
        max_length=50,
        help_text="Display label e.g., 'Current (0-30)', '31-60 Days'"
    )
    from_days = models.PositiveIntegerField(
        help_text="Start of bucket range (inclusive)"
    )
    to_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="End of bucket range (inclusive). Null means open-ended (e.g., 121+ days)"
    )
    reporting_label = models.CharField(
        max_length=50,
        blank=True,
        help_text="Label for reports e.g., 'Current', '31-60 Days'"
    )
    color_code = models.CharField(
        max_length=20,
        default="Gray",
        help_text="Color name for UI display: Blue, Purple, Orange, Red, Gray"
    )
    include_in_dso = models.BooleanField(
        default=True,
        help_text="Include this bucket in Days Sales Outstanding calculation"
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Display order of buckets"
    )
    status = models.CharField(
        max_length=20,
        choices=[("ACTIVE", "Active"), ("INACTIVE", "Inactive")],
        default="ACTIVE"
    )

    class Meta:
        verbose_name = "Ageing Bucket"
        verbose_name_plural = "Ageing Buckets"
        ordering = ["sort_order", "from_days"]
        constraints = [
            models.UniqueConstraint(
                fields=["scope", "label"],
                name="unique_ageing_bucket_label_per_scope"
            )
        ]

    def __str__(self):
        if self.to_days:
            return f"{self.label} ({self.from_days}-{self.to_days} days)"
        return f"{self.label} ({self.from_days}+ days)"

    def save(self, *args, **kwargs):
        if not self.reporting_label:
            self.reporting_label = self.label
        super().save(*args, **kwargs)


class AgeingConfig(TenantModel):
    """
    Scope-level ageing configuration settings.
    Controls how ageing is calculated and displayed.

    UI: Ageing Bucket Configuration tab - Ageing Logic & Display sections
    """

    class ReferenceDateType(models.TextChoices):
        INVOICE_DATE = "INVOICE_DATE", "Invoice Date"
        DUE_DATE = "DUE_DATE", "Due Date"

    class CurrencyHandling(models.TextChoices):
        DOCUMENT_CURRENCY = "DOCUMENT_CURRENCY", "Document Currency"
        BASE_CURRENCY = "BASE_CURRENCY", "Base Currency"

    # Ageing Logic
    reference_date = models.CharField(
        max_length=20,
        choices=ReferenceDateType.choices,
        default=ReferenceDateType.INVOICE_DATE,
        help_text="Which date to use for ageing calculation"
    )
    currency_handling = models.CharField(
        max_length=20,
        choices=CurrencyHandling.choices,
        default=CurrencyHandling.DOCUMENT_CURRENCY,
        help_text="How to handle multi-currency for ageing"
    )
    include_disputed_in_standard_ageing = models.BooleanField(
        default=False,
        help_text="Include disputed invoices in standard ageing"
    )
    exclude_credit_blocked_customers = models.BooleanField(
        default=True,
        help_text="Exclude credit-blocked customers from ageing"
    )

    # Display & Reporting
    show_on_ar_dashboard = models.BooleanField(
        default=True,
        help_text="Show ageing buckets on AR dashboard"
    )
    show_in_customer_statements = models.BooleanField(
        default=True,
        help_text="Show bucket totals in customer statements"
    )
    enable_separate_disputed_ageing = models.BooleanField(
        default=False,
        help_text="Enable separate ageing for disputed amounts"
    )

    class Meta:
        verbose_name = "Ageing Configuration"
        verbose_name_plural = "Ageing Configurations"
        constraints = [
            models.UniqueConstraint(
                fields=["scope"],
                name="unique_ageing_config_per_scope"
            )
        ]

    def __str__(self):
        return f"Ageing Config - {self.scope}"


# =============================================================================
# SITE BILLING CONFIGURATION (Tab 1)
# =============================================================================

class SiteBillingConfig(TenantModel):
    """
    Site-level billing configuration.
    Controls invoice generation, payment terms, tax settings, and GL mapping.

    UI: Billing & Invoice Rules tab - Detail view
    """

    class InvoiceGenerationMode(models.TextChoices):
        AUTO = "AUTO", "Auto"
        MANUAL = "MANUAL", "Manual"

    class InvoiceGranularity(models.TextChoices):
        PER_CHARGE_TYPE = "PER_CHARGE_TYPE", "Per-charge-type Invoice"
        CONSOLIDATED = "CONSOLIDATED", "Consolidated tenant/month Invoice"

    class GSTSplitLogic(models.TextChoices):
        IGST = "IGST", "IGST"
        CGST_SGST = "CGST_SGST", "CGST+SGST"

    class DefaultPaymentTerm(models.TextChoices):
        NET_7 = "NET_7", "Net 7"
        NET_15 = "NET_15", "Net 15"
        NET_30 = "NET_30", "Net 30"
        NET_45 = "NET_45", "Net 45"
        NET_60 = "NET_60", "Net 60"
        DUE_ON_RECEIPT = "DUE_ON_RECEIPT", "Due on Receipt"

    site = models.OneToOneField(
        "properties.Site",
        on_delete=models.CASCADE,
        related_name="billing_config"
    )

    # =========================================================================
    # NUMBERING & COUNTERS
    # =========================================================================
    invoice_pattern = models.CharField(
        max_length=100,
        default="INV/{PROP}/{YEAR}/{COUNTER}",
        help_text="Invoice number pattern. Tokens: {PROP}, {YEAR}, {MONTH}, {COUNTER}"
    )
    include_property_code = models.BooleanField(
        default=True,
        help_text="Include property code in invoice number"
    )
    include_year_token = models.BooleanField(
        default=True,
        help_text="Include year in invoice number"
    )
    current_counter = models.PositiveIntegerField(
        default=1,
        help_text="Current invoice counter value"
    )
    counter_reset_frequency = models.CharField(
        max_length=20,
        choices=[
            ("NEVER", "Never"),
            ("YEARLY", "Yearly"),
            ("MONTHLY", "Monthly"),
        ],
        default="YEARLY",
        help_text="When to reset the invoice counter"
    )
    counter_last_reset = models.DateField(
        null=True,
        blank=True,
        help_text="Date the invoice counter was last reset"
    )
    counter_padding = models.PositiveIntegerField(
        default=4,
        help_text="Zero-padding for counter (4 = 0001)"
    )

    # =========================================================================
    # INVOICE GENERATION RULES
    # =========================================================================
    generation_mode = models.CharField(
        max_length=10,
        choices=InvoiceGenerationMode.choices,
        default=InvoiceGenerationMode.AUTO,
        help_text="Auto or Manual invoice generation"
    )
    generation_day_of_month = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(28)],
        help_text="Day of month to generate invoices (1-28)"
    )
    relative_generation_rule = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Relative rule e.g., 'Day after due date', '5 days before due'"
    )
    invoice_granularity = models.CharField(
        max_length=20,
        choices=InvoiceGranularity.choices,
        default=InvoiceGranularity.CONSOLIDATED,
        help_text="How to group charges on invoices"
    )
    billing_address_override = models.BooleanField(
        default=False,
        help_text="Allow billing address override on invoices"
    )
    default_gst_invoice_flag = models.BooleanField(
        default=True,
        help_text="Default GST invoice flag for new invoices"
    )

    # =========================================================================
    # REQUIRED HEADER FIELDS (stored as JSON for flexibility)
    # =========================================================================
    header_fields = models.JSONField(
        default=dict,
        blank=True,
        help_text="Required header fields configuration: {field_name: is_required}"
    )
    # Default structure:
    # {
    #     "lease_id": true,
    #     "property": true,
    #     "unit": true,
    #     "tenant": true,
    #     "billing_period": true,
    #     "billing_address": false,
    #     "gst_invoice_flag": true
    # }

    # =========================================================================
    # PAYMENT TERMS
    # =========================================================================
    default_payment_term = models.CharField(
        max_length=20,
        choices=DefaultPaymentTerm.choices,
        default=DefaultPaymentTerm.NET_30,
        help_text="Default payment terms"
    )
    grace_period_days = models.PositiveIntegerField(
        default=7,
        help_text="Grace period in days after due date"
    )

    # =========================================================================
    # TAX SETTINGS
    # =========================================================================
    default_gst_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("18.00"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        help_text="Default GST rate percentage"
    )
    gst_split_logic = models.CharField(
        max_length=10,
        choices=GSTSplitLogic.choices,
        default=GSTSplitLogic.IGST,
        help_text="GST split logic: IGST or CGST+SGST"
    )
    state_tax_rules = models.JSONField(
        default=list,
        blank=True,
        help_text="State-based tax splitting rules"
    )
    # Structure:
    # [
    #     {"state": "MH", "split": "CGST_SGST", "cgst_rate": 9, "sgst_rate": 9},
    #     {"state": "KA", "split": "CGST_SGST", "cgst_rate": 9, "sgst_rate": 9}
    # ]

    # =========================================================================
    # LEDGER MAPPING
    # =========================================================================
    revenue_gl = models.CharField(
        max_length=50,
        blank=True,
        help_text="Revenue GL code e.g., 4000-RENT-REV"
    )
    gst_output_gl = models.CharField(
        max_length=50,
        blank=True,
        help_text="GST Output GL code e.g., 2100-GST-OUT"
    )
    gst_input_gl = models.CharField(
        max_length=50,
        blank=True,
        help_text="GST Input GL code e.g., 2100-GST-IN"
    )
    receivables_gl = models.CharField(
        max_length=50,
        blank=True,
        help_text="Receivables GL code e.g., 1200-AR"
    )
    late_fee_gl = models.CharField(
        max_length=50,
        blank=True,
        help_text="Late Fee GL code"
    )
    interest_gl = models.CharField(
        max_length=50,
        blank=True,
        help_text="Interest Income GL code"
    )

    class Meta:
        verbose_name = "Site Billing Configuration"
        verbose_name_plural = "Site Billing Configurations"

    def __str__(self):
        return f"Billing Config - {self.site.name}"

    def clean(self):
        super().clean()
        if self.site_id and self.scope_id and self.site.scope_id != self.scope_id:
            raise ValidationError("SiteBillingConfig scope must match Site scope.")

    def get_next_invoice_number(self):
        """Generate next invoice number based on pattern, resetting counter per frequency."""
        from datetime import date, datetime
        now = datetime.now()
        today = date.today()

        # Reset counter if frequency demands it
        update_fields = ["current_counter"]
        if self.counter_reset_frequency == "YEARLY":
            if self.counter_last_reset is None or self.counter_last_reset.year < today.year:
                self.current_counter = 1
                self.counter_last_reset = today
                update_fields.append("counter_last_reset")
        elif self.counter_reset_frequency == "MONTHLY":
            if self.counter_last_reset is None or (
                self.counter_last_reset.year < today.year
                or self.counter_last_reset.month < today.month
            ):
                self.current_counter = 1
                self.counter_last_reset = today
                update_fields.append("counter_last_reset")

        number = self.invoice_pattern
        if self.include_property_code:
            number = number.replace("{PROP}", self.site.code)
        else:
            number = number.replace("{PROP}/", "").replace("{PROP}", "")

        if self.include_year_token:
            number = number.replace("{YEAR}", str(now.year))
        else:
            number = number.replace("{YEAR}/", "").replace("{YEAR}", "")

        number = number.replace("{MONTH}", f"{now.month:02d}")
        counter_str = str(self.current_counter).zfill(self.counter_padding)
        number = number.replace("{COUNTER}", counter_str)

        self.current_counter += 1
        self.save(update_fields=update_fields)

        return number


# =============================================================================
# BILLING RULES (Tab 1 - List view)
# =============================================================================

class BillingRule(TenantModel):
    """
    Master billing rules that can be applied at Lease or Property level.
    Defines what charge to raise, how to calculate it, and when to trigger it.

    UI: Billing & Invoice Rules tab - Rules list
    """

    class RuleCategory(models.TextChoices):
        RENTAL = "RENTAL", "Rental"
        CONTRACT = "CONTRACT", "Contract"
        SERVICE = "SERVICE", "Service"
        UTILITY = "UTILITY", "Utility"

    class AppliesTo(models.TextChoices):
        LEASE = "LEASE", "Lease"
        PROPERTY = "PROPERTY", "Property"

    class RuleStatus(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        DRAFT = "DRAFT", "Draft"
        INACTIVE = "INACTIVE", "Inactive"

    class TriggerMode(models.TextChoices):
        MANUAL = "MANUAL", "Manual (alert, I'll apply)"
        AUTO = "AUTO", "Auto (fire immediately)"

    class ChargeType(models.TextChoices):
        LATE_PAYMENT_FEE = "LATE_PAYMENT_FEE", "Late Payment Fee"
        INTEREST = "INTEREST", "Interest"
        PENALTY = "PENALTY", "Penalty"
        ADMINISTRATIVE_FEE = "ADMINISTRATIVE_FEE", "Administrative Fee"
        CAM_RECONCILIATION = "CAM_RECONCILIATION", "CAM Reconciliation"
        OTHER = "OTHER", "Other"

    class CalculationMethod(models.TextChoices):
        FLAT = "FLAT", "Flat Amount"
        PERCENTAGE_OF_OUTSTANDING = "PERCENTAGE_OF_OUTSTANDING", "% of Outstanding"
        PERCENTAGE_OF_RENT = "PERCENTAGE_OF_RENT", "% of Rent"
        PER_DAY = "PER_DAY", "Per Day (flat × overdue days)"

    class TriggerEvent(models.TextChoices):
        OVERDUE = "OVERDUE", "When Invoice is Overdue"

    rule_id = models.CharField(
        max_length=20,
        help_text="Auto-generated rule ID e.g., BR-001"
    )
    name = models.CharField(
        max_length=100,
        help_text="Rule name e.g., 'Late Payment Fee 2%'"
    )
    description = models.TextField(
        blank=True,
        help_text="Detailed description of the rule"
    )
    category = models.CharField(
        max_length=20,
        choices=RuleCategory.choices,
        default=RuleCategory.RENTAL
    )
    applies_to = models.CharField(
        max_length=20,
        choices=AppliesTo.choices,
        default=AppliesTo.LEASE,
        help_text="Whether rule applies to Lease or Property level"
    )
    status = models.CharField(
        max_length=20,
        choices=RuleStatus.choices,
        default=RuleStatus.DRAFT
    )
    trigger_mode = models.CharField(
        max_length=10,
        choices=TriggerMode.choices,
        default=TriggerMode.MANUAL,
        help_text="MANUAL = create a pending action alert; AUTO = fire immediately"
    )

    # What charge to raise
    charge_type = models.CharField(
        max_length=30,
        choices=ChargeType.choices,
        default=ChargeType.LATE_PAYMENT_FEE,
        help_text="Type of charge this rule raises"
    )

    # How to calculate the charge
    calculation_method = models.CharField(
        max_length=40,
        choices=CalculationMethod.choices,
        default=CalculationMethod.FLAT,
        help_text="How the charge amount is calculated"
    )
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Flat amount (used when method is FLAT or PER_DAY)"
    )
    rate = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Rate as a percentage e.g., 2.00 = 2% (used when method is PERCENTAGE_*)"
    )
    max_cap_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum charge amount (ceiling). Leave blank for no cap."
    )

    # When to trigger
    trigger_event = models.CharField(
        max_length=20,
        choices=TriggerEvent.choices,
        default=TriggerEvent.OVERDUE,
        help_text="Event that triggers this rule"
    )
    grace_period_days = models.PositiveIntegerField(
        default=0,
        help_text="Days after trigger event before rule fires (e.g., 7 = charge after 7 overdue days)"
    )

    # GL mapping
    gl_code = models.CharField(
        max_length=50,
        blank=True,
        help_text="GL account code for this charge e.g., 4100-LATE-FEE"
    )

    # Ownership
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_billing_rules"
    )

    # Agreement-level override (null = scope-level, applies to all agreements)
    agreement = models.ForeignKey(
        "leases.Agreement",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="billing_rules",
        help_text="If set, this rule only applies to this specific agreement"
    )

    class Meta:
        verbose_name = "Billing Rule"
        verbose_name_plural = "Billing Rules"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["scope", "rule_id"],
                name="unique_billing_rule_id_per_scope"
            )
        ]

    def __str__(self):
        return f"{self.rule_id} - {self.name}"

    def save(self, *args, **kwargs):
        if not self.rule_id:
            # Auto-generate rule_id
            last_rule = BillingRule.objects.filter(scope=self.scope).order_by("-id").first()
            if last_rule and last_rule.rule_id:
                try:
                    last_num = int(last_rule.rule_id.split("-")[1])
                    self.rule_id = f"BR-{last_num + 1:03d}"
                except (IndexError, ValueError):
                    self.rule_id = "BR-001"
            else:
                self.rule_id = "BR-001"
        super().save(*args, **kwargs)


# =============================================================================
# DISPUTE RULES (Tab 5)
# =============================================================================

class DisputeRule(TenantModel):
    """
    Rules for automatic dispute routing and handling.
    Scope-level configuration.

    UI: AR Rules (Dispute, Credit) tab - Dispute Rules section
    """

    class ConditionType(models.TextChoices):
        INVOICE_AMOUNT = "INVOICE_AMOUNT", "Invoice Amount"
        DISPUTE_COUNT = "DISPUTE_COUNT", "Dispute Count"
        INVOICE_AGE = "INVOICE_AGE", "Invoice Age (Days)"
        DISPUTE_AMOUNT = "DISPUTE_AMOUNT", "Dispute Amount"

    class Operator(models.TextChoices):
        GREATER_THAN = "GT", "> (Greater Than)"
        LESS_THAN = "LT", "< (Less Than)"
        EQUAL = "EQ", "= (Equal)"
        GREATER_EQUAL = "GTE", ">= (Greater or Equal)"
        LESS_EQUAL = "LTE", "<= (Less or Equal)"
        NOT_EQUAL = "NE", "!= (Not Equal)"

    class RuleStatus(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"

    class TriggerMode(models.TextChoices):
        MANUAL = "MANUAL", "Manual (alert, I'll apply)"
        AUTO = "AUTO", "Auto (fire immediately)"

    name = models.CharField(
        max_length=100,
        help_text="Rule name e.g., 'High Value Dispute'"
    )
    description = models.TextField(
        blank=True,
        help_text="Brief description of the rule"
    )

    # Condition
    condition_type = models.CharField(
        max_length=30,
        choices=ConditionType.choices,
        default=ConditionType.INVOICE_AMOUNT
    )
    operator = models.CharField(
        max_length=10,
        choices=Operator.choices,
        default=Operator.GREATER_THAN
    )
    threshold_value = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text="Threshold value for condition"
    )
    threshold_currency = models.CharField(
        max_length=3,
        default="INR",
        help_text="Currency for amount thresholds"
    )

    # For time-based conditions (e.g., disputes in last X days)
    time_window_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Time window in days for count-based conditions"
    )

    # Action
    action_description = models.CharField(
        max_length=255,
        help_text="Action to take e.g., 'Auto route to Finance Manager'"
    )
    route_to_role = models.CharField(
        max_length=100,
        blank=True,
        help_text="Role to route dispute to e.g., 'AR Manager', 'Finance Manager'"
    )
    route_to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dispute_route_rules",
        help_text="Specific user to route dispute to"
    )
    auto_resolve = models.BooleanField(
        default=False,
        help_text="Automatically resolve disputes matching this rule"
    )
    auto_resolve_action = models.CharField(
        max_length=100,
        blank=True,
        help_text="Action for auto-resolve e.g., 'Apply customer credit'"
    )
    require_approval = models.BooleanField(
        default=False,
        help_text="Require manager approval for disputes matching this rule"
    )
    flag_customer = models.BooleanField(
        default=False,
        help_text="Flag customer when dispute matches this rule"
    )

    # Priority & Status
    priority = models.PositiveIntegerField(
        default=1,
        help_text="Rule execution priority (lower = higher priority)"
    )
    status = models.CharField(
        max_length=20,
        choices=RuleStatus.choices,
        default=RuleStatus.ACTIVE
    )
    trigger_mode = models.CharField(
        max_length=10,
        choices=TriggerMode.choices,
        default=TriggerMode.MANUAL,
        help_text="MANUAL = create a pending action alert; AUTO = fire immediately"
    )

    # Agreement-level override (null = scope-level, applies to all agreements)
    agreement = models.ForeignKey(
        "leases.Agreement",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="dispute_rules",
        help_text="If set, this rule only applies to this specific agreement"
    )

    class Meta:
        verbose_name = "Dispute Rule"
        verbose_name_plural = "Dispute Rules"
        ordering = ["priority", "name"]

    def __str__(self):
        return f"{self.name} (Priority: {self.priority})"


# =============================================================================
# CREDIT RULES (Tab 5)
# =============================================================================

class CreditRule(TenantModel):
    """
    Rules for automatic credit note creation and approval.
    Scope-level configuration.

    UI: AR Rules (Dispute, Credit) tab - Credit Rules section
    """

    class TriggerType(models.TextChoices):
        PAYMENT_VARIANCE = "PAYMENT_VARIANCE", "Payment Variance"
        DISCOUNT_REQUEST = "DISCOUNT_REQUEST", "Approved Discount Request"
        RETURN_REQUEST = "RETURN_REQUEST", "Validated Return Request"
        BILLING_ERROR = "BILLING_ERROR", "Billing Error"
        SERVICE_CREDIT = "SERVICE_CREDIT", "Service Credit"
        GOODWILL = "GOODWILL", "Goodwill Adjustment"

    class VarianceBasis(models.TextChoices):
        PERCENTAGE = "PERCENTAGE", "Percentage"
        FIXED_AMOUNT = "FIXED_AMOUNT", "Fixed Amount"

    class RuleStatus(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"

    class TriggerMode(models.TextChoices):
        MANUAL = "MANUAL", "Manual (alert, I'll apply)"
        AUTO = "AUTO", "Auto (fire immediately)"

    name = models.CharField(
        max_length=100,
        help_text="Rule name e.g., 'Short Payment Adjustment'"
    )
    description = models.TextField(
        blank=True,
        help_text="Brief description of the rule"
    )

    # Trigger
    trigger_type = models.CharField(
        max_length=30,
        choices=TriggerType.choices,
        default=TriggerType.PAYMENT_VARIANCE
    )
    variance_threshold = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Variance threshold value"
    )
    variance_basis = models.CharField(
        max_length=20,
        choices=VarianceBasis.choices,
        default=VarianceBasis.PERCENTAGE,
        help_text="How variance is measured"
    )
    max_credit_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum credit note amount for this rule"
    )

    # Approval & Posting
    approval_role = models.ForeignKey(
        "accounts.Role",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="credit_rules_requiring_approval",
        help_text="Role that must approve credit notes triggered by this rule",
    )
    auto_approve = models.BooleanField(
        default=False,
        help_text="Auto-approve credit notes matching this rule"
    )
    auto_post_to_gl = models.BooleanField(
        default=False,
        help_text="Automatically post approved credit notes to GL"
    )
    requires_documentation = models.BooleanField(
        default=False,
        help_text="Require supporting documentation for credit note"
    )

    # Status
    status = models.CharField(
        max_length=20,
        choices=RuleStatus.choices,
        default=RuleStatus.ACTIVE
    )
    trigger_mode = models.CharField(
        max_length=10,
        choices=TriggerMode.choices,
        default=TriggerMode.MANUAL,
        help_text="MANUAL = create a pending action alert; AUTO = fire immediately"
    )

    # Agreement-level override (null = scope-level, applies to all agreements)
    agreement = models.ForeignKey(
        "leases.Agreement",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="credit_rules",
        help_text="If set, this rule only applies to this specific agreement"
    )

    class Meta:
        verbose_name = "Credit Rule"
        verbose_name_plural = "Credit Rules"
        ordering = ["name"]

    def __str__(self):
        role = self.approval_role.name if self.approval_role_id else "No role"
        return f"{self.name} - {role}"


# =============================================================================
# AR GLOBAL SETTINGS
# =============================================================================

class ARGlobalSettings(TenantModel):
    """
    Global AR settings for dispute and credit management.
    Scope-level configuration.

    UI: AR Rules (Dispute, Credit) tab - Toggle switches
    """

    enable_dispute_management = models.BooleanField(
        default=True,
        help_text="Enable dispute management workflow"
    )
    enable_credit_note_workflow = models.BooleanField(
        default=True,
        help_text="Enable credit note workflow"
    )

    # Dispute defaults
    default_dispute_hold_collection = models.BooleanField(
        default=True,
        help_text="Default: Hold collection when invoice is disputed"
    )
    default_stop_interest_on_dispute = models.BooleanField(
        default=True,
        help_text="Default: Stop interest accrual during dispute"
    )
    default_stop_reminders_on_dispute = models.BooleanField(
        default=True,
        help_text="Default: Stop payment reminders during dispute"
    )

    # Credit note defaults
    credit_note_requires_approval = models.BooleanField(
        default=True,
        help_text="Default: Require approval for credit notes"
    )
    max_auto_credit_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("2.00"),
        help_text="Maximum percentage for auto-approved credit notes"
    )

    # Accounting & AR (Invoice / Revenue Recognition)
    revenue_recognition_rule = models.CharField(
        max_length=30,
        choices=[
            ("ACCRUAL_BASIS", "Accrual Basis"),
            ("CASH_BASIS", "Cash Basis"),
            ("HYBRID", "Hybrid"),
        ],
        default="ACCRUAL_BASIS",
        blank=True,
        help_text="How revenue is recognized for accounting"
    )
    ar_ageing_bucket = models.ForeignKey(
        AgeingBucket,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ar_settings_default",
        help_text="Default AR ageing bucket mapping (e.g. Current 0-30)"
    )
    eligible_for_dunning = models.BooleanField(
        default=True,
        help_text="Include in dunning (payment reminder) workflow"
    )
    include_in_auto_email_batch = models.BooleanField(
        default=True,
        help_text="Include invoices in automated email batch"
    )

    class Meta:
        verbose_name = "AR Global Settings"
        verbose_name_plural = "AR Global Settings"
        constraints = [
            models.UniqueConstraint(
                fields=["scope"],
                name="unique_ar_global_settings_per_scope"
            )
        ]

    def __str__(self):
        return f"AR Settings - {self.scope}"


# =============================================================================
# EXISTING MODELS (Updated)
# =============================================================================

class ARRule(TenantModel):
    """
    Accounts Receivable rules for a lease agreement.
    Controls dispute handling, credit notes, and collection behavior.

    Links to scope-level DisputeRule and CreditRule for automatic processing.
    """

    agreement = models.OneToOneField(
        "leases.Agreement",
        on_delete=models.CASCADE,
        related_name="ar_rules"
    )

    # Dispute Handling
    dispute_hold = models.BooleanField(
        default=False,
        help_text="Hold collection activity when invoice is disputed"
    )
    stop_interest_on_dispute = models.BooleanField(
        default=True,
        help_text="Stop interest accrual during dispute"
    )
    stop_reminders_on_dispute = models.BooleanField(
        default=True,
        help_text="Stop payment reminders during dispute"
    )

    # Credit Notes
    credit_note_allowed = models.BooleanField(
        default=True,
        help_text="Allow credit notes for this lease"
    )
    credit_note_requires_approval = models.BooleanField(
        default=True,
        help_text="Require approval for credit notes"
    )
    max_credit_note_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum credit note as % of invoice (e.g., 100.00 for 100%)"
    )

    # Collection Settings
    auto_reminder_enabled = models.BooleanField(default=True)
    reminder_days_before_due = models.PositiveIntegerField(
        default=7,
        help_text="Days before due date to send reminder"
    )
    reminder_days_after_due = models.PositiveIntegerField(
        default=7,
        help_text="Days after due date to send overdue reminder"
    )
    escalation_days = models.PositiveIntegerField(
        default=30,
        help_text="Days overdue before escalation"
    )

    class Meta:
        verbose_name = "AR Rule"
        verbose_name_plural = "AR Rules"

    def __str__(self):
        return f"AR Rules - {self.agreement.lease_id}"


# =============================================================================
# PENDING ACTIONS (Rules Engine output)
# =============================================================================

class PendingAction(TenantModel):
    """
    Created when a rule condition is met in MANUAL trigger_mode.
    User reviews and clicks Apply or Dismiss.
    In AUTO mode rules fire immediately and a log entry is created (status=APPLIED).
    """

    class RuleType(models.TextChoices):
        BILLING = "BILLING", "Billing Rule"
        CREDIT = "CREDIT", "Credit Rule"
        DISPUTE = "DISPUTE", "Dispute Rule"

    class ObjectType(models.TextChoices):
        INVOICE = "INVOICE", "Invoice"
        CREDIT_NOTE = "CREDIT_NOTE", "Credit Note"
        DISPUTE = "DISPUTE", "Invoice Dispute"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPLIED = "APPLIED", "Applied"
        DISMISSED = "DISMISSED", "Dismissed"

    rule_type = models.CharField(max_length=10, choices=RuleType.choices)
    billing_rule = models.ForeignKey(
        BillingRule, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="pending_actions"
    )
    credit_rule = models.ForeignKey(
        CreditRule, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="pending_actions"
    )
    dispute_rule = models.ForeignKey(
        DisputeRule, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="pending_actions"
    )

    object_type = models.CharField(max_length=20, choices=ObjectType.choices)
    object_id = models.PositiveIntegerField(help_text="PK of the invoice/credit note/dispute")

    action_description = models.TextField(help_text="Human-readable description of what will happen when applied")
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDING)

    triggered_at = models.DateTimeField(auto_now_add=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    applied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="applied_pending_actions"
    )
    note = models.TextField(blank=True, help_text="Optional note when applying or dismissing")

    class Meta:
        verbose_name = "Pending Action"
        verbose_name_plural = "Pending Actions"
        ordering = ["-triggered_at"]

    def __str__(self):
        return f"[{self.rule_type}] {self.action_description[:60]} — {self.status}"


class Invoice(TenantModel):
    """
    Generated invoice for a lease agreement.
    """

    class InvoiceStatus(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PENDING = "PENDING", "Pending"
        SENT = "SENT", "Sent"
        PARTIALLY_PAID = "PARTIALLY_PAID", "Partially Paid"
        PAID = "PAID", "Paid"
        OVERDUE = "OVERDUE", "Overdue"
        DISPUTED = "DISPUTED", "Disputed"
        CANCELLED = "CANCELLED", "Cancelled"
        WRITTEN_OFF = "WRITTEN_OFF", "Written Off"

    class InvoiceType(models.TextChoices):
        RENT = "RENT", "Rent"
        CAM = "CAM", "CAM"
        DEPOSIT = "DEPOSIT", "Security Deposit"
        UTILITY = "UTILITY", "Utility"
        LATE_FEE = "LATE_FEE", "Late Fee"
        INTEREST = "INTEREST", "Interest"
        OTHER = "OTHER", "Other"

    agreement = models.ForeignKey(
        "leases.Agreement",
        on_delete=models.PROTECT,
        related_name="invoices"
    )

    # Invoice Details
    invoice_number = models.CharField(max_length=50)
    invoice_type = models.CharField(
        max_length=20,
        choices=InvoiceType.choices,
        default=InvoiceType.RENT
    )
    status = models.CharField(
        max_length=20,
        choices=InvoiceStatus.choices,
        default=InvoiceStatus.DRAFT
    )

    # Dates
    invoice_date = models.DateField()
    due_date = models.DateField()
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)

    # Amounts
    subtotal = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))]
    )
    tax_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))]
    )

    # GST split breakdown
    gst_type = models.CharField(
        max_length=10,
        choices=[("IGST", "IGST"), ("CGST_SGST", "CGST+SGST")],
        blank=True,
        default="",
    )
    cgst_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0")
    )
    sgst_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0")
    )
    igst_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0")
    )

    total_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))]
    )
    amount_paid = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))]
    )
    balance_due = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))]
    )

    # Late Fees & Interest
    late_fee_applied = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0")
    )
    interest_applied = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0")
    )

    # Currency
    currency = models.CharField(max_length=3, default="INR")

    # GST / billing flags
    is_gst_invoice = models.BooleanField(
        default=True,
        help_text="Whether this is a GST invoice (seeded from SiteBillingConfig)"
    )
    billing_address = models.TextField(
        blank=True,
        help_text="Overridden billing address for this invoice"
    )

    # Notes
    notes = models.TextField(blank=True)
    internal_notes = models.TextField(blank=True)

    # Dispute
    is_disputed = models.BooleanField(default=False)
    dispute_reason = models.TextField(blank=True)
    disputed_at = models.DateTimeField(null=True, blank=True)
    disputed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="disputed_invoices"
    )

    class Meta:
        verbose_name = "Invoice"
        verbose_name_plural = "Invoices"
        ordering = ["-invoice_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["scope", "invoice_number"],
                name="unique_invoice_number_per_scope"
            )
        ]

    def __str__(self):
        return f"{self.invoice_number} - {self.agreement.tenant.legal_name}"

    def save(self, *args, **kwargs):
        # Calculate balance_due
        self.balance_due = self.total_amount - self.amount_paid
        super().save(*args, **kwargs)


class InvoiceLineItem(TenantModel):
    """
    Line items within an invoice.
    """

    class LineItemType(models.TextChoices):
        BASE_RENT = "BASE_RENT", "Base Rent"
        CAM = "CAM", "Common Area Maintenance"
        PARKING = "PARKING", "Parking"
        UTILITY = "UTILITY", "Utility"
        INSURANCE = "INSURANCE", "Insurance"
        TAX = "TAX", "Tax"
        LATE_FEE = "LATE_FEE", "Late Fee"
        INTEREST = "INTEREST", "Interest"
        ADJUSTMENT = "ADJUSTMENT", "Adjustment"
        OTHER = "OTHER", "Other"

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="line_items"
    )

    item_type = models.CharField(
        max_length=20,
        choices=LineItemType.choices
    )
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("1")
    )
    unit_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))]
    )
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))]
    )
    tax_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0")
    )
    tax_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0")
    )
    total = models.DecimalField(
        max_digits=14,
        decimal_places=2
    )

    # Period (optional; for line-level period when different from invoice)
    period_start = models.DateField(null=True, blank=True, help_text="Start of charge period for this line")
    period_end = models.DateField(null=True, blank=True, help_text="End of charge period for this line")

    # Reference to unit if applicable
    unit = models.ForeignKey(
        "properties.Unit",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invoice_line_items"
    )

    # Reference to CAM component if applicable
    cam_component = models.ForeignKey(
        "properties.CAMComponent",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invoice_line_items"
    )

    class Meta:
        verbose_name = "Invoice Line Item"
        verbose_name_plural = "Invoice Line Items"
        ordering = ["id"]

    def __str__(self):
        return f"{self.description} - {self.total}"

    def save(self, *args, **kwargs):
        # Calculate amount and total
        self.amount = self.quantity * self.unit_price
        self.tax_amount = self.amount * (self.tax_rate / 100)
        self.total = self.amount + self.tax_amount
        super().save(*args, **kwargs)


class Payment(TenantModel):
    """
    Payment record against invoices.
    """

    class PaymentMethod(models.TextChoices):
        BANK_TRANSFER = "BANK_TRANSFER", "Bank Transfer"
        CHEQUE = "CHEQUE", "Cheque"
        CASH = "CASH", "Cash"
        UPI = "UPI", "UPI"
        CARD = "CARD", "Card"
        OTHER = "OTHER", "Other"

    class PaymentStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        CONFIRMED = "CONFIRMED", "Confirmed"
        FAILED = "FAILED", "Failed"
        REVERSED = "REVERSED", "Reversed"
        REFUNDED = "REFUNDED", "Refunded"

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.PROTECT,
        related_name="payments"
    )

    # Payment Details
    payment_number = models.CharField(max_length=50)
    payment_date = models.DateField()
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))]
    )
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices
    )
    status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.CONFIRMED
    )

    # Reference
    reference_number = models.CharField(max_length=100, blank=True)
    bank_name = models.CharField(max_length=100, blank=True)
    cheque_number = models.CharField(max_length=50, blank=True)
    transaction_id = models.CharField(max_length=100, blank=True)

    # Notes
    notes = models.TextField(blank=True)

    # Currency
    currency = models.CharField(max_length=3, default="INR")

    class Meta:
        verbose_name = "Payment"
        verbose_name_plural = "Payments"
        ordering = ["-payment_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["scope", "payment_number"],
                name="unique_payment_number_per_scope"
            )
        ]

    def __str__(self):
        return f"{self.payment_number} - {self.amount}"


class CreditNote(TenantModel):
    """
    Credit note issued against an invoice.
    """

    class CreditNoteStatus(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PENDING_APPROVAL = "PENDING_APPROVAL", "Pending Approval"
        APPROVED = "APPROVED", "Approved"
        APPLIED = "APPLIED", "Applied"
        REJECTED = "REJECTED", "Rejected"
        CANCELLED = "CANCELLED", "Cancelled"

    class CreditNoteReason(models.TextChoices):
        BILLING_ERROR = "BILLING_ERROR", "Billing Error"
        RATE_ADJUSTMENT = "RATE_ADJUSTMENT", "Rate Adjustment"
        GOODWILL = "GOODWILL", "Goodwill"
        SERVICE_ISSUE = "SERVICE_ISSUE", "Service Issue"
        EARLY_TERMINATION = "EARLY_TERMINATION", "Early Termination"
        PAYMENT_VARIANCE = "PAYMENT_VARIANCE", "Payment Variance"
        OTHER = "OTHER", "Other"

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.PROTECT,
        related_name="credit_notes"
    )

    # Credit Note Details
    credit_note_number = models.CharField(max_length=50)
    credit_note_date = models.DateField()
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))]
    )
    reason = models.CharField(
        max_length=30,
        choices=CreditNoteReason.choices
    )
    reason_details = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=CreditNoteStatus.choices,
        default=CreditNoteStatus.DRAFT
    )

    # Linked Credit Rule (if auto-created)
    credit_rule = models.ForeignKey(
        CreditRule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="credit_notes",
        help_text="Credit rule that triggered this credit note"
    )

    # Approval
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_credit_notes"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    # GL Posting
    posted_to_gl = models.BooleanField(default=False)
    posted_at = models.DateTimeField(null=True, blank=True)

    # Application
    applied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Credit Note"
        verbose_name_plural = "Credit Notes"
        ordering = ["-credit_note_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["scope", "credit_note_number"],
                name="unique_credit_note_number_per_scope"
            )
        ]

    def __str__(self):
        return f"{self.credit_note_number} - {self.amount}"


class InvoiceAttachment(TenantModel):
    """
    File attachment for an invoice (e.g. terms PDF, receipt).
    """

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="attachments"
    )

    file = models.FileField(
        upload_to="invoice_attachments/%Y/%m/",
        help_text="Uploaded file"
    )
    filename = models.CharField(
        max_length=255,
        help_text="Original filename for display"
    )
    file_size = models.PositiveIntegerField(
        default=0,
        help_text="File size in bytes"
    )

    class Meta:
        verbose_name = "Invoice Attachment"
        verbose_name_plural = "Invoice Attachments"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.filename} - {self.invoice.invoice_number}"


class InvoiceSchedule(TenantModel):
    """
    Scheduled invoice generation rules.
    """

    class ScheduleFrequency(models.TextChoices):
        MONTHLY = "MONTHLY", "Monthly"
        QUARTERLY = "QUARTERLY", "Quarterly"
        HALF_YEARLY = "HALF_YEARLY", "Half Yearly"
        ANNUALLY = "ANNUALLY", "Annually"
        ONE_TIME = "ONE_TIME", "One Time"

    agreement = models.ForeignKey(
        "leases.Agreement",
        on_delete=models.CASCADE,
        related_name="invoice_schedules"
    )

    # Schedule Details
    schedule_name = models.CharField(max_length=100)
    invoice_type = models.CharField(
        max_length=20,
        choices=Invoice.InvoiceType.choices
    )
    frequency = models.CharField(
        max_length=20,
        choices=ScheduleFrequency.choices,
        default=ScheduleFrequency.MONTHLY
    )

    # Amount
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))]
    )
    tax_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("18.00")
    )

    # Schedule
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    day_of_month = models.PositiveIntegerField(
        default=1,
        help_text="Day of month to generate invoice"
    )
    generate_days_before = models.PositiveIntegerField(
        default=0,
        help_text="Days before due date to generate invoice"
    )

    # Status
    is_active = models.BooleanField(default=True)
    last_generated_date = models.DateField(null=True, blank=True)
    next_scheduled_date = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "Invoice Schedule"
        verbose_name_plural = "Invoice Schedules"
        ordering = ["agreement", "start_date"]

    def __str__(self):
        return f"{self.schedule_name} - {self.agreement.lease_id}"


class ARSummary(TenantModel):
    """
    Cached AR summary for quick reporting.
    Updated periodically.
    """

    agreement = models.OneToOneField(
        "leases.Agreement",
        on_delete=models.CASCADE,
        related_name="ar_summary"
    )

    # Totals
    total_invoiced = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0")
    )
    total_paid = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0")
    )
    total_outstanding = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0")
    )
    total_overdue = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0")
    )

    # Ageing
    current_bucket = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
        help_text="0-30 days"
    )
    bucket_30_60 = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
        help_text="31-60 days"
    )
    bucket_60_90 = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
        help_text="61-90 days"
    )
    bucket_90_plus = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
        help_text="90+ days"
    )

    # Counts
    open_invoice_count = models.PositiveIntegerField(default=0)
    overdue_invoice_count = models.PositiveIntegerField(default=0)
    disputed_invoice_count = models.PositiveIntegerField(default=0)

    # Last Updated
    last_calculated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "AR Summary"
        verbose_name_plural = "AR Summaries"

    def __str__(self):
        return f"AR Summary - {self.agreement.lease_id}"


# =============================================================================
# RENT SCHEDULE (Tab 1 - Rent Schedule & Revenue Recognition)
# =============================================================================

class RentScheduleLine(TenantModel):
    """
    Per-period rent schedule line.
    Represents a single period charge for a lease (e.g. monthly rent for Jan 2025).

    UI: Rent Schedule List, Detail
    """

    class ChargeType(models.TextChoices):
        BASE_RENT = "BASE_RENT", "Base Rent"
        CAM = "CAM", "CAM"
        PARKING = "PARKING", "Parking"
        UTILITY = "UTILITY", "Utility"
        TAX = "TAX", "Tax"
        LATE_FEE = "LATE_FEE", "Late Fee"
        ADJUSTMENT = "ADJUSTMENT", "Adjustment"
        OTHER = "OTHER", "Other"

    class ScheduleStatus(models.TextChoices):
        SCHEDULED = "SCHEDULED", "Scheduled"
        INVOICED = "INVOICED", "Invoiced"
        PAID = "PAID", "Paid"
        CANCELLED = "CANCELLED", "Cancelled"

    agreement = models.ForeignKey(
        "leases.Agreement",
        on_delete=models.CASCADE,
        related_name="rent_schedule_lines",
    )
    unit = models.ForeignKey(
        "properties.Unit",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="rent_schedule_lines",
    )

    # Period
    period_start = models.DateField()
    period_end = models.DateField()

    # Charge
    charge_type = models.CharField(
        max_length=20,
        choices=ChargeType.choices,
        default=ChargeType.BASE_RENT,
    )
    amount_before_tax = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    gst = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text="GST/tax amount",
    )
    amount_after_tax = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text="amount_before_tax + gst",
    )

    due_date = models.DateField()
    status = models.CharField(
        max_length=20,
        choices=ScheduleStatus.choices,
        default=ScheduleStatus.SCHEDULED,
    )

    # Override / adjustment
    override_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Manual override of amount_after_tax",
    )
    adjustment_reason = models.TextField(blank=True)
    effective_date = models.DateField(null=True, blank=True)

    escalation_applied = models.BooleanField(default=False)
    escalation_notes = models.TextField(blank=True)

    notes = models.TextField(blank=True)

    # Link to invoice when invoiced
    invoice = models.ForeignKey(
        Invoice,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="rent_schedule_lines",
    )

    class Meta:
        verbose_name = "Rent Schedule Line"
        verbose_name_plural = "Rent Schedule Lines"
        ordering = ["agreement", "period_start", "period_end"]
        indexes = [
            models.Index(fields=["agreement", "period_start"]),
            models.Index(fields=["status"]),
            models.Index(fields=["due_date"]),
        ]

    def __str__(self):
        return f"{self.agreement.lease_id} - {self.period_start} to {self.period_end} ({self.charge_type})"

    def save(self, *args, **kwargs):
        if self.override_amount is not None:
            self.amount_after_tax = self.override_amount
        elif not self.amount_after_tax and self.amount_before_tax:
            self.amount_after_tax = self.amount_before_tax + (self.gst or Decimal("0"))
        super().save(*args, **kwargs)
