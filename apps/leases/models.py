from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal, ROUND_HALF_UP
from apps.core.models import TenantModel


# =============================================================================
# ESCALATION TEMPLATE (Tab 2 - Rent Escalation Templates)
# =============================================================================

class EscalationTemplate(TenantModel):
    """
    Reusable rent escalation templates that can be applied to leases.
    Scope-level configuration.

    UI: Rent Escalation Templates tab
    """

    class EscalationType(models.TextChoices):
        FIXED_PERCENT = "FIXED_PERCENT", "Fixed %"
        INDEX_LINKED = "INDEX_LINKED", "Index-linked"
        STEP_WISE = "STEP_WISE", "Step-wise"

    class Frequency(models.TextChoices):
        ANNUAL = "ANNUAL", "Annual"
        EVERY_2_YEARS = "EVERY_2_YEARS", "Every 2 Years"
        EVERY_3_YEARS = "EVERY_3_YEARS", "Every 3 Years"
        EVERY_5_YEARS = "EVERY_5_YEARS", "Every 5 Years"

    class RoundingRule(models.TextChoices):
        NEAREST_UNIT = "NEAREST_UNIT", "Nearest Unit"
        NEAREST_TEN = "NEAREST_TEN", "Nearest Ten"
        NEAREST_HUNDRED = "NEAREST_HUNDRED", "Nearest Hundred"
        NEAREST_DOLLAR = "NEAREST_DOLLAR", "Nearest Dollar"
        NO_ROUNDING = "NO_ROUNDING", "No Rounding"

    class ApplicabilityType(models.TextChoices):
        COMMERCIAL_OFFICE = "COMMERCIAL_OFFICE", "Commercial, Office"
        RESIDENTIAL_APARTMENTS = "RESIDENTIAL_APARTMENTS", "Residential, Apartments"
        RETAIL_SHOPPING_MALL = "RETAIL_SHOPPING_MALL", "Retail, Shopping Mall"
        INDUSTRIAL_WAREHOUSE = "INDUSTRIAL_WAREHOUSE", "Industrial, Warehouse"
        MIXED_USE = "MIXED_USE", "Mixed Use"
        ALL = "ALL", "All Types"

    class TemplateStatus(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        DRAFT = "DRAFT", "Draft"
        ARCHIVED = "ARCHIVED", "Archived"

    # Basic Info
    name = models.CharField(
        max_length=100,
        help_text="Template name e.g., 'Annual CPI-linked Commercial'"
    )
    description = models.TextField(
        blank=True,
        help_text="Description of the template"
    )

    # Applicability
    applicability = models.CharField(
        max_length=30,
        choices=ApplicabilityType.choices,
        default=ApplicabilityType.ALL,
        help_text="Which property/unit types this template applies to"
    )

    # Escalation Configuration
    escalation_type = models.CharField(
        max_length=20,
        choices=EscalationType.choices,
        default=EscalationType.FIXED_PERCENT
    )
    escalation_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        help_text="Escalation percentage for FIXED_PERCENT type"
    )
    index_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Index name for INDEX_LINKED type e.g., 'CPI', 'WPI'"
    )
    index_base_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Base index value for INDEX_LINKED type"
    )

    # Step-wise escalation (stored as JSON)
    step_schedule = models.JSONField(
        default=list,
        blank=True,
        help_text="Step-wise escalation schedule"
    )
    # Structure:
    # [
    #     {"year": 1, "percentage": 0},
    #     {"year": 2, "percentage": 3},
    #     {"year": 3, "percentage": 5},
    #     {"year": 4, "percentage": 7},
    #     {"year": 5, "percentage": 10}
    # ]

    # Frequency & Timing
    frequency = models.CharField(
        max_length=20,
        choices=Frequency.choices,
        default=Frequency.ANNUAL
    )
    first_escalation_logic = models.CharField(
        max_length=100,
        default="After 12 months from rent start",
        help_text="When first escalation occurs e.g., 'After 12 months from rent start'"
    )
    first_escalation_months = models.PositiveIntegerField(
        default=12,
        help_text="Months after rent start for first escalation"
    )

    # Rounding
    rounding_rule = models.CharField(
        max_length=20,
        choices=RoundingRule.choices,
        default=RoundingRule.NEAREST_DOLLAR
    )

    # Cap & Floor
    cap_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        help_text="Maximum escalation cap percentage"
    )
    floor_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        help_text="Minimum escalation floor percentage"
    )

    # Apply to Other Charges
    apply_to_cam = models.BooleanField(
        default=False,
        help_text="Apply escalation to CAM charges"
    )
    apply_to_parking = models.BooleanField(
        default=False,
        help_text="Apply escalation to Parking charges"
    )

    # Status
    status = models.CharField(
        max_length=20,
        choices=TemplateStatus.choices,
        default=TemplateStatus.DRAFT
    )

    class Meta:
        verbose_name = "Escalation Template"
        verbose_name_plural = "Escalation Templates"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["scope", "name"],
                name="unique_escalation_template_name_per_scope"
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.get_escalation_type_display()})"

    def calculate_escalated_rent(self, base_rent, years_elapsed):
        """
        Calculate escalated rent based on template configuration.

        Args:
            base_rent: Original rent amount
            years_elapsed: Number of years since rent start

        Returns:
            Escalated rent amount
        """
        if years_elapsed < (self.first_escalation_months / 12):
            return base_rent

        escalation_periods = 0
        if self.frequency == self.Frequency.ANNUAL:
            escalation_periods = int(years_elapsed - (self.first_escalation_months / 12)) + 1
        elif self.frequency == self.Frequency.EVERY_2_YEARS:
            escalation_periods = int((years_elapsed - (self.first_escalation_months / 12)) / 2) + 1
        elif self.frequency == self.Frequency.EVERY_3_YEARS:
            escalation_periods = int((years_elapsed - (self.first_escalation_months / 12)) / 3) + 1
        elif self.frequency == self.Frequency.EVERY_5_YEARS:
            escalation_periods = int((years_elapsed - (self.first_escalation_months / 12)) / 5) + 1

        if self.escalation_type == self.EscalationType.FIXED_PERCENT:
            if self.escalation_percentage:
                multiplier = (1 + self.escalation_percentage / 100) ** escalation_periods
                return base_rent * multiplier

        elif self.escalation_type == self.EscalationType.STEP_WISE:
            if self.step_schedule:
                year = int(years_elapsed) + 1
                for step in self.step_schedule:
                    if step.get("year") == year:
                        return base_rent * (1 + Decimal(str(step.get("percentage", 0))) / 100)
                # Return last step if year exceeds schedule
                if self.step_schedule:
                    last_step = self.step_schedule[-1]
                    return base_rent * (1 + Decimal(str(last_step.get("percentage", 0))) / 100)

        return base_rent


# =============================================================================
# AGREEMENT STRUCTURE (Document Sections Template)
# =============================================================================

class AgreementStructure(TenantModel):
    """
    Reusable template defining the document structure for lease agreements.
    Sections define how clauses are grouped (e.g. Part 1: Rent & Payment).

    UI: Agreement Structure / Sections configuration
    """

    name = models.CharField(
        max_length=255,
        help_text="Structure name e.g., 'Standard Commercial Lease'"
    )
    description = models.TextField(
        blank=True,
        help_text="Description of the structure"
    )
    is_default = models.BooleanField(
        default=False,
        help_text="Use as default for new agreements"
    )

    class Meta:
        verbose_name = "Agreement Structure"
        verbose_name_plural = "Agreement Structures"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["scope", "name"],
                name="unique_agreement_structure_name_per_scope",
            )
        ]

    def __str__(self):
        return self.name


class AgreementSection(TenantModel):
    """
    Section within an agreement structure (e.g. Part 1: Rent & Payment).
    Defines the order and grouping of clauses in the final document.
    """

    structure = models.ForeignKey(
        AgreementStructure,
        on_delete=models.CASCADE,
        related_name="sections",
    )
    name = models.CharField(
        max_length=255,
        help_text="Section title e.g., 'Rent & Payment'"
    )
    description = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="children",
    )

    class Meta:
        verbose_name = "Agreement Section"
        verbose_name_plural = "Agreement Sections"
        ordering = ["structure", "sort_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["structure", "name"],
                name="unique_section_name_per_structure",
            )
        ]

    def __str__(self):
        return f"{self.structure.name} / {self.name}"


class Agreement(TenantModel):
    """
    Main lease agreement model.
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PENDING = "PENDING", "Pending Approval"
        ACTIVE = "ACTIVE", "Active"
        EXPIRED = "EXPIRED", "Expired"
        TERMINATED = "TERMINATED", "Terminated"

    class AgreementType(models.TextChoices):
        COMMERCIAL_RETAIL = "COMMERCIAL_RETAIL", "Commercial Retail Lease"
        OFFICE = "OFFICE", "Office Lease"
        WAREHOUSE = "WAREHOUSE", "Warehouse Lease"
        INDUSTRIAL = "INDUSTRIAL", "Industrial Lease"
        RESIDENTIAL = "RESIDENTIAL", "Residential Lease"

    # Identification
    lease_id = models.CharField(
        max_length=50,
        help_text="Human-readable lease identifier (e.g., LSE-2024-001)"
    )
    version_number = models.PositiveIntegerField(default=1)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT
    )
    agreement_type = models.CharField(
        max_length=30,
        choices=AgreementType.choices,
        default=AgreementType.OFFICE
    )

    # Parties
    tenant = models.ForeignKey(
        "tenants.TenantCompany",
        on_delete=models.PROTECT,
        related_name="lease_agreements"
    )
    primary_contact = models.ForeignKey(
        "tenants.TenantContact",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="primary_lease_agreements"
    )
    site = models.ForeignKey(
        "properties.Site",
        on_delete=models.PROTECT,
        related_name="lease_agreements"
    )
    landlord_entity = models.CharField(max_length=255, blank=True)

    # Reference
    ref_code = models.CharField(max_length=50, blank=True)
    notes = models.TextField(blank=True)

    # Document structure (optional - defines how clauses are grouped)
    structure = models.ForeignKey(
        AgreementStructure,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agreements",
    )

    class Meta:
        verbose_name = "Lease Agreement"
        verbose_name_plural = "Lease Agreements"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["scope", "lease_id", "version_number"],
                name="unique_lease_id_version_per_scope"
            )
        ]

    def __str__(self):
        return f"{self.lease_id} v{self.version_number} - {self.tenant}"

    def clean(self):
        super().clean()
        if self.tenant_id and self.scope_id and self.tenant.scope_id != self.scope_id:
            raise ValidationError("Agreement scope must match tenant scope.")
        if self.site_id and self.scope_id and self.site.scope_id != self.scope_id:
            raise ValidationError("Agreement scope must match site scope.")


class LeaseTermDates(TenantModel):
    """
    Lease term dates and duration.
    """

    agreement = models.OneToOneField(
        Agreement,
        on_delete=models.CASCADE,
        related_name="term_dates"
    )

    # Lease Period
    commencement_date = models.DateField(null=True, blank=True)
    initial_term_months = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Lease duration in months"
    )
    expiry_date = models.DateField(null=True, blank=True)

    # Lock-in Period
    lock_in_start_date = models.DateField(null=True, blank=True)
    lock_in_end_date = models.DateField(null=True, blank=True)
    lock_in_months = models.PositiveIntegerField(null=True, blank=True)

    # Notice Periods
    notice_renewal_days = models.PositiveIntegerField(
        default=90,
        help_text="Days before expiry to notify for renewal"
    )
    notice_landlord_days = models.PositiveIntegerField(
        default=90,
        help_text="Days notice required by landlord"
    )
    notice_tenant_days = models.PositiveIntegerField(
        default=90,
        help_text="Days notice required by tenant"
    )

    class Meta:
        verbose_name = "Lease Term Dates"
        verbose_name_plural = "Lease Term Dates"

    def __str__(self):
        return f"Terms - {self.agreement.lease_id}"


class LeaseRentFree(TenantModel):
    """
    Rent-free and fit-out periods.
    """

    agreement = models.OneToOneField(
        Agreement,
        on_delete=models.CASCADE,
        related_name="rent_free"
    )

    # Rent-Free Period
    rent_free_start_date = models.DateField(null=True, blank=True)
    rent_free_days = models.PositiveIntegerField(null=True, blank=True)
    rent_free_end_date = models.DateField(null=True, blank=True)
    extended_buffer_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Additional days after rent-free period where partial rent is charged"
    )
    extended_buffer_charge_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        default=Decimal("50.00"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        help_text="Charge percentage during extended buffer days"
    )

    # Fit-out Period
    fitout_start_date = models.DateField(null=True, blank=True)
    fitout_end_date = models.DateField(null=True, blank=True)
    cam_during_fitout = models.BooleanField(
        default=False,
        help_text="Whether CAM is charged during fit-out period"
    )
    fitout_completion_cert_required = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Lease Rent Free Period"
        verbose_name_plural = "Lease Rent Free Periods"

    def __str__(self):
        return f"Rent Free - {self.agreement.lease_id}"


class LeaseFinancials(TenantModel):
    """
    Base rent and billing terms.
    """

    class BillingFrequency(models.TextChoices):
        MONTHLY = "MONTHLY", "Monthly"
        QUARTERLY = "QUARTERLY", "Quarterly"
        HALF_YEARLY = "HALF_YEARLY", "Half Yearly"
        ANNUALLY = "ANNUALLY", "Annually"

    class PaymentDueDate(models.TextChoices):
        FIRST_DAY = "1ST_DAY_OF_MONTH", "1st Day of Month"
        FIFTH_DAY = "5TH_DAY_OF_MONTH", "5th Day of Month"
        TENTH_DAY = "10TH_DAY_OF_MONTH", "10th Day of Month"
        FIFTEENTH_DAY = "15TH_DAY_OF_MONTH", "15th Day of Month"
        ON_COMMENCEMENT = "ON_COMMENCEMENT_DATE", "On Lease Start Date"

    agreement = models.OneToOneField(
        Agreement,
        on_delete=models.CASCADE,
        related_name="financials"
    )

    # Base Rent
    base_rent_monthly = models.DecimalField(
        max_digits=14, decimal_places=2,
        null=True, blank=True,
        validators=[MinValueValidator(Decimal("0"))]
    )
    rate_per_sqft_monthly = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        validators=[MinValueValidator(Decimal("0"))]
    )
    annual_rent = models.DecimalField(
        max_digits=14, decimal_places=2,
        null=True, blank=True
    )

    # Billing
    billing_frequency = models.CharField(
        max_length=20,
        choices=BillingFrequency.choices,
        default=BillingFrequency.MONTHLY
    )
    payment_due_date = models.CharField(
        max_length=30,
        choices=PaymentDueDate.choices,
        default=PaymentDueDate.FIRST_DAY
    )
    first_rent_due_date = models.DateField(null=True, blank=True)

    # Currency
    currency = models.CharField(max_length=3, default="INR")

    class Meta:
        verbose_name = "Lease Financials"
        verbose_name_plural = "Lease Financials"

    def __str__(self):
        return f"Financials - {self.agreement.lease_id}"


class LeaseEscalation(TenantModel):
    """
    Rent escalation terms for a lease agreement.
    Can use a template or custom configuration.
    """

    class EscalationType(models.TextChoices):
        FIXED_PERCENT = "FIXED_PERCENT", "Fixed Percentage"
        CPI_INDEX = "CPI_INDEX", "CPI Index"
        MARKET_RATE = "MARKET_RATE", "Market Rate"
        STEP_UP = "STEP_UP", "Step Up"
        NONE = "NONE", "No Escalation"

    agreement = models.OneToOneField(
        Agreement,
        on_delete=models.CASCADE,
        related_name="escalation"
    )

    # Template Reference (optional)
    template = models.ForeignKey(
        EscalationTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lease_escalations",
        help_text="Optional: Use an escalation template"
    )
    use_template_values = models.BooleanField(
        default=False,
        help_text="If true and template is set, inherit all values from template"
    )

    # Custom/Override Configuration
    escalation_type = models.CharField(
        max_length=20,
        choices=EscalationType.choices,
        default=EscalationType.FIXED_PERCENT
    )
    escalation_value = models.DecimalField(
        max_digits=5, decimal_places=2,
        null=True, blank=True,
        help_text="Escalation percentage (e.g., 5.00 for 5%)"
    )
    escalation_frequency_months = models.PositiveIntegerField(
        default=12,
        help_text="How often escalation is applied (in months)"
    )

    # Index-linked specific
    index_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Index name for CPI_INDEX type e.g., 'CPI', 'WPI'"
    )
    index_base_value = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        help_text="Base index value"
    )

    # Step-wise escalation
    step_schedule = models.JSONField(
        default=list,
        blank=True,
        help_text="Step-wise escalation schedule"
    )

    # Timing
    first_escalation_months = models.PositiveIntegerField(
        default=12,
        help_text="Months after rent start for first escalation"
    )
    next_review_date = models.DateField(null=True, blank=True)
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)

    # Cap & Floor
    cap_percentage = models.DecimalField(
        max_digits=5, decimal_places=2,
        null=True, blank=True,
        help_text="Maximum escalation cap"
    )
    floor_percentage = models.DecimalField(
        max_digits=5, decimal_places=2,
        null=True, blank=True,
        help_text="Minimum escalation floor"
    )

    # Apply to Other Charges
    apply_to_cam = models.BooleanField(
        default=False,
        help_text="Apply escalation to CAM charges"
    )
    apply_to_parking = models.BooleanField(
        default=False,
        help_text="Apply escalation to Parking charges"
    )

    class Meta:
        verbose_name = "Lease Escalation"
        verbose_name_plural = "Lease Escalations"

    def __str__(self):
        return f"Escalation - {self.agreement.lease_id}"

    def get_effective_escalation_type(self):
        """Get escalation type from template if use_template_values is True."""
        if self.use_template_values and self.template:
            return self.template.escalation_type
        return self.escalation_type

    def get_effective_escalation_value(self):
        """Get escalation value from template if use_template_values is True."""
        if self.use_template_values and self.template:
            return self.template.escalation_percentage
        return self.escalation_value

    def get_effective_frequency_months(self):
        """Get frequency from template if use_template_values is True."""
        if self.use_template_values and self.template:
            freq_map = {
                'ANNUAL': 12,
                'EVERY_2_YEARS': 24,
                'EVERY_3_YEARS': 36,
                'EVERY_5_YEARS': 60,
            }
            return freq_map.get(self.template.frequency, 12)
        return self.escalation_frequency_months


class LeaseCAM(TenantModel):
    """
    Common Area Maintenance charges.
    """

    class CAMBasis(models.TextChoices):
        PRO_RATA = "PRO_RATA", "Pro-rata (based on area)"
        FIXED = "FIXED", "Fixed Amount"
        PERCENTAGE = "PERCENTAGE", "Percentage of Rent"

    agreement = models.OneToOneField(
        Agreement,
        on_delete=models.CASCADE,
        related_name="cam"
    )

    allocation_basis = models.CharField(
        max_length=20,
        choices=CAMBasis.choices,
        default=CAMBasis.PRO_RATA
    )
    per_sqft_monthly = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        validators=[MinValueValidator(Decimal("0"))]
    )
    fixed_amount_monthly = models.DecimalField(
        max_digits=14, decimal_places=2,
        null=True, blank=True,
        validators=[MinValueValidator(Decimal("0"))]
    )
    percentage_value = models.DecimalField(
        max_digits=5, decimal_places=2,
        null=True, blank=True,
        help_text="Percentage of rent"
    )
    monthly_total = models.DecimalField(
        max_digits=14, decimal_places=2,
        null=True, blank=True
    )

    class Meta:
        verbose_name = "Lease CAM"
        verbose_name_plural = "Lease CAMs"

    def __str__(self):
        return f"CAM - {self.agreement.lease_id}"


class LeaseDeposit(TenantModel):
    """
    Security deposit terms.
    """

    agreement = models.OneToOneField(
        Agreement,
        on_delete=models.CASCADE,
        related_name="deposit"
    )

    amount = models.DecimalField(
        max_digits=14, decimal_places=2,
        null=True, blank=True,
        validators=[MinValueValidator(Decimal("0"))]
    )
    months_equivalent = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Number of months rent equivalent"
    )
    held_by = models.CharField(max_length=255, blank=True)
    refund_conditions = models.TextField(blank=True)
    interest_bearing = models.BooleanField(default=False)
    interest_rate = models.DecimalField(
        max_digits=5, decimal_places=2,
        null=True, blank=True
    )

    class Meta:
        verbose_name = "Lease Deposit"
        verbose_name_plural = "Lease Deposits"

    def __str__(self):
        return f"Deposit - {self.agreement.lease_id}"


class LeaseBilling(TenantModel):
    """
    Invoice and billing rules.
    """

    class InvoiceRule(models.TextChoices):
        FIRST_DAY = "1ST_DAY_OF_MONTH", "1st Day of Month"
        FIFTH_DAY = "5TH_DAY_OF_MONTH", "5th Day of Month"
        TENTH_DAY = "10TH_DAY_OF_MONTH", "10th Day of Month"
        ON_COMMENCEMENT = "ON_COMMENCEMENT_DATE", "On Commencement Date"

    agreement = models.OneToOneField(
        Agreement,
        on_delete=models.CASCADE,
        related_name="billing"
    )

    invoice_generate_rule = models.CharField(
        max_length=30,
        choices=InvoiceRule.choices,
        default=InvoiceRule.FIRST_DAY
    )
    grace_days = models.PositiveIntegerField(default=7)
    late_fee_flat = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True
    )
    late_fee_percent = models.DecimalField(
        max_digits=5, decimal_places=2,
        null=True, blank=True
    )
    interest_annual_percent = models.DecimalField(
        max_digits=5, decimal_places=2,
        null=True, blank=True
    )

    # Tax
    gst_applicable = models.BooleanField(default=True)
    gst_rate = models.DecimalField(
        max_digits=5, decimal_places=2,
        default=Decimal("18.00")
    )

    class Meta:
        verbose_name = "Lease Billing"
        verbose_name_plural = "Lease Billings"

    def __str__(self):
        return f"Billing - {self.agreement.lease_id}"


class LeaseTermination(TenantModel):
    """
    Termination, early exit, and break clause terms.

    UI: Legal & Operational Clauses tab - Termination & Early Exit section
    """

    class PenaltyType(models.TextChoices):
        MONTHS_RENT = "MONTHS_RENT", "Months Rent"
        FIXED_AMOUNT = "FIXED_AMOUNT", "Fixed Amount"
        PERCENTAGE_REMAINING = "PERCENTAGE_REMAINING", "Percentage of Remaining Rent"
        DEPOSIT_FORFEITURE = "DEPOSIT_FORFEITURE", "Security Deposit Forfeiture"

    agreement = models.OneToOneField(
        Agreement,
        on_delete=models.CASCADE,
        related_name="termination"
    )

    # =========================================================================
    # TENANT EARLY EXIT
    # =========================================================================
    tenant_early_exit_permitted = models.BooleanField(
        default=False,
        help_text="Whether tenant can exit lease early"
    )
    tenant_notice_days = models.PositiveIntegerField(
        default=90,
        help_text="Days notice required from tenant for early exit"
    )
    tenant_penalty_type = models.CharField(
        max_length=30,
        choices=PenaltyType.choices,
        default=PenaltyType.MONTHS_RENT,
        blank=True
    )
    tenant_penalty_value = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Penalty value (e.g., 3 for 3 months rent, or fixed amount)"
    )
    tenant_exit_conditions = models.TextField(
        blank=True,
        help_text="Conditions under which tenant can exit early"
    )

    # =========================================================================
    # LANDLORD EARLY TERMINATION
    # =========================================================================
    landlord_early_termination_permitted = models.BooleanField(
        default=False,
        help_text="Whether landlord can terminate lease early"
    )
    landlord_notice_days = models.PositiveIntegerField(
        default=180,
        help_text="Days notice required from landlord for early termination"
    )
    landlord_compensation_type = models.CharField(
        max_length=30,
        choices=PenaltyType.choices,
        default=PenaltyType.MONTHS_RENT,
        blank=True
    )
    landlord_compensation_value = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Compensation value landlord must pay tenant"
    )
    landlord_relocation_assistance = models.BooleanField(
        default=False,
        help_text="Whether landlord must provide relocation assistance"
    )
    landlord_termination_conditions = models.TextField(
        blank=True,
        help_text="Conditions under which landlord can terminate"
    )

    # =========================================================================
    # BREAK CLAUSE
    # =========================================================================
    break_clause_enabled = models.BooleanField(
        default=False,
        help_text="Whether a break clause exists"
    )
    break_date = models.DateField(
        null=True,
        blank=True,
        help_text="Specific date when break can be exercised"
    )
    break_window_start = models.DateField(
        null=True,
        blank=True,
        help_text="Start of window when break can be exercised"
    )
    break_window_end = models.DateField(
        null=True,
        blank=True,
        help_text="End of window when break can be exercised"
    )
    break_notice_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Days notice required to exercise break"
    )
    break_penalty = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True
    )
    break_penalty_type = models.CharField(
        max_length=30,
        choices=PenaltyType.choices,
        blank=True
    )
    break_conditions = models.TextField(
        blank=True,
        help_text="Conditions for exercising break clause"
    )

    # =========================================================================
    # TERMINATION FOR CAUSE
    # =========================================================================
    termination_for_cause_events = models.JSONField(
        default=list,
        blank=True,
        help_text="Events that allow termination for cause"
    )
    # Structure: ["Non-payment > 30 days", "Breach of use clause", "Bankruptcy"]

    cure_period_days = models.PositiveIntegerField(
        default=30,
        help_text="Days allowed to cure breach before termination"
    )

    # =========================================================================
    # GENERAL TERMINATION CLAUSE
    # =========================================================================
    termination_clause = models.TextField(
        blank=True,
        help_text="Full termination clause text"
    )

    # =========================================================================
    # LEGACY FIELDS (kept for backward compatibility)
    # =========================================================================
    governing_law = models.CharField(
        max_length=100,
        default="India",
        help_text="Deprecated: Use LeaseDisputeResolution instead"
    )
    jurisdiction = models.CharField(
        max_length=100,
        blank=True,
        help_text="Deprecated: Use LeaseDisputeResolution instead"
    )

    class Meta:
        verbose_name = "Lease Termination"
        verbose_name_plural = "Lease Terminations"

    def __str__(self):
        return f"Termination - {self.agreement.lease_id}"

    def get_tenant_penalty_display(self):
        """Get human-readable tenant penalty."""
        if self.tenant_penalty_type == self.PenaltyType.MONTHS_RENT:
            return f"{self.tenant_penalty_value} months rent"
        elif self.tenant_penalty_type == self.PenaltyType.FIXED_AMOUNT:
            return f"₹{self.tenant_penalty_value}"
        elif self.tenant_penalty_type == self.PenaltyType.PERCENTAGE_REMAINING:
            return f"{self.tenant_penalty_value}% of remaining rent"
        elif self.tenant_penalty_type == self.PenaltyType.DEPOSIT_FORFEITURE:
            return "Security deposit forfeiture"
        return ""

    def get_landlord_compensation_display(self):
        """Get human-readable landlord compensation."""
        if self.landlord_compensation_type == self.PenaltyType.MONTHS_RENT:
            return f"{self.landlord_compensation_value} months rent"
        elif self.landlord_compensation_type == self.PenaltyType.FIXED_AMOUNT:
            return f"₹{self.landlord_compensation_value}"
        return ""


class UnitAllocation(TenantModel):
    """
    Granular allocation target for a lease agreement.
    Supports allocation at site/tower/floor/unit level.
    """

    class AllocationMode(models.TextChoices):
        FULL = "FULL", "Full"
        PARTIAL = "PARTIAL", "Partial"

    class AllocationLevel(models.TextChoices):
        SITE = "SITE", "Site"
        TOWER = "TOWER", "Tower"
        FLOOR = "FLOOR", "Floor"
        UNIT = "UNIT", "Unit"

    agreement = models.ForeignKey(
        Agreement,
        on_delete=models.CASCADE,
        related_name="unit_allocations"
    )
    allocation_level = models.CharField(
        max_length=10,
        choices=AllocationLevel.choices,
        default=AllocationLevel.UNIT
    )
    site = models.ForeignKey(
        "properties.Site",
        on_delete=models.PROTECT,
        related_name="lease_allocations",
        null=True,
        blank=True
    )
    tower = models.ForeignKey(
        "properties.Tower",
        on_delete=models.PROTECT,
        related_name="lease_allocations",
        null=True,
        blank=True
    )
    floor = models.ForeignKey(
        "properties.Floor",
        on_delete=models.PROTECT,
        related_name="lease_allocations",
        null=True,
        blank=True
    )
    unit = models.ForeignKey(
        "properties.Unit",
        on_delete=models.PROTECT,
        related_name="lease_allocations",
        null=True,
        blank=True
    )

    allocation_mode = models.CharField(
        max_length=10,
        choices=AllocationMode.choices,
        default=AllocationMode.FULL
    )
    allocated_area_sqft = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))]
    )

    # Rent for this specific allocation
    monthly_rent = models.DecimalField(
        max_digits=14, decimal_places=2,
        null=True, blank=True
    )

    class Meta:
        verbose_name = "Unit Allocation"
        verbose_name_plural = "Unit Allocations"
        constraints = [
            models.CheckConstraint(
                condition=(
                    (
                        models.Q(site__isnull=False)
                        & models.Q(tower__isnull=True)
                        & models.Q(floor__isnull=True)
                        & models.Q(unit__isnull=True)
                    )
                    | (
                        models.Q(site__isnull=True)
                        & models.Q(tower__isnull=False)
                        & models.Q(floor__isnull=True)
                        & models.Q(unit__isnull=True)
                    )
                    | (
                        models.Q(site__isnull=True)
                        & models.Q(tower__isnull=True)
                        & models.Q(floor__isnull=False)
                        & models.Q(unit__isnull=True)
                    )
                    | (
                        models.Q(site__isnull=True)
                        & models.Q(tower__isnull=True)
                        & models.Q(floor__isnull=True)
                        & models.Q(unit__isnull=False)
                    )
                ),
                name="ck_alloc_single_target",
            ),
            models.CheckConstraint(
                condition=(
                    (
                        models.Q(allocation_level="SITE")
                        & models.Q(site__isnull=False)
                        & models.Q(tower__isnull=True)
                        & models.Q(floor__isnull=True)
                        & models.Q(unit__isnull=True)
                    )
                    | (
                        models.Q(allocation_level="TOWER")
                        & models.Q(site__isnull=True)
                        & models.Q(tower__isnull=False)
                        & models.Q(floor__isnull=True)
                        & models.Q(unit__isnull=True)
                    )
                    | (
                        models.Q(allocation_level="FLOOR")
                        & models.Q(site__isnull=True)
                        & models.Q(tower__isnull=True)
                        & models.Q(floor__isnull=False)
                        & models.Q(unit__isnull=True)
                    )
                    | (
                        models.Q(allocation_level="UNIT")
                        & models.Q(site__isnull=True)
                        & models.Q(tower__isnull=True)
                        & models.Q(floor__isnull=True)
                        & models.Q(unit__isnull=False)
                    )
                ),
                name="ck_alloc_level_target_match",
            ),
            models.UniqueConstraint(
                fields=["agreement", "site"],
                condition=models.Q(site__isnull=False),
                name="uq_alloc_agreement_site",
            ),
            models.UniqueConstraint(
                fields=["agreement", "tower"],
                condition=models.Q(tower__isnull=False),
                name="uq_alloc_agreement_tower",
            ),
            models.UniqueConstraint(
                fields=["agreement", "floor"],
                condition=models.Q(floor__isnull=False),
                name="uq_alloc_agreement_floor",
            ),
            models.UniqueConstraint(
                fields=["agreement", "unit"],
                condition=models.Q(unit__isnull=False),
                name="uq_alloc_agreement_unit",
            )
        ]

    def __str__(self):
        target = self.site or self.tower or self.floor or self.unit
        return f"{self.agreement.lease_id} - {self.allocation_level} - {target}"

    @classmethod
    def _blocking_statuses(cls):
        return [
            Agreement.Status.DRAFT,
            Agreement.Status.PENDING,
            Agreement.Status.ACTIVE,
        ]

    def _target_field_and_obj(self):
        target_map = {
            "site": self.site,
            "tower": self.tower,
            "floor": self.floor,
            "unit": self.unit,
        }
        targets = [(field, obj) for field, obj in target_map.items() if obj is not None]
        if len(targets) != 1:
            return None, None
        return targets[0]

    def _target_area(self):
        if self.site:
            return self.site.leasable_area_sqft
        if self.tower:
            return self.tower.leasable_area_sqft
        if self.floor:
            return self.floor.leasable_area_sqft
        if self.unit:
            return self.unit.leasable_area_sqft
        return None

    def _effective_rate_per_sqft(self):
        if not self.agreement_id:
            return None
        try:
            financials = self.agreement.financials
            if financials.rate_per_sqft_monthly is not None:
                return Decimal(financials.rate_per_sqft_monthly)
        except LeaseFinancials.DoesNotExist:
            pass
        if self.agreement.site and self.agreement.site.base_rate_sqft is not None:
            return Decimal(self.agreement.site.base_rate_sqft)
        return None

    def _calculated_monthly_rent(self):
        if self.allocated_area_sqft is None:
            return None
        rate = self._effective_rate_per_sqft()
        if rate is None:
            return None
        return (Decimal(self.allocated_area_sqft) * rate).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    def clean(self):
        super().clean()
        target_field, target_obj = self._target_field_and_obj()
        if not target_field:
            raise ValidationError("Exactly one target must be set: site, tower, floor, or unit.")

        if not self.allocation_level and target_field == "unit":
            self.allocation_level = self.AllocationLevel.UNIT

        expected_level = target_field.upper()
        if self.allocation_level != expected_level:
            raise ValidationError(
                f"allocation_level must be '{expected_level}' when '{target_field}' is provided."
            )

        if self.scope_id and self.agreement_id and self.agreement.scope_id != self.scope_id:
            raise ValidationError("Allocation scope must match agreement scope.")
        if self.scope_id and target_obj and target_obj.scope_id != self.scope_id:
            raise ValidationError("Allocation scope must match target scope.")

        target_site_id = None
        if self.site:
            target_site_id = self.site_id
        elif self.tower:
            target_site_id = self.tower.site_id
        elif self.floor:
            target_site_id = self.floor.site_id
        elif self.unit:
            target_site_id = self.unit.floor.site_id

        if self.agreement_id and target_site_id and self.agreement.site_id != target_site_id:
            raise ValidationError("Allocation target must belong to the agreement site.")

        if self.allocated_area_sqft is not None and self.allocated_area_sqft <= 0:
            raise ValidationError("allocated_area_sqft must be greater than 0.")
        if self.monthly_rent is not None and self.monthly_rent < 0:
            raise ValidationError("monthly_rent must be greater than or equal to 0.")
        if self.monthly_rent is None:
            calculated = self._calculated_monthly_rent()
            if calculated is not None:
                self.monthly_rent = calculated

        target_area = self._target_area()
        if target_area is not None and self.allocated_area_sqft and self.allocated_area_sqft > target_area:
            raise ValidationError("allocated_area_sqft cannot exceed target leasable area.")

        base_qs = UnitAllocation.objects.filter(
            is_active=True,
            agreement__status__in=self._blocking_statuses(),
        ).exclude(pk=self.pk)
        if self.scope_id:
            base_qs = base_qs.filter(scope_id=self.scope_id)

        same_target_qs = base_qs.filter(**{f"{target_field}_id": getattr(self, f"{target_field}_id")})
        existing_allocated = same_target_qs.aggregate(total=models.Sum("allocated_area_sqft"))["total"] or Decimal("0")
        requested = self.allocated_area_sqft or Decimal("0")
        if target_area is not None and (existing_allocated + requested) > target_area:
            raise ValidationError("Allocation exceeds remaining target area.")

        if self.unit and not self.unit.is_divisible:
            existing_same_unit = same_target_qs
            if existing_same_unit.exists():
                raise ValidationError("Unit is not divisible and already has an allocation.")

        # Prevent mixed parent/child allocations for the same physical branch.
        overlap_q = models.Q()
        if self.site:
            overlap_q = (
                models.Q(tower__site_id=self.site_id)
                | models.Q(floor__site_id=self.site_id)
                | models.Q(unit__floor__site_id=self.site_id)
            )
        elif self.tower:
            overlap_q = (
                models.Q(site_id=self.tower.site_id)
                | models.Q(floor__tower_id=self.tower_id)
                | models.Q(unit__floor__tower_id=self.tower_id)
            )
        elif self.floor:
            overlap_q = (
                models.Q(site_id=self.floor.site_id)
                | models.Q(tower_id=self.floor.tower_id)
                | models.Q(unit__floor_id=self.floor_id)
            )
        elif self.unit:
            overlap_q = (
                models.Q(site_id=self.unit.floor.site_id)
                | models.Q(tower_id=self.unit.floor.tower_id)
                | models.Q(floor_id=self.unit.floor_id)
            )

        if overlap_q and base_qs.filter(overlap_q).exists():
            raise ValidationError(
                "Overlapping parent/child allocation already exists for this target branch."
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class LeaseDocument(TenantModel):
    """
    Documents attached to a lease agreement.
    """

    class DocumentType(models.TextChoices):
        AGREEMENT = "AGREEMENT", "Lease Agreement"
        AMENDMENT = "AMENDMENT", "Amendment"
        ADDENDUM = "ADDENDUM", "Addendum"
        NOTICE = "NOTICE", "Notice"
        RENEWAL = "RENEWAL", "Renewal"
        OTHER = "OTHER", "Other"

    agreement = models.ForeignKey(
        Agreement,
        on_delete=models.CASCADE,
        related_name="documents"
    )

    document_type = models.CharField(
        max_length=20,
        choices=DocumentType.choices,
        default=DocumentType.AGREEMENT
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to="lease_documents/%Y/%m/")
    file_size = models.PositiveIntegerField(null=True, blank=True)
    mime_type = models.CharField(max_length=100, blank=True)

    class Meta:
        verbose_name = "Lease Document"
        verbose_name_plural = "Lease Documents"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} - {self.agreement.lease_id}"


class LeaseNote(TenantModel):
    """
    Notes and comments on a lease agreement.
    """

    agreement = models.ForeignKey(
        Agreement,
        on_delete=models.CASCADE,
        related_name="notes_list"
    )

    note_text = models.TextField()

    class Meta:
        verbose_name = "Lease Note"
        verbose_name_plural = "Lease Notes"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Note on {self.agreement.lease_id} by {self.created_by}"


# =============================================================================
# CLAUSE CONFIGURATION MODELS (Legal & Operational Clauses)
# =============================================================================

class LeaseRenewalOption(TenantModel):
    """
    Renewal options and cycles for a lease agreement.

    UI: Legal & Operational Clauses tab - Renewal Options section
    """

    class RentFormula(models.TextChoices):
        FIXED_ESCALATION = "FIXED_ESCALATION", "Base Rent + Fixed % Escalation"
        MARKET_RATE = "MARKET_RATE", "Market Rate"
        NEGOTIATED = "NEGOTIATED", "Negotiated"
        CPI_LINKED = "CPI_LINKED", "CPI-Linked"
        CAPPED_MARKET = "CAPPED_MARKET", "Market Rate with Cap"

    agreement = models.OneToOneField(
        Agreement,
        on_delete=models.CASCADE,
        related_name="renewal_option"
    )

    # Pre-Renewal Settings
    pre_renewal_notice_days = models.PositiveIntegerField(
        default=120,
        help_text="Days before expiry tenant must notify intent to renew"
    )
    auto_renewal_enabled = models.BooleanField(
        default=False,
        help_text="Whether lease auto-renews if no notice given"
    )
    auto_renewal_term_months = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Term for auto-renewal if enabled"
    )

    # Renewal Cycles (stored as JSON for flexibility)
    renewal_cycles = models.JSONField(
        default=list,
        blank=True,
        help_text="List of renewal cycles with terms"
    )
    # Structure:
    # [
    #     {"cycle": 1, "term_months": 36, "rent_formula": "FIXED_ESCALATION", "escalation_percent": 5},
    #     {"cycle": 2, "term_months": 24, "rent_formula": "MARKET_RATE", "cap_percent": 10},
    #     {"cycle": 3, "term_months": 12, "rent_formula": "NEGOTIATED"}
    # ]

    # Maximum renewals
    max_renewal_cycles = models.PositiveIntegerField(
        default=3,
        help_text="Maximum number of renewal cycles allowed"
    )

    # Current renewal status
    current_cycle = models.PositiveIntegerField(
        default=0,
        help_text="Current renewal cycle (0 = original term)"
    )
    last_renewal_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date of last renewal"
    )
    next_renewal_deadline = models.DateField(
        null=True,
        blank=True,
        help_text="Deadline to exercise next renewal option"
    )

    # Notes
    renewal_notes = models.TextField(
        blank=True,
        help_text="Additional renewal terms or conditions"
    )

    class Meta:
        verbose_name = "Lease Renewal Option"
        verbose_name_plural = "Lease Renewal Options"

    def __str__(self):
        return f"Renewal Options - {self.agreement.lease_id}"

    def get_current_cycle_config(self):
        """Get configuration for current renewal cycle."""
        if self.renewal_cycles and self.current_cycle > 0:
            for cycle in self.renewal_cycles:
                if cycle.get("cycle") == self.current_cycle:
                    return cycle
        return None

    def get_next_cycle_config(self):
        """Get configuration for next renewal cycle."""
        next_cycle = self.current_cycle + 1
        if self.renewal_cycles and next_cycle <= self.max_renewal_cycles:
            for cycle in self.renewal_cycles:
                if cycle.get("cycle") == next_cycle:
                    return cycle
        return None


class LeaseSubletSignage(TenantModel):
    """
    Sub-letting and signage rights for a lease agreement.

    UI: Legal & Operational Clauses tab - Sub-letting & Signage Rights section
    """

    class SubletPermission(models.TextChoices):
        PERMITTED = "PERMITTED", "Permitted"
        PROHIBITED = "PROHIBITED", "Prohibited"
        WITH_APPROVAL = "WITH_APPROVAL", "With Landlord Approval"

    agreement = models.OneToOneField(
        Agreement,
        on_delete=models.CASCADE,
        related_name="sublet_signage"
    )

    # =========================================================================
    # SUB-LETTING
    # =========================================================================
    sublet_permission = models.CharField(
        max_length=20,
        choices=SubletPermission.choices,
        default=SubletPermission.WITH_APPROVAL
    )
    sublet_approval_required = models.BooleanField(
        default=True,
        help_text="Whether landlord approval is required for sub-letting"
    )
    max_sublet_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        help_text="Maximum percentage of area that can be sub-let"
    )
    sublet_restrictions = models.TextField(
        blank=True,
        help_text="Restrictions on who can be a sub-tenant (e.g., no competitors)"
    )
    sublet_rent_share_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Percentage of sub-let rent to be shared with landlord"
    )

    # =========================================================================
    # SIGNAGE RIGHTS
    # =========================================================================
    signage_permitted = models.BooleanField(
        default=True,
        help_text="Whether tenant is allowed to display signage"
    )
    signage_approval_required = models.BooleanField(
        default=True,
        help_text="Whether landlord approval is required for signage"
    )
    signage_area_sqft = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Allowed signage area (unit in signage_area_unit)"
    )
    signage_area_unit = models.CharField(
        max_length=10,
        choices=[("SQFT", "Square Feet"), ("SQM", "Square Meters")],
        default="SQFT",
        help_text="Unit for signage area (SQFT or SQM)"
    )
    signage_locations = models.TextField(
        blank=True,
        help_text="Permitted signage locations (e.g., Main entrance, Building facade)"
    )
    signage_specifications = models.TextField(
        blank=True,
        help_text="Signage specifications (e.g., Backlit, max height, materials)"
    )
    signage_cost_responsibility = models.CharField(
        max_length=50,
        blank=True,
        default="Tenant",
        help_text="Who bears signage installation/maintenance costs"
    )

    class Meta:
        verbose_name = "Lease Sublet & Signage"
        verbose_name_plural = "Lease Sublet & Signage"

    def __str__(self):
        return f"Sublet & Signage - {self.agreement.lease_id}"


class LeaseExclusivity(TenantModel):
    """
    Exclusivity and non-compete terms for a lease agreement.

    UI: Legal & Operational Clauses tab - Exclusivity & Non-Compete section
    """

    agreement = models.OneToOneField(
        Agreement,
        on_delete=models.CASCADE,
        related_name="exclusivity"
    )

    # =========================================================================
    # EXCLUSIVE USE
    # =========================================================================
    exclusive_use_granted = models.BooleanField(
        default=False,
        help_text="Whether tenant has exclusive use rights for their business category"
    )
    exclusive_category = models.CharField(
        max_length=255,
        blank=True,
        help_text="Business category for exclusivity (e.g., Coffee Shop & Cafe)"
    )
    exclusive_radius = models.CharField(
        max_length=100,
        blank=True,
        default="Within Property",
        help_text="Radius of exclusivity (Within Property, Floor, Building, Campus)"
    )
    exclusive_exceptions = models.TextField(
        blank=True,
        help_text="Exceptions to exclusivity (e.g., existing tenants, food courts)"
    )

    # Excluded Categories (what landlord cannot lease to)
    excluded_categories = models.JSONField(
        default=list,
        blank=True,
        help_text="Categories landlord cannot lease to"
    )
    # Structure: ["Fast Food", "Convenience Store", "Food Court"]

    # =========================================================================
    # NON-COMPETE
    # =========================================================================
    non_compete_enabled = models.BooleanField(
        default=False,
        help_text="Whether non-compete clause is active"
    )
    non_compete_duration_months = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Duration of non-compete after lease termination (months)"
    )
    non_compete_radius_km = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Geographic radius for non-compete (in km)"
    )
    non_compete_scope = models.TextField(
        blank=True,
        help_text="Scope of non-compete (e.g., Same business line, Similar products)"
    )

    # Breach Penalties
    exclusivity_breach_penalty = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Penalty amount if landlord breaches exclusivity"
    )
    non_compete_breach_penalty = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Penalty amount if tenant breaches non-compete"
    )

    class Meta:
        verbose_name = "Lease Exclusivity"
        verbose_name_plural = "Lease Exclusivities"

    def __str__(self):
        return f"Exclusivity - {self.agreement.lease_id}"


class LeaseInsuranceRequirement(TenantModel):
    """
    Insurance requirements and reinstatement terms for a lease agreement.

    UI: Legal & Operational Clauses tab - Reinstatement & Insurance section
    """

    class RestoreCondition(models.TextChoices):
        ORIGINAL = "ORIGINAL", "Original Condition"
        BROOM_CLEAN = "BROOM_CLEAN", "Broom Clean"
        AS_IS = "AS_IS", "As-Is"
        IMPROVED = "IMPROVED", "Improved Condition"

    agreement = models.OneToOneField(
        Agreement,
        on_delete=models.CASCADE,
        related_name="insurance_requirement"
    )

    # =========================================================================
    # REINSTATEMENT
    # =========================================================================
    restore_condition = models.CharField(
        max_length=20,
        choices=RestoreCondition.choices,
        default=RestoreCondition.ORIGINAL,
        help_text="Condition premises must be returned in"
    )
    restore_exceptions = models.TextField(
        blank=True,
        help_text="Alterations exempt from restoration (e.g., approved modifications)"
    )
    restore_details = models.TextField(
        blank=True,
        help_text="Free-text reinstatement details (e.g., Return to original white box condition)"
    )
    reinstatement_deposit = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Deposit held for reinstatement"
    )
    reinstatement_timeline_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Days allowed for reinstatement after lease end"
    )

    # =========================================================================
    # PUBLIC LIABILITY INSURANCE
    # =========================================================================
    public_liability_required = models.BooleanField(
        default=True,
        help_text="Whether public liability insurance is required"
    )
    public_liability_coverage = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Required coverage amount"
    )
    public_liability_currency = models.CharField(
        max_length=3,
        default="INR"
    )

    # =========================================================================
    # PROPERTY INSURANCE
    # =========================================================================
    property_insurance_required = models.BooleanField(
        default=True,
        help_text="Whether property/contents insurance is required"
    )
    property_insurance_coverage = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Required coverage amount"
    )

    # =========================================================================
    # BUSINESS INTERRUPTION INSURANCE
    # =========================================================================
    business_interruption_required = models.BooleanField(
        default=False,
        help_text="Whether business interruption insurance is required"
    )
    business_interruption_coverage_months = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Months of revenue coverage required"
    )

    # =========================================================================
    # OTHER INSURANCE REQUIREMENTS
    # =========================================================================
    other_insurance_requirements = models.JSONField(
        default=list,
        blank=True,
        help_text="Other insurance requirements"
    )
    # Structure: [{"type": "Workers Comp", "required": true, "coverage": 500000}]

    # =========================================================================
    # LANDLORD AS ADDITIONAL INSURED
    # =========================================================================
    landlord_additional_insured = models.BooleanField(
        default=True,
        help_text="Whether landlord should be named as additional insured"
    )

    # =========================================================================
    # PROOF REQUIREMENTS
    # =========================================================================
    proof_required = models.BooleanField(
        default=True,
        help_text="Whether tenant must provide proof of insurance"
    )
    proof_frequency = models.CharField(
        max_length=50,
        default="Annual",
        help_text="How often proof must be submitted (Annual, Semi-Annual, etc.)"
    )
    proof_due_days_before_expiry = models.PositiveIntegerField(
        default=30,
        help_text="Days before policy expiry to submit renewal proof"
    )

    # =========================================================================
    # INDEMNITY
    # =========================================================================
    indemnity_notes = models.TextField(
        blank=True,
        help_text="Indemnity clause text / notes"
    )

    class Meta:
        verbose_name = "Lease Insurance Requirement"
        verbose_name_plural = "Lease Insurance Requirements"

    def __str__(self):
        return f"Insurance Requirements - {self.agreement.lease_id}"


class LeaseDisputeResolution(TenantModel):
    """
    Dispute resolution and governing law terms for a lease agreement.

    UI: Legal & Operational Clauses tab - Dispute Resolution & Governing Law section
    """

    class DisputeMechanism(models.TextChoices):
        MEDIATION = "MEDIATION", "Mediation"
        ARBITRATION = "ARBITRATION", "Arbitration"
        LITIGATION = "LITIGATION", "Litigation"
        MED_ARB = "MED_ARB", "Mediation then Arbitration"
        NEGOTIATION = "NEGOTIATION", "Negotiation"

    agreement = models.OneToOneField(
        Agreement,
        on_delete=models.CASCADE,
        related_name="dispute_resolution"
    )

    # =========================================================================
    # DISPUTE MECHANISM
    # =========================================================================
    dispute_mechanism = models.CharField(
        max_length=20,
        choices=DisputeMechanism.choices,
        default=DisputeMechanism.ARBITRATION
    )

    # =========================================================================
    # ARBITRATION DETAILS
    # =========================================================================
    arbitration_seat = models.CharField(
        max_length=100,
        blank=True,
        help_text="Seat/place of arbitration (e.g., Mumbai)"
    )
    arbitration_rules = models.CharField(
        max_length=255,
        blank=True,
        help_text="Applicable arbitration rules (e.g., Indian Arbitration Act)"
    )
    arbitration_language = models.CharField(
        max_length=50,
        default="English",
        help_text="Language of arbitration proceedings"
    )
    number_of_arbitrators = models.PositiveIntegerField(
        default=1,
        help_text="Number of arbitrators (1 or 3 typically)"
    )
    arbitration_institution = models.CharField(
        max_length=255,
        blank=True,
        help_text="Arbitration institution (e.g., ICC, LCIA, Ad-hoc)"
    )

    # =========================================================================
    # MEDIATION DETAILS
    # =========================================================================
    mediation_required_first = models.BooleanField(
        default=False,
        help_text="Whether mediation is required before arbitration/litigation"
    )
    mediation_period_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Days allowed for mediation before escalation"
    )
    mediation_venue = models.CharField(
        max_length=100,
        blank=True,
        help_text="Venue for mediation"
    )

    # =========================================================================
    # GOVERNING LAW
    # =========================================================================
    governing_law_country = models.CharField(
        max_length=100,
        default="India",
        help_text="Country whose laws govern the agreement"
    )
    governing_law_state = models.CharField(
        max_length=100,
        blank=True,
        help_text="State/Province whose laws govern (if applicable)"
    )
    jurisdiction_court = models.CharField(
        max_length=255,
        blank=True,
        help_text="Courts having jurisdiction (e.g., Mumbai High Court)"
    )
    exclusive_jurisdiction = models.BooleanField(
        default=True,
        help_text="Whether jurisdiction is exclusive"
    )

    # =========================================================================
    # SUMMARY
    # =========================================================================
    dispute_summary = models.TextField(
        blank=True,
        help_text="Human-readable summary of dispute resolution terms"
    )

    class Meta:
        verbose_name = "Lease Dispute Resolution"
        verbose_name_plural = "Lease Dispute Resolutions"

    def __str__(self):
        return f"Dispute Resolution - {self.agreement.lease_id}"


# =============================================================================
# AMENDMENT & VERSIONING MODELS
# =============================================================================

class LeaseAmendment(TenantModel):
    """
    Tracks amendments/changes to lease agreements over time.
    Each amendment creates a new version of the lease.

    UI: Amendment & Versioning tab
    """

    class AmendmentType(models.TextChoices):
        ORIGINAL = "ORIGINAL", "Original Agreement"
        RENT_REVISION = "RENT_REVISION", "Rent Revision"
        AREA_CHANGE = "AREA_CHANGE", "Area Change"
        TERM_EXTENSION = "TERM_EXTENSION", "Term Extension"
        RENEWAL = "RENEWAL", "Renewal"
        EARLY_TERMINATION = "EARLY_TERMINATION", "Early Termination"
        PARTY_CHANGE = "PARTY_CHANGE", "Party Change (Assignment)"
        CLAUSE_MODIFICATION = "CLAUSE_MODIFICATION", "Clause Modification"
        ADDENDUM = "ADDENDUM", "Addendum"
        OTHER = "OTHER", "Other"

    class ApprovalStatus(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PENDING_REVIEW = "PENDING_REVIEW", "Pending Review"
        UNDER_NEGOTIATION = "UNDER_NEGOTIATION", "Under Negotiation"
        PENDING_APPROVAL = "PENDING_APPROVAL", "Pending Approval"
        APPROVED = "APPROVED", "Approved"
        EXECUTED = "EXECUTED", "Executed"
        REJECTED = "REJECTED", "Rejected"
        SUPERSEDED = "SUPERSEDED", "Superseded"

    agreement = models.ForeignKey(
        Agreement,
        on_delete=models.CASCADE,
        related_name="amendments"
    )

    # Amendment Identification
    amendment_id = models.CharField(
        max_length=50,
        help_text="Auto-generated amendment ID (e.g., AMD-2023-042)"
    )
    amendment_type = models.CharField(
        max_length=30,
        choices=AmendmentType.choices,
        default=AmendmentType.OTHER
    )
    title = models.CharField(
        max_length=255,
        blank=True,
        help_text="Brief title describing the amendment"
    )

    # Version Tracking
    previous_version = models.CharField(
        max_length=20,
        blank=True,
        help_text="Previous agreement version (e.g., v1.0)"
    )
    new_version = models.CharField(
        max_length=20,
        blank=True,
        help_text="New agreement version after this amendment (e.g., v1.1)"
    )
    is_major_version = models.BooleanField(
        default=False,
        help_text="Whether this is a major version change (v1.x → v2.0)"
    )

    # Dates
    amendment_date = models.DateField(
        help_text="Date amendment was created/signed"
    )
    effective_from = models.DateField(
        help_text="Date amendment takes effect"
    )
    effective_to = models.DateField(
        null=True,
        blank=True,
        help_text="Date amendment expires (if temporary)"
    )

    # Status
    approval_status = models.CharField(
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.DRAFT
    )

    # Changes Summary (stored as JSON for flexibility)
    changes_summary = models.JSONField(
        default=list,
        blank=True,
        help_text="Summary of changes made"
    )
    # Structure:
    # [
    #     {"field": "Base Rent", "previous": "₹1,00,000", "new": "₹1,05,000"},
    #     {"field": "CAM Rate", "previous": "₹25/sqft", "new": "₹27/sqft"}
    # ]

    # Full Description
    description = models.TextField(
        blank=True,
        help_text="Detailed description of the amendment"
    )

    # Reason
    reason = models.TextField(
        blank=True,
        help_text="Reason for the amendment"
    )

    # Parties
    initiated_by = models.CharField(
        max_length=50,
        blank=True,
        help_text="Who initiated the amendment (Tenant/Landlord)"
    )

    # Metadata
    executed_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date amendment was formally executed"
    )

    class Meta:
        verbose_name = "Lease Amendment"
        verbose_name_plural = "Lease Amendments"
        ordering = ["-amendment_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["scope", "amendment_id"],
                name="unique_amendment_id_per_scope"
            )
        ]

    def __str__(self):
        return f"{self.amendment_id} - {self.agreement.lease_id}"

    def save(self, *args, **kwargs):
        # Auto-generate amendment_id if not provided
        if not self.amendment_id:
            from datetime import datetime
            year = datetime.now().year
            count = LeaseAmendment.objects.filter(
                scope=self.scope,
                created_at__year=year
            ).count() + 1
            self.amendment_id = f"AMD-{year}-{count:03d}"
        super().save(*args, **kwargs)


class AmendmentApproval(TenantModel):
    """
    Approval workflow steps for lease amendments.

    UI: Amendment & Versioning tab - Approval Workflow section
    """

    class ApprovalStepStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        SKIPPED = "SKIPPED", "Skipped"

    amendment = models.ForeignKey(
        LeaseAmendment,
        on_delete=models.CASCADE,
        related_name="approvals"
    )

    # Step Details
    step_order = models.PositiveIntegerField(
        default=1,
        help_text="Order of this approval step"
    )
    step_name = models.CharField(
        max_length=100,
        help_text="Name of approval step (e.g., Legal Review, Finance Review)"
    )
    step_description = models.TextField(
        blank=True,
        help_text="Description of what this step entails"
    )

    # Approver
    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="amendment_approvals"
    )
    approver_role = models.CharField(
        max_length=100,
        blank=True,
        help_text="Role required for approval (e.g., Legal Manager)"
    )

    # Status
    status = models.CharField(
        max_length=20,
        choices=ApprovalStepStatus.choices,
        default=ApprovalStepStatus.PENDING
    )

    # Action Details
    actioned_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When action was taken"
    )
    comments = models.TextField(
        blank=True,
        help_text="Approver's comments"
    )

    # Deadline
    due_date = models.DateField(
        null=True,
        blank=True,
        help_text="Deadline for this approval step"
    )

    class Meta:
        verbose_name = "Amendment Approval"
        verbose_name_plural = "Amendment Approvals"
        ordering = ["amendment", "step_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["amendment", "step_order"],
                name="unique_amendment_approval_step"
            )
        ]

    def __str__(self):
        return f"{self.step_name} - {self.amendment.amendment_id}"


class AmendmentAttachment(TenantModel):
    """
    Documents attached to a lease amendment.

    UI: Amendment & Versioning tab - Attachments section
    """

    class AttachmentType(models.TextChoices):
        AMENDMENT_AGREEMENT = "AMENDMENT_AGREEMENT", "Amendment Agreement"
        SIGNED_ADDENDUM = "SIGNED_ADDENDUM", "Signed Addendum"
        SUPPORTING_DOC = "SUPPORTING_DOC", "Supporting Document"
        APPROVAL_DOC = "APPROVAL_DOC", "Approval Document"
        CORRESPONDENCE = "CORRESPONDENCE", "Correspondence"
        OTHER = "OTHER", "Other"

    amendment = models.ForeignKey(
        LeaseAmendment,
        on_delete=models.CASCADE,
        related_name="attachments"
    )

    # File Details
    title = models.CharField(max_length=255)
    attachment_type = models.CharField(
        max_length=30,
        choices=AttachmentType.choices,
        default=AttachmentType.OTHER
    )
    file = models.FileField(upload_to="amendment_attachments/%Y/%m/")
    file_size = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="File size in bytes"
    )
    mime_type = models.CharField(max_length=100, blank=True)

    # Description
    description = models.TextField(blank=True)

    # Uploader
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_amendment_attachments"
    )

    class Meta:
        verbose_name = "Amendment Attachment"
        verbose_name_plural = "Amendment Attachments"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} - {self.amendment.amendment_id}"


# =============================================================================
# DOCUMENT LINKS (Enhanced Document Management)
# =============================================================================

class LeaseLinkedDocument(TenantModel):
    """
    Enhanced document management for lease agreements.
    Links documents with categories, expiry tracking, and approval workflow.

    UI: Document Links tab
    """

    class DocumentCategory(models.TextChoices):
        LEGAL = "LEGAL", "Legal Documents"
        COMPLIANCE = "COMPLIANCE", "Compliance Documents"
        FINANCIAL = "FINANCIAL", "Financial Documents"
        CORRESPONDENCE = "CORRESPONDENCE", "Correspondence"
        INSURANCE = "INSURANCE", "Insurance Documents"
        PERMITS = "PERMITS", "Permits & Licenses"
        OTHER = "OTHER", "Other"

    class DocumentStatus(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PENDING_REVIEW = "PENDING_REVIEW", "Pending Review"
        PENDING_SIGNATURE = "PENDING_SIGNATURE", "Pending Signature"
        EXECUTED = "EXECUTED", "Executed"
        VALID = "VALID", "Valid"
        EXPIRING = "EXPIRING", "Expiring Soon"
        EXPIRED = "EXPIRED", "Expired"
        SUPERSEDED = "SUPERSEDED", "Superseded"
        CANCELLED = "CANCELLED", "Cancelled"

    agreement = models.ForeignKey(
        Agreement,
        on_delete=models.CASCADE,
        related_name="linked_documents"
    )

    # Document Details
    title = models.CharField(max_length=255)
    category = models.CharField(
        max_length=20,
        choices=DocumentCategory.choices,
        default=DocumentCategory.OTHER
    )
    status = models.CharField(
        max_length=20,
        choices=DocumentStatus.choices,
        default=DocumentStatus.DRAFT
    )

    # File
    file = models.FileField(
        upload_to="lease_linked_documents/%Y/%m/",
        null=True,
        blank=True
    )
    file_size = models.PositiveIntegerField(null=True, blank=True)
    mime_type = models.CharField(max_length=100, blank=True)
    external_url = models.URLField(
        blank=True,
        help_text="External link if document is stored elsewhere"
    )

    # Version
    version = models.CharField(
        max_length=20,
        blank=True,
        help_text="Document version (e.g., v1.0, v2.0)"
    )

    # Dates
    document_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date on the document"
    )
    effective_date = models.DateField(
        null=True,
        blank=True,
        help_text="When document becomes effective"
    )
    expiry_date = models.DateField(
        null=True,
        blank=True,
        help_text="When document expires"
    )

    # Renewal Tracking
    requires_renewal = models.BooleanField(
        default=False,
        help_text="Whether this document needs periodic renewal"
    )
    renewal_reminder_days = models.PositiveIntegerField(
        default=30,
        help_text="Days before expiry to send renewal reminder"
    )

    # Description
    description = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    # Uploader
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_lease_documents"
    )

    class Meta:
        verbose_name = "Lease Linked Document"
        verbose_name_plural = "Lease Linked Documents"
        ordering = ["category", "-created_at"]

    def __str__(self):
        return f"{self.title} - {self.agreement.lease_id}"

    @property
    def is_expiring_soon(self):
        """Check if document is expiring within reminder period."""
        if not self.expiry_date:
            return False
        from datetime import date, timedelta
        warning_date = self.expiry_date - timedelta(days=self.renewal_reminder_days)
        return date.today() >= warning_date and date.today() < self.expiry_date

    @property
    def is_expired(self):
        """Check if document has expired."""
        if not self.expiry_date:
            return False
        from datetime import date
        return date.today() > self.expiry_date

    def save(self, *args, **kwargs):
        # Auto-update status based on expiry
        if self.expiry_date:
            from datetime import date, timedelta
            today = date.today()
            if today > self.expiry_date:
                self.status = self.DocumentStatus.EXPIRED
            elif today >= self.expiry_date - timedelta(days=self.renewal_reminder_days):
                if self.status not in [self.DocumentStatus.EXPIRED, self.DocumentStatus.SUPERSEDED]:
                    self.status = self.DocumentStatus.EXPIRING
        super().save(*args, **kwargs)


class DocumentApproval(TenantModel):
    """
    Approval workflow for lease linked documents.

    UI: Document Links tab - Approval Workflow
    """

    class ApprovalStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        SKIPPED = "SKIPPED", "Skipped"

    document = models.ForeignKey(
        LeaseLinkedDocument,
        on_delete=models.CASCADE,
        related_name="approvals"
    )

    # Step Details
    step_order = models.PositiveIntegerField(default=1)
    step_name = models.CharField(max_length=100)

    # Approver
    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="document_approvals"
    )
    approver_role = models.CharField(max_length=100, blank=True)

    # Status
    status = models.CharField(
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING
    )

    # Action
    actioned_at = models.DateTimeField(null=True, blank=True)
    comments = models.TextField(blank=True)

    class Meta:
        verbose_name = "Document Approval"
        verbose_name_plural = "Document Approvals"
        ordering = ["document", "step_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "step_order"],
                name="unique_document_approval_step"
            )
        ]

    def __str__(self):
        return f"{self.step_name} - {self.document.title}"
