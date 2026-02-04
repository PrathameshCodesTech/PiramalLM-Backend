from django.core.exceptions import PermissionDenied

from apps.accounts.models import ScopeMembership, TenantScope


def get_active_scope(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        raise PermissionDenied("Authentication required.")

    header_scope_id = request.headers.get("X-Scope-ID")
    if header_scope_id:
        try:
            scope = TenantScope.objects.get(id=header_scope_id, is_active=True)
        except TenantScope.DoesNotExist:
            raise PermissionDenied("Invalid scope.")
        if user.is_superuser:
            return scope
        if not ScopeMembership.objects.filter(
            user=user,
            scope=scope,
            is_active=True,
        ).exists():
            raise PermissionDenied("Not a member of requested scope.")
        return scope

    profile = getattr(user, "profile", None)
    if profile and profile.active_scope_id:
        return profile.active_scope

    raise PermissionDenied("Active scope is not set.")
