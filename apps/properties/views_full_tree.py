"""
Full Tree API - Aggregated endpoint for fetching complete site hierarchy.

GET /api/v1/properties/sites/{site_id}/full-tree/

Returns the complete site structure in one call:
- Site details
- Towers with their floors
- Floors with their units
- Units with their assets
- Asset categories and items (master data)
- Form configurations
"""

from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.properties import models


# =============================================================================
# NESTED SERIALIZERS (for read-only full tree response)
# =============================================================================

class AssetItemNestedSerializer(serializers.ModelSerializer):
    """Asset item with minimal fields for tree view."""
    class Meta:
        model = models.AssetItem
        fields = ("id", "name", "code", "description")


class AssetCategoryNestedSerializer(serializers.ModelSerializer):
    """Asset category with its items."""
    items = AssetItemNestedSerializer(many=True, read_only=True)

    class Meta:
        model = models.AssetCategory
        fields = ("id", "name", "code", "description", "items")


class UnitAssetNestedSerializer(serializers.ModelSerializer):
    """Unit asset with asset item details."""
    asset_item_name = serializers.CharField(source="asset_item.name", read_only=True)
    asset_item_code = serializers.CharField(source="asset_item.code", read_only=True)
    category_name = serializers.CharField(source="asset_item.category.name", read_only=True)

    class Meta:
        model = models.UnitAsset
        fields = (
            "id", "asset_item", "asset_item_name", "asset_item_code",
            "category_name", "quantity", "condition", "notes"
        )


class UnitNestedSerializer(serializers.ModelSerializer):
    """Unit with its assets."""
    assets = UnitAssetNestedSerializer(source="unit_assets", many=True, read_only=True)

    class Meta:
        model = models.Unit
        fields = (
            "id", "unit_no", "unit_type", "status",
            "leasable_area_sqft", "builtup_area_sqft",
            "base_rent_default", "cam_default", "security_deposit_default",
            "layout_notes", "is_divisible", "min_divisible_area_sqft",
            "form_version", "custom_data",
            "assets"
        )


def _decimal_to_float(val):
    """Convert Decimal to float for JSON serialization."""
    if val is None:
        return None
    return float(val)


class FloorNestedSerializer(serializers.ModelSerializer):
    """Floor with its units and allocation info."""
    units = UnitNestedSerializer(many=True, read_only=True)

    # Computed allocation fields
    allocated_builtup = serializers.SerializerMethodField()
    allocated_leasable = serializers.SerializerMethodField()
    remaining_builtup = serializers.SerializerMethodField()
    remaining_leasable = serializers.SerializerMethodField()

    class Meta:
        model = models.Floor
        fields = (
            "id", "number", "label", "status",
            "total_area_sqft", "leasable_area_sqft", "cam_area_sqft",
            "floor_type", "allowed_use", "leasing_type", "max_units_allowed",
            # Allocation fields
            "allocated_builtup", "allocated_leasable",
            "remaining_builtup", "remaining_leasable",
            "units"
        )

    def get_allocated_builtup(self, obj):
        """Sum of unit builtup_area_sqft for this floor."""
        total = sum(
            float(u.builtup_area_sqft or 0)
            for u in obj.units.filter(is_active=True)
        )
        return total

    def get_allocated_leasable(self, obj):
        """Sum of unit leasable_area_sqft for this floor."""
        total = sum(
            float(u.leasable_area_sqft or 0)
            for u in obj.units.filter(is_active=True)
        )
        return total

    def get_remaining_builtup(self, obj):
        """Floor total_area - allocated builtup."""
        if obj.total_area_sqft is None:
            return None
        allocated = self.get_allocated_builtup(obj)
        return max(0, float(obj.total_area_sqft) - allocated)

    def get_remaining_leasable(self, obj):
        """Floor leasable_area - allocated leasable."""
        if obj.leasable_area_sqft is None:
            return None
        allocated = self.get_allocated_leasable(obj)
        return max(0, float(obj.leasable_area_sqft) - allocated)


class TowerNestedSerializer(serializers.ModelSerializer):
    """Tower with its floors and allocation info."""
    floors = FloorNestedSerializer(many=True, read_only=True)

    # Computed allocation fields
    allocated_total = serializers.SerializerMethodField()
    allocated_leasable = serializers.SerializerMethodField()
    remaining_total = serializers.SerializerMethodField()
    remaining_leasable = serializers.SerializerMethodField()

    class Meta:
        model = models.Tower
        fields = (
            "id", "name", "code", "building_type",
            "total_floors", "total_area_sqft", "leasable_area_sqft",
            "completion_date", "occupancy_date",
            # Allocation fields
            "allocated_total", "allocated_leasable",
            "remaining_total", "remaining_leasable",
            "floors"
        )

    def get_allocated_total(self, obj):
        """Sum of floor total_area_sqft for this tower."""
        total = sum(
            float(f.total_area_sqft or 0)
            for f in obj.floors.filter(is_active=True)
        )
        return total

    def get_allocated_leasable(self, obj):
        """Sum of floor leasable_area_sqft for this tower."""
        total = sum(
            float(f.leasable_area_sqft or 0)
            for f in obj.floors.filter(is_active=True)
        )
        return total

    def get_remaining_total(self, obj):
        """Tower total_area - allocated total."""
        if obj.total_area_sqft is None:
            return None
        allocated = self.get_allocated_total(obj)
        return max(0, float(obj.total_area_sqft) - allocated)

    def get_remaining_leasable(self, obj):
        """Tower leasable_area - allocated leasable."""
        if obj.leasable_area_sqft is None:
            return None
        allocated = self.get_allocated_leasable(obj)
        return max(0, float(obj.leasable_area_sqft) - allocated)


class FormFieldNestedSerializer(serializers.ModelSerializer):
    """Form field for tree view."""
    class Meta:
        model = models.FormField
        fields = (
            "id", "field_name", "field_type", "label",
            "placeholder", "default_value", "is_required",
            "validation_rules", "options", "order"
        )


class FormTemplateVersionNestedSerializer(serializers.ModelSerializer):
    """Form template version with fields."""
    fields = FormFieldNestedSerializer(many=True, read_only=True)

    class Meta:
        model = models.FormTemplateVersion
        fields = ("id", "version_number", "is_published", "fields")


class FormTemplateNestedSerializer(serializers.ModelSerializer):
    """Form template with versions."""
    versions = FormTemplateVersionNestedSerializer(many=True, read_only=True)

    class Meta:
        model = models.FormTemplate
        fields = ("id", "name", "code", "description", "unit_type", "versions")


class SiteUnitFormConfigNestedSerializer(serializers.ModelSerializer):
    """Site form config with template details."""
    template_name = serializers.CharField(source="form_version.template.name", read_only=True)
    version_number = serializers.IntegerField(source="form_version.version_number", read_only=True)

    class Meta:
        model = models.SiteUnitFormConfig
        fields = (
            "id", "form_version", "template_name", "version_number",
            "unit_type", "is_active"
        )


class SiteFullTreeSerializer(serializers.ModelSerializer):
    """
    Complete site tree with all nested data.

    Includes:
    - Site details
    - Towers → Floors → Units → Assets
    - Asset categories (master data for this scope)
    - Form configurations
    - Allocation metrics (allocated/remaining areas)
    """
    towers = TowerNestedSerializer(many=True, read_only=True)
    form_configs = SiteUnitFormConfigNestedSerializer(
        source="unit_form_configs", many=True, read_only=True
    )

    # Computed allocation fields
    allocated_total = serializers.SerializerMethodField()
    allocated_leasable = serializers.SerializerMethodField()
    remaining_total = serializers.SerializerMethodField()
    remaining_leasable = serializers.SerializerMethodField()

    class Meta:
        model = models.Site
        fields = (
            # Site identification
            "id", "name", "code", "site_type",
            # Address
            "address_line1", "address_line2", "landmark",
            "city", "state", "country", "pincode",
            # Area metrics
            "base_rate_sqft", "leasable_area_sqft",
            "total_builtup_area_sqft", "common_area_percent", "common_area_sqft",
            # Allocation metrics
            "allocated_total", "allocated_leasable",
            "remaining_total", "remaining_leasable",
            # Management
            "management_fee_type", "management_fee_value",
            # Contract
            "contract_start_date", "contract_end_date",
            # Nested data
            "towers",
            "form_configs",
        )

    def get_allocated_total(self, obj):
        """Sum of tower total_area_sqft for this site."""
        total = sum(
            float(t.total_area_sqft or 0)
            for t in obj.towers.filter(is_active=True)
        )
        return total

    def get_allocated_leasable(self, obj):
        """Sum of tower leasable_area_sqft for this site."""
        total = sum(
            float(t.leasable_area_sqft or 0)
            for t in obj.towers.filter(is_active=True)
        )
        return total

    def get_remaining_total(self, obj):
        """Site total_builtup_area - allocated total."""
        if obj.total_builtup_area_sqft is None:
            return None
        allocated = self.get_allocated_total(obj)
        return max(0, float(obj.total_builtup_area_sqft) - allocated)

    def get_remaining_leasable(self, obj):
        """Site leasable_area - allocated leasable."""
        if obj.leasable_area_sqft is None:
            return None
        allocated = self.get_allocated_leasable(obj)
        return max(0, float(obj.leasable_area_sqft) - allocated)


# =============================================================================
# MIXIN FOR SITEVIEWSET
# =============================================================================

class SiteFullTreeMixin:
    """
    Mixin to add full-tree action to SiteViewSet.

    Usage:
        class SiteViewSet(SiteFullTreeMixin, ScopedViewSet):
            ...
    """

    @action(detail=True, methods=["get"], url_path="full-tree")
    def full_tree(self, request, pk=None):
        """
        GET /api/v1/properties/sites/{id}/full-tree/

        Returns complete site hierarchy with optimized queries.
        """
        site = self.get_object()

        # Prefetch all related data to minimize DB queries
        site = models.Site.objects.select_related().prefetch_related(
            # Towers and their floors
            "towers__floors__units__unit_assets__asset_item__category",
            # Form configs
            "unit_form_configs__form_version__template",
        ).get(pk=site.pk)

        # Get asset categories for this scope (master data)
        asset_categories = models.AssetCategory.objects.filter(
            scope=site.scope, is_active=True
        ).prefetch_related("items")

        # Serialize the data
        site_data = SiteFullTreeSerializer(site).data
        site_data["asset_categories"] = AssetCategoryNestedSerializer(
            asset_categories, many=True
        ).data

        # Get form templates for this scope
        form_templates = models.FormTemplate.objects.filter(
            scope=site.scope, is_active=True
        ).prefetch_related("versions__fields")
        site_data["form_templates"] = FormTemplateNestedSerializer(
            form_templates, many=True
        ).data

        return Response(site_data)
