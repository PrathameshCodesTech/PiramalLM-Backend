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
