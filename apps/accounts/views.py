import secrets
import string

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q, Prefetch
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.accounts import models, serializers
from apps.core.utils import get_active_scope
from apps.core.viewsets import ScopedViewSet

User = get_user_model()


def generate_password(length=12):
    """Generate a random password with letters, digits, and symbols."""
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(chars) for _ in range(length))


# ===================== Helper: Validate Scope Access =====================

def validate_scope_header(request):
    """
    Validate X-Scope-ID header for bootstrap endpoints (/me/, /me/available-scopes/).

    Returns (scope, error_response) tuple.
    - Header provided + valid: (scope, None)
    - Header not provided: (None, None) — caller must handle unscoped access
    - Header provided + invalid: raises PermissionDenied

    Without header, both superusers and non-superusers get (None, None).
    The calling view is responsible for scoping data appropriately:
    - Superuser + None scope → all system data
    - Non-superuser + None scope → only data from user's memberships
    """
    from rest_framework.exceptions import PermissionDenied

    user = request.user
    header_scope_id = request.headers.get("X-Scope-ID")

    # No header: allowed for all users (bootstrap scenario — scope picker, initial login)
    if not header_scope_id:
        # Verify user has at least one active membership (unless superuser)
        if not user.is_superuser:
            has_membership = models.ScopeMembership.objects.filter(
                user=user, is_active=True
            ).exists()
            if not has_membership:
                raise PermissionDenied(
                    "No active scope memberships found for your account. "
                    "Contact your administrator to be assigned to a scope."
                )
        return None, None

    # Validate scope exists
    try:
        scope = models.TenantScope.objects.get(id=header_scope_id, is_active=True)
    except models.TenantScope.DoesNotExist:
        raise PermissionDenied(
            f"X-Scope-ID: Scope with id '{header_scope_id}' does not exist or is inactive."
        )

    # Superuser with header - validate scope exists (already done), return it
    if user.is_superuser:
        return scope, None

    # Non-superuser: validate membership
    if not models.ScopeMembership.objects.filter(
        user=user,
        scope=scope,
        is_active=True,
    ).exists():
        raise PermissionDenied(
            f"X-Scope-ID: You are not a member of scope '{scope.name}' (id={scope.id}). "
            "Pass a scope id you have access to."
        )

    return scope, None


def get_scopes_in_boundary(scope):
    """
    Get all scope IDs within the boundary of the given scope.
    Includes the scope itself + all child scopes.
    """
    if scope is None:
        return None  # None means all scopes

    scope_ids = {scope.id}
    child_scopes = scope.get_child_scopes()
    scope_ids.update(s.id for s in child_scopes)
    return scope_ids


def _get_scope_or_none(request):
    """Returns active scope if X-Scope-ID present and valid, else None. Does not raise."""
    from rest_framework.exceptions import PermissionDenied
    try:
        return get_active_scope(request)
    except PermissionDenied:
        return None


def _org_company_entity_ids_for_scope(scope):
    """
    Return (org_ids, company_ids, entity_ids) for scope boundary filtering.
    None in a set means no filter (show all at that level).
    """
    if scope is None:
        return None, None, None
    if scope.scope_type == models.TenantScope.ScopeType.ORG and scope.org_id:
        return {scope.org_id}, None, None  # org + all its companies and entities
    if scope.scope_type == models.TenantScope.ScopeType.COMPANY and scope.company_id:
        org_id = scope.company.org_id
        return {org_id}, {scope.company_id}, None
    if scope.scope_type == models.TenantScope.ScopeType.ENTITY and scope.entity_id:
        entity = scope.entity
        return {entity.company.org_id}, {entity.company_id}, {entity.id}
    if scope.scope_type == models.TenantScope.ScopeType.SITE and scope.site_id:
        site = scope.site
        entity = getattr(site, "entity", None)
        if entity:
            return {entity.company.org_id}, {entity.company_id}, {entity.id}
        return None, None, None
    return None, None, None


# ===================== Me Endpoint =====================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    """
    Get current user info with memberships within scope boundary.

    Headers:
    - X-Scope-ID: Required for non-superusers. Returns memberships within that scope boundary.

    Superuser without X-Scope-ID: Returns all memberships.
    Regular user without X-Scope-ID: 403 error.
    """
    user = request.user
    profile = getattr(user, "profile", None)

    # Validate scope header
    active_scope, _ = validate_scope_header(request)

    # Get boundary scope IDs
    boundary_scope_ids = get_scopes_in_boundary(active_scope)

    # Get memberships (filtered by boundary if applicable)
    memberships = models.ScopeMembership.objects.filter(
        user=user, is_active=True
    ).select_related("scope", "role", "scope__org", "scope__company", "scope__entity", "scope__site")

    if boundary_scope_ids is not None:
        memberships = memberships.filter(scope_id__in=boundary_scope_ids)

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
        "active_scope": {
            "id": active_scope.id,
            "name": active_scope.name,
            "scope_type": active_scope.scope_type,
        } if active_scope else None,
        "memberships": membership_data,
    }
    return Response(data)


# ===================== Available Scopes Endpoint =====================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def available_scopes(request):
    """
    Get scopes the current user can access within the X-Scope-ID boundary.

    Headers:
    - X-Scope-ID: Required for non-superusers. Returns scopes within that boundary.

    Superuser without X-Scope-ID: Returns all scopes.
    Regular user without X-Scope-ID: 403 error.

    Response:
    {
        "scopes": [
            {
                "id": 1,
                "name": "ABC Group",
                "scope_type": "ORG",
                "level": 0,
                "org": {"id": 1, "name": "ABC Group"},
                "company": null,
                "entity": null
            },
            ...
        ],
        "active_scope": {"id": 1, "name": "ABC Group", "scope_type": "ORG"},
        "highest_level": "ORG"
    }
    """
    user = request.user

    # Validate scope header
    active_scope, _ = validate_scope_header(request)

    # Get boundary scope IDs
    boundary_scope_ids = get_scopes_in_boundary(active_scope)

    # Get scopes within boundary
    if boundary_scope_ids is None:
        base_qs = models.TenantScope.objects.select_related(
            "org", "company", "company__org", "entity", "entity__company", "entity__company__org", "site"
        )
        if user.is_superuser:
            # Superuser without header — all system scopes
            all_scopes = base_qs.filter(is_active=True)
        else:
            # Non-superuser without header — only scopes from their memberships
            user_scope_ids = models.ScopeMembership.objects.filter(
                user=user, is_active=True
            ).values_list("scope_id", flat=True)
            all_scopes = base_qs.filter(id__in=user_scope_ids, is_active=True)
    else:
        # Filter to boundary
        all_scopes = models.TenantScope.objects.select_related(
            "org", "company", "company__org", "entity", "entity__company", "entity__company__org", "site"
        ).filter(id__in=boundary_scope_ids, is_active=True)

    if not all_scopes.exists():
        return Response({"scopes": [], "active_scope": None, "highest_level": None})

    # Determine level order for sorting and display
    level_order = {
        models.TenantScope.ScopeType.ORG: 0,
        models.TenantScope.ScopeType.COMPANY: 1,
        models.TenantScope.ScopeType.ENTITY: 2,
        models.TenantScope.ScopeType.SITE: 3,
    }

    # Build scope list with hierarchy info
    scope_list = []
    for scope in all_scopes:
        entry = {
            "id": scope.id,
            "name": scope.name,
            "code": scope.code,
            "scope_type": scope.scope_type,
            "level": level_order.get(scope.scope_type, 99),
            "org": None,
            "company": None,
            "entity": None,
            "site": None,
        }

        # Add hierarchy references
        if scope.scope_type == models.TenantScope.ScopeType.ORG and scope.org:
            entry["org"] = {"id": scope.org.id, "name": scope.org.name, "code": scope.org.code}

        elif scope.scope_type == models.TenantScope.ScopeType.COMPANY and scope.company:
            entry["company"] = {"id": scope.company.id, "name": scope.company.name, "code": scope.company.code}
            entry["org"] = {"id": scope.company.org.id, "name": scope.company.org.name, "code": scope.company.org.code}

        elif scope.scope_type == models.TenantScope.ScopeType.ENTITY and scope.entity:
            entry["entity"] = {"id": scope.entity.id, "name": scope.entity.name, "code": scope.entity.code}
            entry["company"] = {
                "id": scope.entity.company.id,
                "name": scope.entity.company.name,
                "code": scope.entity.company.code
            }
            entry["org"] = {
                "id": scope.entity.company.org.id,
                "name": scope.entity.company.org.name,
                "code": scope.entity.company.org.code
            }

        elif scope.scope_type == models.TenantScope.ScopeType.SITE and scope.site:
            entry["site"] = {"id": scope.site.id, "name": scope.site.name, "code": scope.site.code}

        scope_list.append(entry)

    # Sort by level, then by name
    scope_list.sort(key=lambda x: (x["level"], x["name"]))

    # Determine highest level
    highest_level = min(scope_list, key=lambda x: x["level"])["scope_type"] if scope_list else None

    return Response({
        "scopes": scope_list,
        "active_scope": {
            "id": active_scope.id,
            "name": active_scope.name,
            "scope_type": active_scope.scope_type,
        } if active_scope else None,
        "highest_level": highest_level,
    })


# ===================== Permissions =====================


def _user_can_manage_org(user, org):
    """True if user can manage this org (create companies under it)."""
    if user.is_superuser:
        return True
    org_scope = models.TenantScope.objects.filter(
        org=org, scope_type=models.TenantScope.ScopeType.ORG, is_active=True
    ).first()
    if not org_scope:
        return False
    return models.ScopeMembership.objects.filter(
        user=user, scope=org_scope, is_active=True
    ).exists()


def _user_can_manage_company(user, company):
    """True if user can manage this company (create entities under it)."""
    if user.is_superuser:
        return True
    org_scope = models.TenantScope.objects.filter(
        org=company.org, scope_type=models.TenantScope.ScopeType.ORG, is_active=True
    ).first()
    company_scope = models.TenantScope.objects.filter(
        company=company, scope_type=models.TenantScope.ScopeType.COMPANY, is_active=True
    ).first()
    scope_ids = [s.id for s in [org_scope, company_scope] if s]
    if not scope_ids:
        return False
    return models.ScopeMembership.objects.filter(
        user=user, scope_id__in=scope_ids, is_active=True
    ).exists()


class IsSuperuserForOrg(BasePermission):
    """Org: read = any authenticated; create/update/delete = superuser only."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return request.user.is_superuser


class IsSuperuserOrOrgAdminForCompany(BasePermission):
    """Company: read = any authenticated; create/update/delete = superuser OR org admin."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        if request.user.is_superuser:
            return True
        org_id = None
        if view.action == "create" and request.data:
            org_id = request.data.get("org") or request.data.get("org_id")
        if org_id is not None:
            try:
                org = models.Org.objects.get(id=org_id)
                return _user_can_manage_org(request.user, org)
            except (models.Org.DoesNotExist, TypeError, ValueError):
                return False
        return False

    def has_object_permission(self, request, view, obj):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return _user_can_manage_org(request.user, obj.org)


class IsSuperuserOrOrgOrCompanyAdminForEntity(BasePermission):
    """Entity: read = any authenticated; create/update/delete = superuser OR org/company admin."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        if request.user.is_superuser:
            return True
        company_id = None
        if view.action == "create" and request.data:
            company_id = request.data.get("company") or request.data.get("company_id")
        if company_id is not None:
            try:
                company = models.Company.objects.get(id=company_id)
                return _user_can_manage_company(request.user, company)
            except (models.Company.DoesNotExist, TypeError, ValueError):
                return False
        return False

    def has_object_permission(self, request, view, obj):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return _user_can_manage_company(request.user, obj.company)


# ===================== Org / Company / Entity ViewSets =====================

class OrgViewSet(ModelViewSet):
    queryset = models.Org.objects.all()
    serializer_class = serializers.OrgSerializer
    permission_classes = [IsAuthenticated, IsSuperuserForOrg]

    def get_queryset(self):
        qs = super().get_queryset()
        if not self.request.user.is_superuser:
            scope = _get_scope_or_none(self.request)
            if scope:
                org_ids, _, _ = _org_company_entity_ids_for_scope(scope)
                if org_ids is not None:
                    qs = qs.filter(id__in=org_ids)
        org_id = self.request.query_params.get("org_id")
        if org_id:
            qs = qs.filter(id=org_id)
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(code__icontains=search))
        return qs


class CompanyViewSet(ModelViewSet):
    queryset = models.Company.objects.all()
    serializer_class = serializers.CompanySerializer
    permission_classes = [IsAuthenticated, IsSuperuserOrOrgAdminForCompany]

    def get_queryset(self):
        qs = super().get_queryset().select_related("org")
        if not self.request.user.is_superuser:
            scope = _get_scope_or_none(self.request)
            if scope:
                _, company_ids, _ = _org_company_entity_ids_for_scope(scope)
                if company_ids is not None:
                    qs = qs.filter(id__in=company_ids)
                else:
                    org_ids, _, _ = _org_company_entity_ids_for_scope(scope)
                    if org_ids is not None:
                        qs = qs.filter(org_id__in=org_ids)
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
    permission_classes = [IsAuthenticated, IsSuperuserOrOrgOrCompanyAdminForEntity]

    def get_queryset(self):
        qs = super().get_queryset().select_related("company", "company__org")
        if not self.request.user.is_superuser:
            scope = _get_scope_or_none(self.request)
            if scope:
                _, _, entity_ids = _org_company_entity_ids_for_scope(scope)
                if entity_ids is not None:
                    qs = qs.filter(id__in=entity_ids)
                else:
                    _, company_ids, _ = _org_company_entity_ids_for_scope(scope)
                    if company_ids is not None:
                        qs = qs.filter(company_id__in=company_ids)
                    else:
                        org_ids, _, _ = _org_company_entity_ids_for_scope(scope)
                        if org_ids is not None:
                            qs = qs.filter(company__org_id__in=org_ids)
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
            # Show user's scope + all child scopes (org admin sees org+company+entity)
            allowed_scopes = models.TenantScope.get_available_scopes_for_user(user)
            allowed_ids = list(allowed_scopes.values_list("id", flat=True))
            qs = qs.filter(id__in=allowed_ids)

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

# ===================== Permission ViewSet =====================

class PermissionViewSet(ModelViewSet):
    queryset = models.Permission.objects.all()
    serializer_class = serializers.PermissionSerializer
    permission_classes = [IsAuthenticated]


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

        filter_scope_id = self.request.query_params.get("scope_id")
        if filter_scope_id:
            qs = qs.filter(scope_id=filter_scope_id)

        user_id = self.request.query_params.get("user_id")
        if user_id:
            qs = qs.filter(user_id=user_id)

        return qs


# ===================== UserProfile ViewSet =====================

class UserProfileViewSet(ModelViewSet):
    queryset = models.UserProfile.objects.all()
    serializer_class = serializers.UserProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset().select_related("user")

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
            "scope_memberships", "scope_memberships__scope", "scope_memberships__role", "profile"
        )

        if not user.is_superuser:
            scope = get_active_scope(self.request)
            if scope:
                # Only users with ScopeMembership in active scope or its children (org/company/entity admins)
                allowed_scope_ids = list(scope.get_child_scopes().values_list("id", flat=True))
                qs = qs.filter(
                    scope_memberships__scope_id__in=allowed_scope_ids,
                    scope_memberships__is_active=True,
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

        # Optional: filter by scope (narrow within allowed scopes)
        scope_type = self.request.query_params.get("scope_type")
        scope_id = self.request.query_params.get("scope_id")
        if scope_type and scope_id:
            qs = qs.filter(
                scope_memberships__scope__scope_type=scope_type,
                scope_memberships__scope_id=scope_id,
                scope_memberships__is_active=True,
            ).distinct()

        # Optional: filter by org_id (narrow within allowed scopes)
        org_id = self.request.query_params.get("org_id")
        if org_id:
            qs = qs.filter(
                Q(scope_memberships__scope__org_id=org_id) |
                Q(scope_memberships__scope__company__org_id=org_id) |
                Q(scope_memberships__scope__entity__company__org_id=org_id),
                scope_memberships__is_active=True,
            ).distinct()

        # Filter by profile status
        user_status = self.request.query_params.get("status")
        if user_status:
            qs = qs.filter(profile__status__iexact=user_status)

        # Filter by department
        department = self.request.query_params.get("department")
        if department:
            qs = qs.filter(profile__department__iexact=department)

        # Filter by profile role (ADMIN/MANAGER/BROKER/TENANT/VIEWER)
        profile_role = self.request.query_params.get("role")
        if profile_role:
            qs = qs.filter(profile__role__iexact=profile_role)

        return qs

    @action(detail=False, methods=["post"], url_path="bulk-action")
    @transaction.atomic
    def bulk_action(self, request):
        """
        Bulk actions on multiple users.
        Body: { action: "deactivate"|"activate"|"change_role", user_ids: [1,2,3], role_id: 5 }
        """
        action_type = request.data.get("action", "").lower()
        user_ids = request.data.get("user_ids", [])
        if not user_ids or not isinstance(user_ids, list):
            raise ValidationError({"user_ids": "Provide a non-empty list of user IDs."})

        target_users = User.objects.filter(id__in=user_ids)
        count = target_users.count()

        if action_type == "deactivate":
            target_users.update(is_active=False)
            models.UserProfile.objects.filter(user__in=target_users).update(
                status=models.UserProfile.UserStatus.INACTIVE
            )
            for u in target_users:
                models.UserChangeLog.objects.create(
                    user=u, changed_by=request.user,
                    field_changed="status", old_value="", new_value="INACTIVE",
                )
        elif action_type == "activate":
            target_users.update(is_active=True)
            models.UserProfile.objects.filter(user__in=target_users).update(
                status=models.UserProfile.UserStatus.ACTIVE
            )
            for u in target_users:
                models.UserChangeLog.objects.create(
                    user=u, changed_by=request.user,
                    field_changed="status", old_value="", new_value="ACTIVE",
                )
        elif action_type == "change_role":
            role_id = request.data.get("role_id")
            if not role_id:
                raise ValidationError({"role_id": "role_id is required for change_role action."})
            try:
                role_obj = models.Role.objects.get(id=role_id)
            except models.Role.DoesNotExist:
                raise ValidationError({"role_id": "Role not found."})
            active_scope = get_active_scope(request)
            mbrs = models.ScopeMembership.objects.filter(user_id__in=user_ids, is_active=True)
            if active_scope:
                mbrs = mbrs.filter(scope=active_scope)
            mbrs.update(role=role_obj)
            for u in target_users:
                models.UserChangeLog.objects.create(
                    user=u, changed_by=request.user,
                    field_changed="role", old_value="", new_value=role_obj.name,
                )
        else:
            raise ValidationError({"action": f"Unknown action '{action_type}'."})

        return Response({
            "action": action_type,
            "affected_users": count,
            "message": f"Bulk '{action_type}' applied to {count} user(s).",
        })

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Extract fields
        password = data.pop("password", None) or generate_password()
        role = data.pop("role", models.UserProfile.UserRole.MANAGER)
        profile_json = data.pop("profile_json", {})
        scope_id = data.pop("scope_id", None)
        role_id = data.pop("role_id", None)

        # Create user
        user = User(**data)
        user.set_password(password)
        user.save()

        # Create profile
        profile = models.UserProfile.objects.create(
            user=user,
            role=role,
            profile_json=profile_json
        )

        # Create ScopeMembership (Org/Company/Entity admin) if scope_id + role_id provided
        membership = None
        if scope_id and role_id:
            scope = models.TenantScope.objects.get(id=scope_id)
            role_obj = models.Role.objects.get(id=role_id, scope=scope)

            # Validate creator has access to assign users to this scope
            active_scope = get_active_scope(request)
            if active_scope:
                child_scopes = active_scope.get_child_scopes()
                allowed_ids = {s.id for s in child_scopes} | {active_scope.id}
                if scope_id not in allowed_ids:
                    raise ValidationError({
                        "scope_id": f"You can only assign users to your active scope (id={active_scope.id}) or its child scopes."
                    })

            membership = models.ScopeMembership.objects.create(
                user=user,
                scope=scope,
                role=role_obj
            )
            # Sync UserProfile.role from ScopeMembership role (admin/manager/staff/viewer)
            role_code_to_profile = {
                "admin": models.UserProfile.UserRole.ADMIN,
                "manager": models.UserProfile.UserRole.MANAGER,
                "staff": models.UserProfile.UserRole.MANAGER,  # no STAFF in UserRole, use MANAGER
                "viewer": models.UserProfile.UserRole.VIEWER,
            }
            profile.role = role_code_to_profile.get(
                role_obj.code.lower(),
                models.UserProfile.UserRole.MANAGER
            )
            profile.save(update_fields=["role"])

        out = serializers.UserDetailSerializer(user).data
        out["password_plain"] = password
        if membership:
            out["membership_id"] = membership.id

        return Response(out, status=status.HTTP_201_CREATED)

    # ── User management actions ─────────────────────────────────────────────

    @action(detail=False, methods=["post"], url_path="invite")
    @transaction.atomic
    def invite_user(self, request):
        """
        Invite a user by email. Creates user account + sends invite token.
        Body: { email, first_name, last_name, role_id, scope_id, department }
        """
        import secrets as _secrets
        email = request.data.get("email", "").strip().lower()
        if not email:
            raise ValidationError({"email": "Email is required."})
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError({"email": "A user with this email already exists."})

        first_name = request.data.get("first_name", "")
        last_name = request.data.get("last_name", "")
        department = request.data.get("department", "")
        scope_id = request.data.get("scope_id")
        role_id = request.data.get("role_id")

        password = generate_password()
        username = email.split("@")[0] + "_" + _secrets.token_hex(3)
        user = User.objects.create_user(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            password=password,
        )
        invite_token = _secrets.token_urlsafe(32)
        profile = models.UserProfile.objects.create(
            user=user,
            status=models.UserProfile.UserStatus.PENDING,
            department=department,
            invite_token=invite_token,
            invite_accepted=False,
        )
        models.UserChangeLog.objects.create(
            user=user,
            changed_by=request.user,
            field_changed="status",
            old_value="",
            new_value="PENDING",
        )

        membership = None
        if scope_id and role_id:
            try:
                scope = models.TenantScope.objects.get(id=scope_id)
                role_obj = models.Role.objects.get(id=role_id)
                membership = models.ScopeMembership.objects.create(
                    user=user, scope=scope, role=role_obj, created_by=request.user
                )
            except (models.TenantScope.DoesNotExist, models.Role.DoesNotExist) as e:
                raise ValidationError(str(e))

        out = serializers.UserDetailSerializer(user).data
        out["invite_token"] = invite_token
        out["password_plain"] = password
        return Response(out, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="reset-password")
    def reset_password(self, request, pk=None):
        """Admin: generate a new password for a user and return it."""
        target_user = self.get_object()
        new_pass = generate_password()
        target_user.set_password(new_pass)
        target_user.save(update_fields=["password"])
        models.UserChangeLog.objects.create(
            user=target_user,
            changed_by=request.user,
            field_changed="password",
            old_value="",
            new_value="[reset]",
        )
        return Response({"password_plain": new_pass, "message": "Password reset successfully."})

    @action(detail=True, methods=["post"], url_path="revoke-invitation")
    def revoke_invitation(self, request, pk=None):
        """Revoke a pending invite — marks user INACTIVE and clears token."""
        target_user = self.get_object()
        profile = getattr(target_user, "profile", None)
        if not profile:
            raise ValidationError("User has no profile.")
        if profile.status != models.UserProfile.UserStatus.PENDING:
            raise ValidationError("User is not in PENDING state.")
        profile.status = models.UserProfile.UserStatus.INACTIVE
        profile.invite_token = ""
        profile.save(update_fields=["status", "invite_token"])
        target_user.is_active = False
        target_user.save(update_fields=["is_active"])
        models.UserChangeLog.objects.create(
            user=target_user,
            changed_by=request.user,
            field_changed="status",
            old_value="PENDING",
            new_value="INACTIVE",
        )
        return Response({"message": "Invitation revoked."})

    @action(detail=True, methods=["post"], url_path="set-status")
    def set_status(self, request, pk=None):
        """Set user status: ACTIVE / INACTIVE / SUSPENDED."""
        target_user = self.get_object()
        new_status = request.data.get("status", "").upper()
        valid = [c[0] for c in models.UserProfile.UserStatus.choices]
        if new_status not in valid:
            raise ValidationError({"status": f"Must be one of {valid}."})
        profile, _ = models.UserProfile.objects.get_or_create(user=target_user)
        old_status = profile.status
        profile.status = new_status
        profile.save(update_fields=["status"])
        target_user.is_active = (new_status == models.UserProfile.UserStatus.ACTIVE)
        target_user.save(update_fields=["is_active"])
        models.UserChangeLog.objects.create(
            user=target_user,
            changed_by=request.user,
            field_changed="status",
            old_value=old_status,
            new_value=new_status,
        )
        return Response({"status": new_status, "message": f"User status set to {new_status}."})

    @action(detail=True, methods=["get"], url_path="change-log")
    def change_log(self, request, pk=None):
        """Return audit log for this user."""
        target_user = self.get_object()
        logs = models.UserChangeLog.objects.filter(user=target_user).order_by("-changed_at")[:50]
        return Response(serializers.UserChangeLogSerializer(logs, many=True).data)


# ===================== Role ViewSet — enhanced =====================

class RoleViewSet(ScopedViewSet):
    queryset = models.Role.objects.all()
    serializer_class = serializers.RoleSerializer

    def get_serializer_class(self):
        if self.action == "list":
            return serializers.RoleListSerializer
        if self.action in ("create", "update", "partial_update"):
            return serializers.RoleWriteSerializer
        return serializers.RoleSerializer

    def get_queryset(self):
        qs = super().get_queryset().select_related("scope", "base_on").prefetch_related(
            "module_permissions", "role_permissions__permission"
        )
        scope_id = self.request.query_params.get("scope_id")
        if scope_id:
            try:
                return models.Role.objects.filter(scope_id=int(scope_id)).order_by("code")
            except ValueError:
                pass
        role_type = self.request.query_params.get("role_type")
        if role_type:
            qs = qs.filter(role_type=role_type)
        role_status = self.request.query_params.get("status")
        if role_status:
            qs = qs.filter(status=role_status)
        return qs

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        """Publish a DRAFT role (make it active/assignable)."""
        role = self.get_object()
        if role.status == models.Role.RoleStatus.PUBLISHED:
            return Response({"detail": "Role is already published."}, status=status.HTTP_400_BAD_REQUEST)
        role.publish()
        return Response(serializers.RoleSerializer(role, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def duplicate(self, request, pk=None):
        """Clone this role as a new DRAFT."""
        original = self.get_object()
        new_role = models.Role.objects.create(
            scope=original.scope,
            name=f"{original.name} (Copy)",
            code=f"{original.code}-copy-{secrets.token_hex(2)}",
            description=original.description,
            role_type=original.role_type,
            status=models.Role.RoleStatus.DRAFT,
            base_on=original,
            approval_cap_amount=original.approval_cap_amount,
            can_approve_amendments=original.can_approve_amendments,
            can_approve_waivers=original.can_approve_waivers,
            can_modify_matrices=original.can_modify_matrices,
            data_scope_type=original.data_scope_type,
            data_scope_property_ids=original.data_scope_property_ids,
            created_by=request.user,
        )
        for mp in original.module_permissions.all():
            models.ModulePermission.objects.create(
                role=new_role,
                module=mp.module,
                can_view=mp.can_view,
                can_create=mp.can_create,
                can_edit=mp.can_edit,
                can_delete=mp.can_delete,
                can_approve=mp.can_approve,
            )
        return Response(serializers.RoleSerializer(new_role, context={"request": request}).data,
                        status=status.HTTP_201_CREATED)


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
