from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.shortcuts import get_object_or_404
from decimal import Decimal

from apps.core.viewsets import ScopedViewSet, InheritableScopedViewSet
from . import models, serializers


# =============================================================================
# AGEING CONFIG VIEWS (Tab 4 - Ageing Logic)
# =============================================================================

class AgeingConfigViewSet(ScopedViewSet):
    """
    ViewSet for ageing configuration (scope-level).

    Endpoints:
    - GET /ageing-config/ - Get ageing config for scope
    - POST /ageing-config/ - Create ageing config
    - PATCH /ageing-config/ - Update ageing config
    """

    queryset = models.AgeingConfig.objects.all()
    serializer_class = serializers.AgeingConfigSerializer

    def get_serializer_class(self):
        if self.action in ["update", "partial_update"]:
            return serializers.AgeingConfigUpdateSerializer
        return serializers.AgeingConfigSerializer

    def list(self, request):
        """Get ageing config for current scope (returns single object)."""
        scope = self.get_active_scope()
        try:
            config = models.AgeingConfig.objects.get(scope=scope)
            serializer = self.get_serializer(config)
            return Response(serializer.data)
        except models.AgeingConfig.DoesNotExist:
            return Response(
                {"detail": "Ageing config not found. Use POST to create."},
                status=status.HTTP_404_NOT_FOUND
            )

    def create(self, request):
        """Create ageing config for scope."""
        scope = self.get_active_scope()

        # Check if already exists
        if models.AgeingConfig.objects.filter(scope=scope).exists():
            return Response(
                {"error": "Ageing config already exists for this scope. Use PATCH to update."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(scope=scope, created_by=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["patch"])
    def update_config(self, request):
        """Update ageing config for scope."""
        scope = self.get_active_scope()
        config, created = models.AgeingConfig.objects.get_or_create(
            scope=scope,
            defaults={"created_by": request.user}
        )

        serializer = serializers.AgeingConfigUpdateSerializer(
            config, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user)
        return Response(serializer.data)


# =============================================================================
# SITE BILLING CONFIG VIEWS (Tab 1 - Billing & Invoice Rules)
# =============================================================================

class SiteBillingConfigViewSet(ScopedViewSet):
    """
    ViewSet for site-level billing configuration.

    Endpoints:
    - GET /site-billing-configs/ - List all site configs
    - POST /site-billing-configs/ - Create site config
    - GET /site-billing-configs/{id}/ - Get config details
    - PATCH /site-billing-configs/{id}/ - Update config
    - DELETE /site-billing-configs/{id}/ - Delete config
    - GET /site-billing-configs/by-site/{site_id}/ - Get config for site
    - POST /site-billing-configs/{id}/reset-counter/ - Reset invoice counter
    """

    queryset = models.SiteBillingConfig.objects.all()
    serializer_class = serializers.SiteBillingConfigSerializer

    def get_serializer_class(self):
        if self.action == "list":
            return serializers.SiteBillingConfigListSerializer
        if self.action == "retrieve":
            return serializers.SiteBillingConfigDetailSerializer
        if self.action == "create":
            return serializers.SiteBillingConfigCreateSerializer
        return serializers.SiteBillingConfigSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.select_related("site")

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        serializer.save(scope=scope, created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=False, methods=["get"], url_path="by-site/(?P<site_id>[^/.]+)")
    def by_site(self, request, site_id=None):
        """Get billing config for a specific site."""
        scope = self.get_active_scope()
        try:
            config = models.SiteBillingConfig.objects.get(
                site_id=site_id,
                scope=scope
            )
            serializer = serializers.SiteBillingConfigDetailSerializer(config)
            return Response(serializer.data)
        except models.SiteBillingConfig.DoesNotExist:
            return Response(
                {"error": "Billing config not found for this site"},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=True, methods=["post"], url_path="reset-counter")
    def reset_counter(self, request, pk=None):
        """Reset invoice counter for site."""
        config = self.get_object()
        new_value = request.data.get("value", 1)
        config.current_counter = new_value
        config.save(update_fields=["current_counter"])
        serializer = serializers.SiteBillingConfigDetailSerializer(config)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="preview-invoice-number")
    def preview_invoice_number(self, request, pk=None):
        """Preview next invoice number without incrementing counter."""
        config = self.get_object()
        from datetime import datetime
        now = datetime.now()

        pattern = config.invoice_pattern
        preview = pattern

        if config.include_property_code:
            preview = preview.replace("{PROP}", config.site.code)
        else:
            preview = preview.replace("{PROP}/", "").replace("{PROP}", "")

        if config.include_year_token:
            preview = preview.replace("{YEAR}", str(now.year))
        else:
            preview = preview.replace("{YEAR}/", "").replace("{YEAR}", "")

        preview = preview.replace("{MONTH}", f"{now.month:02d}")
        counter_str = str(config.current_counter).zfill(config.counter_padding)
        preview = preview.replace("{COUNTER}", counter_str)

        return Response({
            "current_counter": config.current_counter,
            "next_invoice_number": preview
        })


# =============================================================================
# BILLING RULE VIEWS (Tab 1 - Rules List)
# =============================================================================

class BillingRuleViewSet(InheritableScopedViewSet):
    """
    ViewSet for billing rules.

    Uses InheritableScopedViewSet for upward visibility:
    - ENTITY scope sees ENTITY + COMPANY + ORG rules
    - COMPANY scope sees COMPANY + ORG rules
    - ORG scope sees ORG rules only

    Endpoints:
    - GET /billing-rules/ - List all rules (includes inherited from parent scopes)
    - POST /billing-rules/ - Create rule
    - GET /billing-rules/{id}/ - Get rule details
    - PATCH /billing-rules/{id}/ - Update rule
    - DELETE /billing-rules/{id}/ - Delete rule
    - POST /billing-rules/{id}/activate/ - Activate rule
    - POST /billing-rules/{id}/deactivate/ - Deactivate rule
    - POST /billing-rules/{id}/clone/ - Clone rule
    """

    queryset = models.BillingRule.objects.all()
    serializer_class = serializers.BillingRuleSerializer

    def get_serializer_class(self):
        if self.action == "list":
            return serializers.BillingRuleListSerializer
        if self.action == "retrieve":
            return serializers.BillingRuleDetailSerializer
        return serializers.BillingRuleSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by category
        category = self.request.query_params.get("category")
        if category:
            queryset = queryset.filter(category=category)

        # Filter by applies_to
        applies_to = self.request.query_params.get("applies_to")
        if applies_to:
            queryset = queryset.filter(applies_to=applies_to)

        # Filter by status
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset.select_related("owner")

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        serializer.save(
            scope=scope,
            created_by=self.request.user,
            owner=self.request.user
        )

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        """Activate a billing rule."""
        rule = self.get_object()
        rule.status = models.BillingRule.RuleStatus.ACTIVE
        rule.save()
        serializer = self.get_serializer(rule)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        """Deactivate a billing rule."""
        rule = self.get_object()
        rule.status = models.BillingRule.RuleStatus.INACTIVE
        rule.save()
        serializer = self.get_serializer(rule)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def clone(self, request, pk=None):
        """Clone a billing rule."""
        original = self.get_object()
        scope = self.get_active_scope()

        # Create copy
        cloned = models.BillingRule.objects.create(
            scope=scope,
            name=f"{original.name} (Copy)",
            description=original.description,
            category=original.category,
            applies_to=original.applies_to,
            status=models.BillingRule.RuleStatus.DRAFT,
            rule_config=original.rule_config,
            owner=request.user,
            created_by=request.user
        )

        serializer = self.get_serializer(cloned)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


# =============================================================================
# DISPUTE RULE VIEWS (Tab 5 - AR Rules)
# =============================================================================

class DisputeRuleViewSet(InheritableScopedViewSet):
    """
    ViewSet for dispute rules.

    Uses InheritableScopedViewSet for upward visibility:
    - Child scopes see rules from parent scopes

    Endpoints:
    - GET /dispute-rules/ - List all rules (includes inherited from parent scopes)
    - POST /dispute-rules/ - Create rule
    - GET /dispute-rules/{id}/ - Get rule details
    - PATCH /dispute-rules/{id}/ - Update rule
    - DELETE /dispute-rules/{id}/ - Delete rule
    - POST /dispute-rules/{id}/activate/ - Activate rule
    - POST /dispute-rules/{id}/deactivate/ - Deactivate rule
    - POST /dispute-rules/reorder/ - Reorder priorities
    """

    queryset = models.DisputeRule.objects.all()
    serializer_class = serializers.DisputeRuleSerializer

    def get_serializer_class(self):
        if self.action == "list":
            return serializers.DisputeRuleListSerializer
        if self.action == "retrieve":
            return serializers.DisputeRuleDetailSerializer
        return serializers.DisputeRuleSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by status
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Filter by condition type
        condition_type = self.request.query_params.get("condition_type")
        if condition_type:
            queryset = queryset.filter(condition_type=condition_type)

        return queryset.select_related("route_to_user")

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        # Set priority to max + 1
        max_priority = models.DisputeRule.objects.filter(scope=scope).aggregate(
            max_p=models.models.Max("priority")
        )["max_p"] or 0
        serializer.save(
            scope=scope,
            created_by=self.request.user,
            priority=max_priority + 1
        )

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        """Activate a dispute rule."""
        rule = self.get_object()
        rule.status = models.DisputeRule.RuleStatus.ACTIVE
        rule.save()
        serializer = self.get_serializer(rule)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        """Deactivate a dispute rule."""
        rule = self.get_object()
        rule.status = models.DisputeRule.RuleStatus.INACTIVE
        rule.save()
        serializer = self.get_serializer(rule)
        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    def reorder(self, request):
        """Reorder dispute rule priorities."""
        scope = self.get_active_scope()
        order = request.data.get("order", [])  # List of rule IDs in priority order

        for idx, rule_id in enumerate(order, start=1):
            models.DisputeRule.objects.filter(
                id=rule_id, scope=scope
            ).update(priority=idx)

        rules = models.DisputeRule.objects.filter(scope=scope).order_by("priority")
        serializer = serializers.DisputeRuleListSerializer(rules, many=True)
        return Response(serializer.data)


# =============================================================================
# CREDIT RULE VIEWS (Tab 5 - AR Rules)
# =============================================================================

class CreditRuleViewSet(InheritableScopedViewSet):
    """
    ViewSet for credit rules.

    Uses InheritableScopedViewSet for upward visibility:
    - Child scopes see rules from parent scopes

    Endpoints:
    - GET /credit-rules/ - List all rules (includes inherited from parent scopes)
    - POST /credit-rules/ - Create rule
    - GET /credit-rules/{id}/ - Get rule details
    - PATCH /credit-rules/{id}/ - Update rule
    - DELETE /credit-rules/{id}/ - Delete rule
    - POST /credit-rules/{id}/activate/ - Activate rule
    - POST /credit-rules/{id}/deactivate/ - Deactivate rule
    """

    queryset = models.CreditRule.objects.all()
    serializer_class = serializers.CreditRuleSerializer

    def get_serializer_class(self):
        if self.action == "list":
            return serializers.CreditRuleListSerializer
        if self.action == "retrieve":
            return serializers.CreditRuleDetailSerializer
        return serializers.CreditRuleSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by status
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Filter by trigger type
        trigger_type = self.request.query_params.get("trigger_type")
        if trigger_type:
            queryset = queryset.filter(trigger_type=trigger_type)

        # Filter by approval level
        approval_level = self.request.query_params.get("approval_level")
        if approval_level:
            queryset = queryset.filter(approval_level=approval_level)

        return queryset

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        serializer.save(scope=scope, created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        """Activate a credit rule."""
        rule = self.get_object()
        rule.status = models.CreditRule.RuleStatus.ACTIVE
        rule.save()
        serializer = self.get_serializer(rule)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        """Deactivate a credit rule."""
        rule = self.get_object()
        rule.status = models.CreditRule.RuleStatus.INACTIVE
        rule.save()
        serializer = self.get_serializer(rule)
        return Response(serializer.data)


# =============================================================================
# AR GLOBAL SETTINGS VIEWS (Tab 5 - Toggle Switches)
# =============================================================================

class ARGlobalSettingsViewSet(ScopedViewSet):
    """
    ViewSet for AR global settings (scope-level).

    Endpoints:
    - GET /ar-global-settings/ - Get settings for scope
    - POST /ar-global-settings/ - Create settings
    - PATCH /ar-global-settings/ - Update settings
    """

    queryset = models.ARGlobalSettings.objects.all()
    serializer_class = serializers.ARGlobalSettingsSerializer

    def get_serializer_class(self):
        if self.action in ["update", "partial_update", "update_settings"]:
            return serializers.ARGlobalSettingsUpdateSerializer
        return serializers.ARGlobalSettingsSerializer

    def list(self, request):
        """Get AR settings for current scope (returns single object)."""
        scope = self.get_active_scope()
        try:
            settings = models.ARGlobalSettings.objects.get(scope=scope)
            serializer = self.get_serializer(settings)
            return Response(serializer.data)
        except models.ARGlobalSettings.DoesNotExist:
            return Response(
                {"detail": "AR settings not found. Use POST to create."},
                status=status.HTTP_404_NOT_FOUND
            )

    def create(self, request):
        """Create AR settings for scope."""
        scope = self.get_active_scope()

        if models.ARGlobalSettings.objects.filter(scope=scope).exists():
            return Response(
                {"error": "AR settings already exist for this scope. Use PATCH to update."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(scope=scope, created_by=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["patch"], url_path="update")
    def update_settings(self, request):
        """Update AR settings for scope."""
        scope = self.get_active_scope()
        settings, created = models.ARGlobalSettings.objects.get_or_create(
            scope=scope,
            defaults={"created_by": request.user}
        )

        serializer = serializers.ARGlobalSettingsUpdateSerializer(
            settings, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user)
        return Response(serializer.data)


# =============================================================================
# BILLING CONFIGURATION BUNDLE VIEW
# =============================================================================

class BillingConfigBundleView(APIView):
    """
    Get all billing configuration for a scope in one request.

    GET /api/billing/config/
    Returns: ageing_config, ageing_buckets, ar_global_settings, dispute_rules, credit_rules, billing_rules
    """

    def get_active_scope(self):
        """Get scope from request header."""
        from apps.core.models import TenantScope
        scope_id = self.request.headers.get("X-Scope-ID") or self.request.headers.get("X-Tenant-Scope")
        if not scope_id:
            return None
        try:
            return TenantScope.objects.get(id=scope_id)
        except TenantScope.DoesNotExist:
            return None

    def get(self, request):
        scope = self.get_active_scope()
        if not scope:
            return Response(
                {"error": "X-Scope-ID header required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Ageing config
        ageing_config = None
        try:
            ageing_config = models.AgeingConfig.objects.get(scope=scope)
        except models.AgeingConfig.DoesNotExist:
            pass

        # Ageing buckets
        ageing_buckets = models.AgeingBucket.objects.filter(scope=scope)

        # AR global settings
        ar_settings = None
        try:
            ar_settings = models.ARGlobalSettings.objects.get(scope=scope)
        except models.ARGlobalSettings.DoesNotExist:
            pass

        # Rules
        dispute_rules = models.DisputeRule.objects.filter(scope=scope)
        credit_rules = models.CreditRule.objects.filter(scope=scope)
        billing_rules = models.BillingRule.objects.filter(scope=scope)

        return Response({
            "ageing_config": serializers.AgeingConfigSerializer(ageing_config).data if ageing_config else None,
            "ageing_buckets": serializers.AgeingBucketListSerializer(ageing_buckets, many=True).data,
            "ar_global_settings": serializers.ARGlobalSettingsSerializer(ar_settings).data if ar_settings else None,
            "dispute_rules": serializers.DisputeRuleListSerializer(dispute_rules, many=True).data,
            "credit_rules": serializers.CreditRuleListSerializer(credit_rules, many=True).data,
            "billing_rules": serializers.BillingRuleListSerializer(billing_rules, many=True).data,
        })


class SiteBillingConfigBundleView(APIView):
    """
    Get all billing configuration for a specific site.

    GET /api/billing/site/{site_id}/config/
    Returns: site_billing_config + scope_config (ageing, ar_settings, rules)
    """

    def get_active_scope(self):
        from apps.core.models import TenantScope
        scope_id = self.request.headers.get("X-Scope-ID") or self.request.headers.get("X-Tenant-Scope")
        if not scope_id:
            return None
        try:
            return TenantScope.objects.get(id=scope_id)
        except TenantScope.DoesNotExist:
            return None

    def get(self, request, site_id):
        scope = self.get_active_scope()
        if not scope:
            return Response(
                {"error": "X-Scope-ID header required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Site billing config
        try:
            site_config = models.SiteBillingConfig.objects.select_related("site").get(
                site_id=site_id, scope=scope
            )
        except models.SiteBillingConfig.DoesNotExist:
            return Response(
                {"error": "Billing config not found for this site"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Scope-level config
        ageing_config = None
        try:
            ageing_config = models.AgeingConfig.objects.get(scope=scope)
        except models.AgeingConfig.DoesNotExist:
            pass

        ar_settings = None
        try:
            ar_settings = models.ARGlobalSettings.objects.get(scope=scope)
        except models.ARGlobalSettings.DoesNotExist:
            pass

        return Response({
            "site_billing_config": serializers.SiteBillingConfigDetailSerializer(site_config).data,
            "scope_config": {
                "ageing_config": serializers.AgeingConfigSerializer(ageing_config).data if ageing_config else None,
                "ageing_buckets": serializers.AgeingBucketListSerializer(
                    models.AgeingBucket.objects.filter(scope=scope), many=True
                ).data,
                "ar_global_settings": serializers.ARGlobalSettingsSerializer(ar_settings).data if ar_settings else None,
            }
        })


class AgeingBucketViewSet(InheritableScopedViewSet):
    """
    ViewSet for ageing bucket configuration.

    Uses InheritableScopedViewSet for upward visibility:
    - Child scopes see buckets from parent scopes

    Endpoints:
    - GET /ageing-buckets/ - List all ageing buckets (includes inherited from parent scopes)
    - POST /ageing-buckets/ - Create ageing bucket
    - GET /ageing-buckets/{id}/ - Get bucket details
    - PATCH /ageing-buckets/{id}/ - Update bucket
    - DELETE /ageing-buckets/{id}/ - Delete bucket
    - POST /ageing-buckets/initialize-defaults/ - Create default buckets
    """

    queryset = models.AgeingBucket.objects.all()
    serializer_class = serializers.AgeingBucketSerializer

    def get_serializer_class(self):
        if self.action == "list":
            return serializers.AgeingBucketListSerializer
        return serializers.AgeingBucketSerializer

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        serializer.save(scope=scope, created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=False, methods=["post"], url_path="initialize-defaults")
    def initialize_defaults(self, request):
        """Create default ageing buckets for the scope."""
        scope = self.get_active_scope()

        # Check if buckets already exist
        if models.AgeingBucket.objects.filter(scope=scope).exists():
            return Response(
                {"error": "Ageing buckets already exist for this scope"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Create default buckets
        defaults = [
            {"label": "Current", "from_days": 0, "to_days": 30, "sort_order": 1, "color_code": "#10B981"},
            {"label": "31-60 Days", "from_days": 31, "to_days": 60, "sort_order": 2, "color_code": "#F59E0B"},
            {"label": "61-90 Days", "from_days": 61, "to_days": 90, "sort_order": 3, "color_code": "#EF4444"},
            {"label": "90+ Days", "from_days": 91, "to_days": None, "sort_order": 4, "color_code": "#991B1B"},
        ]

        created_buckets = []
        for bucket_data in defaults:
            bucket = models.AgeingBucket.objects.create(
                scope=scope,
                created_by=request.user,
                **bucket_data
            )
            created_buckets.append(bucket)

        serializer = serializers.AgeingBucketListSerializer(created_buckets, many=True)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ARRuleViewSet(ScopedViewSet):
    """
    ViewSet for AR rules.

    Endpoints:
    - GET /ar-rules/ - List all AR rules
    - POST /ar-rules/ - Create AR rule
    - GET /ar-rules/{id}/ - Get rule details
    - PATCH /ar-rules/{id}/ - Update rule
    - DELETE /ar-rules/{id}/ - Delete rule
    - GET /ar-rules/by-agreement/{agreement_id}/ - Get rules for agreement
    """

    queryset = models.ARRule.objects.all()
    serializer_class = serializers.ARRuleSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        agreement_id = self.request.query_params.get("agreement_id")
        if agreement_id:
            queryset = queryset.filter(agreement_id=agreement_id)
        return queryset.select_related("agreement")

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        serializer.save(scope=scope, created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=False, methods=["get"], url_path="by-agreement/(?P<agreement_id>[^/.]+)")
    def by_agreement(self, request, agreement_id=None):
        """Get AR rules for a specific agreement."""
        scope = self.get_active_scope()
        try:
            ar_rule = models.ARRule.objects.get(
                agreement_id=agreement_id,
                scope=scope
            )
            serializer = self.get_serializer(ar_rule)
            return Response(serializer.data)
        except models.ARRule.DoesNotExist:
            return Response(
                {"error": "AR rules not found for this agreement"},
                status=status.HTTP_404_NOT_FOUND
            )


class InvoiceViewSet(ScopedViewSet):
    """
    ViewSet for invoices.

    Endpoints:
    - GET /invoices/ - List all invoices
    - POST /invoices/ - Create invoice
    - GET /invoices/{id}/ - Get invoice details
    - PATCH /invoices/{id}/ - Update invoice
    - DELETE /invoices/{id}/ - Delete invoice
    - POST /invoices/{id}/send/ - Send invoice
    - POST /invoices/{id}/dispute/ - Mark as disputed
    - POST /invoices/{id}/resolve-dispute/ - Resolve dispute
    - GET /invoices/overdue/ - List overdue invoices
    - GET /invoices/summary/ - Get invoice summary stats
    """

    queryset = models.Invoice.objects.all()
    serializer_class = serializers.InvoiceSerializer

    def get_serializer_class(self):
        if self.action == "list":
            return serializers.InvoiceListSerializer
        if self.action == "retrieve":
            return serializers.InvoiceDetailSerializer
        if self.action == "create":
            return serializers.InvoiceCreateSerializer
        if self.action in ("update", "partial_update"):
            return serializers.InvoiceUpdateSerializer
        return serializers.InvoiceSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by agreement
        agreement_id = self.request.query_params.get("agreement_id")
        if agreement_id:
            queryset = queryset.filter(agreement_id=agreement_id)

        # Filter by status
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Filter by invoice type
        invoice_type = self.request.query_params.get("invoice_type")
        if invoice_type:
            queryset = queryset.filter(invoice_type=invoice_type)

        # Filter by date range
        from_date = self.request.query_params.get("from_date")
        to_date = self.request.query_params.get("to_date")
        if from_date:
            queryset = queryset.filter(invoice_date__gte=from_date)
        if to_date:
            queryset = queryset.filter(invoice_date__lte=to_date)

        # Filter overdue
        if self.request.query_params.get("overdue") == "true":
            today = timezone.now().date()
            queryset = queryset.filter(
                due_date__lt=today,
                balance_due__gt=0
            )

        # Filter by property/site
        site_ids = self.request.query_params.get("site_ids") or self.request.query_params.get("property_ids")
        if site_ids:
            ids = [x.strip() for x in str(site_ids).split(",") if x.strip()]
            if ids:
                queryset = queryset.filter(agreement__site_id__in=ids)

        # Filter by tenant
        tenant_ids = self.request.query_params.get("tenant_ids")
        if tenant_ids:
            ids = [x.strip() for x in str(tenant_ids).split(",") if x.strip()]
            if ids:
                queryset = queryset.filter(agreement__tenant_id__in=ids)

        return queryset.select_related("agreement", "agreement__tenant", "agreement__site")

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        serializer.save(scope=scope, created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        """Send invoice to tenant."""
        invoice = self.get_object()
        if invoice.status == models.Invoice.InvoiceStatus.DRAFT:
            invoice.status = models.Invoice.InvoiceStatus.SENT
            invoice.save()
        serializer = self.get_serializer(invoice)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def dispute(self, request, pk=None):
        """Mark invoice as disputed."""
        invoice = self.get_object()
        invoice.is_disputed = True
        invoice.dispute_reason = request.data.get("reason", "")
        invoice.disputed_at = timezone.now()
        invoice.disputed_by = request.user
        invoice.status = models.Invoice.InvoiceStatus.DISPUTED
        invoice.save()
        serializer = self.get_serializer(invoice)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="resolve-dispute")
    def resolve_dispute(self, request, pk=None):
        """Resolve invoice dispute."""
        invoice = self.get_object()
        invoice.is_disputed = False
        invoice.status = models.Invoice.InvoiceStatus.PENDING
        if invoice.balance_due <= 0:
            invoice.status = models.Invoice.InvoiceStatus.PAID
        invoice.save()
        serializer = self.get_serializer(invoice)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def overdue(self, request):
        """List overdue invoices."""
        scope = self.get_active_scope()
        today = timezone.now().date()
        queryset = models.Invoice.objects.filter(
            scope=scope,
            due_date__lt=today,
            balance_due__gt=0
        ).select_related("agreement", "agreement__tenant")

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = serializers.InvoiceListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = serializers.InvoiceListSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Get invoice summary statistics."""
        scope = self.get_active_scope()
        today = timezone.now().date()

        queryset = models.Invoice.objects.filter(scope=scope)

        stats = queryset.aggregate(
            total_invoiced=Sum("total_amount"),
            total_paid=Sum("amount_paid"),
            total_outstanding=Sum("balance_due"),
        )

        overdue_stats = queryset.filter(
            due_date__lt=today,
            balance_due__gt=0
        ).aggregate(
            total_overdue=Sum("balance_due"),
            overdue_count=Count("id"),
        )

        disputed_stats = queryset.filter(
            is_disputed=True
        ).aggregate(
            disputed_amount=Sum("balance_due"),
            disputed_count=Count("id"),
        )

        return Response({
            "total_invoiced": float(stats["total_invoiced"] or 0),
            "total_paid": float(stats["total_paid"] or 0),
            "total_outstanding": float(stats["total_outstanding"] or 0),
            "total_overdue": float(overdue_stats["total_overdue"] or 0),
            "overdue_count": overdue_stats["overdue_count"] or 0,
            "disputed_amount": float(disputed_stats["disputed_amount"] or 0),
            "disputed_count": disputed_stats["disputed_count"] or 0,
        })

    @action(detail=False, methods=["post"])
    def bulk_email(self, request):
        """Send email for selected invoices."""
        invoice_ids = request.data.get("invoice_ids", [])
        if not invoice_ids:
            return Response({"error": "invoice_ids required"}, status=status.HTTP_400_BAD_REQUEST)
        scope = self.get_active_scope()
        qs = models.Invoice.objects.filter(scope=scope, id__in=invoice_ids)
        count = qs.count()
        return Response({"message": f"Email queued for {count} invoice(s)"})

    @action(detail=False, methods=["get"])
    def export(self, request):
        """Export invoice list to CSV."""
        import csv
        from django.http import HttpResponse
        scope = self.get_active_scope()
        qs = models.Invoice.objects.filter(scope=scope).select_related(
            "agreement", "agreement__tenant"
        ).order_by("-invoice_date")

        from_date = request.query_params.get("from_date")
        to_date = request.query_params.get("to_date")
        status_filter = request.query_params.get("status")
        if from_date:
            qs = qs.filter(invoice_date__gte=from_date)
        if to_date:
            qs = qs.filter(invoice_date__lte=to_date)
        if status_filter:
            qs = qs.filter(status=status_filter)

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = "attachment; filename=invoices.csv"
        writer = csv.writer(response)
        writer.writerow([
            "Invoice No", "Issue Date", "Due Date", "Tenant", "Lease ID",
            "Period", "Subtotal", "Tax", "Total Due", "Status"
        ])
        for inv in qs[:10000]:
            period = f"{inv.period_start} to {inv.period_end}" if inv.period_start and inv.period_end else ""
            writer.writerow([
                inv.invoice_number,
                inv.invoice_date,
                inv.due_date,
                inv.agreement.tenant.legal_name if inv.agreement and inv.agreement.tenant else "",
                inv.agreement.lease_id if inv.agreement else "",
                period,
                inv.subtotal,
                inv.tax_amount,
                inv.total_amount,
                inv.status,
            ])
        return response


class InvoiceAttachmentViewSet(ScopedViewSet):
    """
    ViewSet for invoice attachments.
    - GET /invoice-attachments/ - List (filter by invoice_id)
    - POST /invoice-attachments/ - Upload (multipart: file, invoice)
    - GET /invoice-attachments/{id}/ - Get
    - GET /invoice-attachments/{id}/download/ - Download file
    - DELETE /invoice-attachments/{id}/ - Delete
    """
    queryset = models.InvoiceAttachment.objects.all()
    serializer_class = serializers.InvoiceAttachmentSerializer

    def get_serializer_class(self):
        if self.action == "list":
            return serializers.InvoiceAttachmentListSerializer
        return serializers.InvoiceAttachmentSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        invoice_id = self.request.query_params.get("invoice_id")
        if invoice_id:
            queryset = queryset.filter(invoice_id=invoice_id)
        return queryset.select_related("invoice")

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        serializer.save(scope=scope, created_by=self.request.user)

    def create(self, request, *args, **kwargs):
        file_obj = request.FILES.get("file")
        invoice_id = request.data.get("invoice")
        if not file_obj or not invoice_id:
            return Response(
                {"error": "file and invoice are required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        scope = self.get_active_scope()
        invoice = get_object_or_404(models.Invoice, id=invoice_id, scope=scope)
        att = models.InvoiceAttachment.objects.create(
            invoice=invoice,
            scope=scope,
            created_by=request.user,
            file=file_obj,
            filename=file_obj.name,
            file_size=file_obj.size,
        )
        ser = serializers.InvoiceAttachmentListSerializer(att)
        return Response(ser.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        from django.http import FileResponse
        att = self.get_object()
        return FileResponse(att.file.open("rb"), as_attachment=True, filename=att.filename)


class PaymentViewSet(ScopedViewSet):
    """
    ViewSet for payments.

    Endpoints:
    - GET /payments/ - List all payments
    - POST /payments/ - Record payment
    - GET /payments/{id}/ - Get payment details
    - PATCH /payments/{id}/ - Update payment
    - DELETE /payments/{id}/ - Delete payment
    - POST /payments/{id}/reverse/ - Reverse payment
    """

    queryset = models.Payment.objects.all()
    serializer_class = serializers.PaymentSerializer

    def get_serializer_class(self):
        if self.action == "list":
            return serializers.PaymentListSerializer
        if self.action == "retrieve":
            return serializers.PaymentDetailSerializer
        if self.action == "create":
            return serializers.PaymentCreateSerializer
        return serializers.PaymentSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by invoice
        invoice_id = self.request.query_params.get("invoice_id")
        if invoice_id:
            queryset = queryset.filter(invoice_id=invoice_id)

        # Filter by payment method
        payment_method = self.request.query_params.get("payment_method")
        if payment_method:
            queryset = queryset.filter(payment_method=payment_method)

        # Filter by date range
        from_date = self.request.query_params.get("from_date")
        to_date = self.request.query_params.get("to_date")
        if from_date:
            queryset = queryset.filter(payment_date__gte=from_date)
        if to_date:
            queryset = queryset.filter(payment_date__lte=to_date)

        return queryset.select_related("invoice", "invoice__agreement")

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        payment = serializer.save(scope=scope, created_by=self.request.user)

        # Update invoice amount_paid
        invoice = payment.invoice
        total_paid = invoice.payments.filter(
            status=models.Payment.PaymentStatus.CONFIRMED
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

        invoice.amount_paid = total_paid
        if invoice.balance_due <= 0:
            invoice.status = models.Invoice.InvoiceStatus.PAID
        elif invoice.amount_paid > 0:
            invoice.status = models.Invoice.InvoiceStatus.PARTIALLY_PAID
        invoice.save()

    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        """Reverse a payment."""
        payment = self.get_object()
        payment.status = models.Payment.PaymentStatus.REVERSED
        payment.save()

        # Update invoice
        invoice = payment.invoice
        total_paid = invoice.payments.filter(
            status=models.Payment.PaymentStatus.CONFIRMED
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

        invoice.amount_paid = total_paid
        if invoice.amount_paid == 0:
            invoice.status = models.Invoice.InvoiceStatus.PENDING
        elif invoice.balance_due > 0:
            invoice.status = models.Invoice.InvoiceStatus.PARTIALLY_PAID
        invoice.save()

        serializer = self.get_serializer(payment)
        return Response(serializer.data)


class CreditNoteViewSet(ScopedViewSet):
    """
    ViewSet for credit notes.

    Endpoints:
    - GET /credit-notes/ - List all credit notes
    - POST /credit-notes/ - Create credit note
    - GET /credit-notes/{id}/ - Get credit note details
    - PATCH /credit-notes/{id}/ - Update credit note
    - DELETE /credit-notes/{id}/ - Delete credit note
    - POST /credit-notes/{id}/approve/ - Approve credit note
    - POST /credit-notes/{id}/reject/ - Reject credit note
    - POST /credit-notes/{id}/apply/ - Apply credit note to invoice
    """

    queryset = models.CreditNote.objects.all()
    serializer_class = serializers.CreditNoteSerializer

    def get_serializer_class(self):
        if self.action == "list":
            return serializers.CreditNoteListSerializer
        if self.action == "retrieve":
            return serializers.CreditNoteDetailSerializer
        if self.action == "create":
            return serializers.CreditNoteCreateSerializer
        return serializers.CreditNoteSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by invoice
        invoice_id = self.request.query_params.get("invoice_id")
        if invoice_id:
            queryset = queryset.filter(invoice_id=invoice_id)

        # Filter by status
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset.select_related("invoice", "invoice__agreement", "approved_by")

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        serializer.save(scope=scope, created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        """Approve credit note."""
        credit_note = self.get_object()
        credit_note.status = models.CreditNote.CreditNoteStatus.APPROVED
        credit_note.approved_by = request.user
        credit_note.approved_at = timezone.now()
        credit_note.save()
        serializer = self.get_serializer(credit_note)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        """Reject credit note."""
        credit_note = self.get_object()
        credit_note.status = models.CreditNote.CreditNoteStatus.REJECTED
        credit_note.rejection_reason = request.data.get("reason", "")
        credit_note.save()
        serializer = self.get_serializer(credit_note)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def apply(self, request, pk=None):
        """Apply credit note to invoice."""
        credit_note = self.get_object()

        if credit_note.status != models.CreditNote.CreditNoteStatus.APPROVED:
            return Response(
                {"error": "Credit note must be approved before applying"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Apply to invoice
        invoice = credit_note.invoice
        invoice.amount_paid += credit_note.amount
        if invoice.balance_due <= 0:
            invoice.status = models.Invoice.InvoiceStatus.PAID
        invoice.save()

        credit_note.status = models.CreditNote.CreditNoteStatus.APPLIED
        credit_note.applied_at = timezone.now()
        credit_note.save()

        serializer = self.get_serializer(credit_note)
        return Response(serializer.data)


class InvoiceScheduleViewSet(ScopedViewSet):
    """
    ViewSet for invoice schedules.

    Endpoints:
    - GET /invoice-schedules/ - List all schedules
    - POST /invoice-schedules/ - Create schedule
    - GET /invoice-schedules/{id}/ - Get schedule details
    - PATCH /invoice-schedules/{id}/ - Update schedule
    - DELETE /invoice-schedules/{id}/ - Delete schedule
    - POST /invoice-schedules/{id}/generate/ - Generate invoice now
    """

    queryset = models.InvoiceSchedule.objects.all()
    serializer_class = serializers.InvoiceScheduleSerializer

    def get_serializer_class(self):
        if self.action == "list":
            return serializers.InvoiceScheduleListSerializer
        return serializers.InvoiceScheduleSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by agreement
        agreement_id = self.request.query_params.get("agreement_id")
        if agreement_id:
            queryset = queryset.filter(agreement_id=agreement_id)

        # Filter by active status
        is_active = self.request.query_params.get("is_active")
        if is_active == "true":
            queryset = queryset.filter(is_active=True)
        elif is_active == "false":
            queryset = queryset.filter(is_active=False)

        return queryset.select_related("agreement")

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        serializer.save(scope=scope, created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def _get_invoice_number_and_due_date(self, schedule):
        """Resolve invoice number from site config and due_date from payment terms."""
        from datetime import timedelta

        today = timezone.now().date()
        invoice_number = f"INV-{today.strftime('%Y%m%d')}-{schedule.id}"
        due_date = today

        site = getattr(schedule.agreement, "site", None)
        if site:
            try:
                config = models.SiteBillingConfig.objects.get(site=site, scope=schedule.scope)
                invoice_number = config.get_next_invoice_number()
                term_days = {
                    "DUE_ON_RECEIPT": 0,
                    "NET_7": 7,
                    "NET_15": 15,
                    "NET_30": 30,
                    "NET_45": 45,
                    "NET_60": 60,
                }
                days = term_days.get(config.default_payment_term, 30)
                due_date = today + timedelta(days=days)
            except models.SiteBillingConfig.DoesNotExist:
                pass

        return invoice_number, due_date

    @action(detail=True, methods=["post"])
    def generate(self, request, pk=None):
        """Generate invoice from schedule immediately."""
        schedule = self.get_object()

        today = timezone.now().date()
        invoice_number, due_date = self._get_invoice_number_and_due_date(schedule)

        tax_amt = schedule.amount * (schedule.tax_rate / 100)
        total = schedule.amount + tax_amt

        invoice = models.Invoice.objects.create(
            scope=schedule.scope,
            agreement=schedule.agreement,
            invoice_number=invoice_number,
            invoice_type=schedule.invoice_type,
            status=models.Invoice.InvoiceStatus.PENDING,
            invoice_date=today,
            due_date=due_date,
            subtotal=schedule.amount,
            tax_amount=tax_amt,
            total_amount=total,
            amount_paid=Decimal("0"),
            balance_due=total,
            created_by=request.user,
        )

        schedule.last_generated_date = today
        schedule.save()

        return Response(
            serializers.InvoiceSerializer(invoice).data,
            status=status.HTTP_201_CREATED
        )


class ARSummaryViewSet(ScopedViewSet):
    """
    ViewSet for AR summaries.

    Endpoints:
    - GET /ar-summaries/ - List all summaries
    - GET /ar-summaries/{id}/ - Get summary details
    - GET /ar-summaries/by-agreement/{agreement_id}/ - Get summary for agreement
    - POST /ar-summaries/refresh/{agreement_id}/ - Refresh summary for agreement
    - GET /ar-summaries/overall/ - Get overall AR summary
    """

    queryset = models.ARSummary.objects.all()
    serializer_class = serializers.ARSummarySerializer

    def get_serializer_class(self):
        if self.action == "retrieve":
            return serializers.ARSummaryDetailSerializer
        return serializers.ARSummarySerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.select_related("agreement", "agreement__tenant")

    @action(detail=False, methods=["get"], url_path="by-agreement/(?P<agreement_id>[^/.]+)")
    def by_agreement(self, request, agreement_id=None):
        """Get AR summary for a specific agreement."""
        scope = self.get_active_scope()
        try:
            summary = models.ARSummary.objects.get(
                agreement_id=agreement_id,
                scope=scope
            )
            serializer = serializers.ARSummaryDetailSerializer(summary)
            return Response(serializer.data)
        except models.ARSummary.DoesNotExist:
            return Response(
                {"error": "AR summary not found for this agreement"},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=False, methods=["post"], url_path="refresh/(?P<agreement_id>[^/.]+)")
    def refresh(self, request, agreement_id=None):
        """Refresh AR summary for a specific agreement."""
        scope = self.get_active_scope()
        today = timezone.now().date()

        # Get or create summary
        summary, created = models.ARSummary.objects.get_or_create(
            agreement_id=agreement_id,
            scope=scope,
            defaults={"created_by": request.user}
        )

        # Calculate totals from invoices
        invoices = models.Invoice.objects.filter(
            agreement_id=agreement_id,
            scope=scope
        )

        totals = invoices.aggregate(
            total_invoiced=Sum("total_amount"),
            total_paid=Sum("amount_paid"),
            total_outstanding=Sum("balance_due"),
        )

        # Calculate overdue
        overdue_invoices = invoices.filter(
            due_date__lt=today,
            balance_due__gt=0
        )
        total_overdue = overdue_invoices.aggregate(
            total=Sum("balance_due")
        )["total"] or Decimal("0")

        # Calculate ageing buckets
        current = overdue_invoices.filter(
            due_date__gte=today - timezone.timedelta(days=30)
        ).aggregate(total=Sum("balance_due"))["total"] or Decimal("0")

        bucket_30_60 = overdue_invoices.filter(
            due_date__lt=today - timezone.timedelta(days=30),
            due_date__gte=today - timezone.timedelta(days=60)
        ).aggregate(total=Sum("balance_due"))["total"] or Decimal("0")

        bucket_60_90 = overdue_invoices.filter(
            due_date__lt=today - timezone.timedelta(days=60),
            due_date__gte=today - timezone.timedelta(days=90)
        ).aggregate(total=Sum("balance_due"))["total"] or Decimal("0")

        bucket_90_plus = overdue_invoices.filter(
            due_date__lt=today - timezone.timedelta(days=90)
        ).aggregate(total=Sum("balance_due"))["total"] or Decimal("0")

        # Counts
        open_count = invoices.filter(
            balance_due__gt=0
        ).count()
        overdue_count = overdue_invoices.count()
        disputed_count = invoices.filter(is_disputed=True).count()

        # Update summary
        summary.total_invoiced = totals["total_invoiced"] or Decimal("0")
        summary.total_paid = totals["total_paid"] or Decimal("0")
        summary.total_outstanding = totals["total_outstanding"] or Decimal("0")
        summary.total_overdue = total_overdue
        summary.current_bucket = current
        summary.bucket_30_60 = bucket_30_60
        summary.bucket_60_90 = bucket_60_90
        summary.bucket_90_plus = bucket_90_plus
        summary.open_invoice_count = open_count
        summary.overdue_invoice_count = overdue_count
        summary.disputed_invoice_count = disputed_count
        summary.updated_by = request.user
        summary.save()

        serializer = serializers.ARSummaryDetailSerializer(summary)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def overall(self, request):
        """Get overall AR summary across all agreements."""
        scope = self.get_active_scope()
        today = timezone.now().date()

        invoices = models.Invoice.objects.filter(scope=scope)

        totals = invoices.aggregate(
            total_invoiced=Sum("total_amount"),
            total_paid=Sum("amount_paid"),
            total_outstanding=Sum("balance_due"),
        )

        overdue_stats = invoices.filter(
            due_date__lt=today,
            balance_due__gt=0
        ).aggregate(
            total_overdue=Sum("balance_due"),
            overdue_count=Count("id"),
        )

        disputed_stats = invoices.filter(
            is_disputed=True
        ).aggregate(
            disputed_amount=Sum("balance_due"),
            disputed_count=Count("id"),
        )

        # Ageing buckets
        overdue_invoices = invoices.filter(
            due_date__lt=today,
            balance_due__gt=0
        )

        ageing = {
            "current": float(overdue_invoices.filter(
                due_date__gte=today - timezone.timedelta(days=30)
            ).aggregate(total=Sum("balance_due"))["total"] or 0),
            "30_60": float(overdue_invoices.filter(
                due_date__lt=today - timezone.timedelta(days=30),
                due_date__gte=today - timezone.timedelta(days=60)
            ).aggregate(total=Sum("balance_due"))["total"] or 0),
            "60_90": float(overdue_invoices.filter(
                due_date__lt=today - timezone.timedelta(days=60),
                due_date__gte=today - timezone.timedelta(days=90)
            ).aggregate(total=Sum("balance_due"))["total"] or 0),
            "90_plus": float(overdue_invoices.filter(
                due_date__lt=today - timezone.timedelta(days=90)
            ).aggregate(total=Sum("balance_due"))["total"] or 0),
        }

        return Response({
            "total_invoiced": float(totals["total_invoiced"] or 0),
            "total_paid": float(totals["total_paid"] or 0),
            "total_outstanding": float(totals["total_outstanding"] or 0),
            "total_overdue": float(overdue_stats["total_overdue"] or 0),
            "overdue_count": overdue_stats["overdue_count"] or 0,
            "disputed_amount": float(disputed_stats["disputed_amount"] or 0),
            "disputed_count": disputed_stats["disputed_count"] or 0,
            "ageing": ageing,
        })


class ReceivablesListAPIView(APIView):
    """
    GET /api/v1/billing/receivables/
    List receivables (open invoices with balance_due > 0).
    Filters: site_ids, tenant_ids, from_date, to_date, ageing_bucket
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.core.utils import get_active_scope

        scope = get_active_scope(request)
        if not scope:
            return Response(
                {"error": "Scope required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        today = timezone.now().date()
        qs = models.Invoice.objects.filter(
            scope=scope,
            balance_due__gt=0,
        ).exclude(
            status__in=[models.Invoice.InvoiceStatus.CANCELLED, models.Invoice.InvoiceStatus.WRITTEN_OFF]
        ).select_related("agreement", "agreement__tenant", "agreement__site")

        # Filters
        site_ids = request.query_params.get("site_ids") or request.query_params.get("property_ids")
        if site_ids:
            ids = [x.strip() for x in str(site_ids).split(",") if x.strip()]
            if ids:
                qs = qs.filter(agreement__site_id__in=ids)

        tenant_ids = request.query_params.get("tenant_ids")
        if tenant_ids:
            ids = [x.strip() for x in str(tenant_ids).split(",") if x.strip()]
            if ids:
                qs = qs.filter(agreement__tenant_id__in=ids)

        from_date = request.query_params.get("from_date")
        to_date = request.query_params.get("to_date")
        if from_date:
            qs = qs.filter(due_date__gte=from_date)
        if to_date:
            qs = qs.filter(due_date__lte=to_date)

        # Get ageing buckets for scope
        ageing_buckets = list(
            models.AgeingBucket.objects.filter(scope=scope, status="ACTIVE").order_by("from_days")
        )

        def get_bucket_label(days_overdue):
            for b in ageing_buckets:
                if days_overdue >= b.from_days and (b.to_days is None or days_overdue <= b.to_days):
                    return b.label or b.reporting_label
            return "Current" if days_overdue <= 0 else "90+"

        ageing_filter = request.query_params.get("ageing_bucket")
        results = []
        for inv in qs.order_by("due_date", "invoice_number"):
            days_overdue = 0
            if inv.balance_due > 0 and inv.due_date and inv.due_date < today:
                days_overdue = (today - inv.due_date).days

            bucket_label = get_bucket_label(days_overdue)
            if ageing_filter and bucket_label != ageing_filter:
                continue

            tenant_name = inv.agreement.tenant.legal_name if inv.agreement and inv.agreement.tenant else None
            site_name = inv.agreement.site.name if inv.agreement and getattr(inv.agreement, "site", None) else None

            results.append({
                "id": inv.id,
                "invoice_id": inv.id,
                "invoice_number": inv.invoice_number,
                "tenant_id": inv.agreement.tenant_id if inv.agreement else None,
                "tenant_name": tenant_name,
                "lease_id": inv.agreement.lease_id if inv.agreement else None,
                "site_id": inv.agreement.site_id if inv.agreement else None,
                "site_name": site_name,
                "amount_due": float(inv.balance_due),
                "days_overdue": days_overdue,
                "ageing_bucket": bucket_label,
                "due_date": str(inv.due_date),
                "invoice_date": str(inv.invoice_date),
                "status": inv.status,
                "is_disputed": inv.is_disputed,
            })

        return Response({"results": results})


class RentScheduleLineViewSet(ScopedViewSet):
    """
    ViewSet for Rent Schedule Lines (per-period rent schedule).

    Endpoints:
    - GET /rent-schedule-lines/ - List with filters
    - GET /rent-schedule-lines/{id}/ - Detail
    - POST /rent-schedule-lines/ - Create
    - PATCH /rent-schedule-lines/{id}/ - Update
    - POST /rent-schedule-lines/generate/ - Generate schedules
    - POST /rent-schedule-lines/mark_invoiced/ - Bulk mark as invoiced
    - POST /rent-schedule-lines/adjust_amounts/ - Bulk adjust amounts
    - GET /rent-schedule-lines/export/ - Export to CSV
    """

    queryset = models.RentScheduleLine.objects.all()
    serializer_class = serializers.RentScheduleLineListSerializer

    def get_serializer_class(self):
        if self.action == "retrieve":
            return serializers.RentScheduleLineDetailSerializer
        return serializers.RentScheduleLineListSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.select_related("agreement", "agreement__tenant", "agreement__site", "unit", "invoice")

        # Filters
        agreement_id = self.request.query_params.get("agreement_id")
        if agreement_id:
            queryset = queryset.filter(agreement_id=agreement_id)

        site_ids = self.request.query_params.get("site_ids") or self.request.query_params.get("property_ids")
        if site_ids:
            ids = [x.strip() for x in str(site_ids).split(",") if x.strip()]
            if ids:
                queryset = queryset.filter(agreement__site_id__in=ids)

        tenant_ids = self.request.query_params.get("tenant_ids")
        if tenant_ids:
            ids = [x.strip() for x in str(tenant_ids).split(",") if x.strip()]
            if ids:
                queryset = queryset.filter(agreement__tenant_id__in=ids)

        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        period_from = self.request.query_params.get("period_from") or self.request.query_params.get("from_date")
        period_to = self.request.query_params.get("period_to") or self.request.query_params.get("to_date")
        if period_from:
            queryset = queryset.filter(period_end__gte=period_from)
        if period_to:
            queryset = queryset.filter(period_start__lte=period_to)

        return queryset.order_by("-period_start", "agreement", "charge_type")

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        serializer.save(scope=scope, created_by=self.request.user)

    @action(detail=False, methods=["post"])
    def generate(self, request):
        """Generate rent schedule lines for agreements. Payload: { agreement_ids: [], period_start, period_end, charge_type }."""
        scope = self.get_active_scope()
        agreement_ids = request.data.get("agreement_ids", [])
        period_start = request.data.get("period_start")
        period_end = request.data.get("period_end")
        charge_type = request.data.get("charge_type", "BASE_RENT")
        if not agreement_ids or not period_start or not period_end:
            return Response(
                {"error": "agreement_ids, period_start, period_end required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        created = 0
        from apps.leases.models import Agreement
        for aid in agreement_ids:
            try:
                ag = Agreement.objects.select_related("billing").get(id=aid, scope=scope)
            except Agreement.DoesNotExist:
                continue
            amount = 0
            if hasattr(ag, "billing") and ag.billing and ag.billing.base_rent_monthly is not None:
                amount = ag.billing.base_rent_monthly
            due_date = period_end  # Simple: due at period end
            line, created_flag = models.RentScheduleLine.objects.get_or_create(
                scope=scope,
                agreement=ag,
                period_start=period_start,
                period_end=period_end,
                charge_type=charge_type,
                defaults={
                    "amount_before_tax": amount,
                    "amount_after_tax": amount,
                    "due_date": due_date,
                    "status": models.RentScheduleLine.ScheduleStatus.SCHEDULED,
                    "created_by": request.user,
                }
            )
            if created_flag:
                created += 1
        return Response({"created": created})

    @action(detail=False, methods=["post"], url_path="mark-invoiced")
    def mark_invoiced(self, request):
        """Bulk mark lines as invoiced. Payload: { line_ids: [], invoice_id }."""
        scope = self.get_active_scope()
        line_ids = request.data.get("line_ids", [])
        invoice_id = request.data.get("invoice_id")
        if not line_ids:
            return Response({"error": "line_ids required"}, status=status.HTTP_400_BAD_REQUEST)
        qs = models.RentScheduleLine.objects.filter(id__in=line_ids, scope=scope)
        for line in qs:
            line.status = models.RentScheduleLine.ScheduleStatus.INVOICED
            line.invoice_id = invoice_id
            line.updated_by = request.user
            line.save(update_fields=["status", "invoice_id", "updated_by", "updated_at"])
        return Response({"updated": qs.count()})

    @action(detail=False, methods=["post"], url_path="adjust-amounts")
    def adjust_amounts(self, request):
        """Bulk adjust amounts. Payload: { line_ids: [], override_amount, adjustment_reason }."""
        scope = self.get_active_scope()
        line_ids = request.data.get("line_ids", [])
        override_amount = request.data.get("override_amount")
        adjustment_reason = request.data.get("adjustment_reason", "")
        if not line_ids or override_amount is None:
            return Response(
                {"error": "line_ids and override_amount required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        from decimal import Decimal
        amt = Decimal(str(override_amount))
        qs = models.RentScheduleLine.objects.filter(id__in=line_ids, scope=scope)
        for line in qs:
            line.override_amount = amt
            line.adjustment_reason = adjustment_reason
            line.amount_after_tax = amt
            line.save(update_fields=["override_amount", "adjustment_reason", "amount_after_tax", "updated_at"])
        return Response({"updated": qs.count()})

    @action(detail=False, methods=["get"])
    def export(self, request):
        """Export rent schedule list to CSV."""
        import csv
        from django.http import HttpResponse
        qs = self.get_queryset()[:10000]
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = "attachment; filename=rent-schedules.csv"
        writer = csv.writer(response)
        writer.writerow([
            "ID", "Lease ID", "Tenant", "Property", "Unit", "Period Start", "Period End",
            "Charge Type", "Amt Before Tax", "GST", "Amt After Tax", "Due Date", "Status",
            "Escalation Applied", "Notes"
        ])
        for line in qs:
            tenant = line.agreement.tenant.legal_name if line.agreement and line.agreement.tenant else ""
            site = line.agreement.site.name if line.agreement and getattr(line.agreement, "site", None) else ""
            unit = line.unit.unit_no if line.unit else ""
            eff = line.override_amount if line.override_amount is not None else line.amount_after_tax
            writer.writerow([
                line.id, line.agreement.lease_id if line.agreement else "",
                tenant, site, unit,
                line.period_start, line.period_end,
                line.charge_type, line.amount_before_tax, line.gst, eff,
                line.due_date, line.status,
                line.escalation_applied, line.notes or "",
            ])
        return response


class RentScheduleKPIsAPIView(APIView):
    """
    GET /api/v1/billing/rent-schedule-kpis/
    Returns MRR Forecast and Overdue Variance KPIs.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.core.utils import get_active_scope

        scope = get_active_scope(request)
        if not scope:
            return Response({"error": "Scope required"}, status=status.HTTP_400_BAD_REQUEST)

        today = timezone.now().date()
        qs = models.RentScheduleLine.objects.filter(
            scope=scope,
            status=models.RentScheduleLine.ScheduleStatus.SCHEDULED,
            period_start__lte=today,
            period_end__gte=today,
        ).aggregate(total=Sum("amount_after_tax"))

        mrr = float(qs["total"] or 0)

        # Overdue: scheduled lines past due_date not yet invoiced
        overdue_qs = models.RentScheduleLine.objects.filter(
            scope=scope,
            status=models.RentScheduleLine.ScheduleStatus.SCHEDULED,
            due_date__lt=today,
        ).aggregate(total=Sum("amount_after_tax"))
        overdue_amount = float(overdue_qs["total"] or 0)

        return Response({
            "mrr_forecast": mrr,
            "mrr_trend": 0,  # Placeholder: compare to last month
            "overdue_variance": overdue_amount,
            "overdue_trend": 0,  # Placeholder
        })


# =============================================================================
# REVENUE RECOGNITION (Tab 4 - Rent Schedule & Revenue Recognition)
# =============================================================================

class RevenueRecognitionAPIView(APIView):
    """
    GET /api/v1/billing/revenue-recognition/
    Returns: details (list), trend (time series), by_charge_type (donut data).

    Query params: from_date, to_date, site_ids, tenant_ids, search (invoice # or tenant)
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.core.utils import get_active_scope

        scope = get_active_scope(request)
        if not scope:
            return Response({"error": "Scope required"}, status=status.HTTP_400_BAD_REQUEST)

        from_date = request.query_params.get("from_date")
        to_date = request.query_params.get("to_date")
        site_ids = request.query_params.get("site_ids") or request.query_params.get("property_ids")
        tenant_ids = request.query_params.get("tenant_ids")
        search = request.query_params.get("search", "").strip()

        qs = models.Invoice.objects.filter(scope=scope).exclude(
            status__in=[models.Invoice.InvoiceStatus.CANCELLED, models.Invoice.InvoiceStatus.WRITTEN_OFF]
        ).select_related("agreement", "agreement__tenant", "agreement__site")

        if from_date:
            qs = qs.filter(invoice_date__gte=from_date)
        if to_date:
            qs = qs.filter(invoice_date__lte=to_date)
        if site_ids:
            ids = [x.strip() for x in str(site_ids).split(",") if x.strip()]
            if ids:
                qs = qs.filter(agreement__site_id__in=ids)
        if tenant_ids:
            ids = [x.strip() for x in str(tenant_ids).split(",") if x.strip()]
            if ids:
                qs = qs.filter(agreement__tenant_id__in=ids)
        if search:
            qs = qs.filter(
                Q(invoice_number__icontains=search) |
                Q(agreement__tenant__legal_name__icontains=search) |
                Q(agreement__lease_id__icontains=search)
            )

        # Details list
        details = []
        for inv in qs.order_by("-invoice_date")[:500]:
            tenant = inv.agreement.tenant.legal_name if inv.agreement and inv.agreement.tenant else None
            period = f"{inv.period_start} to {inv.period_end}" if inv.period_start and inv.period_end else inv.invoice_date
            rec_status = "ACCRUED" if inv.status != models.Invoice.InvoiceStatus.DRAFT else "DEFERRED"
            details.append({
                "id": inv.id,
                "invoice_number": inv.invoice_number,
                "invoice_id": inv.id,
                "billing_period": period,
                "tenant_name": tenant,
                "tenant_id": inv.agreement.tenant_id if inv.agreement else None,
                "billed": float(inv.total_amount or 0),
                "collected": float(inv.amount_paid or 0),
                "recognition_status": rec_status,
                "invoice_type": inv.invoice_type,
                "escalation_notes": getattr(inv, "escalation_notes", None) or "",
            })

        # Trend: billed vs collected by month
        trend_data = {}
        for inv in qs:
            month_key = (inv.invoice_date.year, inv.invoice_date.month)
            if month_key not in trend_data:
                trend_data[month_key] = {"billed": 0, "collected": 0, "month": f"{inv.invoice_date.year}-{inv.invoice_date.month:02d}"}
            trend_data[month_key]["billed"] += float(inv.total_amount or 0)
            trend_data[month_key]["collected"] += float(inv.amount_paid or 0)

        trend = sorted(
            [{"month": v["month"], "billed": v["billed"], "collected": v["collected"]} for v in trend_data.values()]
        )

        # By charge type
        by_type = {}
        for inv in qs:
            t = inv.invoice_type or "OTHER"
            if t not in by_type:
                by_type[t] = {"charge_type": t, "billed": 0, "collected": 0}
            by_type[t]["billed"] += float(inv.total_amount or 0)
            by_type[t]["collected"] += float(inv.amount_paid or 0)

        by_charge_type = sorted(by_type.values(), key=lambda x: -x["billed"])

        return Response({
            "details": details,
            "trend": trend,
            "by_charge_type": by_charge_type,
        })


class RevenueRecognitionExportAPIView(APIView):
    """
    GET /api/v1/billing/revenue-recognition/export/
    Export revenue recognition details to CSV.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        import csv
        from django.http import HttpResponse
        from apps.core.utils import get_active_scope

        scope = get_active_scope(request)
        if not scope:
            return HttpResponse("Scope required", status=400)

        from_date = request.query_params.get("from_date")
        to_date = request.query_params.get("to_date")
        search = request.query_params.get("search", "").strip()

        qs = models.Invoice.objects.filter(scope=scope).exclude(
            status__in=[models.Invoice.InvoiceStatus.CANCELLED, models.Invoice.InvoiceStatus.WRITTEN_OFF]
        ).select_related("agreement", "agreement__tenant")

        if from_date:
            qs = qs.filter(invoice_date__gte=from_date)
        if to_date:
            qs = qs.filter(invoice_date__lte=to_date)
        if search:
            qs = qs.filter(
                Q(invoice_number__icontains=search) |
                Q(agreement__tenant__legal_name__icontains=search)
            )

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = "attachment; filename=revenue-recognition.csv"
        writer = csv.writer(response)
        writer.writerow([
            "Invoice #", "Billing Period", "Tenant", "Billed", "Collected", "Recognition Status", "Invoice Type"
        ])
        for inv in qs.order_by("-invoice_date")[:5000]:
            period = f"{inv.period_start} to {inv.period_end}" if inv.period_start and inv.period_end else str(inv.invoice_date)
            tenant = inv.agreement.tenant.legal_name if inv.agreement and inv.agreement.tenant else ""
            rec = "ACCRUED" if inv.status != models.Invoice.InvoiceStatus.DRAFT else "DEFERRED"
            writer.writerow([
                inv.invoice_number, period, tenant,
                float(inv.total_amount or 0), float(inv.amount_paid or 0),
                rec, inv.invoice_type or "",
            ])
        return response


class LeaseRulesViewSet(ScopedViewSet):
    """
    ViewSet for lease-level billing and AR rules.

    Endpoints:
    - GET /lease-rules/{agreement_id}/ - Get all rules for a lease
    - PATCH /lease-rules/{agreement_id}/ - Update rules for a lease
    """

    from apps.leases.models import Agreement
    queryset = Agreement.objects.all()

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.select_related(
            "billing", "escalation"
        ).prefetch_related("ar_rules")

    @action(detail=True, methods=["get", "patch"])
    def rules(self, request, pk=None):
        """Get or update all rules for a lease."""
        agreement = self.get_object()
        scope = self.get_active_scope()

        if request.method == "GET":
            # Get billing rules from leases app
            from apps.leases.serializers import LeaseBillingSerializer, LeaseEscalationSerializer

            billing_data = None
            if hasattr(agreement, "billing"):
                billing_data = LeaseBillingSerializer(agreement.billing).data

            escalation_data = None
            if hasattr(agreement, "escalation"):
                escalation_data = LeaseEscalationSerializer(agreement.escalation).data

            ar_rules_data = None
            try:
                ar_rules_data = serializers.ARRuleSerializer(agreement.ar_rules).data
            except models.ARRule.DoesNotExist:
                pass

            # Get ageing buckets for scope
            ageing_buckets = models.AgeingBucket.objects.filter(scope=scope)
            ageing_data = serializers.AgeingBucketListSerializer(ageing_buckets, many=True).data

            return Response({
                "billing": billing_data,
                "escalation": escalation_data,
                "ar_rules": ar_rules_data,
                "ageing_buckets": ageing_data,
            })

        elif request.method == "PATCH":
            from apps.leases import models as lease_models
            from apps.leases.serializers import LeaseBillingSerializer, LeaseEscalationSerializer

            data = request.data

            # Update billing rules
            if "billing" in data:
                billing_instance, _ = lease_models.LeaseBilling.objects.update_or_create(
                    agreement=agreement,
                    defaults={
                        "scope": scope,
                        "updated_by": request.user,
                        **{k: v for k, v in data["billing"].items()
                           if k not in ["id", "scope", "agreement", "created_at", "updated_at",
                                        "created_by", "updated_by", "is_active", "deleted_at"]}
                    }
                )

            # Update escalation rules
            if "escalation" in data:
                escalation_instance, _ = lease_models.LeaseEscalation.objects.update_or_create(
                    agreement=agreement,
                    defaults={
                        "scope": scope,
                        "updated_by": request.user,
                        **{k: v for k, v in data["escalation"].items()
                           if k not in ["id", "scope", "agreement", "created_at", "updated_at",
                                        "created_by", "updated_by", "is_active", "deleted_at"]}
                    }
                )

            # Update AR rules
            if "ar_rules" in data:
                ar_instance, _ = models.ARRule.objects.update_or_create(
                    agreement=agreement,
                    defaults={
                        "scope": scope,
                        "updated_by": request.user,
                        **{k: v for k, v in data["ar_rules"].items()
                           if k not in ["id", "scope", "agreement", "created_at", "updated_at",
                                        "created_by", "updated_by", "is_active", "deleted_at"]}
                    }
                )

            # Return updated data
            return self.rules(request._request, pk=pk)

        return Response({"error": "Method not allowed"}, status=status.HTTP_405_METHOD_NOT_ALLOWED)
