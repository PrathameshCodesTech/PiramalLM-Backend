from django.contrib import admin
from . import models


@admin.register(models.TenantCompany)
class TenantCompanyAdmin(admin.ModelAdmin):
    list_display = ("legal_name", "trade_name", "email", "city", "status", "is_active")
    list_filter = ("status", "is_active", "city", "state")
    search_fields = ("legal_name", "trade_name", "email")
    ordering = ("legal_name",)
    readonly_fields = ("created_at", "updated_at", "created_by", "updated_by", "deleted_at")


@admin.register(models.TenantContact)
class TenantContactAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "email", "phone", "designation", "is_primary")
    list_filter = ("is_primary", "is_active")
    search_fields = ("name", "email", "company__legal_name")
    ordering = ("name",)


@admin.register(models.TenantKYC)
class TenantKYCAdmin(admin.ModelAdmin):
    list_display = ("company", "pan", "gstin", "kyc_status", "verified_at")
    list_filter = ("kyc_status", "is_active")
    search_fields = ("company__legal_name", "pan", "gstin")
    readonly_fields = ("verified_at", "verified_by")


@admin.register(models.TenantPreferences)
class TenantPreferencesAdmin(admin.ModelAdmin):
    list_display = ("company", "billing_email", "preferred_language", "timezone")
    list_filter = ("preferred_language", "invoice_delivery_method")
    search_fields = ("company__legal_name", "billing_email")
