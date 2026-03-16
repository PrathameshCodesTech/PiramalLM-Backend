from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from rest_framework import serializers

from apps.accounts import models

User = get_user_model()


# ===================== Org / Company / Entity Serializers =====================

class OrgSerializer(serializers.ModelSerializer):
    companies_count = serializers.SerializerMethodField()

    class Meta:
        model = models.Org
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at", "created_by", "updated_by", "is_active", "deleted_at")

    def get_companies_count(self, obj):
        return obj.companies.count()


class CompanySerializer(serializers.ModelSerializer):
    org_name = serializers.CharField(source="org.name", read_only=True)
    entities_count = serializers.SerializerMethodField()

    class Meta:
        model = models.Company
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at", "created_by", "updated_by", "is_active", "deleted_at")

    def get_entities_count(self, obj):
        return obj.entities.count()


class EntitySerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="company.name", read_only=True)
    org_name = serializers.CharField(source="company.org.name", read_only=True)

    class Meta:
        model = models.Entity
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at", "created_by", "updated_by", "is_active", "deleted_at")


# ===================== TenantScope Serializers =====================

class TenantScopeSerializer(serializers.ModelSerializer):
    org_name = serializers.CharField(source="org.name", read_only=True)
    company_name = serializers.CharField(source="company.name", read_only=True)
    entity_name = serializers.CharField(source="entity.name", read_only=True)
    site_name = serializers.CharField(source="site.name", read_only=True)

    def validate(self, attrs):
        attrs = super().validate(attrs)

        org = attrs.get("org") or getattr(self.instance, "org", None)
        company = attrs.get("company") or getattr(self.instance, "company", None)
        entity = attrs.get("entity") or getattr(self.instance, "entity", None)
        site = attrs.get("site") or getattr(self.instance, "site", None)
        scope_type = attrs.get("scope_type") or getattr(self.instance, "scope_type", None)

        refs = [bool(org), bool(company), bool(entity), bool(site)]
        if sum(refs) != 1:
            raise serializers.ValidationError(
                "TenantScope must link to exactly one of org/company/entity/site."
            )

        # Ensure scope_type matches the linked ref
        if org and scope_type != models.TenantScope.ScopeType.ORG:
            raise serializers.ValidationError({"scope_type": "scope_type must be ORG when org is set."})
        if company and scope_type != models.TenantScope.ScopeType.COMPANY:
            raise serializers.ValidationError({"scope_type": "scope_type must be COMPANY when company is set."})
        if entity and scope_type != models.TenantScope.ScopeType.ENTITY:
            raise serializers.ValidationError({"scope_type": "scope_type must be ENTITY when entity is set."})
        if site and scope_type != models.TenantScope.ScopeType.SITE:
            raise serializers.ValidationError({"scope_type": "scope_type must be SITE when site is set."})

        # Enforce 1:1 scope per ref with a clean 400 instead of DB IntegrityError
        qs = models.TenantScope.objects.all()
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if org and qs.filter(org=org).exists():
            raise serializers.ValidationError({"org": "A scope already exists for this org."})
        if company and qs.filter(company=company).exists():
            raise serializers.ValidationError({"company": "A scope already exists for this company."})
        if entity and qs.filter(entity=entity).exists():
            raise serializers.ValidationError({"entity": "A scope already exists for this entity."})
        if site and qs.filter(site=site).exists():
            raise serializers.ValidationError({"site": "A scope already exists for this site."})

        return attrs

    class Meta:
        model = models.TenantScope
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at", "created_by", "updated_by", "is_active", "deleted_at")


class TenantScopeListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for dropdowns."""
    class Meta:
        model = models.TenantScope
        fields = ("id", "scope_type", "name", "code")


# ===================== Role Serializers =====================

class ModulePermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ModulePermission
        fields = (
            "id", "module",
            "can_view", "can_create", "can_edit", "can_delete", "can_approve",
        )


class RoleSerializer(serializers.ModelSerializer):
    scope_name = serializers.CharField(source="scope.name", read_only=True)
    module_permissions = ModulePermissionSerializer(many=True, read_only=True)
    base_on_name = serializers.CharField(source="base_on.name", read_only=True, default=None)

    class Meta:
        model = models.Role
        fields = (
            "id", "scope", "scope_name", "name", "code",
            "description", "role_type", "status", "is_system",
            "base_on", "base_on_name",
            # Approval caps
            "approval_cap_amount", "can_approve_amendments",
            "can_approve_waivers", "can_modify_matrices",
            # Relations
            "module_permissions",
            # Audit
            "created_at", "updated_at", "created_by", "updated_by",
            "is_active", "deleted_at",
        )
        read_only_fields = ("id", "created_at", "updated_at", "created_by", "updated_by", "is_active", "deleted_at")


class RoleWriteSerializer(serializers.ModelSerializer):
    """Write serializer — accepts nested module_permissions for bulk upsert."""
    module_permissions = ModulePermissionSerializer(many=True, required=False)

    class Meta:
        model = models.Role
        fields = (
            "scope", "name", "code", "description", "role_type", "status",
            "is_system", "base_on",
            "approval_cap_amount", "can_approve_amendments",
            "can_approve_waivers", "can_modify_matrices",
            "module_permissions",
        )

    def _save_module_permissions(self, role, mp_data):
        if mp_data is None:
            return
        existing = {mp.module: mp for mp in role.module_permissions.all()}
        for mp_item in mp_data:
            module = mp_item["module"]
            if module in existing:
                for field in ("can_view", "can_create", "can_edit", "can_delete", "can_approve"):
                    setattr(existing[module], field, mp_item.get(field, False))
                existing[module].save()
            else:
                models.ModulePermission.objects.create(role=role, **mp_item)

    def create(self, validated_data):
        mp_data = validated_data.pop("module_permissions", None)
        role = super().create(validated_data)
        self._save_module_permissions(role, mp_data)
        return role

    def update(self, instance, validated_data):
        mp_data = validated_data.pop("module_permissions", None)
        role = super().update(instance, validated_data)
        self._save_module_permissions(role, mp_data)
        return role


class RoleListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for dropdowns — includes scope context for labelling."""
    scope_name = serializers.CharField(source="scope.name", read_only=True)
    scope_type = serializers.CharField(source="scope.scope_type", read_only=True)

    class Meta:
        model = models.Role
        fields = ("id", "name", "code", "is_system", "role_type", "status", "scope_name", "scope_type")


# ===================== ScopeMembership Serializers =====================

class ScopeMembershipSerializer(serializers.ModelSerializer):
    scope_name = serializers.CharField(source="scope.name", read_only=True)
    scope_type = serializers.CharField(source="scope.scope_type", read_only=True)
    role_name = serializers.CharField(source="role.name", read_only=True)
    role_code = serializers.CharField(source="role.code", read_only=True)
    user_email = serializers.CharField(source="user.email", read_only=True)

    class Meta:
        model = models.ScopeMembership
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at", "created_by", "updated_by", "is_active", "deleted_at")

    def validate(self, attrs):
        role = attrs.get("role") or (self.instance.role if self.instance else None)
        scope = attrs.get("scope") or (self.instance.scope if self.instance else None)
        if role and scope:
            if role.scope_id != scope.id:
                raise serializers.ValidationError({"role": "Role does not belong to the selected scope."})
            if role.status != models.Role.RoleStatus.PUBLISHED:
                raise serializers.ValidationError({"role": "Only published roles can be assigned."})
        return attrs


# ===================== UserChangeLog Serializer =====================

class UserChangeLogSerializer(serializers.ModelSerializer):
    changed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = models.UserChangeLog
        fields = ("id", "field_changed", "old_value", "new_value", "changed_at", "changed_by_name")
        read_only_fields = fields

    def get_changed_by_name(self, obj):
        if obj.changed_by:
            return obj.changed_by.get_full_name() or obj.changed_by.username
        return "System"


# ===================== UserProfile Serializers =====================

class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.UserProfile
        fields = (
            "id", "user", "status", "department",
            "phone", "avatar", "profile_json",
            "invite_token", "invite_accepted",
            "created_at", "updated_at", "is_active",
        )
        read_only_fields = ("id", "user", "invite_token", "created_at", "updated_at", "is_active")


# ===================== User Serializers =====================

class UserSerializer(serializers.ModelSerializer):
    """Basic user serializer."""

    class Meta:
        model = User
        fields = ("id", "username", "email", "first_name", "last_name", "is_active", "is_staff", "is_superuser")
        read_only_fields = ("id", "is_active", "is_staff", "is_superuser")


class UserListSerializer(serializers.ModelSerializer):
    """User list with memberships count and scope info."""
    department = serializers.SerializerMethodField()
    user_status = serializers.SerializerMethodField()
    memberships_count = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()
    memberships = serializers.SerializerMethodField()
    last_active = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id", "username", "email", "first_name", "last_name",
            "is_active", "department", "user_status",
            "memberships_count", "full_name", "memberships", "last_active",
        )

    def get_department(self, obj):
        profile = getattr(obj, "profile", None)
        return profile.department if profile else ""

    def get_user_status(self, obj):
        profile = getattr(obj, "profile", None)
        return profile.status if profile else "ACTIVE"

    def get_memberships_count(self, obj):
        return obj.scope_memberships.filter(is_active=True).count()

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.username

    def get_last_active(self, obj):
        return getattr(obj, "last_login", None)

    def get_memberships(self, obj):
        return [
            {
                "scope_id": m.scope_id,
                "scope_name": m.scope.name,
                "scope_type": m.scope.scope_type,
                "role_name": m.role.name,
            }
            for m in obj.scope_memberships.filter(is_active=True).select_related("scope", "role")
        ]


class UserDetailSerializer(serializers.ModelSerializer):
    """Full user detail with profile, memberships, and recent change log."""
    profile = serializers.SerializerMethodField()
    memberships = serializers.SerializerMethodField()
    recent_changes = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id", "username", "email", "first_name", "last_name",
            "is_active", "is_staff", "is_superuser", "date_joined", "last_login",
            "profile", "memberships", "recent_changes",
        )

    def get_profile(self, obj):
        profile = getattr(obj, "profile", None)
        if profile:
            return {
                "id": profile.id,
                "status": profile.status,
                "department": profile.department,
                "phone": profile.phone,
                "avatar": profile.avatar.url if profile.avatar else None,
                "invite_accepted": profile.invite_accepted,
                "profile_json": profile.profile_json,
            }
        return None

    def get_memberships(self, obj):
        memberships = obj.scope_memberships.filter(is_active=True).select_related("scope", "role")
        return [
            {
                "id": m.id,
                "scope_id": m.scope_id,
                "scope_name": m.scope.name,
                "scope_type": m.scope.scope_type,
                "role_id": m.role_id,
                "role_name": m.role.name,
            }
            for m in memberships
        ]

    def get_recent_changes(self, obj):
        logs = models.UserChangeLog.objects.filter(user=obj).order_by("-changed_at")[:5]
        return UserChangeLogSerializer(logs, many=True).data


class UserCreateSerializer(serializers.ModelSerializer):
    """For creating users with optional ScopeMembership (Org/Company/Entity admin)."""
    password = serializers.CharField(write_only=True, min_length=6, required=False, allow_blank=True)
    profile_json = serializers.JSONField(required=False, default=dict)

    scope_id = serializers.IntegerField(write_only=True, required=False)
    role_id = serializers.IntegerField(write_only=True, required=False)

    class Meta:
        model = User
        fields = (
            "id", "username", "email", "first_name", "last_name", "password",
            "profile_json",
            "scope_id", "role_id",
        )
        read_only_fields = ("id",)

    def validate(self, data):
        scope_id = data.get("scope_id")
        role_id = data.get("role_id")
        if scope_id and not role_id:
            raise serializers.ValidationError({"role_id": "role_id is required when scope_id is provided."})
        if role_id and not scope_id:
            raise serializers.ValidationError({"scope_id": "scope_id is required when role_id is provided."})
        if scope_id and role_id:
            try:
                scope = models.TenantScope.objects.get(id=scope_id, is_active=True)
            except models.TenantScope.DoesNotExist:
                raise serializers.ValidationError({"scope_id": "Invalid scope_id or scope is inactive."})
            try:
                role = models.Role.objects.get(id=role_id, scope=scope)
            except models.Role.DoesNotExist:
                raise serializers.ValidationError({"role_id": "Invalid role_id or role does not belong to this scope."})
        return data


# ===================== Me / Auth Serializers =====================

class MembershipTreeSerializer(serializers.Serializer):
    """Serializer for membership tree structure."""
    scope_type = serializers.CharField()
    scope_id = serializers.IntegerField()
    scope_name = serializers.CharField()
    role_id = serializers.IntegerField(required=False)
    role_name = serializers.CharField(required=False)
    org = serializers.DictField(required=False)
    company = serializers.DictField(required=False)
    entity = serializers.DictField(required=False)
    sites = serializers.ListField(required=False)
    permissions = serializers.DictField(required=False)


class MeSerializer(serializers.Serializer):
    """Serializer for /me/ endpoint response."""
    user = serializers.DictField()
    memberships = MembershipTreeSerializer(many=True)
    permissions = serializers.DictField(required=False)
