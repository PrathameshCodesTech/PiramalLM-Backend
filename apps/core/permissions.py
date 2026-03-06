from rest_framework.permissions import BasePermission, SAFE_METHODS


class RBACPermission(BasePermission):
    """
    Module-level RBAC permission class for ScopedViewSets.

    Usage — set `rbac_module` on the ViewSet:

        class AgreementViewSet(ScopedViewSet):
            rbac_module = "LEASE"

    If `rbac_module` is not set the check is skipped (backwards compatible).
    Superusers and Admin-role members are always allowed.

    HTTP method → ModulePermission flag mapping:
        GET/HEAD/OPTIONS  → can_view
        POST              → can_create
        PATCH/PUT         → can_edit
        DELETE            → can_delete
    """

    message = "You do not have permission to perform this action in the current module."

    def _get_required_flag(self, method):
        if method in SAFE_METHODS:
            return "can_view"
        if method == "POST":
            return "can_create"
        if method in ("PATCH", "PUT"):
            return "can_edit"
        if method == "DELETE":
            return "can_delete"
        return "can_view"

    def has_permission(self, request, view):
        # Module not configured → skip (backwards compatible)
        rbac_module = getattr(view, "rbac_module", None)
        if not rbac_module:
            return True

        user = request.user
        if not user or not user.is_authenticated:
            return False

        # Superuser → always allow
        if user.is_superuser:
            return True

        # Resolve active scope from header
        scope_id = request.headers.get("X-Scope-ID")
        if not scope_id:
            # No scope → no RBAC context, deny for scoped modules
            return False

        try:
            from apps.accounts.models import ScopeMembership, ModulePermission

            membership = (
                ScopeMembership.objects.filter(
                    user=user,
                    scope_id=scope_id,
                    is_active=True,
                )
                .select_related("role")
                .prefetch_related("role__module_permissions")
                .first()
            )

            if not membership or not membership.role:
                return False

            role = membership.role

            # Admin role type → always allow
            if role.role_type == role.RoleType.ADMIN:
                return True

            required_flag = self._get_required_flag(request.method)

            mp = membership.role.module_permissions.filter(
                module=rbac_module,
                is_active=True,
            ).first()

            if not mp:
                return False

            return bool(getattr(mp, required_flag, False))

        except Exception:
            # Never block on internal errors — fail open to avoid locking out users
            return True
