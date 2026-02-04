from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q, Sum

from apps.core.viewsets import ScopedViewSet
from . import models, serializers


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
            "unit_allocations", "unit_allocations__unit"
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
    ViewSet for unit allocations.
    """

    queryset = models.UnitAllocation.objects.all()
    serializer_class = serializers.UnitAllocationSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        agreement_id = self.request.query_params.get("agreement_id", "")
        unit_id = self.request.query_params.get("unit_id", "")

        if agreement_id:
            queryset = queryset.filter(agreement_id=agreement_id)
        if unit_id:
            queryset = queryset.filter(unit_id=unit_id)

        return queryset.select_related("agreement", "unit")

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
                for unit in floor.units.filter(is_active=True).order_by("unit_no"):
                    # Check active allocations
                    active_allocations = models.UnitAllocation.objects.filter(
                        unit=unit,
                        agreement__status=models.Agreement.Status.ACTIVE,
                        is_active=True
                    ).aggregate(
                        total_allocated=Sum("allocated_area_sqft")
                    )

                    allocated = float(active_allocations["total_allocated"] or 0)
                    leasable = float(unit.leasable_area_sqft or 0)
                    available = max(0, leasable - allocated)

                    units_data.append({
                        "id": unit.id,
                        "unit_no": unit.unit_no,
                        "unit_type": unit.unit_type,
                        "leasable_area_sqft": leasable,
                        "builtup_area_sqft": float(unit.builtup_area_sqft or 0),
                        "allocated_area_sqft": allocated,
                        "available_area_sqft": available,
                        "is_divisible": getattr(unit, "is_divisible", False),
                        "status": unit.status,
                    })

                floors_data.append({
                    "id": floor.id,
                    "number": floor.number,
                    "label": floor.label,
                    "total_area_sqft": float(floor.total_area_sqft or 0),
                    "leasable_area_sqft": float(floor.leasable_area_sqft or 0),
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