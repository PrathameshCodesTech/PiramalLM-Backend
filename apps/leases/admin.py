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
    list_display = ("agreement", "invoice_generate_rule", "gst_applicable", "gst_rate")


@admin.register(models.UnitAllocation)
class UnitAllocationAdmin(admin.ModelAdmin):
    list_display = (
        "agreement",
        "allocation_level",
        "site",
        "tower",
        "floor",
        "unit",
        "allocation_mode",
        "allocated_area_sqft",
        "monthly_rent",
    )
    list_filter = ("allocation_level", "allocation_mode", "is_active")
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


@admin.register(models.LeaseRentFree)
class LeaseRentFreeAdmin(admin.ModelAdmin):
    list_display = ("agreement", "rent_free_days", "rent_free_start_date", "rent_free_end_date")
    search_fields = ("agreement__lease_id",)


@admin.register(models.LeaseTermination)
class LeaseTerminationAdmin(admin.ModelAdmin):
    list_display = (
        "agreement", "tenant_early_exit_permitted", "tenant_notice_days",
        "landlord_early_termination_permitted", "break_clause_enabled"
    )
    list_filter = (
        "tenant_early_exit_permitted", "landlord_early_termination_permitted",
        "break_clause_enabled"
    )
    search_fields = ("agreement__lease_id",)
    fieldsets = (
        ("Agreement", {
            "fields": ("agreement",)
        }),
        ("Tenant Early Exit", {
            "fields": (
                "tenant_early_exit_permitted", "tenant_notice_days",
                "tenant_penalty_type", "tenant_penalty_value", "tenant_exit_conditions"
            )
        }),
        ("Landlord Early Termination", {
            "fields": (
                "landlord_early_termination_permitted", "landlord_notice_days",
                "landlord_compensation_type", "landlord_compensation_value",
                "landlord_relocation_assistance", "landlord_termination_conditions"
            )
        }),
        ("Break Clause", {
            "fields": (
                "break_clause_enabled", "break_date", "break_window_start",
                "break_window_end", "break_notice_days", "break_penalty",
                "break_penalty_type", "break_conditions"
            )
        }),
        ("Termination for Cause", {
            "fields": ("termination_for_cause_events", "cure_period_days")
        }),
        ("General", {
            "fields": ("termination_clause",)
        }),
    )


@admin.register(models.EscalationTemplate)
class EscalationTemplateAdmin(admin.ModelAdmin):
    list_display = (
        "name", "escalation_type", "escalation_percentage",
        "frequency", "status", "applicability"
    )
    list_filter = ("status", "escalation_type", "frequency", "applicability")
    search_fields = ("name", "description")
    ordering = ("name",)


# =============================================================================
# CLAUSE CONFIGURATION ADMIN
# =============================================================================

@admin.register(models.LeaseRenewalOption)
class LeaseRenewalOptionAdmin(admin.ModelAdmin):
    list_display = (
        "agreement", "pre_renewal_notice_days", "auto_renewal_enabled",
        "max_renewal_cycles", "current_cycle"
    )
    list_filter = ("auto_renewal_enabled",)
    search_fields = ("agreement__lease_id",)
    fieldsets = (
        ("Agreement", {
            "fields": ("agreement",)
        }),
        ("Pre-Renewal Settings", {
            "fields": (
                "pre_renewal_notice_days", "auto_renewal_enabled", "auto_renewal_term_months"
            )
        }),
        ("Renewal Cycles", {
            "fields": ("renewal_cycles", "max_renewal_cycles")
        }),
        ("Current Status", {
            "fields": (
                "current_cycle", "last_renewal_date", "next_renewal_deadline", "renewal_notes"
            )
        }),
    )


@admin.register(models.LeaseSubletSignage)
class LeaseSubletSignageAdmin(admin.ModelAdmin):
    list_display = (
        "agreement", "sublet_permission", "sublet_approval_required",
        "signage_permitted", "signage_approval_required"
    )
    list_filter = ("sublet_permission", "sublet_approval_required", "signage_permitted")
    search_fields = ("agreement__lease_id",)
    fieldsets = (
        ("Agreement", {
            "fields": ("agreement",)
        }),
        ("Sub-Letting", {
            "fields": (
                "sublet_permission", "sublet_approval_required", "max_sublet_percentage",
                "sublet_restrictions", "sublet_rent_share_percent"
            )
        }),
        ("Signage Rights", {
            "fields": (
                "signage_permitted", "signage_approval_required", "signage_area_sqft",
                "signage_locations", "signage_specifications", "signage_cost_responsibility"
            )
        }),
    )


@admin.register(models.LeaseExclusivity)
class LeaseExclusivityAdmin(admin.ModelAdmin):
    list_display = (
        "agreement", "exclusive_use_granted", "exclusive_category",
        "non_compete_enabled", "non_compete_duration_months"
    )
    list_filter = ("exclusive_use_granted", "non_compete_enabled")
    search_fields = ("agreement__lease_id", "exclusive_category")
    fieldsets = (
        ("Agreement", {
            "fields": ("agreement",)
        }),
        ("Exclusive Use", {
            "fields": (
                "exclusive_use_granted", "exclusive_category", "exclusive_radius",
                "exclusive_exceptions", "excluded_categories", "exclusivity_breach_penalty"
            )
        }),
        ("Non-Compete", {
            "fields": (
                "non_compete_enabled", "non_compete_duration_months", "non_compete_radius_km",
                "non_compete_scope", "non_compete_breach_penalty"
            )
        }),
    )


@admin.register(models.LeaseInsuranceRequirement)
class LeaseInsuranceRequirementAdmin(admin.ModelAdmin):
    list_display = (
        "agreement", "restore_condition", "public_liability_required",
        "property_insurance_required", "business_interruption_required"
    )
    list_filter = (
        "restore_condition", "public_liability_required",
        "property_insurance_required", "business_interruption_required"
    )
    search_fields = ("agreement__lease_id",)
    fieldsets = (
        ("Agreement", {
            "fields": ("agreement",)
        }),
        ("Reinstatement", {
            "fields": (
                "restore_condition", "restore_exceptions",
                "reinstatement_deposit", "reinstatement_timeline_days"
            )
        }),
        ("Public Liability Insurance", {
            "fields": (
                "public_liability_required", "public_liability_coverage",
                "public_liability_currency"
            )
        }),
        ("Property Insurance", {
            "fields": ("property_insurance_required", "property_insurance_coverage")
        }),
        ("Business Interruption Insurance", {
            "fields": (
                "business_interruption_required", "business_interruption_coverage_months"
            )
        }),
        ("Other Requirements", {
            "fields": (
                "other_insurance_requirements", "landlord_additional_insured",
                "proof_required", "proof_frequency", "proof_due_days_before_expiry"
            )
        }),
    )


@admin.register(models.LeaseDisputeResolution)
class LeaseDisputeResolutionAdmin(admin.ModelAdmin):
    list_display = (
        "agreement", "dispute_mechanism", "arbitration_seat",
        "governing_law_country", "exclusive_jurisdiction"
    )
    list_filter = ("dispute_mechanism", "governing_law_country", "exclusive_jurisdiction")
    search_fields = ("agreement__lease_id", "arbitration_seat")
    fieldsets = (
        ("Agreement", {
            "fields": ("agreement",)
        }),
        ("Dispute Mechanism", {
            "fields": ("dispute_mechanism",)
        }),
        ("Arbitration Details", {
            "fields": (
                "arbitration_seat", "arbitration_rules", "arbitration_language",
                "number_of_arbitrators", "arbitration_institution"
            )
        }),
        ("Mediation Details", {
            "fields": (
                "mediation_required_first", "mediation_period_days", "mediation_venue"
            )
        }),
        ("Governing Law", {
            "fields": (
                "governing_law_country", "governing_law_state",
                "jurisdiction_court", "exclusive_jurisdiction"
            )
        }),
        ("Summary", {
            "fields": ("dispute_summary",)
        }),
    )


# =============================================================================
# AMENDMENT ADMIN
# =============================================================================

class AmendmentApprovalInline(admin.TabularInline):
    model = models.AmendmentApproval
    extra = 0
    fields = ("step_order", "step_name", "approver", "status", "actioned_at", "comments")
    readonly_fields = ("actioned_at",)


class AmendmentAttachmentInline(admin.TabularInline):
    model = models.AmendmentAttachment
    extra = 0
    fields = ("title", "attachment_type", "file", "uploaded_by")
    readonly_fields = ("uploaded_by",)


@admin.register(models.LeaseAmendment)
class LeaseAmendmentAdmin(admin.ModelAdmin):
    list_display = (
        "amendment_id", "agreement", "amendment_type", "title",
        "previous_version", "new_version", "approval_status", "amendment_date"
    )
    list_filter = ("amendment_type", "approval_status", "is_major_version")
    search_fields = ("amendment_id", "title", "agreement__lease_id")
    date_hierarchy = "amendment_date"
    ordering = ("-amendment_date",)
    inlines = [AmendmentApprovalInline, AmendmentAttachmentInline]
    readonly_fields = ("amendment_id", "created_at", "updated_at", "created_by", "updated_by")
    fieldsets = (
        ("Identification", {
            "fields": ("agreement", "amendment_id", "amendment_type", "title")
        }),
        ("Version", {
            "fields": ("previous_version", "new_version", "is_major_version")
        }),
        ("Dates", {
            "fields": ("amendment_date", "effective_from", "effective_to", "executed_date")
        }),
        ("Status", {
            "fields": ("approval_status",)
        }),
        ("Details", {
            "fields": ("changes_summary", "description", "reason", "initiated_by")
        }),
        ("Audit", {
            "fields": ("created_at", "updated_at", "created_by", "updated_by"),
            "classes": ("collapse",)
        }),
    )


@admin.register(models.AmendmentApproval)
class AmendmentApprovalAdmin(admin.ModelAdmin):
    list_display = (
        "amendment", "step_order", "step_name", "approver",
        "status", "actioned_at", "due_date"
    )
    list_filter = ("status",)
    search_fields = ("step_name", "amendment__amendment_id")
    ordering = ("amendment", "step_order")


@admin.register(models.AmendmentAttachment)
class AmendmentAttachmentAdmin(admin.ModelAdmin):
    list_display = (
        "title", "amendment", "attachment_type", "file_size",
        "uploaded_by", "created_at"
    )
    list_filter = ("attachment_type",)
    search_fields = ("title", "amendment__amendment_id")
    ordering = ("-created_at",)


# =============================================================================
# LINKED DOCUMENT ADMIN
# =============================================================================

class DocumentApprovalInline(admin.TabularInline):
    model = models.DocumentApproval
    extra = 0
    fields = ("step_order", "step_name", "approver", "status", "actioned_at", "comments")
    readonly_fields = ("actioned_at",)


@admin.register(models.LeaseLinkedDocument)
class LeaseLinkedDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "title", "agreement", "category", "status",
        "expiry_date", "requires_renewal", "created_at"
    )
    list_filter = ("category", "status", "requires_renewal")
    search_fields = ("title", "agreement__lease_id")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    inlines = [DocumentApprovalInline]
    readonly_fields = ("created_at", "updated_at", "created_by", "updated_by", "is_expiring_soon", "is_expired")
    fieldsets = (
        ("Agreement", {
            "fields": ("agreement",)
        }),
        ("Document Details", {
            "fields": ("title", "category", "status", "version")
        }),
        ("File", {
            "fields": ("file", "file_size", "mime_type", "external_url")
        }),
        ("Dates", {
            "fields": ("document_date", "effective_date", "expiry_date")
        }),
        ("Renewal Tracking", {
            "fields": (
                "requires_renewal", "renewal_reminder_days",
                "is_expiring_soon", "is_expired"
            )
        }),
        ("Description", {
            "fields": ("description", "notes")
        }),
        ("Upload Info", {
            "fields": ("uploaded_by", "created_at", "updated_at")
        }),
    )


@admin.register(models.DocumentApproval)
class DocumentApprovalAdmin(admin.ModelAdmin):
    list_display = (
        "document", "step_order", "step_name", "approver",
        "status", "actioned_at"
    )
    list_filter = ("status",)
    search_fields = ("step_name", "document__title")
    ordering = ("document", "step_order")
