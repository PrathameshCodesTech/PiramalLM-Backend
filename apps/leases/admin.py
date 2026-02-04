from django.contrib import admin
from . import models


@admin.register(models.Agreement)
class AgreementAdmin(admin.ModelAdmin):
    list_display = (
        "lease_id", "version_number", "tenant", "site",
        "agreement_type", "status", "created_at"
    )
    list_filter = ("status", "agreement_type", "is_active")
    search_fields = ("lease_id",)
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at", "created_by", "updated_by", "deleted_at")


@admin.register(models.LeaseTermDates)
class LeaseTermDatesAdmin(admin.ModelAdmin):
    list_display = ("agreement", "commencement_date", "expiry_date", "initial_term_months")


@admin.register(models.LeaseFinancials)
class LeaseFinancialsAdmin(admin.ModelAdmin):
    list_display = ("agreement", "base_rent_monthly", "billing_frequency")


@admin.register(models.LeaseEscalation)
class LeaseEscalationAdmin(admin.ModelAdmin):
    list_display = ("agreement", "escalation_type", "escalation_value")


@admin.register(models.LeaseCAM)
class LeaseCAMAdmin(admin.ModelAdmin):
    list_display = ("agreement", "allocation_basis", "monthly_total")


@admin.register(models.LeaseDeposit)
class LeaseDepositAdmin(admin.ModelAdmin):
    list_display = ("agreement", "amount", "held_by")


@admin.register(models.LeaseBilling)
class LeaseBillingAdmin(admin.ModelAdmin):
    list_display = ("agreement", "invoice_generate_rule", "grace_days")


@admin.register(models.UnitAllocation)
class UnitAllocationAdmin(admin.ModelAdmin):
    list_display = ("agreement", "unit", "allocation_mode", "allocated_area_sqft", "monthly_rent")
    list_filter = ("allocation_mode", "is_active")
    search_fields = ("agreement__lease_id",)


@admin.register(models.LeaseDocument)
class LeaseDocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "agreement", "document_type", "file_size", "created_at")
    list_filter = ("document_type", "is_active")
    search_fields = ("title",)


@admin.register(models.LeaseNote)
class LeaseNoteAdmin(admin.ModelAdmin):
    list_display = ("agreement", "created_by", "created_at")
    list_filter = ("is_active",)