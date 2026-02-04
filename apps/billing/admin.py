from django.contrib import admin
from . import models


@admin.register(models.AgeingBucket)
class AgeingBucketAdmin(admin.ModelAdmin):
    list_display = ("label", "from_days", "to_days", "sort_order", "color_code", "is_active")
    list_filter = ("is_active",)
    search_fields = ("label",)
    ordering = ("sort_order", "from_days")


@admin.register(models.ARRule)
class ARRuleAdmin(admin.ModelAdmin):
    list_display = (
        "agreement", "dispute_hold", "credit_note_allowed",
        "credit_note_requires_approval", "auto_reminder_enabled"
    )
    list_filter = ("dispute_hold", "credit_note_allowed", "auto_reminder_enabled")
    search_fields = ("agreement__lease_id",)


@admin.register(models.Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "invoice_number", "agreement", "invoice_type", "status",
        "invoice_date", "due_date", "total_amount", "balance_due"
    )
    list_filter = ("status", "invoice_type", "is_disputed")
    search_fields = ("invoice_number", "agreement__lease_id", "agreement__tenant__legal_name")
    date_hierarchy = "invoice_date"
    ordering = ("-invoice_date",)


@admin.register(models.InvoiceLineItem)
class InvoiceLineItemAdmin(admin.ModelAdmin):
    list_display = ("invoice", "item_type", "description", "quantity", "unit_price", "total")
    list_filter = ("item_type",)
    search_fields = ("description", "invoice__invoice_number")


@admin.register(models.Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "payment_number", "invoice", "payment_date", "amount",
        "payment_method", "status"
    )
    list_filter = ("payment_method", "status")
    search_fields = ("payment_number", "reference_number", "invoice__invoice_number")
    date_hierarchy = "payment_date"
    ordering = ("-payment_date",)


@admin.register(models.CreditNote)
class CreditNoteAdmin(admin.ModelAdmin):
    list_display = (
        "credit_note_number", "invoice", "credit_note_date", "amount",
        "reason", "status"
    )
    list_filter = ("status", "reason")
    search_fields = ("credit_note_number", "invoice__invoice_number")
    date_hierarchy = "credit_note_date"
    ordering = ("-credit_note_date",)


@admin.register(models.InvoiceSchedule)
class InvoiceScheduleAdmin(admin.ModelAdmin):
    list_display = (
        "schedule_name", "agreement", "invoice_type", "frequency",
        "amount", "start_date", "is_active"
    )
    list_filter = ("invoice_type", "frequency", "is_active")
    search_fields = ("schedule_name", "agreement__lease_id")
    ordering = ("agreement", "start_date")


@admin.register(models.ARSummary)
class ARSummaryAdmin(admin.ModelAdmin):
    list_display = (
        "agreement", "total_invoiced", "total_paid", "total_outstanding",
        "total_overdue", "open_invoice_count", "last_calculated_at"
    )
    search_fields = ("agreement__lease_id", "agreement__tenant__legal_name")
    ordering = ("-last_calculated_at",)
