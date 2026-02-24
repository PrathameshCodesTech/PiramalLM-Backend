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


# =============================================================================
# AGEING CONFIG ADMIN
# =============================================================================

@admin.register(models.AgeingConfig)
class AgeingConfigAdmin(admin.ModelAdmin):
    list_display = (
        "scope", "reference_date", "currency_handling",
        "include_disputed_in_standard_ageing", "exclude_credit_blocked_customers"
    )
    list_filter = (
        "reference_date", "currency_handling",
        "include_disputed_in_standard_ageing", "exclude_credit_blocked_customers"
    )
    fieldsets = (
        ("Scope", {
            "fields": ("scope",)
        }),
        ("Ageing Logic", {
            "fields": (
                "reference_date", "currency_handling",
                "include_disputed_in_standard_ageing", "exclude_credit_blocked_customers"
            )
        }),
        ("Display & Reporting", {
            "fields": (
                "show_on_ar_dashboard", "show_in_customer_statements",
                "enable_separate_disputed_ageing"
            )
        }),
    )


# =============================================================================
# SITE BILLING CONFIG ADMIN
# =============================================================================

@admin.register(models.SiteBillingConfig)
class SiteBillingConfigAdmin(admin.ModelAdmin):
    list_display = (
        "site", "invoice_pattern", "generation_mode",
        "default_payment_term", "default_gst_rate", "current_counter"
    )
    list_filter = ("generation_mode", "counter_reset_frequency", "gst_split_logic")
    search_fields = ("site__name", "site__code")
    ordering = ("site__name",)
    fieldsets = (
        ("Site", {
            "fields": ("site",)
        }),
        ("Invoice Numbering", {
            "fields": (
                "invoice_pattern", "include_property_code", "include_year_token",
                "counter_reset_frequency", "counter_padding", "current_counter"
            )
        }),
        ("Generation Settings", {
            "fields": (
                "generation_mode", "generation_day_of_month", "relative_generation_rule",
                "invoice_granularity", "billing_address_override", "default_gst_invoice_flag",
                "header_fields"
            )
        }),
        ("Payment Terms", {
            "fields": (
                "default_payment_term", "grace_period_days",
                "early_payment_discount_percent", "early_payment_discount_days",
                "late_fee_percent", "late_fee_flat_amount", "interest_rate_annual"
            )
        }),
        ("Tax Settings", {
            "fields": ("default_gst_rate", "gst_split_logic", "state_tax_rules")
        }),
        ("GL Accounts", {
            "fields": (
                "revenue_gl", "gst_output_gl", "gst_input_gl",
                "receivables_gl", "late_fee_gl", "interest_gl"
            )
        }),
    )


# =============================================================================
# BILLING RULE ADMIN
# =============================================================================

@admin.register(models.BillingRule)
class BillingRuleAdmin(admin.ModelAdmin):
    list_display = (
        "rule_id", "name", "charge_type", "calculation_method",
        "trigger_event", "category", "applies_to", "status", "owner", "created_at"
    )
    list_filter = ("charge_type", "calculation_method", "trigger_event", "category", "applies_to", "status")
    search_fields = ("rule_id", "name", "description", "gl_code")
    ordering = ("-created_at",)
    readonly_fields = ("rule_id", "created_at", "updated_at", "created_by", "updated_by")
    fieldsets = (
        ("Identification", {
            "fields": ("rule_id", "name", "description")
        }),
        ("Classification", {
            "fields": ("category", "applies_to", "charge_type", "status")
        }),
        ("Calculation", {
            "fields": ("calculation_method", "amount", "rate", "max_cap_amount")
        }),
        ("Trigger", {
            "fields": ("trigger_event", "grace_period_days", "trigger_mode")
        }),
        ("GL Mapping", {
            "fields": ("gl_code",)
        }),
        ("Ownership", {
            "fields": ("owner",)
        }),
        ("Audit", {
            "fields": ("created_at", "updated_at", "created_by", "updated_by"),
            "classes": ("collapse",)
        }),
    )


# =============================================================================
# DISPUTE RULE ADMIN
# =============================================================================

@admin.register(models.DisputeRule)
class DisputeRuleAdmin(admin.ModelAdmin):
    list_display = (
        "name", "condition_type", "operator", "threshold_value",
        "priority", "status", "auto_resolve"
    )
    list_filter = ("condition_type", "status", "auto_resolve", "require_approval")
    search_fields = ("name", "action_description")
    ordering = ("priority",)
    fieldsets = (
        ("Identification", {
            "fields": ("name", "description")
        }),
        ("Condition", {
            "fields": ("condition_type", "operator", "threshold_value", "threshold_currency", "time_window_days")
        }),
        ("Priority & Status", {
            "fields": ("priority", "status")
        }),
        ("Action", {
            "fields": (
                "action_description", "route_to_role", "route_to_user",
                "auto_resolve", "auto_resolve_action", "require_approval", "flag_customer"
            )
        }),
    )


# =============================================================================
# CREDIT RULE ADMIN
# =============================================================================

@admin.register(models.CreditRule)
class CreditRuleAdmin(admin.ModelAdmin):
    list_display = (
        "name", "trigger_type", "variance_threshold", "variance_basis",
        "approval_role", "auto_approve", "status"
    )
    list_filter = ("trigger_type", "variance_basis", "auto_approve", "status")
    search_fields = ("name", "description")
    ordering = ("name",)
    fieldsets = (
        ("Identification", {
            "fields": ("name", "description")
        }),
        ("Trigger Condition", {
            "fields": (
                "trigger_type", "variance_threshold", "variance_basis",
                "max_credit_amount"
            )
        }),
        ("Approval & Posting", {
            "fields": (
                "approval_role", "auto_approve",
                "auto_post_to_gl", "requires_documentation"
            )
        }),
        ("Status", {
            "fields": ("status",)
        }),
    )


# =============================================================================
# AR GLOBAL SETTINGS ADMIN
# =============================================================================

@admin.register(models.ARGlobalSettings)
class ARGlobalSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "scope", "enable_dispute_management", "enable_credit_note_workflow",
        "credit_note_requires_approval", "max_auto_credit_percent"
    )
    list_filter = (
        "enable_dispute_management", "enable_credit_note_workflow",
        "credit_note_requires_approval"
    )
    fieldsets = (
        ("Scope", {
            "fields": ("scope",)
        }),
        ("Dispute Management", {
            "fields": (
                "enable_dispute_management", "default_dispute_hold_collection",
                "default_stop_interest_on_dispute", "default_stop_reminders_on_dispute"
            )
        }),
        ("Credit Note Workflow", {
            "fields": (
                "enable_credit_note_workflow", "credit_note_requires_approval",
                "max_auto_credit_percent"
            )
        }),
    )
