from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.exceptions import ValidationError as DRFValidationError, PermissionDenied
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.utils import timezone

from apps.core.viewsets import ScopedViewSet, InheritableScopedViewSet
from . import models, serializers
from .pricing_engine import calculate_buffer_summary, resolve_base_rent_monthly


# =============================================================================
# ESCALATION TEMPLATE VIEWSET (Master Data)
# =============================================================================

class EscalationTemplateViewSet(InheritableScopedViewSet):
    """
    ViewSet for escalation templates.

    Uses InheritableScopedViewSet for upward visibility:
    - Child scopes see templates from parent scopes

    Endpoints:
    - GET /escalation-templates/ - List all templates (includes inherited from parent scopes)
    - POST /escalation-templates/ - Create template
    - GET /escalation-templates/{id}/ - Get template details
    - PATCH /escalation-templates/{id}/ - Update template
    - DELETE /escalation-templates/{id}/ - Delete template
    - POST /escalation-templates/{id}/activate/ - Activate template
    - POST /escalation-templates/{id}/archive/ - Archive template
    - POST /escalation-templates/{id}/clone/ - Clone template
    """

    queryset = models.EscalationTemplate.objects.all()
    serializer_class = serializers.EscalationTemplateSerializer

    def get_serializer_class(self):
        if self.action == "list":
            return serializers.EscalationTemplateListSerializer
        if self.action == "retrieve":
            return serializers.EscalationTemplateDetailSerializer
        return serializers.EscalationTemplateSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by escalation type
        escalation_type = self.request.query_params.get("escalation_type")
        if escalation_type:
            queryset = queryset.filter(escalation_type=escalation_type)

        # Filter by status
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Filter by applicability
        applicability = self.request.query_params.get("applicability")
        if applicability:
            queryset = queryset.filter(applicability=applicability)

        # Search by name
        search = self.request.query_params.get("q")
        if search:
            queryset = queryset.filter(name__icontains=search)

        return queryset

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        serializer.save(scope=scope, created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        """Activate a template."""
        from rest_framework.decorators import action
        template = self.get_object()
        template.status = models.EscalationTemplate.TemplateStatus.ACTIVE
        template.updated_by = request.user
        template.save()
        return Response(serializers.EscalationTemplateSerializer(template).data)

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        """Archive a template."""
        template = self.get_object()
        template.status = models.EscalationTemplate.TemplateStatus.ARCHIVED
        template.updated_by = request.user
        template.save()
        return Response(serializers.EscalationTemplateSerializer(template).data)

    @action(detail=True, methods=["post"])
    def clone(self, request, pk=None):
        """Clone a template."""
        from rest_framework import status
        original = self.get_object()
        scope = self.get_active_scope()

        # Create copy
        cloned = models.EscalationTemplate.objects.create(
            scope=scope,
            name=f"{original.name} (Copy)",
            description=original.description,
            applicability=original.applicability,
            escalation_type=original.escalation_type,
            escalation_percentage=original.escalation_percentage,
            index_name=original.index_name,
            index_base_value=original.index_base_value,
            step_schedule=original.step_schedule,
            frequency=original.frequency,
            first_escalation_logic=original.first_escalation_logic,
            first_escalation_months=original.first_escalation_months,
            rounding_rule=original.rounding_rule,
            cap_percentage=original.cap_percentage,
            floor_percentage=original.floor_percentage,
            apply_to_cam=original.apply_to_cam,
            apply_to_parking=original.apply_to_parking,
            status=models.EscalationTemplate.TemplateStatus.DRAFT,
            created_by=request.user
        )

        return Response(
            serializers.EscalationTemplateSerializer(cloned).data,
            status=status.HTTP_201_CREATED
        )


# =============================================================================
# AGREEMENT STRUCTURE VIEWSETS
# =============================================================================

class AgreementStructureViewSet(InheritableScopedViewSet):
    """
    ViewSet for agreement structures (document section templates).

    Endpoints:
    - GET /agreement-structures/ - List all structures
    - POST /agreement-structures/ - Create structure
    - GET /agreement-structures/{id}/ - Get structure with sections
    - PATCH /agreement-structures/{id}/ - Update structure
    - DELETE /agreement-structures/{id}/ - Delete structure
    - GET /agreement-structures/tree/ - Get structures with section tree
    """

    queryset = models.AgreementStructure.objects.all()
    serializer_class = serializers.AgreementStructureSerializer

    def get_serializer_class(self):
        if self.action == "list":
            return serializers.AgreementStructureListSerializer
        if self.action == "retrieve":
            return serializers.AgreementStructureDetailSerializer
        return serializers.AgreementStructureSerializer

    def _get_scope_for_list(self):
        """Resolve scope for list filtering: X-Scope-ID header or optional scope_id query param."""
        from apps.accounts.models import ScopeMembership, TenantScope

        scope_id_param = self.request.query_params.get("scope_id")
        if scope_id_param:
            try:
                scope = TenantScope.objects.get(id=scope_id_param, is_active=True)
            except (TenantScope.DoesNotExist, ValueError):
                return None
            user = self.request.user
            if user.is_superuser:
                return scope
            # User must have access to this scope or one of its descendants
            allowed_scope_ids = [scope.id] + list(
                scope.get_child_scopes().values_list("id", flat=True)
            )
            if ScopeMembership.objects.filter(
                user=user, scope_id__in=allowed_scope_ids, is_active=True
            ).exists():
                return scope
            return None
        return self.get_active_scope()

    def get_queryset(self):
        queryset = super(ScopedViewSet, self).get_queryset()
        scope = self._get_scope_for_list()

        if scope is None and not self.request.user.is_superuser:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied(
                "Set X-Scope-ID header or a valid scope_id query param you have access to."
            )

        if scope is None:
            # Superuser without scope: full access
            queryset = queryset
        else:
            scope_filter = self.get_inheritable_scope_filter(scope)
            queryset = queryset.filter(scope_filter).distinct()

        search = self.request.query_params.get("q")
        if search:
            queryset = queryset.filter(name__icontains=search)
        return queryset.prefetch_related("sections")

    def perform_create(self, serializer):
        from rest_framework.exceptions import ValidationError as DRFValidationError
        scope = self.get_active_scope()
        if scope is None:
            raise DRFValidationError({
                "scope": "X-Scope-ID header is required to create an agreement structure. Set the scope header and try again."
            })
        instance = serializer.save(scope=scope, created_by=self.request.user)
        if instance.is_default:
            models.AgreementStructure.objects.filter(
                scope=scope
            ).exclude(pk=instance.pk).update(is_default=False)

    def perform_update(self, serializer):
        instance = serializer.save(updated_by=self.request.user)
        if instance.is_default:
            models.AgreementStructure.objects.filter(
                scope=instance.scope
            ).exclude(pk=instance.pk).update(is_default=False)

    @action(detail=False, methods=["get"])
    def tree(self, request):
        """List structures with full section tree."""
        queryset = self.get_queryset()
        serializer = serializers.AgreementStructureDetailSerializer(queryset, many=True)
        return Response(serializer.data)


class AgreementSectionViewSet(InheritableScopedViewSet):
    """
    ViewSet for agreement sections within a structure.

    Endpoints:
    - GET /agreement-sections/ - List sections (filter by structure)
    - POST /agreement-sections/ - Create section
    - GET /agreement-sections/{id}/ - Get section details
    - PATCH /agreement-sections/{id}/ - Update section
    - DELETE /agreement-sections/{id}/ - Delete section
    """

    queryset = models.AgreementSection.objects.all()
    serializer_class = serializers.AgreementSectionSerializer

    def get_serializer_class(self):
        if self.action == "list":
            return serializers.AgreementSectionListSerializer
        if self.action == "tree":
            return serializers.AgreementSectionTreeSerializer
        return serializers.AgreementSectionSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        structure_id = self.request.query_params.get("structure")
        if structure_id:
            queryset = queryset.filter(structure_id=structure_id)
        parent_id = self.request.query_params.get("parent_id")
        if parent_id:
            if parent_id in ("null", "root", ""):
                queryset = queryset.filter(parent__isnull=True)
            else:
                queryset = queryset.filter(parent_id=parent_id)
        return queryset.select_related("structure", "parent")

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        serializer.save(scope=scope, created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=False, methods=["get"])
    def tree(self, request):
        """Get section tree for a structure."""
        structure_id = request.query_params.get("structure")
        if not structure_id:
            return Response({"detail": "structure query param required"}, status=status.HTTP_400_BAD_REQUEST)
        # Keep inheritance/scope visibility from InheritableScopedViewSet.
        root_sections = self.get_queryset().filter(
            structure_id=structure_id,
            parent__isnull=True
        ).order_by("sort_order", "name")
        serializer = serializers.AgreementSectionTreeSerializer(root_sections, many=True)
        return Response(serializer.data)


# =============================================================================
# AGREEMENT VIEWSETS
# =============================================================================

class AgreementViewSet(ScopedViewSet):
    """
    ViewSet for lease agreements.

    Endpoints:
    - GET /agreements/ - List all agreements
    - POST /agreements/ - Create an agreement
    - GET /agreements/{id}/ - Get agreement details
    - PATCH /agreements/{id}/ - Update agreement
    - DELETE /agreements/{id}/ - Soft delete agreement
    - GET /agreements/{id}/terms/ - Get all terms
    - PATCH /agreements/{id}/bundle/ - Update all terms at once
    - POST /agreements/{id}/submit/ - Submit for approval
    - GET /agreements/by-tenant/ - Filter by tenant
    """

    rbac_module = "LEASE"

    queryset = models.Agreement.objects.all()
    serializer_class = serializers.AgreementSerializer

    def get_serializer_class(self):
        if self.action == "list":
            return serializers.AgreementListSerializer
        if self.action == "retrieve":
            return serializers.AgreementDetailSerializer
        if self.action == "create":
            return serializers.AgreementCreateSerializer
        if self.action == "bundle":
            return serializers.LeaseTermsBundleSerializer
        return serializers.AgreementSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        # Apply filters
        tenant_id = self.request.query_params.get("tenant_id", "")
        site_id = self.request.query_params.get("site_id", "")
        status_filter = self.request.query_params.get("status", "")
        agreement_type = self.request.query_params.get("agreement_type", "")
        search = self.request.query_params.get("q", "")

        if tenant_id:
            queryset = queryset.filter(tenant_id=tenant_id)
        if site_id:
            queryset = queryset.filter(site_id=site_id)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if agreement_type:
            queryset = queryset.filter(agreement_type=agreement_type)
        if search:
            queryset = queryset.filter(
                Q(lease_id__icontains=search) |
                Q(tenant__legal_name__icontains=search) |
                Q(site__name__icontains=search)
            )

        return queryset.select_related(
            "tenant", "site", "primary_contact"
        ).prefetch_related(
            "unit_allocations",
            "unit_allocations__site",
            "unit_allocations__tower",
            "unit_allocations__floor",
            "unit_allocations__unit",
            "approval_steps",
            "approval_steps__approver",
        )

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        serializer.save(scope=scope, created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def perform_destroy(self, instance):
        instance.soft_delete()

    def _derive_approval_params(self, agreement):
        """
        Derive (lease_value, tenant_type, lease_term_months) used for ApprovalRule matching.
        """
        agreement = models.Agreement.objects.select_related(
            "term_dates", "financials", "tenant"
        ).get(pk=agreement.pk)

        lease_value = None
        try:
            fin = agreement.financials
        except models.LeaseFinancials.DoesNotExist:
            fin = None

        if fin:
            if fin.annual_rent is not None and fin.annual_rent > 0:
                lease_value = float(fin.annual_rent)
            elif fin.base_rent_monthly is not None and fin.base_rent_monthly > 0:
                lease_value = float(fin.base_rent_monthly) * 12

        tenant_type = getattr(agreement.tenant, "tenant_type", None) if agreement.tenant else None

        lease_term_months = None
        try:
            td = agreement.term_dates
        except models.LeaseTermDates.DoesNotExist:
            td = None

        if td:
            if td.initial_term_months is not None:
                lease_term_months = td.initial_term_months
            elif td.commencement_date and td.expiry_date:
                delta = td.expiry_date - td.commencement_date
                lease_term_months = max(1, delta.days // 30)

        return lease_value, tenant_type, lease_term_months

    def _find_matching_approval_rule(self, agreement, lease_value, tenant_type, lease_term_months):
        """
        Find the first matching active ApprovalRule within agreement scope boundary.
        Walks UP the hierarchy (entity → company → org) so rules defined at parent
        scope levels are correctly found for entity-level agreements.
        """
        from apps.approvals.models import ApprovalRule

        scope_ids = self._get_inheritable_scope_ids(agreement.scope)
        for rule in (
            ApprovalRule.objects.filter(
                scope_id__in=scope_ids,
                status=ApprovalRule.Status.ACTIVE,
                is_active=True,
            )
            .prefetch_related("levels__role")
            .order_by("lease_value_min", "id")
        ):
            if rule.matches(lease_value, tenant_type, lease_term_months):
                return rule
        return None

    def _create_agreement_approval_steps(self, agreement, rule, user):
        """
        Replace agreement approval steps using the matched rule.
        """
        from datetime import timedelta

        models.AgreementApproval.objects.filter(agreement=agreement).delete()
        if not rule:
            return []

        now = timezone.now()
        created_steps = []
        for lvl in rule.levels.order_by("level"):
            due_date = (now + timedelta(hours=lvl.sla_hours)).date() if lvl.sla_hours else None
            created_steps.append(
                models.AgreementApproval.objects.create(
                    scope=agreement.scope,
                    agreement=agreement,
                    step_order=lvl.level,
                    step_name=f"L{lvl.level} - {lvl.role.name}",
                    step_description=(
                        f"Approval from {lvl.role.name} ({lvl.sla_hours}h SLA)"
                        if lvl.approval_required
                        else f"Informational step for {lvl.role.name} ({lvl.sla_hours}h SLA)"
                    ),
                    approval_required=lvl.approval_required,
                    approver_role=lvl.role.name,
                    status=models.AgreementApproval.ApprovalStepStatus.PENDING,
                    due_date=due_date,
                    created_by=user,
                )
            )
        return created_steps

    def _get_inheritable_scope_ids(self, scope):
        """
        Return [current_scope_id, parent_scope_id, ...] for inheritable data lookup.
        """
        from apps.accounts.models import TenantScope

        scope_ids = [scope.id]

        if scope.scope_type == TenantScope.ScopeType.SITE and scope.site:
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
            org = scope.company.org
            if org:
                org_scope = TenantScope.objects.filter(org=org, is_active=True).first()
                if org_scope:
                    scope_ids.append(org_scope.id)

        return scope_ids

    def _build_clause_mapping_response(self, agreement):
        from apps.clauses.models import Clause, ClauseVersion

        mappings = agreement.clause_mapping_draft or []
        def _to_int(value):
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        clause_ids = [
            _to_int(item.get("clause_id"))
            for item in mappings
            if isinstance(item, dict)
        ]
        clause_ids = [item for item in clause_ids if item is not None]
        section_ids = [
            _to_int(item.get("section_id"))
            for item in mappings
            if isinstance(item, dict)
        ]
        section_ids = [item for item in section_ids if item is not None]
        version_ids = [
            _to_int(item.get("clause_version_id"))
            for item in mappings
            if isinstance(item, dict)
        ]
        version_ids = [item for item in version_ids if item is not None]

        clauses_by_id = {
            clause.id: clause
            for clause in Clause.objects.filter(id__in=clause_ids).select_related("category")
        }
        sections_by_id = {
            section.id: section
            for section in models.AgreementSection.objects.filter(id__in=section_ids)
        }
        versions_by_id = {
            version.id: version
            for version in ClauseVersion.objects.filter(id__in=version_ids)
        }

        enriched_mappings = []
        for item in mappings:
            if not isinstance(item, dict):
                continue

            clause_id = _to_int(item.get("clause_id"))
            section_id = _to_int(item.get("section_id"))
            clause_version_id = _to_int(item.get("clause_version_id"))

            clause = clauses_by_id.get(clause_id)
            section = sections_by_id.get(section_id)
            version = versions_by_id.get(clause_version_id)

            enriched_mappings.append(
                {
                    "clause_id": clause_id,
                    "clause_title": clause.title if clause else None,
                    "clause_code": clause.clause_id if clause else None,
                    "clause_version_id": clause_version_id,
                    "clause_version_label": version.version_label if version else None,
                    "section_id": section_id,
                    "section_name": section.name if section else None,
                    "custom_config": item.get("custom_config", {}),
                    "custom_body_text": item.get("custom_body_text", ""),
                }
            )

        return {
            "agreement_id": agreement.id,
            "structure_id": agreement.structure_id,
            "mappings": enriched_mappings,
            "total_mappings": len(enriched_mappings),
        }

    def _normalize_clause_mappings(self, agreement, raw_mappings):
        from apps.clauses.models import Clause, ClauseVersion

        if raw_mappings is None:
            return []

        if not isinstance(raw_mappings, list):
            raise DRFValidationError({"mappings": "Expected a list of clause mapping entries."})

        inheritable_scope_ids = self._get_inheritable_scope_ids(agreement.scope)
        allowed_clauses = {
            clause.id: clause
            for clause in Clause.objects.filter(
                scope_id__in=inheritable_scope_ids,
                is_active=True,
                status=Clause.Status.ACTIVE,
            )
        }

        allowed_sections = {}
        if agreement.structure_id:
            allowed_sections = {
                section.id: section
                for section in models.AgreementSection.objects.filter(
                    structure_id=agreement.structure_id,
                    is_active=True,
                )
            }

        normalized = []
        seen_clause_ids = set()

        for idx, item in enumerate(raw_mappings):
            if not isinstance(item, dict):
                raise DRFValidationError({"mappings": f"Entry {idx + 1} must be an object."})

            clause_id = item.get("clause_id")
            if clause_id in (None, ""):
                raise DRFValidationError({"mappings": f"Entry {idx + 1}: clause_id is required."})
            try:
                clause_id = int(clause_id)
            except (TypeError, ValueError):
                raise DRFValidationError({"mappings": f"Entry {idx + 1}: clause_id must be an integer."})

            clause = allowed_clauses.get(clause_id)
            if clause is None:
                raise DRFValidationError(
                    {"mappings": f"Entry {idx + 1}: clause_id {clause_id} is not visible or not ACTIVE."}
                )
            if clause_id in seen_clause_ids:
                raise DRFValidationError({"mappings": f"Duplicate clause_id {clause_id} is not allowed."})
            seen_clause_ids.add(clause_id)

            section_id = item.get("section_id")
            if section_id in ("", None):
                section_id = None
            else:
                try:
                    section_id = int(section_id)
                except (TypeError, ValueError):
                    raise DRFValidationError({"mappings": f"Entry {idx + 1}: section_id must be an integer."})

            if agreement.structure_id:
                if section_id is None:
                    raise DRFValidationError(
                        {"mappings": f"Entry {idx + 1}: section_id is required when structure is selected."}
                    )
                if section_id not in allowed_sections:
                    raise DRFValidationError(
                        {"mappings": f"Entry {idx + 1}: section_id {section_id} is not part of this structure."}
                    )
            elif section_id is not None:
                raise DRFValidationError(
                    {"mappings": f"Entry {idx + 1}: section_id is not allowed without agreement structure."}
                )

            clause_version_id = item.get("clause_version_id")
            clause_version = None
            if clause_version_id not in ("", None):
                try:
                    clause_version_id = int(clause_version_id)
                except (TypeError, ValueError):
                    raise DRFValidationError(
                        {"mappings": f"Entry {idx + 1}: clause_version_id must be an integer."}
                    )
                clause_version = ClauseVersion.objects.filter(
                    id=clause_version_id,
                    clause_id=clause_id,
                    is_active=True,
                ).first()
                if clause_version is None:
                    raise DRFValidationError(
                        {
                            "mappings": (
                                f"Entry {idx + 1}: clause_version_id {clause_version_id} "
                                f"does not belong to clause_id {clause_id}."
                            )
                        }
                    )
            else:
                clause_version = (
                    ClauseVersion.objects.filter(
                        clause_id=clause_id,
                        version_status=ClauseVersion.VersionStatus.CURRENT,
                        is_active=True,
                    )
                    .order_by("-major_version", "-minor_version")
                    .first()
                )
                clause_version_id = clause_version.id if clause_version else None

            custom_config = item.get("custom_config", {})
            if custom_config in (None, ""):
                custom_config = {}
            if not isinstance(custom_config, dict):
                raise DRFValidationError({"mappings": f"Entry {idx + 1}: custom_config must be an object."})

            custom_body_text = item.get("custom_body_text", "")
            if custom_body_text in (None,):
                custom_body_text = ""
            if not isinstance(custom_body_text, str):
                raise DRFValidationError(
                    {"mappings": f"Entry {idx + 1}: custom_body_text must be a string."}
                )

            normalized.append(
                {
                    "clause_id": clause_id,
                    "clause_version_id": clause_version_id,
                    "section_id": section_id,
                    "custom_config": custom_config,
                    "custom_body_text": custom_body_text,
                }
            )

        return normalized

    def _sync_clause_usages_from_draft(self, agreement, user):
        from apps.clauses.models import ClauseUsage

        mappings = self._normalize_clause_mappings(agreement, agreement.clause_mapping_draft or [])
        mapping_by_clause_id = {item["clause_id"]: item for item in mappings}
        mapped_clause_ids = set(mapping_by_clause_id.keys())

        current_usages = ClauseUsage.objects.filter(
            agreement=agreement,
            scope=agreement.scope,
        )
        current_active_usages = current_usages.filter(is_active=True)

        created_count = 0
        updated_count = 0
        deactivated_count = 0

        for clause_id, mapping in mapping_by_clause_id.items():
            usage, created = ClauseUsage.objects.update_or_create(
                agreement=agreement,
                clause_id=clause_id,
                defaults={
                    "scope": agreement.scope,
                    "clause_version_id": mapping["clause_version_id"],
                    "section_id": mapping["section_id"],
                    "custom_config": mapping["custom_config"],
                    "custom_body_text": mapping["custom_body_text"],
                    "is_active": True,
                    "deleted_at": None,
                    "updated_by": user,
                },
            )
            if created:
                usage.created_by = user
                usage.save(update_fields=["created_by"])
                created_count += 1
            else:
                updated_count += 1

        for usage in current_active_usages.exclude(clause_id__in=mapped_clause_ids):
            usage.updated_by = user
            usage.save(update_fields=["updated_by"])
            usage.soft_delete()
            deactivated_count += 1

        return {
            "created": created_count,
            "updated": updated_count,
            "deactivated": deactivated_count,
            "total_mapped": len(mappings),
        }

    @action(detail=True, methods=["get"])
    def terms(self, request, pk=None):
        """Get all terms for an agreement."""
        agreement = self.get_object()
        serializer = serializers.AgreementDetailSerializer(agreement)
        return Response(serializer.data)

    @action(detail=True, methods=["patch"])
    def bundle(self, request, pk=None):
        """Update all terms at once."""
        agreement = self.get_object()
        serializer = serializers.LeaseTermsBundleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(
            agreement=agreement,
            scope=self.get_active_scope(),
            user=request.user
        )
        # Return updated agreement
        detail_serializer = serializers.AgreementDetailSerializer(agreement)
        return Response(detail_serializer.data)

    @action(detail=True, methods=["post"], url_path="pricing-preview")
    def pricing_preview(self, request, pk=None):
        """Compute pricing preview (calendar-day buffer/proration) with optional unsaved overrides."""
        agreement = self.get_object()
        payload = request.data if isinstance(request.data, dict) else {}
        term_dates_payload = payload.get("term_dates") if isinstance(payload.get("term_dates"), dict) else {}
        financials_payload = payload.get("financials") if isinstance(payload.get("financials"), dict) else {}
        rent_free_payload = payload.get("rent_free") if isinstance(payload.get("rent_free"), dict) else {}

        def pick(section, key, default=None):
            if isinstance(section, dict) and key in section:
                return section.get(key)
            return default

        try:
            term_dates = agreement.term_dates
        except models.LeaseTermDates.DoesNotExist:
            term_dates = None

        try:
            financials = agreement.financials
        except models.LeaseFinancials.DoesNotExist:
            financials = None

        try:
            rent_free = agreement.rent_free
        except models.LeaseRentFree.DoesNotExist:
            rent_free = None

        commencement_date = pick(
            term_dates_payload,
            "commencement_date",
            getattr(term_dates, "commencement_date", None),
        )
        expiry_date = pick(
            term_dates_payload,
            "expiry_date",
            getattr(term_dates, "expiry_date", None),
        )

        rate_per_sqft = pick(
            financials_payload,
            "rate_per_sqft_monthly",
            getattr(financials, "rate_per_sqft_monthly", None),
        )
        if rate_per_sqft in [None, ""] and agreement.site_id:
            rate_per_sqft = getattr(agreement.site, "base_rate_sqft", None)

        total_allocated_area = agreement.unit_allocations.filter(is_active=True).aggregate(
            total=Sum("allocated_area_sqft")
        )["total"] or 0

        base_rent_input = pick(
            financials_payload,
            "base_rent_monthly",
            getattr(financials, "base_rent_monthly", None),
        )
        resolved_base_rent = resolve_base_rent_monthly(
            base_rent_input,
            rate_per_sqft,
            total_allocated_area,
        )

        primary_buffer_days = pick(
            rent_free_payload,
            "rent_free_days",
            getattr(rent_free, "rent_free_days", 0),
        )
        extended_buffer_days = pick(
            rent_free_payload,
            "extended_buffer_days",
            getattr(rent_free, "extended_buffer_days", 0),
        )
        extended_buffer_charge_percent = pick(
            rent_free_payload,
            "extended_buffer_charge_percent",
            getattr(rent_free, "extended_buffer_charge_percent", 50),
        )

        summary = calculate_buffer_summary(
            commencement_date=commencement_date,
            expiry_date=expiry_date,
            monthly_base_rent=resolved_base_rent,
            primary_buffer_days=primary_buffer_days,
            extended_buffer_days=extended_buffer_days,
            extended_buffer_charge_percent=extended_buffer_charge_percent,
            allocated_area_sqft=total_allocated_area,
        )

        try:
            rate_used = float(rate_per_sqft) if rate_per_sqft not in [None, ""] else None
        except (TypeError, ValueError):
            rate_used = None

        return Response(
            {
                "summary": summary,
                "resolved": {
                    "monthly_base_rent": float(resolved_base_rent) if resolved_base_rent is not None else None,
                    "rate_per_sqft_monthly_used": rate_used,
                    "total_allocated_area_sqft": float(total_allocated_area or 0),
                },
            }
        )

    @action(detail=True, methods=["get"], url_path="generate-pdf")
    def generate_pdf(self, request, pk=None):
        """Generate a PDF of the agreement.

        Query params:
            section - Optional section ID for section-only PDF
        """
        from .pdf_generator import render_agreement_pdf

        agreement = self.get_object()
        section_id = request.query_params.get("section")

        buf = render_agreement_pdf(agreement, section_id=section_id)

        if section_id:
            filename = f"{agreement.lease_id}_section_{section_id}.pdf"
        else:
            filename = f"{agreement.lease_id}_v{agreement.version_number}.pdf"

        response = HttpResponse(buf.read(), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    @action(detail=True, methods=["get"], url_path="preview-html")
    def preview_html(self, request, pk=None):
        """Return rendered HTML preview of the agreement.

        Query params:
            section - Optional section ID for section-only preview
        """
        from .pdf_generator import render_agreement_html

        agreement = self.get_object()
        section_id = request.query_params.get("section")

        html = render_agreement_html(agreement, section_id=section_id)
        return HttpResponse(html, content_type="text/html; charset=utf-8")

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        """Submit agreement for approval and generate workflow steps from matching ApprovalRule."""
        agreement = self.get_object()
        if agreement.status != models.Agreement.Status.DRAFT:
            return Response(
                {"error": "Only draft agreements can be submitted"},
                status=status.HTTP_400_BAD_REQUEST
            )

        clause_sync = self._sync_clause_usages_from_draft(agreement, request.user)

        lease_value, tenant_type, lease_term_months = self._derive_approval_params(agreement)
        matched_rule = self._find_matching_approval_rule(
            agreement,
            lease_value,
            tenant_type,
            lease_term_months,
        )
        created_steps = self._create_agreement_approval_steps(
            agreement,
            matched_rule,
            request.user,
        )

        agreement.status = models.Agreement.Status.PENDING
        agreement.updated_by = request.user
        agreement.save(update_fields=["status", "updated_by", "updated_at"])

        response_data = serializers.AgreementSerializer(agreement).data
        response_data["approval_steps_created"] = len(created_steps)
        response_data["approval_rule"] = (
            {
                "id": matched_rule.id,
                "name": matched_rule.name,
            }
            if matched_rule
            else None
        )
        response_data["clause_usage_sync"] = clause_sync
        return Response(response_data)

    @action(detail=True, methods=["get", "patch"], url_path="clause-mappings")
    def clause_mappings(self, request, pk=None):
        """
        Get or update agreement-level clause-to-section mapping draft.
        """
        agreement = self.get_object()

        if request.method == "GET":
            return Response(self._build_clause_mapping_response(agreement))

        mappings = request.data.get("mappings")
        normalized = self._normalize_clause_mappings(agreement, mappings)
        agreement.clause_mapping_draft = normalized
        agreement.updated_by = request.user
        agreement.save(update_fields=["clause_mapping_draft", "updated_by", "updated_at"])

        return Response(self._build_clause_mapping_response(agreement))

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        """Activate a pending agreement after required approval steps are completed."""
        agreement = self.get_object()
        if agreement.status != models.Agreement.Status.PENDING:
            return Response(
                {"error": "Only pending agreements can be activated"},
                status=status.HTTP_400_BAD_REQUEST
            )

        required_steps = agreement.approval_steps.filter(
            is_active=True,
            approval_required=True,
        )
        rejected_count = required_steps.filter(
            status=models.AgreementApproval.ApprovalStepStatus.REJECTED
        ).count()
        if rejected_count > 0:
            return Response(
                {"error": "Agreement has rejected approval step(s) and cannot be activated."},
                status=status.HTTP_400_BAD_REQUEST
            )

        incomplete_count = required_steps.exclude(
            status__in=[
                models.AgreementApproval.ApprovalStepStatus.APPROVED,
                models.AgreementApproval.ApprovalStepStatus.SKIPPED,
            ]
        ).count()
        if incomplete_count > 0:
            return Response(
                {"error": f"{incomplete_count} required approval step(s) are still pending."},
                status=status.HTTP_400_BAD_REQUEST
            )

        agreement.status = models.Agreement.Status.ACTIVE
        agreement.updated_by = request.user
        agreement.save(update_fields=["status", "updated_by", "updated_at"])
        return Response(serializers.AgreementSerializer(agreement).data)

    @action(detail=True, methods=["post"])
    def terminate(self, request, pk=None):
        """Terminate an active agreement."""
        agreement = self.get_object()
        if agreement.status != models.Agreement.Status.ACTIVE:
            return Response(
                {"error": "Only active agreements can be terminated"},
                status=status.HTTP_400_BAD_REQUEST
            )
        agreement.status = models.Agreement.Status.TERMINATED
        agreement.updated_by = request.user
        agreement.save()
        return Response(serializers.AgreementSerializer(agreement).data)

    @action(detail=False, methods=["get"], url_path="by-tenant")
    def by_tenant(self, request):
        """Get agreements filtered by tenant."""
        tenant_id = request.query_params.get("tenant_id")
        if not tenant_id:
            return Response(
                {"error": "tenant_id is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        queryset = self.get_queryset().filter(tenant_id=tenant_id)
        serializer = serializers.AgreementListSerializer(queryset, many=True)
        return Response(serializer.data)


class AgreementApprovalViewSet(ScopedViewSet):
    """
    ViewSet for agreement approval workflow steps.

    Endpoints:
    - GET /agreement-approvals/ - List approval steps (filter by agreement_id/status)
    - POST /agreement-approvals/ - Create approval step
    - PATCH /agreement-approvals/{id}/ - Update step
    - POST /agreement-approvals/{id}/action/ - Approve/reject/skip a step
    """

    queryset = models.AgreementApproval.objects.all()
    serializer_class = serializers.AgreementApprovalSerializer
    AGREEMENT_APPROVE_PERMISSION_CODES = {
        "agreements.approve",
        "agreement.approve",
        "lease.approve",
        "lease.agreement.approve",
        "lease.agreements.approve",
        "leases.approve",
        "leases.agreement.approve",
        "leases.agreements.approve",
        "approvals.approve",
    }

    def _get_active_membership_for_request_user(self):
        from apps.accounts.models import ScopeMembership

        scope = self.get_active_scope()
        if scope is None:
            return None

        return (
            ScopeMembership.objects.filter(
                user=self.request.user,
                scope=scope,
                is_active=True,
            )
            .select_related("role")
            .prefetch_related("role__module_permissions", "role__role_permissions__permission")
            .first()
        )

    def _has_agreement_approve_permission(self, role):
        from apps.accounts.models import ModulePermission

        if role.role_type == role.RoleType.ADMIN:
            return True

        if role.module_permissions.filter(
            module__in=[
                ModulePermission.Module.LEASE,
                ModulePermission.Module.APPROVALS,
            ],
            can_approve=True,
            is_active=True,
        ).exists():
            return True

        permission_codes = set(
            role.role_permissions.filter(is_active=True).values_list(
                "permission__code", flat=True
            )
        )
        return bool(permission_codes.intersection(self.AGREEMENT_APPROVE_PERMISSION_CODES))

    def _validate_agreement_approval_access(self, approval):
        if self.request.user.is_superuser:
            return

        membership = self._get_active_membership_for_request_user()
        if not membership or not membership.role:
            raise PermissionDenied(
                "You do not have an active role membership in the selected scope to action this approval."
            )

        role = membership.role
        required_role = (approval.approver_role or "").strip()
        if required_role:
            required_role_lower = required_role.lower()
            role_matches = (
                (role.name or "").strip().lower() == required_role_lower
                or (role.code or "").strip().lower() == required_role_lower
            )
            if not role_matches:
                raise PermissionDenied(
                    f"This approval step requires role '{approval.approver_role}'. "
                    f"Your active role is '{role.name}'."
                )

        if approval.approver_id and approval.approver_id != self.request.user.id:
            raise PermissionDenied("This approval step is assigned to a different approver.")

        if not self._has_agreement_approve_permission(role):
            raise PermissionDenied("Your active role does not have agreement approval permission.")

    def get_queryset(self):
        queryset = super().get_queryset()
        agreement_id = self.request.query_params.get("agreement_id")
        if agreement_id:
            queryset = queryset.filter(agreement_id=agreement_id)

        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset.select_related("agreement", "approver").order_by("agreement_id", "step_order")

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        serializer.save(scope=scope, created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=True, methods=["post"])
    def action(self, request, pk=None):
        """Take action on a workflow step: approve/reject/skip."""
        approval = self.get_object()
        action_type = request.data.get("action")
        comments = request.data.get("comments", "")

        if action_type not in ["approve", "reject", "skip"]:
            return Response(
                {"error": "Action must be 'approve', 'reject', or 'skip'"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if approval.status != models.AgreementApproval.ApprovalStepStatus.PENDING:
            return Response(
                {"error": "Approval step is not pending"},
                status=status.HTTP_400_BAD_REQUEST
            )

        self._validate_agreement_approval_access(approval)

        if action_type == "approve":
            approval.status = models.AgreementApproval.ApprovalStepStatus.APPROVED
        elif action_type == "reject":
            approval.status = models.AgreementApproval.ApprovalStepStatus.REJECTED
        else:
            approval.status = models.AgreementApproval.ApprovalStepStatus.SKIPPED

        approval.approver = request.user
        approval.actioned_at = timezone.now()
        approval.comments = comments
        approval.updated_by = request.user
        approval.save(
            update_fields=[
                "status", "approver", "actioned_at", "comments", "updated_by", "updated_at"
            ]
        )
        return Response(serializers.AgreementApprovalSerializer(approval).data)


class UnitAllocationViewSet(ScopedViewSet):
    """
    ViewSet for granular lease allocations.
    """

    queryset = models.UnitAllocation.objects.all()
    serializer_class = serializers.UnitAllocationSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        agreement_id = self.request.query_params.get("agreement_id", "")
        allocation_level = self.request.query_params.get("allocation_level", "")
        site_id = self.request.query_params.get("site_id", "")
        tower_id = self.request.query_params.get("tower_id", "")
        floor_id = self.request.query_params.get("floor_id", "")
        unit_id = self.request.query_params.get("unit_id", "")

        if agreement_id:
            queryset = queryset.filter(agreement_id=agreement_id)
        if allocation_level:
            queryset = queryset.filter(allocation_level=allocation_level)
        if site_id:
            queryset = queryset.filter(site_id=site_id)
        if tower_id:
            queryset = queryset.filter(tower_id=tower_id)
        if floor_id:
            queryset = queryset.filter(floor_id=floor_id)
        if unit_id:
            queryset = queryset.filter(unit_id=unit_id)

        return queryset.select_related("agreement", "site", "tower", "floor", "unit").order_by("-created_at", "-id")

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        serializer.save(scope=scope, created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def perform_destroy(self, instance):
        instance.soft_delete()


class DocumentViewSet(ScopedViewSet):
    """
    ViewSet for lease documents.
    """

    queryset = models.LeaseDocument.objects.all()
    serializer_class = serializers.LeaseDocumentSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        agreement_id = self.request.query_params.get("agreement_id", "")

        if agreement_id:
            queryset = queryset.filter(agreement_id=agreement_id)

        return queryset.select_related("agreement")

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        # Calculate file size and mime type
        file = self.request.FILES.get("file")
        extra = {}
        if file:
            extra["file_size"] = file.size
            extra["mime_type"] = file.content_type
        serializer.save(scope=scope, created_by=self.request.user, **extra)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def perform_destroy(self, instance):
        instance.soft_delete()


class NoteViewSet(ScopedViewSet):
    """
    ViewSet for lease notes.
    """

    queryset = models.LeaseNote.objects.all()
    serializer_class = serializers.LeaseNoteSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        agreement_id = self.request.query_params.get("agreement_id", "")

        if agreement_id:
            queryset = queryset.filter(agreement_id=agreement_id)

        return queryset.select_related("agreement", "created_by")

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        serializer.save(scope=scope, created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def perform_destroy(self, instance):
        instance.soft_delete()


class AvailabilityViewSet(ScopedViewSet):
    """
    ViewSet for property availability (for lease allocation).
    Returns site tree with unit availability information.
    """

    queryset = models.Agreement.objects.none()  # Dummy queryset
    serializer_class = serializers.AgreementSerializer

    @action(detail=False, methods=["get"])
    def tree(self, request):
        """
        Get property availability tree for a site.
        Shows which units are available for lease allocation.
        """
        from apps.properties.models import Site, Tower, Floor, Unit

        site_id = request.query_params.get("site_id")
        if not site_id:
            return Response(
                {"error": "site_id is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        scope = self.get_active_scope()

        try:
            site = Site.objects.for_scope(scope).get(pk=site_id)
        except Site.DoesNotExist:
            return Response(
                {"error": "Site not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Build the tree
        towers_data = []
        for tower in site.towers.filter(is_active=True).order_by("name"):
            floors_data = []
            for floor in tower.floors.filter(is_active=True).order_by("number"):
                units_data = []
                floor_allocations = models.UnitAllocation.objects.filter(
                    floor=floor,
                    is_active=True,
                    agreement__status__in=models.UnitAllocation._blocking_statuses(),
                ).aggregate(total_allocated=Sum("allocated_area_sqft"))
                floor_allocated = float(floor_allocations["total_allocated"] or 0)
                floor_leasable = float(floor.leasable_area_sqft or 0)
                floor_available = max(0, floor_leasable - floor_allocated)
                has_floor_allocation = floor_allocated > 0

                for unit in floor.units.filter(is_active=True).order_by("unit_no"):
                    # Check blocking allocations for this unit.
                    active_allocations = models.UnitAllocation.objects.filter(
                        unit=unit,
                        is_active=True,
                        agreement__status__in=models.UnitAllocation._blocking_statuses(),
                    ).aggregate(
                        total_allocated=Sum("allocated_area_sqft")
                    )

                    allocated = float(active_allocations["total_allocated"] or 0)
                    leasable = float(unit.leasable_area_sqft or 0)
                    available = 0 if has_floor_allocation else max(0, leasable - allocated)

                    units_data.append({
                        "id": unit.id,
                        "unit_no": unit.unit_no,
                        "unit_type": unit.unit_type,
                        "leasable_area_sqft": leasable,
                        "builtup_area_sqft": float(unit.builtup_area_sqft or 0),
                        "allocated_area_sqft": allocated,
                        "available_area_sqft": available,
                        "blocked_by_floor_allocation": has_floor_allocation,
                        "is_divisible": getattr(unit, "is_divisible", False),
                        "status": unit.status,
                    })

                floors_data.append({
                    "id": floor.id,
                    "number": floor.number,
                    "label": floor.label,
                    "total_area_sqft": float(floor.total_area_sqft or 0),
                    "leasable_area_sqft": float(floor.leasable_area_sqft or 0),
                    "allocated_area_sqft": floor_allocated,
                    "available_area_sqft": floor_available,
                    "has_floor_allocation": has_floor_allocation,
                    "units": units_data,
                })

            towers_data.append({
                "id": tower.id,
                "name": tower.name,
                "floors": floors_data,
            })

        return Response({
            "id": site.id,
            "name": site.name,
            "towers": towers_data,
        })


# =============================================================================
# AMENDMENT VIEWSETS
# =============================================================================

class LeaseAmendmentViewSet(ScopedViewSet):
    """
    ViewSet for lease amendments.

    Endpoints:
    - GET /amendments/ - List all amendments
    - POST /amendments/ - Create amendment
    - GET /amendments/{id}/ - Get amendment details
    - PATCH /amendments/{id}/ - Update amendment
    - DELETE /amendments/{id}/ - Delete amendment
    - POST /amendments/{id}/submit/ - Submit for approval
    - POST /amendments/{id}/approve/ - Approve amendment
    - POST /amendments/{id}/execute/ - Execute amendment
    - GET /amendments/by-agreement/{agreement_id}/ - Get amendments for agreement
    """

    queryset = models.LeaseAmendment.objects.all()
    serializer_class = serializers.LeaseAmendmentSerializer

    def get_serializer_class(self):
        if self.action == "list":
            return serializers.LeaseAmendmentListSerializer
        if self.action == "retrieve":
            return serializers.LeaseAmendmentDetailSerializer
        if self.action == "create":
            return serializers.LeaseAmendmentCreateSerializer
        return serializers.LeaseAmendmentSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by agreement
        agreement_id = self.request.query_params.get("agreement_id")
        if agreement_id:
            queryset = queryset.filter(agreement_id=agreement_id)

        # Filter by status
        approval_status = self.request.query_params.get("approval_status")
        if approval_status:
            queryset = queryset.filter(approval_status=approval_status)

        # Filter by amendment type
        amendment_type = self.request.query_params.get("amendment_type")
        if amendment_type:
            queryset = queryset.filter(amendment_type=amendment_type)

        # Search
        search = self.request.query_params.get("q")
        if search:
            queryset = queryset.filter(
                Q(amendment_id__icontains=search) |
                Q(title__icontains=search) |
                Q(agreement__lease_id__icontains=search)
            )

        return queryset.select_related("agreement")

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        serializer.save(scope=scope, created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def perform_destroy(self, instance):
        instance.soft_delete()

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        """Submit amendment for review. Auto-creates approval steps from matching ApprovalRule if found."""
        from apps.approvals.models import ApprovalRule
        from datetime import timedelta

        amendment = self.get_object()
        if amendment.approval_status != models.LeaseAmendment.ApprovalStatus.DRAFT:
            return Response(
                {"error": "Only draft amendments can be submitted"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Derive lease params from agreement for ApprovalRule matching
        agreement = amendment.agreement
        agreement = models.Agreement.objects.select_related(
            "term_dates", "financials", "tenant"
        ).prefetch_related().get(pk=agreement.pk)

        lease_value = None
        if hasattr(agreement, "financials") and agreement.financials:
            fin = agreement.financials
            if fin.annual_rent is not None and fin.annual_rent > 0:
                lease_value = float(fin.annual_rent)
            elif fin.base_rent_monthly is not None and fin.base_rent_monthly > 0:
                lease_value = float(fin.base_rent_monthly) * 12

        tenant_type = None  # TenantCompany doesn't have tenant_type; rules with empty tenant_types still match

        lease_term_months = None
        if hasattr(agreement, "term_dates") and agreement.term_dates:
            td = agreement.term_dates
            if td.initial_term_months is not None:
                lease_term_months = td.initial_term_months
            elif td.commencement_date and td.expiry_date:
                delta = td.expiry_date - td.commencement_date
                lease_term_months = max(1, delta.days // 30)

        # Find matching active ApprovalRule - walk UP hierarchy (entity → company → org)
        # so rules defined at parent scope levels are found for entity-level amendments.
        from apps.accounts.models import TenantScope as _TenantScope

        def _inheritable_ids(scope):
            ids = [scope.id]
            if scope.scope_type == _TenantScope.ScopeType.ENTITY and scope.entity:
                company = scope.entity.company
                if company:
                    cs = _TenantScope.objects.filter(company=company, is_active=True).first()
                    if cs:
                        ids.append(cs.id)
                    org = company.org
                    if org:
                        os_ = _TenantScope.objects.filter(org=org, is_active=True).first()
                        if os_:
                            ids.append(os_.id)
            elif scope.scope_type == _TenantScope.ScopeType.COMPANY and scope.company:
                org = scope.company.org
                if org:
                    os_ = _TenantScope.objects.filter(org=org, is_active=True).first()
                    if os_:
                        ids.append(os_.id)
            return ids

        scope_ids = _inheritable_ids(amendment.scope)
        matched_rule = None
        for rule in ApprovalRule.objects.filter(
            scope_id__in=scope_ids,
            status=ApprovalRule.Status.ACTIVE,
            is_active=True,
        ).prefetch_related("levels__role"):
            if rule.matches(lease_value, tenant_type, lease_term_months):
                matched_rule = rule
                break

        # Create AmendmentApproval steps from matched rule
        if matched_rule:
            levels = list(matched_rule.levels.order_by("level"))
            now = timezone.now()
            for lvl in levels:
                due_date = (now + timedelta(hours=lvl.sla_hours)).date() if lvl.sla_hours else None
                models.AmendmentApproval.objects.create(
                    scope=amendment.scope,
                    amendment=amendment,
                    step_order=lvl.level,
                    step_name=f"L{lvl.level} - {lvl.role.name}",
                    step_description=f"Approval required from {lvl.role.name} ({lvl.sla_hours}h SLA)",
                    approver_role=lvl.role.name,
                    status=models.AmendmentApproval.ApprovalStepStatus.PENDING,
                    due_date=due_date,
                    created_by=request.user,
                )

        amendment.approval_status = models.LeaseAmendment.ApprovalStatus.PENDING_REVIEW
        amendment.updated_by = request.user
        amendment.save()
        return Response(serializers.LeaseAmendmentDetailSerializer(amendment).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        """Approve amendment."""
        amendment = self.get_object()
        if amendment.approval_status not in [
            models.LeaseAmendment.ApprovalStatus.PENDING_REVIEW,
            models.LeaseAmendment.ApprovalStatus.PENDING_APPROVAL
        ]:
            return Response(
                {"error": "Amendment is not pending approval"},
                status=status.HTTP_400_BAD_REQUEST
            )
        amendment.approval_status = models.LeaseAmendment.ApprovalStatus.APPROVED
        amendment.updated_by = request.user
        amendment.save()
        return Response(serializers.LeaseAmendmentSerializer(amendment).data)

    @action(detail=True, methods=["post"])
    def execute(self, request, pk=None):
        """Execute approved amendment — apply structured changes to agreement fields."""
        amendment = self.get_object()
        if amendment.approval_status != models.LeaseAmendment.ApprovalStatus.APPROVED:
            return Response(
                {"error": "Only approved amendments can be executed"},
                status=status.HTTP_400_BAD_REQUEST
            )

        amendment.approval_status = models.LeaseAmendment.ApprovalStatus.EXECUTED
        amendment.executed_date = timezone.now().date()
        amendment.updated_by = request.user
        amendment.save()

        # Apply structured changes to agreement sub-models
        agreement = amendment.agreement
        data = amendment.amendment_data or {}
        atype = amendment.amendment_type

        if atype == models.LeaseAmendment.AmendmentType.RENT_REVISION:
            if "base_rent_monthly" in data:
                try:
                    fin = agreement.financials
                    fin.base_rent_monthly = data["base_rent_monthly"]
                    fin.updated_by = request.user
                    fin.save(update_fields=["base_rent_monthly", "updated_by", "updated_at"])
                except models.LeaseFinancials.DoesNotExist:
                    pass

        elif atype in (
            models.LeaseAmendment.AmendmentType.TERM_EXTENSION,
            models.LeaseAmendment.AmendmentType.RENEWAL,
        ):
            try:
                td = agreement.term_dates
                if "expiry_date" in data:
                    td.expiry_date = data["expiry_date"]
                if "initial_term_months" in data:
                    td.initial_term_months = data["initial_term_months"]
                td.updated_by = request.user
                td.save(update_fields=["expiry_date", "initial_term_months", "updated_by", "updated_at"])
            except models.LeaseTermDates.DoesNotExist:
                pass

        elif atype == models.LeaseAmendment.AmendmentType.EARLY_TERMINATION:
            if "termination_date" in data:
                try:
                    td = agreement.term_dates
                    td.expiry_date = data["termination_date"]
                    td.updated_by = request.user
                    td.save(update_fields=["expiry_date", "updated_by", "updated_at"])
                except models.LeaseTermDates.DoesNotExist:
                    pass
                agreement.status = models.Agreement.AgreementStatus.TERMINATED
                agreement.updated_by = request.user

        elif atype == models.LeaseAmendment.AmendmentType.PARTY_CHANGE:
            if "new_tenant_id" in data:
                agreement.tenant_id = data["new_tenant_id"]
                agreement.updated_by = request.user

        # Always bump version
        agreement.version_number = amendment.new_version
        agreement.updated_by = request.user
        agreement.save()

        return Response(serializers.LeaseAmendmentDetailSerializer(amendment).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        """Reject amendment."""
        amendment = self.get_object()
        if amendment.approval_status not in [
            models.LeaseAmendment.ApprovalStatus.PENDING_REVIEW,
            models.LeaseAmendment.ApprovalStatus.PENDING_APPROVAL
        ]:
            return Response(
                {"error": "Amendment is not pending approval"},
                status=status.HTTP_400_BAD_REQUEST
            )
        amendment.approval_status = models.LeaseAmendment.ApprovalStatus.REJECTED
        amendment.updated_by = request.user
        amendment.save()
        return Response(serializers.LeaseAmendmentSerializer(amendment).data)

    @action(detail=False, methods=["get"], url_path="by-agreement/(?P<agreement_id>[^/.]+)")
    def by_agreement(self, request, agreement_id=None):
        """Get all amendments for an agreement."""
        scope = self.get_active_scope()
        amendments = models.LeaseAmendment.objects.filter(
            agreement_id=agreement_id,
            scope=scope
        ).order_by("-amendment_date")

        page = self.paginate_queryset(amendments)
        if page is not None:
            serializer = serializers.LeaseAmendmentListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = serializers.LeaseAmendmentListSerializer(amendments, many=True)
        return Response(serializer.data)


class AmendmentApprovalViewSet(ScopedViewSet):
    """
    ViewSet for amendment approval steps.

    Endpoints:
    - GET /amendment-approvals/ - List approvals (filter by amendment_id)
    - POST /amendment-approvals/ - Create approval step
    - PATCH /amendment-approvals/{id}/ - Update approval
    - POST /amendment-approvals/{id}/action/ - Take action (approve/reject)
    """

    queryset = models.AmendmentApproval.objects.all()
    serializer_class = serializers.AmendmentApprovalSerializer
    AMENDMENT_APPROVE_PERMISSION_CODES = {
        "amendments.approve",
        "amendment.approve",
        "lease.approve",
        "lease.amendment.approve",
        "lease.amendments.approve",
        "leases.approve",
        "leases.amendment.approve",
        "leases.amendments.approve",
        "approvals.approve",
    }

    def _get_active_membership_for_request_user(self):
        from apps.accounts.models import ScopeMembership

        scope = self.get_active_scope()
        if scope is None:
            return None

        return (
            ScopeMembership.objects.filter(
                user=self.request.user,
                scope=scope,
                is_active=True,
            )
            .select_related("role")
            .prefetch_related("role__module_permissions", "role__role_permissions__permission")
            .first()
        )

    def _has_amendment_approve_permission(self, role):
        from apps.accounts.models import ModulePermission

        if role.role_type == role.RoleType.ADMIN:
            return True

        if role.can_approve_amendments:
            return True

        if role.module_permissions.filter(
            module__in=[
                ModulePermission.Module.LEASE,
                ModulePermission.Module.APPROVALS,
            ],
            can_approve=True,
            is_active=True,
        ).exists():
            return True

        permission_codes = set(
            role.role_permissions.filter(is_active=True).values_list(
                "permission__code", flat=True
            )
        )
        return bool(permission_codes.intersection(self.AMENDMENT_APPROVE_PERMISSION_CODES))

    def _validate_amendment_approval_access(self, approval):
        if self.request.user.is_superuser:
            return

        membership = self._get_active_membership_for_request_user()
        if not membership or not membership.role:
            raise PermissionDenied(
                "You do not have an active role membership in the selected scope to action this approval."
            )

        role = membership.role
        required_role = (approval.approver_role or "").strip()
        if required_role:
            required_role_lower = required_role.lower()
            role_matches = (
                (role.name or "").strip().lower() == required_role_lower
                or (role.code or "").strip().lower() == required_role_lower
            )
            if not role_matches:
                raise PermissionDenied(
                    f"This approval step requires role '{approval.approver_role}'. "
                    f"Your active role is '{role.name}'."
                )

        if approval.approver_id and approval.approver_id != self.request.user.id:
            raise PermissionDenied("This approval step is assigned to a different approver.")

        if not self._has_amendment_approve_permission(role):
            raise PermissionDenied("Your active role does not have amendment approval permission.")

    def get_queryset(self):
        queryset = super().get_queryset()

        amendment_id = self.request.query_params.get("amendment_id")
        if amendment_id:
            queryset = queryset.filter(amendment_id=amendment_id)

        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset.select_related("amendment", "approver")

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        serializer.save(scope=scope, created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=True, methods=["post"])
    def action(self, request, pk=None):
        """Take action on approval step."""
        approval = self.get_object()

        action_type = request.data.get("action")  # "approve" or "reject"
        comments = request.data.get("comments", "")

        if action_type not in ["approve", "reject", "skip"]:
            return Response(
                {"error": "Action must be 'approve', 'reject', or 'skip'"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if approval.status != models.AmendmentApproval.ApprovalStepStatus.PENDING:
            return Response(
                {"error": "Approval step is not pending"},
                status=status.HTTP_400_BAD_REQUEST
            )

        self._validate_amendment_approval_access(approval)

        if action_type == "approve":
            approval.status = models.AmendmentApproval.ApprovalStepStatus.APPROVED
        elif action_type == "reject":
            approval.status = models.AmendmentApproval.ApprovalStepStatus.REJECTED
        else:
            approval.status = models.AmendmentApproval.ApprovalStepStatus.SKIPPED

        approval.approver = request.user
        approval.actioned_at = timezone.now()
        approval.comments = comments
        approval.updated_by = request.user
        approval.save()

        return Response(serializers.AmendmentApprovalSerializer(approval).data)


class AmendmentAttachmentViewSet(ScopedViewSet):
    """
    ViewSet for amendment attachments.
    """

    queryset = models.AmendmentAttachment.objects.all()
    serializer_class = serializers.AmendmentAttachmentSerializer
    parser_classes = (MultiPartParser, FormParser)

    def get_queryset(self):
        queryset = super().get_queryset()

        amendment_id = self.request.query_params.get("amendment_id")
        if amendment_id:
            queryset = queryset.filter(amendment_id=amendment_id)

        return queryset.select_related("amendment", "uploaded_by")

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        file = self.request.FILES.get("file")
        extra = {}
        if file:
            extra["file_size"] = file.size
            extra["mime_type"] = file.content_type
        serializer.save(
            scope=scope,
            created_by=self.request.user,
            uploaded_by=self.request.user,
            **extra
        )

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def perform_destroy(self, instance):
        instance.soft_delete()


# =============================================================================
# LINKED DOCUMENT VIEWSETS
# =============================================================================

class LeaseLinkedDocumentViewSet(ScopedViewSet):
    """
    ViewSet for lease linked documents.

    Endpoints:
    - GET /linked-documents/ - List documents
    - POST /linked-documents/ - Upload document
    - GET /linked-documents/{id}/ - Get document details
    - PATCH /linked-documents/{id}/ - Update document
    - DELETE /linked-documents/{id}/ - Delete document
    - GET /linked-documents/expiring/ - Get expiring documents
    - GET /linked-documents/by-agreement/{agreement_id}/ - Get documents for agreement
    """

    queryset = models.LeaseLinkedDocument.objects.all()
    serializer_class = serializers.LeaseLinkedDocumentSerializer
    parser_classes = (MultiPartParser, FormParser)

    def get_serializer_class(self):
        if self.action == "list":
            return serializers.LeaseLinkedDocumentListSerializer
        if self.action == "retrieve":
            return serializers.LeaseLinkedDocumentDetailSerializer
        return serializers.LeaseLinkedDocumentSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by agreement
        agreement_id = self.request.query_params.get("agreement_id")
        if agreement_id:
            queryset = queryset.filter(agreement_id=agreement_id)

        # Filter by category
        category = self.request.query_params.get("category")
        if category:
            queryset = queryset.filter(category=category)

        # Filter by status
        doc_status = self.request.query_params.get("status")
        if doc_status:
            queryset = queryset.filter(status=doc_status)

        # Search
        search = self.request.query_params.get("q")
        if search:
            queryset = queryset.filter(title__icontains=search)

        return queryset.select_related("agreement", "uploaded_by")

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        file = self.request.FILES.get("file")
        extra = {}
        if file:
            extra["file_size"] = file.size
            extra["mime_type"] = file.content_type
        serializer.save(
            scope=scope,
            created_by=self.request.user,
            uploaded_by=self.request.user,
            **extra
        )

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def perform_destroy(self, instance):
        instance.soft_delete()

    @action(detail=False, methods=["get"])
    def expiring(self, request):
        """Get documents expiring within reminder period."""
        scope = self.get_active_scope()
        from datetime import date, timedelta

        today = date.today()
        # Get documents with expiry_date in next 60 days
        expiring_docs = models.LeaseLinkedDocument.objects.filter(
            scope=scope,
            expiry_date__gte=today,
            expiry_date__lte=today + timedelta(days=60),
            is_active=True
        ).order_by("expiry_date")

        serializer = serializers.LeaseLinkedDocumentListSerializer(expiring_docs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def expired(self, request):
        """Get expired documents."""
        scope = self.get_active_scope()
        from datetime import date

        expired_docs = models.LeaseLinkedDocument.objects.filter(
            scope=scope,
            expiry_date__lt=date.today(),
            is_active=True
        ).order_by("-expiry_date")

        serializer = serializers.LeaseLinkedDocumentListSerializer(expired_docs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="by-agreement/(?P<agreement_id>[^/.]+)")
    def by_agreement(self, request, agreement_id=None):
        """Get all linked documents for an agreement."""
        scope = self.get_active_scope()
        documents = models.LeaseLinkedDocument.objects.filter(
            agreement_id=agreement_id,
            scope=scope
        )

        page = self.paginate_queryset(documents)
        if page is not None:
            serializer = serializers.LeaseLinkedDocumentListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = serializers.LeaseLinkedDocumentListSerializer(documents, many=True)
        return Response(serializer.data)


class DocumentApprovalViewSet(ScopedViewSet):
    """
    ViewSet for document approval steps.
    """

    queryset = models.DocumentApproval.objects.all()
    serializer_class = serializers.DocumentApprovalSerializer

    DOC_APPROVE_PERMISSION_CODES = {
        "documents.approve",
        "document.approve",
        "lease.documents.approve",
        "lease.document.approve",
        "leases.documents.approve",
    }

    def _get_active_membership_for_request_user(self):
        from apps.accounts.models import ScopeMembership

        scope = self.get_active_scope()
        if scope is None:
            return None

        return (
            ScopeMembership.objects.filter(
                user=self.request.user,
                scope=scope,
                is_active=True,
            )
            .select_related("role")
            .prefetch_related("role__module_permissions", "role__role_permissions__permission")
            .first()
        )

    def _has_document_approve_permission(self, role):
        from apps.accounts.models import ModulePermission

        if role.role_type == role.RoleType.ADMIN:
            return True

        if role.module_permissions.filter(
            module=ModulePermission.Module.DOCUMENTS,
            can_approve=True,
            is_active=True,
        ).exists():
            return True

        permission_codes = set(
            role.role_permissions.filter(is_active=True).values_list(
                "permission__code", flat=True
            )
        )
        return bool(permission_codes.intersection(self.DOC_APPROVE_PERMISSION_CODES))

    def _validate_document_approval_access(self, approval):
        if self.request.user.is_superuser:
            return

        membership = self._get_active_membership_for_request_user()
        if not membership or not membership.role:
            raise PermissionDenied(
                "You do not have an active role membership in the selected scope to action this approval."
            )

        role = membership.role
        required_role = (approval.approver_role or "").strip()
        if required_role:
            required_role_lower = required_role.lower()
            role_matches = (
                (role.name or "").strip().lower() == required_role_lower
                or (role.code or "").strip().lower() == required_role_lower
            )
            if not role_matches:
                raise PermissionDenied(
                    f"This approval step requires role '{approval.approver_role}'. "
                    f"Your active role is '{role.name}'."
                )

        if approval.approver_id and approval.approver_id != self.request.user.id:
            raise PermissionDenied("This approval step is assigned to a different approver.")

        if not self._has_document_approve_permission(role):
            raise PermissionDenied(
                "Your active role does not have document approval permission."
            )

    def get_queryset(self):
        queryset = super().get_queryset()

        document_id = self.request.query_params.get("document_id")
        if document_id:
            queryset = queryset.filter(document_id=document_id)

        return queryset.select_related("document", "approver")

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        serializer.save(scope=scope, created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=True, methods=["post"])
    def action(self, request, pk=None):
        """Take action on approval step."""
        approval = self.get_object()

        action_type = request.data.get("action")  # "approve" or "reject"
        comments = request.data.get("comments", "")

        if action_type not in ["approve", "reject", "skip"]:
            return Response(
                {"error": "Action must be 'approve', 'reject', or 'skip'"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if approval.status != models.DocumentApproval.ApprovalStatus.PENDING:
            return Response(
                {"error": "Approval step is not pending"},
                status=status.HTTP_400_BAD_REQUEST
            )

        self._validate_document_approval_access(approval)

        if action_type == "approve":
            approval.status = models.DocumentApproval.ApprovalStatus.APPROVED
        elif action_type == "reject":
            approval.status = models.DocumentApproval.ApprovalStatus.REJECTED
        else:
            approval.status = models.DocumentApproval.ApprovalStatus.SKIPPED

        approval.approver = request.user
        approval.actioned_at = timezone.now()
        approval.comments = comments
        approval.updated_by = request.user
        approval.save()

        return Response(serializers.DocumentApprovalSerializer(approval).data)


# =============================================================================
# CLAUSE CONFIGURATION BUNDLE VIEW
# =============================================================================

class LeaseClauseConfigBundleView(ScopedViewSet):
    """
    Bundle endpoint for fetching/updating all clause configurations at once.

    Endpoints:
    - GET /clause-config/{agreement_id}/ - Get all clause configs
    - PATCH /clause-config/{agreement_id}/ - Update all clause configs
    """

    queryset = models.Agreement.objects.all()
    serializer_class = serializers.AgreementSerializer

    def _build_clause_config_response(self, agreement):
        data = {}

        try:
            data["renewal_option"] = serializers.LeaseRenewalOptionSerializer(
                agreement.renewal_option
            ).data
        except models.LeaseRenewalOption.DoesNotExist:
            data["renewal_option"] = None

        try:
            data["sublet_signage"] = serializers.LeaseSubletSignageSerializer(
                agreement.sublet_signage
            ).data
        except models.LeaseSubletSignage.DoesNotExist:
            data["sublet_signage"] = None

        try:
            data["exclusivity"] = serializers.LeaseExclusivitySerializer(
                agreement.exclusivity
            ).data
        except models.LeaseExclusivity.DoesNotExist:
            data["exclusivity"] = None

        try:
            data["insurance_requirement"] = serializers.LeaseInsuranceRequirementSerializer(
                agreement.insurance_requirement
            ).data
        except models.LeaseInsuranceRequirement.DoesNotExist:
            data["insurance_requirement"] = None

        try:
            data["dispute_resolution"] = serializers.LeaseDisputeResolutionSerializer(
                agreement.dispute_resolution
            ).data
        except models.LeaseDisputeResolution.DoesNotExist:
            data["dispute_resolution"] = None

        try:
            data["termination"] = serializers.LeaseTerminationSerializer(
                agreement.termination
            ).data
        except models.LeaseTermination.DoesNotExist:
            data["termination"] = None

        return data

    @action(detail=True, methods=["get", "patch"], url_path="config")
    def config(self, request, pk=None):
        """Get or update all clause configurations for an agreement."""
        agreement = self.get_object()
        scope = self.get_active_scope()

        if request.method == "GET":
            return Response(self._build_clause_config_response(agreement))

        else:  # PATCH
            def sanitize_for_model(data, model_class):
                """Convert empty strings to None for numeric/date fields that accept null."""
                if not isinstance(data, dict):
                    return data
                data = dict(data)
                for field in model_class._meta.get_fields():
                    if not hasattr(field, "null"):
                        continue
                    if field.name not in data or data[field.name] != "":
                        continue
                    # Only convert "" to None for fields that explicitly allow null
                    if getattr(field, "null", False) is True:
                        data[field.name] = None
                return data

            # Update clause configs
            for key, model_class in [
                ("renewal_option", models.LeaseRenewalOption),
                ("sublet_signage", models.LeaseSubletSignage),
                ("exclusivity", models.LeaseExclusivity),
                ("insurance_requirement", models.LeaseInsuranceRequirement),
                ("dispute_resolution", models.LeaseDisputeResolution),
                ("termination", models.LeaseTermination),
            ]:
                if key in request.data:
                    config_data = dict(request.data[key])
                    # Remove read-only fields
                    for field in ["id", "scope", "agreement", "created_at", "updated_at",
                                  "created_by", "updated_by", "is_active", "deleted_at"]:
                        config_data.pop(field, None)
                    config_data = sanitize_for_model(config_data, model_class)

                    model_class.objects.update_or_create(
                        agreement=agreement,
                        defaults={**config_data, "scope": scope, "updated_by": request.user}
                    )

            # Return updated configs
            return Response(self._build_clause_config_response(agreement))
