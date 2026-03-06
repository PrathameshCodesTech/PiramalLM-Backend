from rest_framework.exceptions import ValidationError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.filters import SearchFilter, OrderingFilter

from apps.core.utils import get_active_scope
from apps.core.viewsets import ScopedViewSet
from apps.properties import models, serializers
from apps.properties.views_full_tree import SiteFullTreeMixin


class AmenityViewSet(ScopedViewSet):
    queryset = models.Amenity.objects.all()
    serializer_class = serializers.AmenitySerializer


class RoomViewSet(ScopedViewSet):
    queryset = models.Room.objects.all()
    serializer_class = serializers.RoomSerializer


class SiteViewSet(SiteFullTreeMixin, ScopedViewSet):
    """
    Site ViewSet with full-tree endpoint.

    Endpoints:
    - GET/POST /api/v1/properties/sites/
    - GET/PUT/PATCH/DELETE /api/v1/properties/sites/{id}/
    - GET /api/v1/properties/sites/{id}/full-tree/  (aggregated data)
    """

    rbac_module = "PROPERTY"
    queryset = models.Site.objects.all()
    serializer_class = serializers.SiteSerializer
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["name", "code", "city", "state"]
    ordering_fields = ["name", "created_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params

        site_type = params.get("site_type")
        state = params.get("state")
        city = params.get("city")

        if site_type:
            queryset = queryset.filter(site_type__iexact=site_type)
        if state:
            queryset = queryset.filter(state__iexact=state)
        if city:
            queryset = queryset.filter(city__iexact=city)

        return queryset


class SiteAmenityViewSet(ScopedViewSet):
    queryset = models.SiteAmenity.objects.all()
    serializer_class = serializers.SiteAmenitySerializer

    def get_queryset(self):
        scope = get_active_scope(self.request)
        scope_ids = list(scope.get_child_scopes().values_list("id", flat=True))
        queryset = self.queryset.filter(site__scope_id__in=scope_ids)
        site_id = self.request.query_params.get("site")
        if site_id:
            queryset = queryset.filter(site_id=site_id)
        return queryset

    def perform_create(self, serializer):
        scope = get_active_scope(self.request)
        scope_ids = set(scope.get_child_scopes().values_list("id", flat=True))
        site = serializer.validated_data.get("site")
        amenity = serializer.validated_data.get("amenity")
        if site and site.scope_id not in scope_ids:
            raise ValidationError("Site must belong to active scope or child scope.")
        if amenity and amenity.scope_id not in scope_ids:
            raise ValidationError("Amenity must belong to active scope or child scope.")
        if site and amenity and site.scope_id != amenity.scope_id:
            raise ValidationError("Site and amenity must belong to the same scope.")
        serializer.save()

    def perform_update(self, serializer):
        self.perform_create(serializer)


class TowerViewSet(ScopedViewSet):
    queryset = models.Tower.objects.all().order_by("id")
    serializer_class = serializers.TowerSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        site_id = self.request.query_params.get("site") or self.request.query_params.get("site_id")
        if site_id:
            queryset = queryset.filter(site_id=site_id)
        return queryset


class FloorViewSet(ScopedViewSet):
    queryset = models.Floor.objects.all()
    serializer_class = serializers.FloorSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        site_id = self.request.query_params.get("site") or self.request.query_params.get("site_id")
        tower_id = self.request.query_params.get("tower") or self.request.query_params.get("tower_id")
        if site_id:
            queryset = queryset.filter(site_id=site_id)
        if tower_id:
            queryset = queryset.filter(tower_id=tower_id)
        return queryset


class UnitViewSet(ScopedViewSet):
    queryset = models.Unit.objects.all()
    serializer_class = serializers.UnitSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        site_id = self.request.query_params.get("site") or self.request.query_params.get("site_id")
        tower_id = self.request.query_params.get("tower") or self.request.query_params.get("tower_id")
        floor_id = self.request.query_params.get("floor") or self.request.query_params.get("floor_id")
        if site_id:
            queryset = queryset.filter(floor__site_id=site_id)
        if tower_id:
            queryset = queryset.filter(floor__tower_id=tower_id)
        if floor_id:
            queryset = queryset.filter(floor_id=floor_id)
        return queryset


class UnitAreaReservationViewSet(ScopedViewSet):
    queryset = models.UnitAreaReservation.objects.all()
    serializer_class = serializers.UnitAreaReservationSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        unit_id = self.request.query_params.get("unit") or self.request.query_params.get("unit_id")
        if unit_id:
            queryset = queryset.filter(unit_id=unit_id)
        return queryset


class UnitAmenityViewSet(ScopedViewSet):
    queryset = models.UnitAmenity.objects.all()
    serializer_class = serializers.UnitAmenitySerializer

    def get_queryset(self):
        scope = get_active_scope(self.request)
        scope_ids = list(scope.get_child_scopes().values_list("id", flat=True))
        queryset = self.queryset.filter(unit__scope_id__in=scope_ids)
        unit_id = self.request.query_params.get("unit")
        if unit_id:
            queryset = queryset.filter(unit_id=unit_id)
        return queryset

    def perform_create(self, serializer):
        scope = get_active_scope(self.request)
        scope_ids = set(scope.get_child_scopes().values_list("id", flat=True))
        unit = serializer.validated_data.get("unit")
        amenity = serializer.validated_data.get("amenity")
        if unit and unit.scope_id not in scope_ids:
            raise ValidationError("Unit must belong to active scope or child scope.")
        if amenity and amenity.scope_id not in scope_ids:
            raise ValidationError("Amenity must belong to active scope or child scope.")
        if unit and amenity and unit.scope_id != amenity.scope_id:
            raise ValidationError("Unit and amenity must belong to the same scope.")
        serializer.save()

    def perform_update(self, serializer):
        self.perform_create(serializer)


class UnitRoomViewSet(ScopedViewSet):
    queryset = models.UnitRoom.objects.all()
    serializer_class = serializers.UnitRoomSerializer


class AssetCategoryViewSet(ScopedViewSet):
    queryset = models.AssetCategory.objects.all()
    serializer_class = serializers.AssetCategorySerializer


class AssetItemViewSet(ScopedViewSet):
    queryset = models.AssetItem.objects.all()
    serializer_class = serializers.AssetItemSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        category_id = self.request.query_params.get("category") or self.request.query_params.get("category_id")
        if category_id:
            queryset = queryset.filter(category_id=category_id)
        return queryset


class UnitAssetViewSet(ScopedViewSet):
    queryset = models.UnitAsset.objects.all()
    serializer_class = serializers.UnitAssetSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        unit_id = self.request.query_params.get("unit") or self.request.query_params.get("unit_id")
        if unit_id:
            queryset = queryset.filter(unit_id=unit_id)
        return queryset


class FormTemplateViewSet(ScopedViewSet):
    queryset = models.FormTemplate.objects.all()
    serializer_class = serializers.FormTemplateSerializer


class FormTemplateVersionViewSet(ScopedViewSet):
    queryset = models.FormTemplateVersion.objects.all()
    serializer_class = serializers.FormTemplateVersionSerializer


class FormFieldViewSet(ScopedViewSet):
    queryset = models.FormField.objects.all()
    serializer_class = serializers.FormFieldSerializer


class LandlordViewSet(ScopedViewSet):
    queryset = models.Landlord.objects.all()
    serializer_class = serializers.LandlordSerializer


class LandlordContactViewSet(ScopedViewSet):
    queryset = models.LandlordContact.objects.all()
    serializer_class = serializers.LandlordContactSerializer


class SiteAttachmentViewSet(ScopedViewSet):
    queryset = models.SiteAttachment.objects.all()
    serializer_class = serializers.SiteAttachmentSerializer


class SiteUnitFormConfigViewSet(ScopedViewSet):
    queryset = models.SiteUnitFormConfig.objects.all()
    serializer_class = serializers.SiteUnitFormConfigSerializer


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def site_type_choices(request):
    return Response(
        {
            "choices": [
                {"value": value, "label": label}
                for value, label in models.Site.SiteType.choices
            ]
        }
    )
