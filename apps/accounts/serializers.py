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

    class Meta:
        model = models.TenantScope
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at", "created_by", "updated_by", "is_active", "deleted_at")


class TenantScopeListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for dropdowns."""
    class Meta:
        model = models.TenantScope
        fields = ("id", "scope_type", "name", "code")


# ===================== Permission / Role Serializers =====================

class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Permission
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at", "created_by", "updated_by", "is_active", "deleted_at")


class RoleSerializer(serializers.ModelSerializer):
    scope_name = serializers.CharField(source="scope.name", read_only=True)
    permissions_list = serializers.SerializerMethodField()

    class Meta:
        model = models.Role
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at", "created_by", "updated_by", "is_active", "deleted_at")

    def get_permissions_list(self, obj):
        return list(obj.permissions.values_list("code", flat=True))


class RoleListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for dropdowns."""
    class Meta:
        model = models.Role
        fields = ("id", "name", "code", "is_system")


class RolePermissionSerializer(serializers.ModelSerializer):
    permission_code = serializers.CharField(source="permission.code", read_only=True)
    permission_name = serializers.CharField(source="permission.name", read_only=True)

    class Meta:
        model = models.RolePermission
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at", "created_by", "updated_by", "is_active", "deleted_at")


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


# ===================== UserCredential Serializers =====================

class UserCredentialSerializer(serializers.ModelSerializer):
    user_username = serializers.CharField(source="user.username", read_only=True)
    user_email = serializers.CharField(source="user.email", read_only=True)
    scope_name = serializers.CharField(source="scope.name", read_only=True)

    class Meta:
        model = models.UserCredential
        fields = ("id", "user", "user_username", "user_email", "scope", "scope_name", "password_plain", "created_at")
        read_only_fields = ("id", "created_at")


# ===================== UserProfile Serializers =====================

class UserProfileSerializer(serializers.ModelSerializer):
    active_scope_name = serializers.CharField(source="active_scope.name", read_only=True)
    active_scope_type = serializers.CharField(source="active_scope.scope_type", read_only=True)

    class Meta:
        model = models.UserProfile
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at", "created_by", "updated_by", "is_active", "deleted_at")


# ===================== UserScope Serializers =====================

class UserScopeSerializer(serializers.ModelSerializer):
    scope_type = serializers.CharField(source="scope.scope_type", read_only=True)
    scope_name = serializers.CharField(source="scope.name", read_only=True)
    scope_code = serializers.CharField(source="scope.code", read_only=True)
    user_email = serializers.CharField(source="user.email", read_only=True)
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = models.UserScope
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at", "created_by", "updated_by", "deleted_at")

    def get_user_name(self, obj):
        if obj.user:
            return obj.user.get_full_name() or obj.user.username
        return None


class UserScopeListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""
    scope_type = serializers.CharField(source="scope.scope_type", read_only=True)
    scope_name = serializers.CharField(source="scope.name", read_only=True)
    scope_id = serializers.IntegerField(source="scope.id", read_only=True)

    class Meta:
        model = models.UserScope
        fields = (
            "id", "user", "scope_id", "scope_type", "scope_name",
            "can_view", "can_create", "can_edit", "can_delete", "is_active"
        )


class UserScopeCreateSerializer(serializers.ModelSerializer):
    """For creating user scopes."""
    class Meta:
        model = models.UserScope
        fields = ("user", "scope", "can_view", "can_create", "can_edit", "can_delete")


class UserScopeUpdateSerializer(serializers.ModelSerializer):
    """For updating permissions on existing scope."""
    class Meta:
        model = models.UserScope
        fields = ("can_view", "can_create", "can_edit", "can_delete", "is_active")


# ===================== User Serializers =====================

class UserSerializer(serializers.ModelSerializer):
    """Basic user serializer."""
    role = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "username", "email", "first_name", "last_name", "is_active", "is_staff", "is_superuser", "role")
        read_only_fields = ("id", "is_active", "is_staff", "is_superuser")

    def get_role(self, obj):
        profile = getattr(obj, "profile", None)
        return profile.role if profile else None


class UserListSerializer(serializers.ModelSerializer):
    """User list with scope counts."""
    role = serializers.SerializerMethodField()
    scopes_count = serializers.SerializerMethodField()
    site_scopes_count = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id", "username", "email", "first_name", "last_name",
            "is_active", "role", "scopes_count", "site_scopes_count", "full_name"
        )

    def get_role(self, obj):
        profile = getattr(obj, "profile", None)
        return profile.role if profile else None

    def get_scopes_count(self, obj):
        return obj.user_scopes.filter(is_active=True).count()

    def get_site_scopes_count(self, obj):
        return obj.user_scopes.filter(
            is_active=True,
            scope__scope_type=models.TenantScope.ScopeType.SITE
        ).count()

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.username


class UserDetailSerializer(serializers.ModelSerializer):
    """Full user detail with profile and scopes."""
    role = serializers.SerializerMethodField()
    profile = serializers.SerializerMethodField()
    scopes = serializers.SerializerMethodField()
    memberships = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id", "username", "email", "first_name", "last_name",
            "is_active", "is_staff", "is_superuser", "date_joined",
            "role", "profile", "scopes", "memberships"
        )

    def get_role(self, obj):
        profile = getattr(obj, "profile", None)
        return profile.role if profile else None

    def get_profile(self, obj):
        profile = getattr(obj, "profile", None)
        if profile:
            return {
                "id": profile.id,
                "role": profile.role,
                "phone": profile.phone,
                "profile_json": profile.profile_json,
                "active_scope_id": profile.active_scope_id,
            }
        return None

    def get_scopes(self, obj):
        scopes = obj.user_scopes.filter(is_active=True).select_related("scope")
        return UserScopeListSerializer(scopes, many=True).data

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


class UserCreateSerializer(serializers.ModelSerializer):
    """For creating users with optional site assignment."""
    password = serializers.CharField(write_only=True, min_length=6, required=False, allow_blank=True)
    role = serializers.ChoiceField(
        choices=models.UserProfile.UserRole.choices,
        default=models.UserProfile.UserRole.MANAGER
    )
    profile_json = serializers.JSONField(required=False, default=dict)

    # Optional first site assignment
    site_id = serializers.IntegerField(write_only=True, required=False)
    can_view = serializers.BooleanField(write_only=True, default=True)
    can_create = serializers.BooleanField(write_only=True, default=False)
    can_edit = serializers.BooleanField(write_only=True, default=False)
    can_delete = serializers.BooleanField(write_only=True, default=False)

    class Meta:
        model = User
        fields = (
            "id", "username", "email", "first_name", "last_name", "password",
            "role", "profile_json", "site_id", "can_view", "can_create", "can_edit", "can_delete"
        )
        read_only_fields = ("id",)


# ===================== Assign Site Serializer =====================

class AssignSiteSerializer(serializers.Serializer):
    """For assigning a site to a user (create or update)."""
    # User identification (either existing user_id or new user data)
    user_id = serializers.IntegerField(required=False)
    user = UserCreateSerializer(required=False)

    # Site to assign
    site_id = serializers.IntegerField(required=True)

    # Permissions
    can_view = serializers.BooleanField(default=True)
    can_create = serializers.BooleanField(default=False)
    can_edit = serializers.BooleanField(default=False)
    can_delete = serializers.BooleanField(default=False)

    def validate(self, data):
        if not data.get("user_id") and not data.get("user"):
            raise serializers.ValidationError("Either user_id or user data must be provided.")
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
    active_scope_id = serializers.IntegerField(allow_null=True)
    memberships = MembershipTreeSerializer(many=True)
    permissions = serializers.DictField(required=False)
