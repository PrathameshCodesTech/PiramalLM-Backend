from rest_framework import serializers
from . import models


# ===================== Ageing Bucket Serializers =====================

class AgeingBucketSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.AgeingBucket
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )


class AgeingBucketListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""
    class Meta:
        model = models.AgeingBucket
        fields = ("id", "label", "from_days", "to_days", "sort_order", "color_code")


# ===================== AR Rule Serializers =====================

class ARRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ARRule
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )


class ARRuleUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating AR rules without changing agreement."""
    class Meta:
        model = models.ARRule
        exclude = ("agreement",)
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )


# ===================== Invoice Line Item Serializers =====================

class InvoiceLineItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.InvoiceLineItem
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at",
            "amount", "tax_amount", "total"  # Computed fields
        )


class InvoiceLineItemCreateSerializer(serializers.ModelSerializer):
    """For creating line items (amount/tax_amount/total are computed)."""
    class Meta:
        model = models.InvoiceLineItem
        fields = (
            "item_type", "description", "quantity", "unit_price", "tax_rate", "unit"
        )


# ===================== Invoice Serializers =====================

class InvoiceListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""
    tenant_name = serializers.SerializerMethodField()
    days_overdue = serializers.SerializerMethodField()

    class Meta:
        model = models.Invoice
        fields = (
            "id", "invoice_number", "invoice_type", "status",
            "invoice_date", "due_date", "total_amount", "balance_due",
            "tenant_name", "days_overdue", "is_disputed"
        )

    def get_tenant_name(self, obj):
        return obj.agreement.tenant.legal_name if obj.agreement and obj.agreement.tenant else None

    def get_days_overdue(self, obj):
        from django.utils import timezone
        if obj.balance_due > 0 and obj.due_date:
            today = timezone.now().date()
            if today > obj.due_date:
                return (today - obj.due_date).days
        return 0


class InvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Invoice
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at",
            "balance_due"  # Computed field
        )


class InvoiceDetailSerializer(serializers.ModelSerializer):
    """Full detail serializer with line items and payments."""
    line_items = InvoiceLineItemSerializer(many=True, read_only=True)
    payments = serializers.SerializerMethodField()
    credit_notes = serializers.SerializerMethodField()
    tenant_details = serializers.SerializerMethodField()
    agreement_details = serializers.SerializerMethodField()

    class Meta:
        model = models.Invoice
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )

    def get_payments(self, obj):
        return PaymentListSerializer(obj.payments.all(), many=True).data

    def get_credit_notes(self, obj):
        return CreditNoteListSerializer(obj.credit_notes.all(), many=True).data

    def get_tenant_details(self, obj):
        if obj.agreement and obj.agreement.tenant:
            tenant = obj.agreement.tenant
            return {
                "id": tenant.id,
                "legal_name": tenant.legal_name,
                "email": tenant.email,
                "phone": tenant.phone,
            }
        return None

    def get_agreement_details(self, obj):
        if obj.agreement:
            return {
                "id": obj.agreement.id,
                "lease_id": obj.agreement.lease_id,
                "status": obj.agreement.status,
            }
        return None


class InvoiceCreateSerializer(serializers.ModelSerializer):
    """For creating invoices with line items."""
    line_items = InvoiceLineItemCreateSerializer(many=True, required=False)
    invoice_number = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = models.Invoice
        fields = (
            "agreement", "invoice_number", "invoice_type", "status",
            "invoice_date", "due_date", "period_start", "period_end",
            "subtotal", "tax_amount", "total_amount", "currency", "notes",
            "line_items"
        )

    def create(self, validated_data):
        line_items_data = validated_data.pop("line_items", [])
        invoice_number = validated_data.get("invoice_number", "").strip()
        if not invoice_number:
            agreement = validated_data.get("agreement")
            scope = validated_data.get("scope")
            if agreement and scope and hasattr(agreement, "site") and agreement.site:
                try:
                    config = models.SiteBillingConfig.objects.get(site=agreement.site, scope=scope)
                    invoice_number = config.get_next_invoice_number()
                except models.SiteBillingConfig.DoesNotExist:
                    pass
            if not invoice_number:
                from django.utils import timezone
                if scope:
                    invoice_number = f"INV-{timezone.now().strftime('%Y%m%d')}-{models.Invoice.objects.filter(scope=scope).count() + 1}"
                else:
                    invoice_number = f"INV-{timezone.now().strftime('%Y%m%d%H%M%S')}"
            validated_data["invoice_number"] = invoice_number
        invoice = models.Invoice.objects.create(**validated_data)

        for item_data in line_items_data:
            models.InvoiceLineItem.objects.create(
                invoice=invoice,
                scope=invoice.scope,
                created_by=self.context["request"].user,
                **item_data
            )

        return invoice


# ===================== Payment Serializers =====================

class PaymentListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""
    class Meta:
        model = models.Payment
        fields = (
            "id", "payment_number", "payment_date", "amount",
            "payment_method", "status", "reference_number"
        )


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Payment
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )


class PaymentCreateSerializer(serializers.ModelSerializer):
    """For creating payments; auto-generates payment_number when empty."""
    payment_number = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = models.Payment
        fields = (
            "invoice", "payment_number", "payment_date", "amount",
            "payment_method", "status", "reference_number",
            "bank_name", "cheque_number", "transaction_id", "notes", "currency"
        )

    def create(self, validated_data):
        payment_number = validated_data.get("payment_number", "").strip()
        if not payment_number:
            scope = validated_data.get("scope")
            if scope:
                from django.utils import timezone
                cnt = models.Payment.objects.filter(scope=scope).count() + 1
                payment_number = f"PAY-{timezone.now().strftime('%Y%m%d')}-{cnt}"
            else:
                from django.utils import timezone
                payment_number = f"PAY-{timezone.now().strftime('%Y%m%d%H%M%S')}"
            validated_data["payment_number"] = payment_number
        return models.Payment.objects.create(**validated_data)


class PaymentDetailSerializer(serializers.ModelSerializer):
    """Full detail serializer with invoice details."""
    invoice_details = serializers.SerializerMethodField()

    class Meta:
        model = models.Payment
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )

    def get_invoice_details(self, obj):
        return {
            "id": obj.invoice.id,
            "invoice_number": obj.invoice.invoice_number,
            "total_amount": float(obj.invoice.total_amount),
            "balance_due": float(obj.invoice.balance_due),
        }


# ===================== Credit Note Serializers =====================

class CreditNoteListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""
    class Meta:
        model = models.CreditNote
        fields = (
            "id", "credit_note_number", "credit_note_date", "amount",
            "reason", "status"
        )


class CreditNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.CreditNote
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at",
            "approved_by", "approved_at", "applied_at"
        )


class CreditNoteCreateSerializer(serializers.ModelSerializer):
    """For creating credit notes; auto-generates credit_note_number when empty."""
    credit_note_number = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = models.CreditNote
        fields = (
            "invoice", "credit_note_number", "credit_note_date", "amount",
            "reason", "reason_details", "status"
        )

    def create(self, validated_data):
        credit_note_number = validated_data.get("credit_note_number", "").strip()
        if not credit_note_number:
            scope = validated_data.get("scope")
            if scope:
                from django.utils import timezone
                cnt = models.CreditNote.objects.filter(scope=scope).count() + 1
                credit_note_number = f"CN-{timezone.now().strftime('%Y%m%d')}-{cnt}"
            else:
                from django.utils import timezone
                credit_note_number = f"CN-{timezone.now().strftime('%Y%m%d%H%M%S')}"
            validated_data["credit_note_number"] = credit_note_number
        return models.CreditNote.objects.create(**validated_data)


class CreditNoteDetailSerializer(serializers.ModelSerializer):
    """Full detail serializer with invoice details."""
    invoice_details = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()

    class Meta:
        model = models.CreditNote
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )

    def get_invoice_details(self, obj):
        return {
            "id": obj.invoice.id,
            "invoice_number": obj.invoice.invoice_number,
            "total_amount": float(obj.invoice.total_amount),
        }

    def get_approved_by_name(self, obj):
        if obj.approved_by:
            return obj.approved_by.get_full_name() or obj.approved_by.email
        return None


# ===================== Invoice Schedule Serializers =====================

class InvoiceScheduleSerializer(serializers.ModelSerializer):
    agreement_lease_id = serializers.CharField(source="agreement.lease_id", read_only=True)

    class Meta:
        model = models.InvoiceSchedule
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at",
            "last_generated_date"
        )


class InvoiceScheduleListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""
    agreement_lease_id = serializers.CharField(source="agreement.lease_id", read_only=True)

    class Meta:
        model = models.InvoiceSchedule
        fields = (
            "id", "schedule_name", "invoice_type", "frequency",
            "amount", "start_date", "end_date", "is_active",
            "next_scheduled_date", "agreement_lease_id"
        )


# ===================== AR Summary Serializers =====================

class ARSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ARSummary
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )


class ARSummaryDetailSerializer(serializers.ModelSerializer):
    """Detailed AR summary with computed fields."""
    agreement_details = serializers.SerializerMethodField()
    ageing_buckets = serializers.SerializerMethodField()

    class Meta:
        model = models.ARSummary
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )

    def get_agreement_details(self, obj):
        if obj.agreement:
            return {
                "id": obj.agreement.id,
                "lease_id": obj.agreement.lease_id,
                "tenant_name": obj.agreement.tenant.legal_name if obj.agreement.tenant else None,
            }
        return None

    def get_ageing_buckets(self, obj):
        return [
            {"label": "Current (0-30)", "amount": float(obj.current_bucket)},
            {"label": "31-60 Days", "amount": float(obj.bucket_30_60)},
            {"label": "61-90 Days", "amount": float(obj.bucket_60_90)},
            {"label": "90+ Days", "amount": float(obj.bucket_90_plus)},
        ]


# ===================== Lease Rules Bundle Serializer =====================

class LeaseRulesBundleSerializer(serializers.Serializer):
    """
    Serializer for fetching/updating all lease rules at once.
    Used by /api/leases/{id}/rules/ endpoint.
    """

    # From leases app
    billing = serializers.SerializerMethodField()
    escalation = serializers.SerializerMethodField()

    # From billing app
    ar_rules = ARRuleUpdateSerializer(required=False)
    ageing_buckets = AgeingBucketListSerializer(many=True, read_only=True)

    def get_billing(self, obj):
        from apps.leases.serializers import LeaseBillingSerializer
        if hasattr(obj, "billing"):
            return LeaseBillingSerializer(obj.billing).data
        return None

    def get_escalation(self, obj):
        from apps.leases.serializers import LeaseEscalationSerializer
        if hasattr(obj, "escalation"):
            return LeaseEscalationSerializer(obj.escalation).data
        return None


class TenantLeasesRulesSerializer(serializers.Serializer):
    """
    Serializer for fetching all lease rules for a tenant.
    Used by /api/leases/tenant-leases-rules/{tenant_id}/
    """
    tenant_id = serializers.UUIDField(read_only=True)
    tenant_name = serializers.CharField(read_only=True)
    leases = serializers.ListField(read_only=True)


# =============================================================================
# AGEING CONFIG SERIALIZERS (Tab 4 - Ageing Logic)
# =============================================================================

class AgeingConfigSerializer(serializers.ModelSerializer):
    """Full serializer for ageing configuration."""
    class Meta:
        model = models.AgeingConfig
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )


class AgeingConfigUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating ageing config (scope is read-only)."""
    class Meta:
        model = models.AgeingConfig
        exclude = ("scope",)
        read_only_fields = (
            "id", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )


# =============================================================================
# SITE BILLING CONFIG SERIALIZERS (Tab 1 - Billing & Invoice Rules)
# =============================================================================

class SiteBillingConfigListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""
    site_name = serializers.CharField(source="site.name", read_only=True)
    site_code = serializers.CharField(source="site.code", read_only=True)

    class Meta:
        model = models.SiteBillingConfig
        fields = (
            "id", "site", "site_name", "site_code",
            "invoice_pattern", "generation_mode", "default_payment_term",
            "default_gst_rate", "gst_split_logic"
        )


class SiteBillingConfigSerializer(serializers.ModelSerializer):
    """Full serializer for site billing config."""
    class Meta:
        model = models.SiteBillingConfig
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at",
            "current_counter"  # Counter managed internally
        )


class SiteBillingConfigDetailSerializer(serializers.ModelSerializer):
    """Detail serializer with site info and computed fields."""
    site_name = serializers.CharField(source="site.name", read_only=True)
    site_code = serializers.CharField(source="site.code", read_only=True)
    next_invoice_preview = serializers.SerializerMethodField()

    class Meta:
        model = models.SiteBillingConfig
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )

    def get_next_invoice_preview(self, obj):
        """Preview what the next invoice number will look like."""
        from datetime import datetime
        now = datetime.now()
        pattern = obj.invoice_pattern

        preview = pattern
        if obj.include_property_code:
            preview = preview.replace("{PROP}", obj.site.code)
        else:
            preview = preview.replace("{PROP}/", "").replace("{PROP}", "")

        if obj.include_year_token:
            preview = preview.replace("{YEAR}", str(now.year))
        else:
            preview = preview.replace("{YEAR}/", "").replace("{YEAR}", "")

        preview = preview.replace("{MONTH}", f"{now.month:02d}")
        counter_str = str(obj.current_counter).zfill(obj.counter_padding)
        preview = preview.replace("{COUNTER}", counter_str)

        return preview


class SiteBillingConfigCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating site billing config."""
    class Meta:
        model = models.SiteBillingConfig
        fields = (
            "site", "invoice_pattern", "include_property_code", "include_year_token",
            "counter_reset_frequency", "counter_padding",
            "generation_mode", "generation_day_of_month", "relative_generation_rule",
            "invoice_granularity", "billing_address_override", "default_gst_invoice_flag",
            "header_fields",
            "default_payment_term", "grace_period_days",
            "early_payment_discount_percent", "early_payment_discount_days",
            "late_fee_percent", "late_fee_flat_amount", "interest_rate_annual",
            "default_gst_rate", "gst_split_logic", "state_tax_rules",
            "revenue_gl", "gst_output_gl", "gst_input_gl", "receivables_gl",
            "late_fee_gl", "interest_gl"
        )


# =============================================================================
# BILLING RULE SERIALIZERS (Tab 1 - Rules List)
# =============================================================================

class BillingRuleListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""
    owner_name = serializers.SerializerMethodField()

    class Meta:
        model = models.BillingRule
        fields = (
            "id", "rule_id", "name", "category", "applies_to",
            "status", "owner_name", "created_at"
        )

    def get_owner_name(self, obj):
        if obj.owner:
            return obj.owner.get_full_name() or obj.owner.email
        return None


class BillingRuleSerializer(serializers.ModelSerializer):
    """Full serializer for billing rules."""
    class Meta:
        model = models.BillingRule
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at",
            "rule_id"  # Auto-generated
        )


class BillingRuleDetailSerializer(serializers.ModelSerializer):
    """Detail serializer with owner info."""
    owner_name = serializers.SerializerMethodField()
    owner_email = serializers.SerializerMethodField()

    class Meta:
        model = models.BillingRule
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )

    def get_owner_name(self, obj):
        if obj.owner:
            return obj.owner.get_full_name() or obj.owner.email
        return None

    def get_owner_email(self, obj):
        if obj.owner:
            return obj.owner.email
        return None


# =============================================================================
# DISPUTE RULE SERIALIZERS (Tab 5 - AR Rules)
# =============================================================================

class DisputeRuleListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""
    condition_display = serializers.SerializerMethodField()

    class Meta:
        model = models.DisputeRule
        fields = (
            "id", "name", "condition_type", "operator", "threshold_value",
            "action_description", "priority", "status", "condition_display"
        )

    def get_condition_display(self, obj):
        """Human-readable condition."""
        op_map = {
            "GT": ">", "LT": "<", "EQ": "=",
            "GTE": ">=", "LTE": "<=", "NE": "!="
        }
        op = op_map.get(obj.operator, obj.operator)
        return f"{obj.get_condition_type_display()} {op} {obj.threshold_value}"


class DisputeRuleSerializer(serializers.ModelSerializer):
    """Full serializer for dispute rules."""
    class Meta:
        model = models.DisputeRule
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )


class DisputeRuleDetailSerializer(serializers.ModelSerializer):
    """Detail serializer with route info."""
    route_to_user_name = serializers.SerializerMethodField()
    condition_display = serializers.SerializerMethodField()

    class Meta:
        model = models.DisputeRule
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )

    def get_route_to_user_name(self, obj):
        if obj.route_to_user:
            return obj.route_to_user.get_full_name() or obj.route_to_user.email
        return None

    def get_condition_display(self, obj):
        op_map = {
            "GT": ">", "LT": "<", "EQ": "=",
            "GTE": ">=", "LTE": "<=", "NE": "!="
        }
        op = op_map.get(obj.operator, obj.operator)
        return f"{obj.get_condition_type_display()} {op} {obj.threshold_value}"


# =============================================================================
# CREDIT RULE SERIALIZERS (Tab 5 - AR Rules)
# =============================================================================

class CreditRuleListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""
    class Meta:
        model = models.CreditRule
        fields = (
            "id", "name", "trigger_type", "variance_threshold",
            "variance_basis", "approval_level", "auto_approve", "status"
        )


class CreditRuleSerializer(serializers.ModelSerializer):
    """Full serializer for credit rules."""
    class Meta:
        model = models.CreditRule
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )


class CreditRuleDetailSerializer(serializers.ModelSerializer):
    """Detail serializer with trigger display."""
    trigger_display = serializers.SerializerMethodField()

    class Meta:
        model = models.CreditRule
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )

    def get_trigger_display(self, obj):
        """Human-readable trigger condition."""
        if obj.variance_threshold:
            unit = "%" if obj.variance_basis == "PERCENTAGE" else obj.threshold_currency if hasattr(obj, 'threshold_currency') else "INR"
            return f"{obj.get_trigger_type_display()}: {obj.variance_threshold}{unit}"
        return obj.get_trigger_type_display()


# =============================================================================
# AR GLOBAL SETTINGS SERIALIZERS (Tab 5 - Toggle Switches)
# =============================================================================

class ARGlobalSettingsSerializer(serializers.ModelSerializer):
    """Full serializer for AR global settings."""
    class Meta:
        model = models.ARGlobalSettings
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )


class ARGlobalSettingsUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating AR settings (scope is read-only)."""
    class Meta:
        model = models.ARGlobalSettings
        exclude = ("scope",)
        read_only_fields = (
            "id", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )


# =============================================================================
# BILLING CONFIGURATION BUNDLE SERIALIZER
# =============================================================================

class BillingConfigBundleSerializer(serializers.Serializer):
    """
    Bundle serializer for fetching/updating all billing configuration at once.
    Used by /api/billing/config/ endpoint.
    """
    ageing_config = AgeingConfigSerializer(read_only=True)
    ageing_buckets = AgeingBucketListSerializer(many=True, read_only=True)
    ar_global_settings = ARGlobalSettingsSerializer(read_only=True)
    dispute_rules = DisputeRuleListSerializer(many=True, read_only=True)
    credit_rules = CreditRuleListSerializer(many=True, read_only=True)
    billing_rules = BillingRuleListSerializer(many=True, read_only=True)


class SiteBillingConfigBundleSerializer(serializers.Serializer):
    """
    Bundle serializer for fetching all billing config for a site.
    Used by /api/billing/site/{site_id}/config/ endpoint.
    """
    site_billing_config = SiteBillingConfigDetailSerializer(read_only=True)
    scope_config = BillingConfigBundleSerializer(read_only=True)
