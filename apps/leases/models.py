from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from decimal import Decimal
from apps.core.models import TenantModel


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
    Rent escalation terms.
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
    next_review_date = models.DateField(null=True, blank=True)
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "Lease Escalation"
        verbose_name_plural = "Lease Escalations"

    def __str__(self):
        return f"Escalation - {self.agreement.lease_id}"


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
    Termination and break clause terms.
    """

    agreement = models.OneToOneField(
        Agreement,
        on_delete=models.CASCADE,
        related_name="termination"
    )

    termination_clause = models.TextField(blank=True)
    governing_law = models.CharField(max_length=100, default="India")
    jurisdiction = models.CharField(max_length=100, blank=True)

    # Break Clause
    break_date = models.DateField(null=True, blank=True)
    break_penalty = models.DecimalField(
        max_digits=14, decimal_places=2,
        null=True, blank=True
    )
    break_penalty_type = models.CharField(
        max_length=50,
        blank=True,
        help_text="e.g., 'Months Rent', 'Fixed Amount'"
    )
    break_notice_days = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Days notice required for break"
    )

    class Meta:
        verbose_name = "Lease Termination"
        verbose_name_plural = "Lease Terminations"

    def __str__(self):
        return f"Termination - {self.agreement.lease_id}"


class UnitAllocation(TenantModel):
    """
    Unit allocation for a lease agreement.
    """

    class AllocationMode(models.TextChoices):
        FULL = "FULL", "Full Unit"
        PARTIAL = "PARTIAL", "Partial Unit"

    agreement = models.ForeignKey(
        Agreement,
        on_delete=models.CASCADE,
        related_name="unit_allocations"
    )
    unit = models.ForeignKey(
        "properties.Unit",
        on_delete=models.PROTECT,
        related_name="lease_allocations"
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
            models.UniqueConstraint(
                fields=["agreement", "unit"],
                name="unique_unit_per_agreement"
            )
        ]

    def __str__(self):
        return f"{self.agreement.lease_id} - {self.unit}"

    def clean(self):
        super().clean()
        if self.unit_id and self.scope_id and self.unit.scope_id != self.scope_id:
            raise ValidationError("Unit allocation scope must match unit scope.")


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
