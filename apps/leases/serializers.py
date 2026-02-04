from rest_framework import serializers
from apps.tenants.serializers import TenantCompanyListSerializer, TenantContactSerializer
from . import models


# ===================== Term Serializers =====================

class LeaseTermDatesSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.LeaseTermDates
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )


class LeaseRentFreeSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.LeaseRentFree
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )


class LeaseFinancialsSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.LeaseFinancials
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )


class LeaseEscalationSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.LeaseEscalation
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )


class LeaseCAMSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.LeaseCAM
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )


class LeaseDepositSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.LeaseDeposit
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )


class LeaseBillingSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.LeaseBilling
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )


class LeaseTerminationSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.LeaseTermination
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )


# ===================== Allocation Serializers =====================

class UnitAllocationSerializer(serializers.ModelSerializer):
    unit_details = serializers.SerializerMethodField()

    class Meta:
        model = models.UnitAllocation
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )

    def get_unit_details(self, obj):
        if obj.unit:
            return {
                "id": obj.unit.id,
                "unit_no": obj.unit.unit_no,
                "unit_type": obj.unit.unit_type,
                "leasable_area_sqft": obj.unit.leasable_area_sqft,
                "builtup_area_sqft": obj.unit.builtup_area_sqft,
            }
        return None


class UnitAllocationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.UnitAllocation
        fields = ("unit", "allocation_mode", "allocated_area_sqft", "monthly_rent")


# ===================== Document & Note Serializers =====================

class LeaseDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.LeaseDocument
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at",
            "file_size", "mime_type"
        )


class LeaseNoteSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = models.LeaseNote
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.email
        return None


# ===================== Agreement Serializers =====================

class AgreementListSerializer(serializers.ModelSerializer):
    """Minimal serializer for list views."""

    tenant_name = serializers.SerializerMethodField()
    site_name = serializers.SerializerMethodField()
    total_allocated_area = serializers.SerializerMethodField()
    monthly_rent = serializers.SerializerMethodField()

    class Meta:
        model = models.Agreement
        fields = (
            "id", "lease_id", "version_number", "status", "agreement_type",
            "tenant", "tenant_name", "site", "site_name", "landlord_entity",
            "total_allocated_area", "monthly_rent", "created_at"
        )

    def get_tenant_name(self, obj):
        return obj.tenant.legal_name if obj.tenant else None

    def get_site_name(self, obj):
        return obj.site.name if obj.site else None

    def get_total_allocated_area(self, obj):
        return sum(
            alloc.allocated_area_sqft or 0
            for alloc in obj.unit_allocations.all()
        )

    def get_monthly_rent(self, obj):
        try:
            return obj.financials.base_rent_monthly
        except models.LeaseFinancials.DoesNotExist:
            return None


class AgreementSerializer(serializers.ModelSerializer):
    """Standard serializer for CRUD operations."""

    class Meta:
        model = models.Agreement
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )


class AgreementDetailSerializer(serializers.ModelSerializer):
    """Full detail serializer with nested terms."""

    tenant_details = TenantCompanyListSerializer(source="tenant", read_only=True)
    primary_contact_details = TenantContactSerializer(source="primary_contact", read_only=True)
    site_details = serializers.SerializerMethodField()

    # Nested terms (OneToOne relations)
    term_dates = LeaseTermDatesSerializer(read_only=True)
    rent_free = LeaseRentFreeSerializer(read_only=True)
    financials = LeaseFinancialsSerializer(read_only=True)
    escalation = LeaseEscalationSerializer(read_only=True)
    cam = LeaseCAMSerializer(read_only=True)
    deposit = LeaseDepositSerializer(read_only=True)
    billing = LeaseBillingSerializer(read_only=True)
    termination = LeaseTerminationSerializer(read_only=True)

    # Collections
    unit_allocations = UnitAllocationSerializer(many=True, read_only=True)
    documents = LeaseDocumentSerializer(many=True, read_only=True)
    notes_list = LeaseNoteSerializer(many=True, read_only=True)

    # Computed fields
    total_allocated_area = serializers.SerializerMethodField()
    total_monthly_rent = serializers.SerializerMethodField()

    class Meta:
        model = models.Agreement
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )

    def get_site_details(self, obj):
        if obj.site:
            return {
                "id": obj.site.id,
                "name": obj.site.name,
                "address": getattr(obj.site, "address", ""),
                "city": getattr(obj.site, "city", ""),
            }
        return None

    def get_total_allocated_area(self, obj):
        return sum(
            float(alloc.allocated_area_sqft or 0)
            for alloc in obj.unit_allocations.all()
        )

    def get_total_monthly_rent(self, obj):
        try:
            base = float(obj.financials.base_rent_monthly or 0)
            cam = float(obj.cam.monthly_total or 0) if hasattr(obj, "cam") else 0
            return base + cam
        except (models.LeaseFinancials.DoesNotExist, models.LeaseCAM.DoesNotExist):
            return 0


# ===================== Bundle Serializers =====================

class LeaseTermsBundleSerializer(serializers.Serializer):
    """
    Serializer for updating all lease terms at once.
    Used by the /agreements/{id}/bundle/ endpoint.
    """

    term_dates = LeaseTermDatesSerializer(required=False)
    rent_free = LeaseRentFreeSerializer(required=False)
    financials = LeaseFinancialsSerializer(required=False)
    escalation = LeaseEscalationSerializer(required=False)
    cam = LeaseCAMSerializer(required=False)
    deposit = LeaseDepositSerializer(required=False)
    billing = LeaseBillingSerializer(required=False)
    termination = LeaseTerminationSerializer(required=False)
    unit_allocations = UnitAllocationCreateSerializer(many=True, required=False)

    def update_or_create_term(self, agreement, model_class, data, scope, user):
        """Helper to update or create a term model."""
        if data is None:
            return None

        # Remove read-only fields
        data.pop("id", None)
        data.pop("scope", None)
        data.pop("agreement", None)
        data.pop("created_at", None)
        data.pop("updated_at", None)
        data.pop("created_by", None)
        data.pop("updated_by", None)
        data.pop("is_active", None)
        data.pop("deleted_at", None)

        instance, created = model_class.objects.update_or_create(
            agreement=agreement,
            defaults={**data, "scope": scope, "updated_by": user}
        )
        if created:
            instance.created_by = user
            instance.save(update_fields=["created_by"])
        return instance

    def save(self, agreement, scope, user):
        """Save all terms for the agreement."""
        data = self.validated_data

        # Update each term model
        if "term_dates" in data:
            self.update_or_create_term(
                agreement, models.LeaseTermDates, data["term_dates"], scope, user
            )

        if "rent_free" in data:
            self.update_or_create_term(
                agreement, models.LeaseRentFree, data["rent_free"], scope, user
            )

        if "financials" in data:
            self.update_or_create_term(
                agreement, models.LeaseFinancials, data["financials"], scope, user
            )

        if "escalation" in data:
            self.update_or_create_term(
                agreement, models.LeaseEscalation, data["escalation"], scope, user
            )

        if "cam" in data:
            self.update_or_create_term(
                agreement, models.LeaseCAM, data["cam"], scope, user
            )

        if "deposit" in data:
            self.update_or_create_term(
                agreement, models.LeaseDeposit, data["deposit"], scope, user
            )

        if "billing" in data:
            self.update_or_create_term(
                agreement, models.LeaseBilling, data["billing"], scope, user
            )

        if "termination" in data:
            self.update_or_create_term(
                agreement, models.LeaseTermination, data["termination"], scope, user
            )

        # Handle unit allocations
        if "unit_allocations" in data:
            # Clear existing allocations
            agreement.unit_allocations.all().delete()
            # Create new allocations
            for alloc_data in data["unit_allocations"]:
                models.UnitAllocation.objects.create(
                    agreement=agreement,
                    scope=scope,
                    created_by=user,
                    **alloc_data
                )

        return agreement


class AgreementCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating a new agreement with optional initial terms.
    """

    terms = LeaseTermsBundleSerializer(required=False, write_only=True)

    class Meta:
        model = models.Agreement
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )

    def create(self, validated_data):
        terms_data = validated_data.pop("terms", None)
        agreement = super().create(validated_data)

        if terms_data:
            terms_serializer = LeaseTermsBundleSerializer(data=terms_data)
            terms_serializer.is_valid(raise_exception=True)
            terms_serializer.save(
                agreement=agreement,
                scope=agreement.scope,
                user=self.context["request"].user
            )

        return agreement