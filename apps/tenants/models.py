from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from apps.core.models import TenantModel


class TenantCompany(TenantModel):
    """
    Tenant company entity - represents a business that leases property.
    """

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"
        SUSPENDED = "SUSPENDED", "Suspended"

    # Basic Info
    legal_name = models.CharField(max_length=255, help_text="Official registered company name")
    trade_name = models.CharField(max_length=255, blank=True, help_text="Business trading name")

    # Contact
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    website = models.URLField(blank=True)

    # Address
    address_line1 = models.CharField(max_length=255, blank=True)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    pincode = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=100, default="India")

    # Status
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

    # Business Details
    industry = models.CharField(max_length=100, blank=True)
    company_size = models.CharField(max_length=50, blank=True, help_text="e.g., 1-10, 11-50, 51-200")

    class Meta:
        verbose_name = "Tenant Company"
        verbose_name_plural = "Tenant Companies"
        ordering = ["legal_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["scope", "legal_name"],
                name="unique_tenantcompany_legal_name_per_scope"
            )
        ]

    def __str__(self):
        return self.trade_name or self.legal_name


class TenantContact(TenantModel):
    """
    Contact person for a tenant company.
    """

    company = models.ForeignKey(
        TenantCompany,
        on_delete=models.CASCADE,
        related_name="contacts"
    )

    # Basic Info
    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    mobile = models.CharField(max_length=20, blank=True)

    # Role
    designation = models.CharField(max_length=100, blank=True, help_text="Job title")
    department = models.CharField(max_length=100, blank=True)
    is_primary = models.BooleanField(default=False, help_text="Primary contact for this company")

    class Meta:
        verbose_name = "Tenant Contact"
        verbose_name_plural = "Tenant Contacts"
        ordering = ["-is_primary", "name"]

    def __str__(self):
        return f"{self.name} ({self.company.legal_name})"

    def clean(self):
        super().clean()
        # Ensure scope matches company scope
        if self.company_id and self.scope_id and self.company.scope_id != self.scope_id:
            raise ValidationError("Contact scope must match company scope.")

    def save(self, *args, **kwargs):
        # If this is set as primary, unset other primary contacts
        if self.is_primary:
            TenantContact.objects.filter(
                company=self.company,
                is_primary=True
            ).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)


class TenantKYC(TenantModel):
    """
    Know Your Customer (KYC) documents for a tenant company.
    """

    class KYCStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        VERIFIED = "VERIFIED", "Verified"
        REJECTED = "REJECTED", "Rejected"
        EXPIRED = "EXPIRED", "Expired"

    company = models.OneToOneField(
        TenantCompany,
        on_delete=models.CASCADE,
        related_name="kyc"
    )

    # Indian Tax IDs
    pan = models.CharField(max_length=10, blank=True, help_text="PAN Number")
    gstin = models.CharField(max_length=15, blank=True, help_text="GST Identification Number")
    cin = models.CharField(max_length=21, blank=True, help_text="Corporate Identification Number")
    tan = models.CharField(max_length=10, blank=True, help_text="Tax Deduction Account Number")

    # Bank Details
    bank_name = models.CharField(max_length=100, blank=True)
    bank_account_number = models.CharField(max_length=50, blank=True)
    bank_ifsc = models.CharField(max_length=11, blank=True, help_text="IFSC Code")

    # Status
    kyc_status = models.CharField(
        max_length=20,
        choices=KYCStatus.choices,
        default=KYCStatus.PENDING
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="verified_tenant_kyc_set"
    )
    rejection_reason = models.TextField(blank=True)

    class Meta:
        verbose_name = "Tenant KYC"
        verbose_name_plural = "Tenant KYCs"

    def __str__(self):
        return f"KYC - {self.company.legal_name}"

    def clean(self):
        super().clean()
        if self.company_id and self.scope_id and self.company.scope_id != self.scope_id:
            raise ValidationError("KYC scope must match company scope.")


class TenantPreferences(TenantModel):
    """
    Communication and billing preferences for a tenant company.
    """

    class Language(models.TextChoices):
        EN = "EN", "English"
        HI = "HI", "Hindi"
        MR = "MR", "Marathi"
        GU = "GU", "Gujarati"
        TA = "TA", "Tamil"

    company = models.OneToOneField(
        TenantCompany,
        on_delete=models.CASCADE,
        related_name="preferences"
    )

    # Email Preferences
    billing_email = models.EmailField(blank=True, help_text="Email for invoices and billing")
    communication_email = models.EmailField(blank=True, help_text="Email for general communication")

    # Communication
    preferred_language = models.CharField(
        max_length=5,
        choices=Language.choices,
        default=Language.EN
    )
    timezone = models.CharField(max_length=50, default="Asia/Kolkata")

    # Billing Preferences
    invoice_delivery_method = models.CharField(
        max_length=20,
        choices=[
            ("EMAIL", "Email"),
            ("POST", "Physical Post"),
            ("BOTH", "Both Email and Post"),
        ],
        default="EMAIL"
    )
    payment_reminder_days = models.PositiveIntegerField(
        default=7,
        help_text="Days before due date to send payment reminder"
    )

    class Meta:
        verbose_name = "Tenant Preferences"
        verbose_name_plural = "Tenant Preferences"

    def __str__(self):
        return f"Preferences - {self.company.legal_name}"

    def clean(self):
        super().clean()
        if self.company_id and self.scope_id and self.company.scope_id != self.scope_id:
            raise ValidationError("Preferences scope must match company scope.")
