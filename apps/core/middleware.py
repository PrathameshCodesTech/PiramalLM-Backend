"""
Middleware to add request-context summary to API responses.
Adds headers: X-Request-User-Id, X-Request-Scope-Id, X-Request-Role, X-Request-Permissions
so clients can see who made the request and with what scope/role/access.
"""

from apps.core.utils import get_active_scope


class RequestContextResponseMiddleware:
    """
    Add request-context summary to response headers for authenticated API requests.
    Only runs for /api/ paths. Does not raise; on any error, headers are simply omitted.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not request.path.startswith("/api/"):
            return response

        try:
            if not getattr(request, "user", None) or not request.user.is_authenticated:
                return response
            scope = get_active_scope(request)
        except Exception:
            return response

        if not scope:
            return response

        # Resolve role from ScopeMembership for this user in this scope
        try:
            from apps.accounts.models import ScopeMembership

            membership = (
                ScopeMembership.objects.filter(
                    user=request.user,
                    scope=scope,
                    is_active=True,
                )
                .select_related("role")
                .first()
            )
            role_code = membership.role.code if membership and membership.role else None
            role_id = membership.role_id if membership else None
        except Exception:
            role_code = None
            role_id = None

        # Resolve permission codes from role
        permission_codes = []
        if role_id:
            try:
                from apps.accounts.models import RolePermission

                permission_codes = list(
                    RolePermission.objects.filter(role_id=role_id).values_list(
                        "permission__code", flat=True
                    )
                )
                permission_codes = [c for c in permission_codes if c]
            except Exception:
                pass

        # Add headers (avoid overwriting existing)
        if "X-Request-User-Id" not in response:
            response["X-Request-User-Id"] = str(request.user.id)
        if "X-Request-Scope-Id" not in response:
            response["X-Request-Scope-Id"] = str(scope.id)
        if "X-Request-Scope-Name" not in response:
            response["X-Request-Scope-Name"] = str(scope.name or "")
        if "X-Request-Scope-Type" not in response:
            response["X-Request-Scope-Type"] = str(scope.scope_type or "")
        if role_code and "X-Request-Role" not in response:
            response["X-Request-Role"] = str(role_code)
        if permission_codes and "X-Request-Permissions" not in response:
            response["X-Request-Permissions"] = ",".join(permission_codes)

        return response
