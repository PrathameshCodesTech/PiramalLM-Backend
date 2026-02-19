from django.db.models import Q
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from apps.core.utils import get_active_scope


class ScopedViewSet(ModelViewSet):
    """
    Base ViewSet for models that have a scope FK.
    Provides hierarchy-aware filtering and scope assignment.

    Features:
    - get_queryset(): Returns objects in user's scope + all child scopes
    - perform_create(): Uses X-Scope-ID header for scope assignment
    - Supports explicit scope in payload (for scope picker)
    """

    permission_classes = [IsAuthenticated]

    # Set to True to enable hierarchy-aware filtering (ORG sees COMPANY/ENTITY data)
    # Set to False for exact scope matching only
    hierarchy_aware = True

    def get_active_scope(self):
        return get_active_scope(self.request)

    def get_scope_filter(self, scope):
        """
        Build Q filter for hierarchy-aware scope filtering.
        ORG scope → sees all COMPANY and ENTITY scopes under it
        COMPANY scope → sees all ENTITY scopes under it
        ENTITY scope → sees only that entity
        """
        from apps.accounts.models import TenantScope, Company, Entity

        if not self.hierarchy_aware:
            # Exact scope match only
            return Q(scope=scope)

        if scope.scope_type == TenantScope.ScopeType.ORG and scope.org:
            # ORG sees: ORG scope + all COMPANY scopes + all ENTITY scopes under those
            company_ids = list(Company.objects.filter(org=scope.org).values_list("id", flat=True))
            entity_ids = list(Entity.objects.filter(company_id__in=company_ids).values_list("id", flat=True))

            return (
                Q(scope=scope) |  # ORG scope itself
                Q(scope__company_id__in=company_ids) |  # COMPANY scopes
                Q(scope__entity_id__in=entity_ids)  # ENTITY scopes
            )

        elif scope.scope_type == TenantScope.ScopeType.COMPANY and scope.company:
            # COMPANY sees: COMPANY scope + all ENTITY scopes under it
            entity_ids = list(Entity.objects.filter(company=scope.company).values_list("id", flat=True))

            return (
                Q(scope=scope) |  # COMPANY scope itself
                Q(scope__entity_id__in=entity_ids)  # ENTITY scopes
            )

        elif scope.scope_type == TenantScope.ScopeType.ENTITY and scope.entity:
            # ENTITY sees: only itself
            return Q(scope=scope)

        elif scope.scope_type == TenantScope.ScopeType.SITE and scope.site:
            # SITE sees: only itself
            return Q(scope=scope)

        # Fallback: exact scope match
        return Q(scope=scope)

    def get_queryset(self):
        """
        Filter queryset by user's scope with hierarchy awareness.
        When hierarchy_aware=True, uses get_scope_filter so Org/Company users
        see data from child scopes (Entity, Site). When hierarchy_aware=False,
        uses exact scope match via for_scope if available.
        Superusers without X-Scope-ID (scope=None) see all records.
        """
        queryset = super().get_queryset()
        scope = self.get_active_scope()

        # Superuser without X-Scope-ID → full unscoped access
        if scope is None:
            return queryset

        # Exact scope only (e.g. ExactScopedViewSet): use for_scope if available
        if not self.hierarchy_aware and hasattr(queryset, "for_scope"):
            return queryset.for_scope(scope)

        # Hierarchy-aware: apply scope filter so parent scopes see child data
        scope_filter = self.get_scope_filter(scope)
        return queryset.filter(scope_filter).distinct()

    def validate_scope_access(self, target_scope):
        """
        Validate that user has permission to create/modify in target scope.
        User can only create in their scope or child scopes.
        Superusers (scope=None) can write to any scope.
        """
        from apps.accounts.models import TenantScope

        active_scope = self.get_active_scope()

        # Superuser without X-Scope-ID → allow write to any scope
        if active_scope is None:
            return True

        # Same scope - always allowed
        if target_scope.id == active_scope.id:
            return True

        # Get all child scopes of active scope
        child_scopes = active_scope.get_child_scopes()
        if target_scope in child_scopes:
            return True

        raise PermissionDenied(
            f"Cannot create or modify in scope '{target_scope.name}' (id={target_scope.id}). "
            f"Your permission context (X-Scope-ID) is scope '{active_scope.name}' (id={active_scope.id}). "
            "You can only create or modify in your current scope or its child scopes. "
            "Use a target scope that is under your active scope, or set X-Scope-ID to a scope that includes the target."
        )

    def perform_create(self, serializer):
        """
        Create with scope assignment.
        - If 'scope' is in payload, use that (after validation)
        - Otherwise, use X-Scope-ID header
        """
        from apps.accounts.models import TenantScope

        # Check if scope is explicitly provided in request data
        scope_id = self.request.data.get("scope")

        if scope_id:
            # Explicit scope provided - validate access
            try:
                target_scope = TenantScope.objects.get(id=scope_id, is_active=True)
            except TenantScope.DoesNotExist:
                raise ValidationError({
                    "scope": f"Scope with id '{scope_id}' does not exist or is inactive. "
                    "Create the scope first or use a valid scope id."
                })

            self.validate_scope_access(target_scope)
            serializer.save(scope=target_scope)
        else:
            # Use header scope
            scope = self.get_active_scope()
            if scope is None:
                raise ValidationError({
                    "scope": "Scope is required. Provide 'scope' in the request body or set X-Scope-ID header."
                })
            serializer.save(scope=scope)

    def perform_update(self, serializer):
        """
        Update with scope validation.
        - If changing scope, validate new scope access
        - Otherwise, keep existing scope
        """
        from apps.accounts.models import TenantScope

        instance = serializer.instance
        scope_id = self.request.data.get("scope")

        if scope_id and scope_id != instance.scope_id:
            # Changing scope - validate access
            try:
                target_scope = TenantScope.objects.get(id=scope_id, is_active=True)
            except TenantScope.DoesNotExist:
                raise ValidationError({
                    "scope": f"Scope with id '{scope_id}' does not exist or is inactive."
                })

            self.validate_scope_access(target_scope)
            serializer.save(scope=target_scope)
        else:
            # Keep existing scope
            serializer.save()


class ExactScopedViewSet(ScopedViewSet):
    """
    ViewSet with exact scope matching (no hierarchy traversal).
    Use this when you want data isolated to the exact scope level.
    """
    hierarchy_aware = False


class InheritableScopedViewSet(ScopedViewSet):
    """
    ViewSet for inheritable/config models that cascade down the hierarchy.

    Use this for master data like BillingRule, ClauseTemplate, AgeingBucket, etc.
    that are created at higher scopes (ORG/COMPANY) and inherited by child scopes.

    Query behavior (UPWARD visibility):
    - ENTITY scope → sees ENTITY + COMPANY + ORG configs
    - COMPANY scope → sees COMPANY + ORG configs
    - ORG scope → sees ORG configs only

    Create/Update behavior:
    - Users can only create/modify in their active scope or child scopes
    - Inherited configs from parent scopes are read-only
    """

    def get_ancestor_scope_ids(self, scope):
        """
        Get list of ancestor scope IDs (including current scope).
        Returns [current_scope_id, parent_scope_id, grandparent_scope_id, ...]
        """
        from apps.accounts.models import TenantScope

        scope_ids = [scope.id]

        if scope.scope_type == TenantScope.ScopeType.SITE and scope.site:
            # SITE → ENTITY → COMPANY → ORG
            entity = scope.site.entity
            if entity:
                entity_scope = TenantScope.objects.filter(entity=entity, is_active=True).first()
                if entity_scope:
                    scope_ids.append(entity_scope.id)
                company = entity.company
                if company:
                    company_scope = TenantScope.objects.filter(company=company, is_active=True).first()
                    if company_scope:
                        scope_ids.append(company_scope.id)
                    org = company.org
                    if org:
                        org_scope = TenantScope.objects.filter(org=org, is_active=True).first()
                        if org_scope:
                            scope_ids.append(org_scope.id)

        elif scope.scope_type == TenantScope.ScopeType.ENTITY and scope.entity:
            # ENTITY → COMPANY → ORG
            company = scope.entity.company
            if company:
                company_scope = TenantScope.objects.filter(company=company, is_active=True).first()
                if company_scope:
                    scope_ids.append(company_scope.id)
                org = company.org
                if org:
                    org_scope = TenantScope.objects.filter(org=org, is_active=True).first()
                    if org_scope:
                        scope_ids.append(org_scope.id)

        elif scope.scope_type == TenantScope.ScopeType.COMPANY and scope.company:
            # COMPANY → ORG
            org = scope.company.org
            if org:
                org_scope = TenantScope.objects.filter(org=org, is_active=True).first()
                if org_scope:
                    scope_ids.append(org_scope.id)

        # ORG scope has no ancestors
        return scope_ids

    def get_inheritable_scope_filter(self, scope):
        """
        Build Q filter for upward (inheritable) scope filtering.
        Returns configs from current scope + all ancestor scopes.
        """
        ancestor_ids = self.get_ancestor_scope_ids(scope)
        return Q(scope_id__in=ancestor_ids)

    def get_queryset(self):
        """
        Filter queryset to include configs from current scope AND ancestor scopes.
        This allows child scopes to see/use parent configs.
        """
        queryset = super(ScopedViewSet, self).get_queryset()  # Skip ScopedViewSet.get_queryset
        scope = self.get_active_scope()

        scope_filter = self.get_inheritable_scope_filter(scope)
        return queryset.filter(scope_filter).distinct()
