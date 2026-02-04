import secrets
import string

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q, Prefetch
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from apps.accounts import models, serializers
from apps.core.utils import get_active_scope
from apps.core.viewsets import ScopedViewSet

User = get_user_model()


def generate_password(length=12):
    """Generate a random password with letters, digits, and symbols."""
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(chars) for _ in range(length))


# ===================== Me Endpoint =====================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    """
    Get current user info with full membership tree.
    Returns user details, active scope, and all memberships with permissions.
    """
    user = request.user
    profile = getattr(user, "profile", None)

    # Get active scope
    active_scope_id = None
    if profile and profile.active_scope_id:
        active_scope_id = profile.active_scope_id
    try:
        scope = get_active_scope(request)
        if scope:
            active_scope_id = scope.id
    except Exception:
        pass

    # Get all memberships
    memberships = models.ScopeMembership.objects.filter(
        user=user, is_active=True
    ).select_related("scope", "role", "scope__org", "scope__company", "scope__entity", "scope__site")

    # Get all user scopes with permissions
    user_scopes = models.UserScope.objects.filter(
        user=user, is_active=True
    ).select_related("scope", "scope__site")

    # Build membership tree
    membership_data = []
    for m in memberships:
        entry = {
            "id": m.id,
            "scope_id": m.scope_id,
            "scope_name": m.scope.name,
            "scope_type": m.scope.scope_type,
            "role_id": m.role_id,
            "role_name": m.role.name,
            "role_code": m.role.code,
        }

        # Add hierarchy info
        if m.scope.org:
            entry["org"] = {"id": m.scope.org.id, "name": m.scope.org.name}
        if m.scope.company:
            entry["company"] = {"id": m.scope.company.id, "name": m.scope.company.name}
            entry["org"] = {"id": m.scope.company.org.id, "name": m.scope.company.org.name}
        if m.scope.entity:
            entry["entity"] = {"id": m.scope.entity.id, "name": m.scope.entity.name}
            entry["company"] = {"id": m.scope.entity.company.id, "name": m.scope.entity.company.name}
            entry["org"] = {"id": m.scope.entity.company.org.id, "name": m.scope.entity.company.org.name}
        if m.scope.site:
            entry["site"] = {"id": m.scope.site.id, "name": m.scope.site.name}

        membership_data.append(entry)

    # Build user scope permissions
    scope_permissions = {}
    for us in user_scopes:
        scope_permissions[us.scope_id] = {
            "user_scope_id": us.id,
            "can_view": us.can_view,
            "can_create": us.can_create,
            "can_edit": us.can_edit,
            "can_delete": us.can_delete,
        }
        if us.scope.site:
            scope_permissions[us.scope_id]["site"] = {
                "id": us.scope.site.id,
                "name": us.scope.site.name,
            }

    data = {
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "is_superuser": user.is_superuser,
            "role": profile.role if profile else None,
        },
        "active_scope_id": active_scope_id,
        "memberships": membership_data,
        "scope_permissions": scope_permissions,
    }
    return Response(data)


# ===================== Org / Company / Entity ViewSets =====================

class OrgViewSet(ModelViewSet):
    queryset = models.Org.objects.all()
    serializer_class = serializers.OrgSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(code__icontains=search))
        return qs


class CompanyViewSet(ModelViewSet):
    queryset = models.Company.objects.all()
    serializer_class = serializers.CompanySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset().select_related("org")
        org_id = self.request.query_params.get("org_id")
        if org_id:
            qs = qs.filter(org_id=org_id)
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(code__icontains=search))
        return qs


class EntityViewSet(ModelViewSet):
    queryset = models.Entity.objects.all()
    serializer_class = serializers.EntitySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset().select_related("company", "company__org")
        company_id = self.request.query_params.get("company_id")
        if company_id:
            qs = qs.filter(company_id=company_id)
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(code__icontains=search))
        return qs


# ===================== TenantScope ViewSet =====================

class TenantScopeViewSet(ModelViewSet):
    queryset = models.TenantScope.objects.all()
    serializer_class = serializers.TenantScopeSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset().select_related("org", "company", "entity", "site")

        if not user.is_superuser:
            # Filter to scopes user has access to
            qs = qs.filter(
                Q(memberships__user=user, memberships__is_active=True) |
                Q(user_scopes__user=user, user_scopes__is_active=True)
            ).distinct()

        # Filter by scope type
        scope_type = self.request.query_params.get("scope_type")
        if scope_type:
            qs = qs.filter(scope_type=scope_type)

        # Filter by parent refs
        org_id = self.request.query_params.get("org_id")
        if org_id:
            qs = qs.filter(org_id=org_id)

        company_id = self.request.query_params.get("company_id")
        if company_id:
            qs = qs.filter(company_id=company_id)

        entity_id = self.request.query_params.get("entity_id")
        if entity_id:
            qs = qs.filter(entity_id=entity_id)

        site_id = self.request.query_params.get("site_id")
        if site_id:
            qs = qs.filter(site_id=site_id)

        return qs

    @action(detail=False, methods=["post"], url_path="set-active")
    def set_active(self, request):
        """Set active scope for current user."""
        scope_id = request.data.get("scope_id")

        if scope_id:
            try:
                scope = models.TenantScope.objects.get(id=scope_id)
            except models.TenantScope.DoesNotExist:
                raise ValidationError("Invalid scope_id.")

        profile, _ = models.UserProfile.objects.get_or_create(user=request.user)
        profile.active_scope_id = scope_id
        profile.save()

        return Response({"active_scope_id": scope_id})


# ===================== Permission / Role ViewSets =====================

class PermissionViewSet(ModelViewSet):
    queryset = models.Permission.objects.all()
    serializer_class = serializers.PermissionSerializer
    permission_classes = [IsAuthenticated]


class RoleViewSet(ScopedViewSet):
    queryset = models.Role.objects.all()
    serializer_class = serializers.RoleSerializer

    def get_serializer_class(self):
        if self.action == "list":
            return serializers.RoleListSerializer
        return serializers.RoleSerializer

    def get_queryset(self):
        qs = super().get_queryset().select_related("scope")

        # Allow filtering by scope_id param
        scope_id = self.request.query_params.get("scope_id")
        if scope_id:
            return models.Role.objects.filter(scope_id=scope_id)

        return qs


class RolePermissionViewSet(ModelViewSet):
    queryset = models.RolePermission.objects.all()
    serializer_class = serializers.RolePermissionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset().select_related("role", "permission")

        role_id = self.request.query_params.get("role_id")
        if role_id:
            qs = qs.filter(role_id=role_id)

        scope = get_active_scope(self.request)
        if scope:
            qs = qs.filter(role__scope=scope)

        return qs

    def perform_create(self, serializer):
        scope = get_active_scope(self.request)
        role = serializer.validated_data.get("role")
        if scope and role.scope_id != scope.id:
            raise ValidationError("Role must belong to active scope.")
        serializer.save()


# ===================== ScopeMembership ViewSet =====================

class ScopeMembershipViewSet(ScopedViewSet):
    queryset = models.ScopeMembership.objects.all()
    serializer_class = serializers.ScopeMembershipSerializer

    def get_queryset(self):
        qs = super().get_queryset().select_related("scope", "role", "user")

        scope = get_active_scope(self.request)
        if scope:
            qs = qs.filter(scope=scope)

        user_id = self.request.query_params.get("user_id")
        if user_id:
            qs = qs.filter(user_id=user_id)

        return qs


# ===================== UserScope ViewSet =====================

class UserScopeViewSet(ModelViewSet):
    """
    ViewSet for managing user scope permissions.

    Endpoints:
    - GET /user-scopes/ - List user scopes
    - POST /user-scopes/ - Create user scope
    - GET /user-scopes/{id}/ - Get scope details
    - PATCH /user-scopes/{id}/ - Update permissions
    - DELETE /user-scopes/{id}/ - Deactivate scope (soft delete)
    """

    queryset = models.UserScope.objects.all()
    serializer_class = serializers.UserScopeSerializer
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "list":
            return serializers.UserScopeListSerializer
        if self.action == "create":
            return serializers.UserScopeCreateSerializer
        if self.action in ["update", "partial_update"]:
            return serializers.UserScopeUpdateSerializer
        return serializers.UserScopeSerializer

    def get_queryset(self):
        qs = super().get_queryset().select_related("scope", "user")

        # Filter by user
        user_id = self.request.query_params.get("user")
        if user_id:
            qs = qs.filter(user_id=user_id)

        # Filter by scope type
        scope_type = self.request.query_params.get("scope_type")
        if scope_type:
            qs = qs.filter(scope__scope_type=scope_type)

        # Filter by active status
        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            qs = qs.filter(is_active=is_active in ["1", "true", "True"])

        return qs

    def perform_destroy(self, instance):
        """Soft delete - set is_active to False."""
        instance.is_active = False
        instance.save()


# ===================== UserCredential ViewSet =====================

class UserCredentialViewSet(ReadOnlyModelViewSet):
    queryset = models.UserCredential.objects.select_related("user", "scope")
    serializer_class = serializers.UserCredentialSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if not user.is_superuser:
            return self.queryset.none()
        qs = self.queryset
        scope_id = self.request.query_params.get("scope_id")
        if scope_id:
            qs = qs.filter(scope_id=scope_id)
        return qs.order_by("-id")


# ===================== UserProfile ViewSet =====================

class UserProfileViewSet(ModelViewSet):
    queryset = models.UserProfile.objects.all()
    serializer_class = serializers.UserProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset().select_related("user", "active_scope")

        user_id = self.request.query_params.get("user_id")
        if user_id:
            qs = qs.filter(user_id=user_id)

        return qs


# ===================== User ViewSet =====================

class UserViewSet(ModelViewSet):
    """
    ViewSet for user management.

    Endpoints:
    - GET /users/ - List users with optional search/scope filtering
    - POST /users/ - Create user with optional site assignment
    - GET /users/{id}/ - Get user details
    - PATCH /users/{id}/ - Update user
    - DELETE /users/{id}/ - Deactivate user
    """

    queryset = User.objects.all()
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "list":
            return serializers.UserListSerializer
        if self.action == "create":
            return serializers.UserCreateSerializer
        if self.action == "retrieve":
            return serializers.UserDetailSerializer
        return serializers.UserSerializer

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset().prefetch_related(
            "user_scopes", "user_scopes__scope", "profile"
        )

        if not user.is_superuser:
            scope = get_active_scope(self.request)
            if scope:
                qs = qs.filter(
                    Q(scope_memberships__scope=scope) |
                    Q(user_scopes__scope=scope, user_scopes__is_active=True)
                ).distinct()

        # Search
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(username__icontains=search) |
                Q(email__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search)
            )

        # Filter by scope_type
        scope_type = self.request.query_params.get("scope_type")
        scope_id = self.request.query_params.get("scope_id")
        if scope_type and scope_id:
            qs = qs.filter(
                user_scopes__scope__scope_type=scope_type,
                user_scopes__scope_id=scope_id,
                user_scopes__is_active=True
            ).distinct()

        # Filter by org_id
        org_id = self.request.query_params.get("org_id")
        if org_id:
            qs = qs.filter(
                Q(scope_memberships__scope__org_id=org_id) |
                Q(user_scopes__scope__org_id=org_id, user_scopes__is_active=True)
            ).distinct()

        return qs

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Extract fields
        password = data.pop("password", None) or generate_password()
        role = data.pop("role", models.UserProfile.UserRole.MANAGER)
        profile_json = data.pop("profile_json", {})
        site_id = data.pop("site_id", None)
        can_view = data.pop("can_view", True)
        can_create = data.pop("can_create", False)
        can_edit = data.pop("can_edit", False)
        can_delete = data.pop("can_delete", False)

        # Create user
        user = User(**data)
        user.set_password(password)
        user.save()

        # Create profile
        models.UserProfile.objects.create(
            user=user,
            role=role,
            profile_json=profile_json
        )

        # Assign to site if provided
        user_scope = None
        if site_id:
            from apps.properties.models import Site
            try:
                site = Site.objects.get(id=site_id)
            except Site.DoesNotExist:
                raise ValidationError({"site_id": "Invalid site_id."})

            # Get or create site scope
            scope, _ = models.TenantScope.objects.get_or_create(
                scope_type=models.TenantScope.ScopeType.SITE,
                site=site,
                defaults={
                    "name": site.name,
                    "code": f"site-{site.id}",
                }
            )

            # Create user scope
            user_scope = models.UserScope.objects.create(
                user=user,
                scope=scope,
                can_view=can_view,
                can_create=can_create,
                can_edit=can_edit,
                can_delete=can_delete,
            )

            # Store credential
            models.UserCredential.objects.create(
                user=user,
                scope=scope,
                password_plain=password
            )

        out = serializers.UserDetailSerializer(user).data
        out["password_plain"] = password
        if user_scope:
            out["user_scope_id"] = user_scope.id

        return Response(out, status=status.HTTP_201_CREATED)


# ===================== Assign Site Endpoint =====================

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def assign_site(request):
    """
    Assign a site to a user with permissions.
    Can create new user or assign to existing user.

    Request body:
    {
        "user_id": 123,  // OR
        "user": { "email": "...", "username": "...", "role": "MANAGER", ... },
        "site_id": 456,
        "can_view": true,
        "can_create": false,
        "can_edit": false,
        "can_delete": false
    }

    Response:
    {
        "user": 123,
        "user_detail": { ... },
        "user_scope_id": 789
    }
    """
    serializer = serializers.AssignSiteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    site_id = data["site_id"]
    can_view = data.get("can_view", True)
    can_create = data.get("can_create", False)
    can_edit = data.get("can_edit", False)
    can_delete = data.get("can_delete", False)

    # Get site and create scope
    from apps.properties.models import Site
    try:
        site = Site.objects.get(id=site_id)
    except Site.DoesNotExist:
        raise ValidationError({"site_id": "Invalid site_id."})

    scope, _ = models.TenantScope.objects.get_or_create(
        scope_type=models.TenantScope.ScopeType.SITE,
        site=site,
        defaults={
            "name": site.name,
            "code": f"site-{site.id}",
        }
    )

    with transaction.atomic():
        if data.get("user_id"):
            # Existing user
            try:
                user = User.objects.get(id=data["user_id"])
            except User.DoesNotExist:
                raise ValidationError({"user_id": "Invalid user_id."})

            # Create or update user scope
            user_scope, created = models.UserScope.objects.update_or_create(
                user=user,
                scope=scope,
                defaults={
                    "can_view": can_view,
                    "can_create": can_create,
                    "can_edit": can_edit,
                    "can_delete": can_delete,
                    "is_active": True,
                }
            )
        else:
            # Create new user
            user_data = data["user"]
            password = user_data.pop("password", None) or generate_password()
            role = user_data.pop("role", models.UserProfile.UserRole.MANAGER)
            profile_json = user_data.pop("profile_json", {})

            # Remove site assignment fields (handled here)
            user_data.pop("site_id", None)
            user_data.pop("can_view", None)
            user_data.pop("can_create", None)
            user_data.pop("can_edit", None)
            user_data.pop("can_delete", None)

            user = User(**user_data)
            user.set_password(password)
            user.save()

            # Create profile
            models.UserProfile.objects.create(
                user=user,
                role=role,
                profile_json=profile_json
            )

            # Create user scope
            user_scope = models.UserScope.objects.create(
                user=user,
                scope=scope,
                can_view=can_view,
                can_create=can_create,
                can_edit=can_edit,
                can_delete=can_delete,
            )

            # Store credential
            models.UserCredential.objects.create(
                user=user,
                scope=scope,
                password_plain=password
            )

    response_data = {
        "user": user.id,
        "user_detail": serializers.UserDetailSerializer(user).data,
        "user_scope_id": user_scope.id,
    }

    if "password" not in data.get("user", {}):
        response_data["password_plain"] = password if "password" in locals() else None

    return Response(response_data, status=status.HTTP_201_CREATED)


# ===================== Change Password Endpoint =====================

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def change_password(request):
    """
    Change current user's password.

    Request body:
    {
        "current_password": "...",
        "new_password": "..."
    }
    """
    user = request.user
    current_password = request.data.get("current_password")
    new_password = request.data.get("new_password")

    if not current_password or not new_password:
        raise ValidationError("Both current_password and new_password are required.")

    if not user.check_password(current_password):
        raise ValidationError({"current_password": "Incorrect password."})

    if len(new_password) < 6:
        raise ValidationError({"new_password": "Password must be at least 6 characters."})

    user.set_password(new_password)
    user.save()

    return Response({"message": "Password changed successfully."})
