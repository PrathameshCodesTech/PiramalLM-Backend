"""
Org Tree API - Aggregated endpoint for fetching complete org hierarchy.

GET /api/v1/accounts/org-tree/

Returns the organization structure based on X-Scope-ID boundary:
- Superuser without X-Scope-ID: All orgs
- Superuser with X-Scope-ID: Org tree within that boundary
- Regular user: Must pass X-Scope-ID, returns tree within boundary
"""

from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts import models
from apps.accounts.views import validate_scope_header


# =============================================================================
# NESTED SERIALIZERS (for read-only org tree response)
# =============================================================================

class EntityNestedSerializer(serializers.ModelSerializer):
    """Entity with scope info."""
    scope_id = serializers.SerializerMethodField()

    class Meta:
        model = models.Entity
        fields = (
            "id", "name", "code",
            "scope_id", "is_active"
        )

    def get_scope_id(self, obj):
        scope = models.TenantScope.objects.filter(entity=obj, is_active=True).first()
        return scope.id if scope else None


class CompanyNestedSerializer(serializers.ModelSerializer):
    """Company with its entities."""
    entities = EntityNestedSerializer(many=True, read_only=True)
    scope_id = serializers.SerializerMethodField()
    entities_count = serializers.SerializerMethodField()

    class Meta:
        model = models.Company
        fields = (
            "id", "name", "code",
            "scope_id", "is_active",
            "entities_count", "entities"
        )

    def get_scope_id(self, obj):
        scope = models.TenantScope.objects.filter(company=obj, is_active=True).first()
        return scope.id if scope else None

    def get_entities_count(self, obj):
        return obj.entities.filter(is_active=True).count()


class OrgTreeSerializer(serializers.ModelSerializer):
    """
    Org with all nested companies and entities.
    """
    companies = CompanyNestedSerializer(many=True, read_only=True)
    scope_id = serializers.SerializerMethodField()
    companies_count = serializers.SerializerMethodField()

    class Meta:
        model = models.Org
        fields = (
            "id", "name", "code",
            "scope_id", "is_active",
            "companies_count", "companies"
        )

    def get_scope_id(self, obj):
        scope = models.TenantScope.objects.filter(org=obj, is_active=True).first()
        return scope.id if scope else None

    def get_companies_count(self, obj):
        return obj.companies.filter(is_active=True).count()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_boundary_org_tree(scope):
    """
    Get org tree data based on scope boundary.

    Returns: (org, company_ids, entity_ids) tuple
    - org: The parent Org object
    - company_ids: Set of Company IDs to include (None = all)
    - entity_ids: Set of Entity IDs to include (None = all)
    """
    if scope is None:
        return None, None, None

    if scope.scope_type == models.TenantScope.ScopeType.ORG and scope.org:
        # Org scope - show full org tree
        return scope.org, None, None

    elif scope.scope_type == models.TenantScope.ScopeType.COMPANY and scope.company:
        # Company scope - show parent org with only this company
        org = scope.company.org
        company_ids = {scope.company.id}
        return org, company_ids, None

    elif scope.scope_type == models.TenantScope.ScopeType.ENTITY and scope.entity:
        # Entity scope - show parent org/company with only this entity
        org = scope.entity.company.org
        company_ids = {scope.entity.company.id}
        entity_ids = {scope.entity.id}
        return org, company_ids, entity_ids

    elif scope.scope_type == models.TenantScope.ScopeType.SITE and scope.site:
        # Site scope - sites are under entities, find parent
        # For now, return None - sites don't have org hierarchy
        return None, None, None

    return None, None, None


def build_filtered_org_data(org, company_ids=None, entity_ids=None):
    """
    Build org tree data with optional filtering by company/entity IDs.
    """
    org_scope = models.TenantScope.objects.filter(org=org, is_active=True).first()

    companies_data = []
    companies = org.companies.filter(is_active=True)

    if company_ids is not None:
        companies = companies.filter(id__in=company_ids)

    for company in companies:
        company_scope = models.TenantScope.objects.filter(company=company, is_active=True).first()

        entities_data = []
        entities = company.entities.filter(is_active=True)

        if entity_ids is not None:
            entities = entities.filter(id__in=entity_ids)

        for entity in entities:
            entity_scope = models.TenantScope.objects.filter(entity=entity, is_active=True).first()
            entities_data.append({
                "id": entity.id,
                "name": entity.name,
                "code": entity.code,
                "scope_id": entity_scope.id if entity_scope else None,
                "is_active": entity.is_active,
            })

        companies_data.append({
            "id": company.id,
            "name": company.name,
            "code": company.code,
            "scope_id": company_scope.id if company_scope else None,
            "is_active": company.is_active,
            "entities_count": len(entities_data),
            "entities": entities_data,
        })

    return {
        "id": org.id,
        "name": org.name,
        "code": org.code,
        "scope_id": org_scope.id if org_scope else None,
        "is_active": org.is_active,
        "companies_count": len(companies_data),
        "companies": companies_data,
    }


# =============================================================================
# ORG TREE ENDPOINTS
# =============================================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def org_tree_list(request):
    """
    GET /api/v1/accounts/org-tree/

    Returns organization hierarchy based on X-Scope-ID boundary.

    Headers:
    - X-Scope-ID: Required for non-superusers. Returns tree within that scope boundary.

    Superuser without X-Scope-ID: Returns all orgs.
    Regular user without X-Scope-ID: 403 error.

    Response:
    {
        "orgs": [...],
        "active_scope": {"id": 1, "name": "...", "scope_type": "ORG"},
        "summary": {"total_orgs": 1, "total_companies": 2, "total_entities": 3}
    }
    """
    # Validate scope header
    active_scope, _ = validate_scope_header(request)

    if active_scope is None:
        # Superuser without header - all orgs
        orgs = models.Org.objects.filter(is_active=True).prefetch_related(
            "companies__entities"
        )
        org_data = OrgTreeSerializer(orgs, many=True).data

        # Build summary
        total_companies = 0
        total_entities = 0
        for org in orgs:
            companies = org.companies.filter(is_active=True)
            total_companies += companies.count()
            for company in companies:
                total_entities += company.entities.filter(is_active=True).count()

        return Response({
            "orgs": org_data,
            "active_scope": None,
            "summary": {
                "total_orgs": orgs.count(),
                "total_companies": total_companies,
                "total_entities": total_entities,
            }
        })

    # Get boundary-filtered org tree
    org, company_ids, entity_ids = get_boundary_org_tree(active_scope)

    if org is None:
        return Response({
            "orgs": [],
            "active_scope": {
                "id": active_scope.id,
                "name": active_scope.name,
                "scope_type": active_scope.scope_type,
            },
            "summary": {
                "total_orgs": 0,
                "total_companies": 0,
                "total_entities": 0,
            }
        })

    # Build filtered org data
    org_data = build_filtered_org_data(org, company_ids, entity_ids)

    # Count for summary
    total_companies = org_data["companies_count"]
    total_entities = sum(c["entities_count"] for c in org_data["companies"])

    return Response({
        "orgs": [org_data],
        "active_scope": {
            "id": active_scope.id,
            "name": active_scope.name,
            "scope_type": active_scope.scope_type,
        },
        "summary": {
            "total_orgs": 1,
            "total_companies": total_companies,
            "total_entities": total_entities,
        }
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def org_tree_detail(request, org_id):
    """
    GET /api/v1/accounts/org-tree/{org_id}/

    Returns a single organization with hierarchy, filtered by X-Scope-ID boundary.

    Headers:
    - X-Scope-ID: Required for non-superusers.

    Response:
    {
        "id": 1,
        "name": "ABC Group",
        "companies": [...],
        "active_scope": {...},
        "summary": {"companies_count": 2, "entities_count": 3}
    }
    """
    # Validate scope header
    active_scope, _ = validate_scope_header(request)

    # Get the org
    try:
        org = models.Org.objects.prefetch_related(
            "companies__entities"
        ).get(id=org_id, is_active=True)
    except models.Org.DoesNotExist:
        raise NotFound(f"Organization with id {org_id} not found.")

    if active_scope is None:
        # Superuser without header - full org tree
        org_data = OrgTreeSerializer(org).data
        companies = org.companies.filter(is_active=True)
        entities_count = sum(c.entities.filter(is_active=True).count() for c in companies)

        org_data["active_scope"] = None
        org_data["summary"] = {
            "companies_count": companies.count(),
            "entities_count": entities_count,
        }
        return Response(org_data)

    # Get boundary
    boundary_org, company_ids, entity_ids = get_boundary_org_tree(active_scope)

    # Validate org_id is within boundary
    if boundary_org is None or boundary_org.id != org_id:
        raise PermissionDenied(
            f"Organization id {org_id} is not within your scope boundary. "
            f"Your active scope is '{active_scope.name}' (id={active_scope.id})."
        )

    # Build filtered org data
    org_data = build_filtered_org_data(org, company_ids, entity_ids)

    org_data["active_scope"] = {
        "id": active_scope.id,
        "name": active_scope.name,
        "scope_type": active_scope.scope_type,
    }
    org_data["summary"] = {
        "companies_count": org_data["companies_count"],
        "entities_count": sum(c["entities_count"] for c in org_data["companies"]),
    }

    return Response(org_data)
