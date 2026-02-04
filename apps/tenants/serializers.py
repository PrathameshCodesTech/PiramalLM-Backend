from rest_framework import serializers
from . import models


class TenantContactSerializer(serializers.ModelSerializer):
    """Serializer for tenant contacts."""

    class Meta:
        model = models.TenantContact
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )


class TenantKYCSerializer(serializers.ModelSerializer):
    """Serializer for tenant KYC documents."""

    class Meta:
        model = models.TenantKYC
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at",
            "verified_at", "verified_by"
        )


class TenantPreferencesSerializer(serializers.ModelSerializer):
    """Serializer for tenant preferences."""

    class Meta:
        model = models.TenantPreferences
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )


class TenantCompanyListSerializer(serializers.ModelSerializer):
    """Minimal serializer for company listing."""

    primary_contact_name = serializers.SerializerMethodField()
    kyc_status = serializers.SerializerMethodField()

    class Meta:
        model = models.TenantCompany
        fields = (
            "id", "legal_name", "trade_name", "email", "phone",
            "city", "state", "status", "primary_contact_name", "kyc_status"
        )

    def get_primary_contact_name(self, obj):
        primary = obj.contacts.filter(is_primary=True).first()
        return primary.name if primary else None

    def get_kyc_status(self, obj):
        try:
            return obj.kyc.kyc_status
        except models.TenantKYC.DoesNotExist:
            return None


class TenantCompanySerializer(serializers.ModelSerializer):
    """Full serializer for company CRUD."""

    class Meta:
        model = models.TenantCompany
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )


class TenantCompanyDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer with nested contacts, kyc, and preferences."""

    contacts = TenantContactSerializer(many=True, read_only=True)
    kyc = TenantKYCSerializer(read_only=True)
    preferences = TenantPreferencesSerializer(read_only=True)
    primary_contact = serializers.SerializerMethodField()

    class Meta:
        model = models.TenantCompany
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )

    def get_primary_contact(self, obj):
        primary = obj.contacts.filter(is_primary=True).first()
        if primary:
            return TenantContactSerializer(primary).data
        return None


class TenantCompanyWithLeaseSummarySerializer(serializers.ModelSerializer):
    """Serializer for tenant directory with lease summary."""

    primary_contact = serializers.SerializerMethodField()
    kyc_status = serializers.SerializerMethodField()
    active_leases_count = serializers.SerializerMethodField()
    total_leased_area = serializers.SerializerMethodField()

    class Meta:
        model = models.TenantCompany
        fields = (
            "id", "legal_name", "trade_name", "email", "phone",
            "city", "state", "status", "primary_contact", "kyc_status",
            "active_leases_count", "total_leased_area"
        )

    def get_primary_contact(self, obj):
        primary = obj.contacts.filter(is_primary=True).first()
        if primary:
            return {"id": primary.id, "name": primary.name, "email": primary.email}
        return None

    def get_kyc_status(self, obj):
        try:
            return obj.kyc.kyc_status
        except models.TenantKYC.DoesNotExist:
            return None

    def get_active_leases_count(self, obj):
        # Will be populated when leases app is integrated
        return getattr(obj, "_active_leases_count", 0)

    def get_total_leased_area(self, obj):
        # Will be populated when leases app is integrated
        return getattr(obj, "_total_leased_area", 0)
