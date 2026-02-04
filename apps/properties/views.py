from rest_framework.exceptions import ValidationError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

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
    queryset = models.Site.objects.all()
    serializer_class = serializers.SiteSerializer


class SiteAmenityViewSet(ScopedViewSet):
    queryset = models.SiteAmenity.objects.all()
    serializer_class = serializers.SiteAmenitySerializer

    def get_queryset(self):
        scope = get_active_scope(self.request)
        return super().get_queryset().filter(site__scope=scope)

    def perform_create(self, serializer):
        scope = get_active_scope(self.request)
        site = serializer.validated_data.get("site")
        amenity = serializer.validated_data.get("amenity")
        if site and site.scope_id != scope.id:
            raise ValidationError("Site must belong to the active scope.")
        if amenity and amenity.scope_id != scope.id:
            raise ValidationError("Amenity must belong to the active scope.")
        serializer.save()

    def perform_update(self, serializer):
        self.perform_create(serializer)


class TowerViewSet(ScopedViewSet):
    queryset = models.Tower.objects.all()
    serializer_class = serializers.TowerSerializer


class FloorViewSet(ScopedViewSet):
    queryset = models.Floor.objects.all()
    serializer_class = serializers.FloorSerializer


class UnitViewSet(ScopedViewSet):
    queryset = models.Unit.objects.all()
    serializer_class = serializers.UnitSerializer


class UnitAreaReservationViewSet(ScopedViewSet):
    queryset = models.UnitAreaReservation.objects.all()
    serializer_class = serializers.UnitAreaReservationSerializer


class UnitAmenityViewSet(ScopedViewSet):
    queryset = models.UnitAmenity.objects.all()
    serializer_class = serializers.UnitAmenitySerializer

    def get_queryset(self):
        scope = get_active_scope(self.request)
        return super().get_queryset().filter(unit__scope=scope)

    def perform_create(self, serializer):
        scope = get_active_scope(self.request)
        unit = serializer.validated_data.get("unit")
        amenity = serializer.validated_data.get("amenity")
        if unit and unit.scope_id != scope.id:
            raise ValidationError("Unit must belong to the active scope.")
        if amenity and amenity.scope_id != scope.id:
            raise ValidationError("Amenity must belong to the active scope.")
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


class UnitAssetViewSet(ScopedViewSet):
    queryset = models.UnitAsset.objects.all()
    serializer_class = serializers.UnitAssetSerializer


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
