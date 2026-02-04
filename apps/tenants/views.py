from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q

from apps.core.viewsets import ScopedViewSet
from . import models, serializers


class TenantCompanyViewSet(ScopedViewSet):
    """
    ViewSet for tenant companies.

    Endpoints:
    - GET /companies/ - List all companies
    - POST /companies/ - Create a company
    - GET /companies/{id}/ - Get company details
    - PATCH /companies/{id}/ - Update company
    - DELETE /companies/{id}/ - Soft delete company
    - GET /companies/directory/ - Paginated directory with lease summary
    - GET /companies/leased-summary/ - Summary of tenants with active leases
    """

    queryset = models.TenantCompany.objects.all()
    serializer_class = serializers.TenantCompanySerializer

    def get_serializer_class(self):
        if self.action == "list":
            return serializers.TenantCompanyListSerializer
        if self.action == "retrieve":
            return serializers.TenantCompanyDetailSerializer
        if self.action in ["directory", "leased_summary"]:
            return serializers.TenantCompanyWithLeaseSummarySerializer
        return serializers.TenantCompanySerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        # Apply search filter
        search = self.request.query_params.get("q", "")
        if search:
            queryset = queryset.filter(
                Q(legal_name__icontains=search) |
                Q(trade_name__icontains=search) |
                Q(email__icontains=search)
            )
        # Apply status filter
        status_filter = self.request.query_params.get("status", "")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset.prefetch_related("contacts").select_related()

    @action(detail=False, methods=["get"])
    def directory(self, request):
        """Paginated directory of all tenant companies with lease summary."""
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="leased-summary")
    def leased_summary(self, request):
        """Get summary of tenants with active leases."""
        # This will be enhanced when leases app is integrated
        queryset = self.get_queryset().filter(status=models.TenantCompany.Status.ACTIVE)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        serializer.save(scope=scope, created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def perform_destroy(self, instance):
        # Soft delete
        instance.soft_delete()


class TenantContactViewSet(ScopedViewSet):
    """
    ViewSet for tenant contacts.
    """

    queryset = models.TenantContact.objects.all()
    serializer_class = serializers.TenantContactSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        # Filter by company if provided
        company_id = self.request.query_params.get("company_id", "")
        if company_id:
            queryset = queryset.filter(company_id=company_id)
        return queryset.select_related("company")

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        serializer.save(scope=scope, created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def perform_destroy(self, instance):
        instance.soft_delete()


class TenantKYCViewSet(ScopedViewSet):
    """
    ViewSet for tenant KYC documents.
    """

    queryset = models.TenantKYC.objects.all()
    serializer_class = serializers.TenantKYCSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        # Filter by company if provided
        company_id = self.request.query_params.get("company_id", "")
        if company_id:
            queryset = queryset.filter(company_id=company_id)
        return queryset.select_related("company")

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        serializer.save(scope=scope, created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        """Mark KYC as verified."""
        from django.utils import timezone
        instance = self.get_object()
        instance.kyc_status = models.TenantKYC.KYCStatus.VERIFIED
        instance.verified_at = timezone.now()
        instance.verified_by = request.user
        instance.save()
        return Response(self.get_serializer(instance).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        """Mark KYC as rejected."""
        instance = self.get_object()
        instance.kyc_status = models.TenantKYC.KYCStatus.REJECTED
        instance.rejection_reason = request.data.get("reason", "")
        instance.save()
        return Response(self.get_serializer(instance).data)


class TenantPreferencesViewSet(ScopedViewSet):
    """
    ViewSet for tenant preferences.
    """

    queryset = models.TenantPreferences.objects.all()
    serializer_class = serializers.TenantPreferencesSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        # Filter by company if provided
        company_id = self.request.query_params.get("company_id", "")
        if company_id:
            queryset = queryset.filter(company_id=company_id)
        return queryset.select_related("company")

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        serializer.save(scope=scope, created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)
