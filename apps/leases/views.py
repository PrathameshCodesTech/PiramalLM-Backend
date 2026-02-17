from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from django.db.models import Q, Sum
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
            escalation_type=original.escalation_type,
            frequency=original.frequency,
            fixed_percent=original.fixed_percent,
            index_type=original.index_type,
            base_value=original.base_value,
            cap_percent=original.cap_percent,
            floor_percent=original.floor_percent,
            rounding_rule=original.rounding_rule,
            steps_json=original.steps_json,
            applicability=original.applicability,
            notes=original.notes,
            status=models.EscalationTemplate.TemplateStatus.DRAFT,
            created_by=request.user
        )

        return Response(
            serializers.EscalationTemplateSerializer(cloned).data,
            status=status.HTTP_201_CREATED
        )


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
        )

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        serializer.save(scope=scope, created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def perform_destroy(self, instance):
        instance.soft_delete()

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

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        """Submit agreement for approval."""
        agreement = self.get_object()
        if agreement.status != models.Agreement.Status.DRAFT:
            return Response(
                {"error": "Only draft agreements can be submitted"},
                status=status.HTTP_400_BAD_REQUEST
            )
        agreement.status = models.Agreement.Status.PENDING
        agreement.updated_by = request.user
        agreement.save()
        return Response(serializers.AgreementSerializer(agreement).data)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        """Activate a pending agreement."""
        agreement = self.get_object()
        if agreement.status != models.Agreement.Status.PENDING:
            return Response(
                {"error": "Only pending agreements can be activated"},
                status=status.HTTP_400_BAD_REQUEST
            )
        agreement.status = models.Agreement.Status.ACTIVE
        agreement.updated_by = request.user
        agreement.save()
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
        """Submit amendment for review."""
        amendment = self.get_object()
        if amendment.approval_status != models.LeaseAmendment.ApprovalStatus.DRAFT:
            return Response(
                {"error": "Only draft amendments can be submitted"},
                status=status.HTTP_400_BAD_REQUEST
            )
        amendment.approval_status = models.LeaseAmendment.ApprovalStatus.PENDING_REVIEW
        amendment.updated_by = request.user
        amendment.save()
        return Response(serializers.LeaseAmendmentSerializer(amendment).data)

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
        """Execute approved amendment."""
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

        # Update agreement version
        agreement = amendment.agreement
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
                    config_data = request.data[key]
                    # Remove read-only fields
                    for field in ["id", "scope", "agreement", "created_at", "updated_at",
                                  "created_by", "updated_by", "is_active", "deleted_at"]:
                        config_data.pop(field, None)

                    model_class.objects.update_or_create(
                        agreement=agreement,
                        defaults={**config_data, "scope": scope, "updated_by": request.user}
                    )

            # Return updated configs
            return Response(self._build_clause_config_response(agreement))
