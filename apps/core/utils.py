from rest_framework.exceptions import PermissionDenied

from apps.accounts.models import ScopeMembership, TenantScope


def get_active_scope(request):
    """
    Resolve the permission context (active scope) for the request.
    Requires X-Scope-ID header with a scope id the user has access to.
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        raise PermissionDenied(
            "Authentication required. Provide a valid Bearer token."
        )

    header_scope_id = request.headers.get("X-Scope-ID")
    if header_scope_id:
        try:
            scope = TenantScope.objects.get(id=header_scope_id, is_active=True)
        except TenantScope.DoesNotExist:
            raise PermissionDenied(
                f"X-Scope-ID: Scope with id '{header_scope_id}' does not exist or is inactive. "
                "Check that the scope exists and pass a valid scope id in the X-Scope-ID header."
            )
        if user.is_superuser:
            return scope
        if not ScopeMembership.objects.filter(
            user=user,
            scope=scope,
            is_active=True,
        ).exists():
            raise PermissionDenied(
                f"X-Scope-ID: You are not a member of scope '{scope.name}' (id={scope.id}). "
                "You can only perform actions in scopes where you have membership. "
                "Pass a scope id in X-Scope-ID that you belong to, or contact admin to be added to this scope."
            )
        return scope

    raise PermissionDenied(
        "No permission context (scope) set. Send the X-Scope-ID header with a scope id you have access to."
    )
