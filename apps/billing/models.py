from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from decimal import Decimal
from apps.core.models import TenantModel


class AgeingBucket(TenantModel):
    """
    Defines ageing buckets for AR aging reports.
    These are scope-level configurations.
    """

    label = models.CharField(
        max_length=50,
        help_text="Display label e.g., '0-30 Days', '31-60 Days'"
    )
    from_days = models.PositiveIntegerField(
        help_text="Start of bucket range (inclusive)"
    )
    to_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="End of bucket range (inclusive). Null means open-ended (e.g., 90+ days)"
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Display order of buckets"
    )
    color_code = models.CharField(
        max_length=7,
        default="#6B7280",
        help_text="Hex color for UI display"
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


class ARRule(TenantModel):
    """
    Accounts Receivable rules for a lease agreement.
    Controls dispute handling, credit notes, and collection behavior.
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

    # Reference to unit if applicable
    unit = models.ForeignKey(
        "properties.Unit",
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
