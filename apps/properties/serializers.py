from django.db.models import Sum
from rest_framework import serializers

from apps.properties import models


class AmenitySerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Amenity
        fields = "__all__"
        read_only_fields = ("id", "scope", "created_at", "updated_at", "created_by", "updated_by", "is_active", "deleted_at")


class RoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Room
        fields = "__all__"
        read_only_fields = ("id", "scope", "created_at", "updated_at", "created_by", "updated_by", "is_active", "deleted_at")


class SiteSerializer(serializers.ModelSerializer):
    def validate(self, attrs):
        attrs = super().validate(attrs)
        total_area = attrs.get("total_builtup_area_sqft", getattr(self.instance, "total_builtup_area_sqft", None))
        leasable_area = attrs.get("leasable_area_sqft", getattr(self.instance, "leasable_area_sqft", None))

        # Validate: leasable_area ≤ total_area
        if total_area is not None and leasable_area is not None:
            if leasable_area > total_area:
                raise serializers.ValidationError(
                    {"leasable_area_sqft": "Leasable area cannot exceed total built-up area."}
                )

        return attrs

    class Meta:
        model = models.Site
        fields = "__all__"
        read_only_fields = ("id", "scope", "created_at", "updated_at", "created_by", "updated_by", "is_active", "deleted_at")


class SiteAmenitySerializer(serializers.ModelSerializer):
    class Meta:
        model = models.SiteAmenity
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at", "created_by", "updated_by", "is_active", "deleted_at")


class TowerSerializer(serializers.ModelSerializer):
    def validate(self, attrs):
        attrs = super().validate(attrs)
        site = attrs.get("site") or getattr(self.instance, "site", None)
        total_area = attrs.get("total_area_sqft", getattr(self.instance, "total_area_sqft", None))
        leasable_area = attrs.get("leasable_area_sqft", getattr(self.instance, "leasable_area_sqft", None))

        # Validate: leasable_area ≤ total_area
        if total_area is not None and leasable_area is not None:
            if leasable_area > total_area:
                raise serializers.ValidationError(
                    {"leasable_area_sqft": "Leasable area cannot exceed total area."}
                )

        if site:
            qs = models.Tower.objects.filter(site=site, is_active=True)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)

            agg = qs.aggregate(
                total_sum=Sum("total_area_sqft"),
                leasable_sum=Sum("leasable_area_sqft"),
            )
            total_sum = agg.get("total_sum") or 0
            leasable_sum = agg.get("leasable_sum") or 0

            if site.total_builtup_area_sqft is not None and total_area is not None:
                if total_sum + total_area > site.total_builtup_area_sqft:
                    raise serializers.ValidationError(
                        {"total_area_sqft": f"Sum of tower total area ({total_sum + total_area}) exceeds site total built-up area ({site.total_builtup_area_sqft})."}
                    )
            if site.leasable_area_sqft is not None and leasable_area is not None:
                if leasable_sum + leasable_area > site.leasable_area_sqft:
                    raise serializers.ValidationError(
                        {"leasable_area_sqft": f"Sum of tower leasable area ({leasable_sum + leasable_area}) exceeds site leasable area ({site.leasable_area_sqft})."}
                    )

        return attrs

    class Meta:
        model = models.Tower
        fields = "__all__"
        read_only_fields = ("id", "scope", "created_at", "updated_at", "created_by", "updated_by", "is_active", "deleted_at")


class FloorSerializer(serializers.ModelSerializer):
    def validate(self, attrs):
        attrs = super().validate(attrs)
        tower = attrs.get("tower") or getattr(self.instance, "tower", None)
        total_area = attrs.get("total_area_sqft", getattr(self.instance, "total_area_sqft", None))
        leasable_area = attrs.get("leasable_area_sqft", getattr(self.instance, "leasable_area_sqft", None))
        cam_area = attrs.get("cam_area_sqft", getattr(self.instance, "cam_area_sqft", None))

        # Validate: leasable_area ≤ total_area
        if total_area is not None and leasable_area is not None:
            if leasable_area > total_area:
                raise serializers.ValidationError(
                    {"leasable_area_sqft": "Leasable area cannot exceed total area."}
                )

        # Validate: leasable + cam ≤ total
        if total_area is not None and leasable_area is not None and cam_area is not None:
            if (leasable_area + cam_area) > total_area:
                raise serializers.ValidationError(
                    {"cam_area_sqft": f"Leasable ({leasable_area}) + CAM ({cam_area}) cannot exceed total area ({total_area})."}
                )

        if tower:
            qs = models.Floor.objects.filter(tower=tower, is_active=True)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)

            agg = qs.aggregate(
                total_sum=Sum("total_area_sqft"),
                leasable_sum=Sum("leasable_area_sqft"),
            )
            total_sum = agg.get("total_sum") or 0
            leasable_sum = agg.get("leasable_sum") or 0

            if tower.total_area_sqft is not None and total_area is not None:
                if total_sum + total_area > tower.total_area_sqft:
                    raise serializers.ValidationError(
                        {"total_area_sqft": f"Sum of floor total area ({total_sum + total_area}) exceeds tower total area ({tower.total_area_sqft})."}
                    )
            if tower.leasable_area_sqft is not None and leasable_area is not None:
                if leasable_sum + leasable_area > tower.leasable_area_sqft:
                    raise serializers.ValidationError(
                        {"leasable_area_sqft": f"Sum of floor leasable area ({leasable_sum + leasable_area}) exceeds tower leasable area ({tower.leasable_area_sqft})."}
                    )

        return attrs

    class Meta:
        model = models.Floor
        fields = "__all__"
        read_only_fields = ("id", "scope", "created_at", "updated_at", "created_by", "updated_by", "is_active", "deleted_at")


class UnitSerializer(serializers.ModelSerializer):
    def validate(self, attrs):
        attrs = super().validate(attrs)
        floor = attrs.get("floor") or getattr(self.instance, "floor", None)
        builtup_area = attrs.get("builtup_area_sqft", getattr(self.instance, "builtup_area_sqft", None))
        leasable_area = attrs.get("leasable_area_sqft", getattr(self.instance, "leasable_area_sqft", None))

        # Validate: leasable_area ≤ builtup_area
        if builtup_area is not None and leasable_area is not None:
            if leasable_area > builtup_area:
                raise serializers.ValidationError(
                    {"leasable_area_sqft": "Leasable area cannot exceed built-up area."}
                )

        if floor:
            qs = models.Unit.objects.filter(floor=floor, is_active=True)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)

            agg = qs.aggregate(
                builtup_sum=Sum("builtup_area_sqft"),
                leasable_sum=Sum("leasable_area_sqft"),
            )
            builtup_sum = agg.get("builtup_sum") or 0
            leasable_sum = agg.get("leasable_sum") or 0

            # Sum of unit builtup_area ≤ floor total_area
            if floor.total_area_sqft is not None and builtup_area is not None:
                if builtup_sum + builtup_area > floor.total_area_sqft:
                    raise serializers.ValidationError(
                        {"builtup_area_sqft": f"Sum of unit built-up area ({builtup_sum + builtup_area}) exceeds floor total area ({floor.total_area_sqft})."}
                    )

            # Sum of unit leasable_area ≤ floor leasable_area
            if floor.leasable_area_sqft is not None and leasable_area is not None:
                if leasable_sum + leasable_area > floor.leasable_area_sqft:
                    raise serializers.ValidationError(
                        {"leasable_area_sqft": f"Sum of unit leasable area ({leasable_sum + leasable_area}) exceeds floor leasable area ({floor.leasable_area_sqft})."}
                    )

        return attrs

    class Meta:
        model = models.Unit
        fields = "__all__"
        read_only_fields = ("id", "scope", "created_at", "updated_at", "created_by", "updated_by", "is_active", "deleted_at")


class UnitAreaReservationSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.UnitAreaReservation
        fields = "__all__"
        read_only_fields = ("id", "scope", "created_at", "updated_at", "created_by", "updated_by", "is_active", "deleted_at")


class UnitAmenitySerializer(serializers.ModelSerializer):
    class Meta:
        model = models.UnitAmenity
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at", "created_by", "updated_by", "is_active", "deleted_at")


class UnitRoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.UnitRoom
        fields = "__all__"
        read_only_fields = ("id", "scope", "created_at", "updated_at", "created_by", "updated_by", "is_active", "deleted_at")


class AssetCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = models.AssetCategory
        fields = "__all__"
        read_only_fields = ("id", "scope", "created_at", "updated_at", "created_by", "updated_by", "is_active", "deleted_at")


class AssetItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.AssetItem
        fields = "__all__"
        read_only_fields = ("id", "scope", "created_at", "updated_at", "created_by", "updated_by", "is_active", "deleted_at")


class UnitAssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.UnitAsset
        fields = "__all__"
        read_only_fields = ("id", "scope", "created_at", "updated_at", "created_by", "updated_by", "is_active", "deleted_at")


class FormTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.FormTemplate
        fields = "__all__"
        read_only_fields = ("id", "scope", "created_at", "updated_at", "created_by", "updated_by", "is_active", "deleted_at")


class FormTemplateVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.FormTemplateVersion
        fields = "__all__"
        read_only_fields = ("id", "scope", "created_at", "updated_at", "created_by", "updated_by", "is_active", "deleted_at")


class FormFieldSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.FormField
        fields = "__all__"
        read_only_fields = ("id", "scope", "created_at", "updated_at", "created_by", "updated_by", "is_active", "deleted_at")


class SiteUnitFormConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.SiteUnitFormConfig
        fields = "__all__"
        read_only_fields = ("id", "scope", "created_at", "updated_at", "created_by", "updated_by", "is_active", "deleted_at")


class LandlordSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Landlord
        fields = "__all__"
        read_only_fields = ("id", "scope", "created_at", "updated_at", "created_by", "updated_by", "is_active", "deleted_at")


class LandlordContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.LandlordContact
        fields = "__all__"
        read_only_fields = ("id", "scope", "created_at", "updated_at", "created_by", "updated_by", "is_active", "deleted_at")


class SiteAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.SiteAttachment
        fields = "__all__"
        read_only_fields = ("id", "scope", "created_at", "updated_at", "created_by", "updated_by", "is_active", "deleted_at")
