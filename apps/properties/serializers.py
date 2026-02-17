from decimal import Decimal

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

        if total_area is None:
            raise serializers.ValidationError(
                {"total_builtup_area_sqft": "This field is required."}
            )
        if leasable_area is None:
            raise serializers.ValidationError(
                {"leasable_area_sqft": "This field is required."}
            )
        if leasable_area > total_area:
            raise serializers.ValidationError(
                {"leasable_area_sqft": "Leasable area cannot exceed total built-up area."}
            )

        # Site update: prevent remaining_leasable > remaining_total with existing towers
        if self.instance and (total_area is not None or leasable_area is not None):
            site_obj = self.instance
            tower_agg = site_obj.towers.filter(is_active=True).aggregate(
                total_sum=Sum("total_area_sqft"),
                leasable_sum=Sum("leasable_area_sqft"),
            )
            towers_total = tower_agg.get("total_sum") or Decimal("0")
            towers_leasable = tower_agg.get("leasable_sum") or Decimal("0")
            new_site_total = total_area if total_area is not None else site_obj.total_builtup_area_sqft
            new_site_leasable = leasable_area if leasable_area is not None else site_obj.leasable_area_sqft
            if new_site_total is not None and new_site_leasable is not None:
                rem_total = new_site_total - towers_total
                rem_leasable = new_site_leasable - towers_leasable
                if rem_leasable > rem_total:
                    raise serializers.ValidationError(
                        {
                            "leasable_area_sqft": (
                                f"Cannot save: with existing towers, remaining leasable ({rem_leasable}) would exceed "
                                f"remaining total ({rem_total}). Adjust site or tower areas."
                            )
                        }
                    )

        return attrs

    def get_remaining_total_builtup_area_sqft(self, obj):
        total = obj.total_builtup_area_sqft or Decimal("0")
        used = (
            obj.towers.filter(is_active=True).aggregate(s=Sum("total_area_sqft"))["s"] or Decimal("0")
        )
        return total - used

    def get_remaining_leasable_area_sqft(self, obj):
        total = obj.leasable_area_sqft or Decimal("0")
        used = (
            obj.towers.filter(is_active=True).aggregate(s=Sum("leasable_area_sqft"))["s"] or Decimal("0")
        )
        remaining_leasable = total - used
        remaining_total = self.get_remaining_total_builtup_area_sqft(obj)
        return min(remaining_leasable, remaining_total)

    def get_summary_counts(self, obj):
        """Get aggregated counts for towers, floors, units, and occupancy."""
        towers = obj.towers.filter(is_active=True)
        towers_count = towers.count()

        floors_count = 0
        units_count = 0
        leased_count = 0
        available_count = 0

        for tower in towers:
            floors = tower.floors.filter(is_active=True)
            floors_count += floors.count()
            for floor in floors:
                units = floor.units.filter(is_active=True)
                units_count += units.count()
                leased_count += units.filter(status=models.Unit.UnitStatus.LEASED).count()
                available_count += units.filter(status=models.Unit.UnitStatus.AVAILABLE).count()

        occupancy_percent = round((leased_count / units_count * 100), 1) if units_count > 0 else 0
        vacancy_percent = round(100 - occupancy_percent, 1)

        return {
            "towers_count": towers_count,
            "floors_count": floors_count,
            "units_count": units_count,
            "leased_units": leased_count,
            "available_units": available_count,
            "occupancy_percent": occupancy_percent,
            "vacancy_percent": vacancy_percent,
        }

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["remaining_total_builtup_area_sqft"] = self.get_remaining_total_builtup_area_sqft(instance)
        data["remaining_leasable_area_sqft"] = self.get_remaining_leasable_area_sqft(instance)
        # Add summary counts for list view
        data["summary"] = self.get_summary_counts(instance)
        return data

    class Meta:
        model = models.Site
        fields = "__all__"
        read_only_fields = ("id", "scope", "created_at", "updated_at", "created_by", "updated_by", "is_active", "deleted_at")
        extra_kwargs = {
            "total_builtup_area_sqft": {"required": True},
            "leasable_area_sqft": {"required": True},
        }


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

        if total_area is None:
            raise serializers.ValidationError({"total_area_sqft": "This field is required."})
        if leasable_area is None:
            raise serializers.ValidationError({"leasable_area_sqft": "This field is required."})
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
            total_sum = agg.get("total_sum") or Decimal("0")
            leasable_sum = agg.get("leasable_sum") or Decimal("0")
            new_total = total_sum + total_area
            new_leasable = leasable_sum + leasable_area
            site_total = site.total_builtup_area_sqft
            site_leasable = site.leasable_area_sqft
            if site_total is not None and new_total > site_total:
                raise serializers.ValidationError(
                    {
                        "total_area_sqft": (
                            f"You can allocate only {site_total - total_sum:,.2f} sqft more for total area "
                            f"in this site. You entered {total_area:,.2f} sqft. "
                            f"Current site limit is {site_total:,.2f} sqft."
                        )
                    }
                )
            if site_leasable is not None and new_leasable > site_leasable:
                raise serializers.ValidationError(
                    {
                        "leasable_area_sqft": (
                            f"You can allocate only {site_leasable - leasable_sum:,.2f} sqft more for leasable area "
                            f"in this site. You entered {leasable_area:,.2f} sqft. "
                            f"Current site leasable limit is {site_leasable:,.2f} sqft."
                        )
                    }
                )

        # Tower update: prevent remaining_leasable > remaining_total with existing floors
        if self.instance and (total_area is not None or leasable_area is not None):
            tower_obj = self.instance
            floor_agg = tower_obj.floors.filter(is_active=True).aggregate(
                total_sum=Sum("total_area_sqft"),
                leasable_sum=Sum("leasable_area_sqft"),
            )
            floors_total = floor_agg.get("total_sum") or Decimal("0")
            floors_leasable = floor_agg.get("leasable_sum") or Decimal("0")
            new_tower_total = total_area if total_area is not None else tower_obj.total_area_sqft
            new_tower_leasable = leasable_area if leasable_area is not None else tower_obj.leasable_area_sqft
            if new_tower_total is not None and new_tower_leasable is not None:
                rem_total = new_tower_total - floors_total
                rem_leasable = new_tower_leasable - floors_leasable
                if rem_leasable > rem_total:
                    raise serializers.ValidationError(
                        {
                            "leasable_area_sqft": (
                                f"Cannot save: with existing floors, remaining leasable ({rem_leasable}) would exceed "
                                f"remaining total ({rem_total}). Adjust tower or floor areas."
                            )
                        }
                    )

        return attrs

    def get_remaining_total_area_sqft(self, obj):
        total = obj.total_area_sqft or Decimal("0")
        used = obj.floors.filter(is_active=True).aggregate(s=Sum("total_area_sqft"))["s"] or Decimal("0")
        return total - used

    def get_remaining_leasable_area_sqft(self, obj):
        total = obj.leasable_area_sqft or Decimal("0")
        used = obj.floors.filter(is_active=True).aggregate(s=Sum("leasable_area_sqft"))["s"] or Decimal("0")
        remaining_leasable = total - used
        remaining_total = self.get_remaining_total_area_sqft(obj)
        return min(remaining_leasable, remaining_total)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["remaining_total_area_sqft"] = self.get_remaining_total_area_sqft(instance)
        data["remaining_leasable_area_sqft"] = self.get_remaining_leasable_area_sqft(instance)
        return data

    class Meta:
        model = models.Tower
        fields = "__all__"
        read_only_fields = ("id", "scope", "created_at", "updated_at", "created_by", "updated_by", "is_active", "deleted_at")
        extra_kwargs = {
            "total_area_sqft": {"required": True},
            "leasable_area_sqft": {"required": True},
        }


class FloorSerializer(serializers.ModelSerializer):
    def validate(self, attrs):
        attrs = super().validate(attrs)
        tower = attrs.get("tower") or getattr(self.instance, "tower", None)
        total_area = attrs.get("total_area_sqft", getattr(self.instance, "total_area_sqft", None))
        leasable_area = attrs.get("leasable_area_sqft", getattr(self.instance, "leasable_area_sqft", None))
        cam_area = attrs.get("cam_area_sqft", getattr(self.instance, "cam_area_sqft", None))

        if total_area is None:
            raise serializers.ValidationError({"total_area_sqft": "This field is required."})
        if leasable_area is None:
            raise serializers.ValidationError({"leasable_area_sqft": "This field is required."})
        if leasable_area > total_area:
            raise serializers.ValidationError(
                {"leasable_area_sqft": "Leasable area cannot exceed total area."}
            )
        if total_area is not None and cam_area is not None and (leasable_area + cam_area) > total_area:
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
            total_sum = agg.get("total_sum") or Decimal("0")
            leasable_sum = agg.get("leasable_sum") or Decimal("0")
            new_total = total_sum + total_area
            new_leasable = leasable_sum + leasable_area
            tower_total = tower.total_area_sqft
            tower_leasable = tower.leasable_area_sqft
            if tower_total is not None and new_total > tower_total:
                raise serializers.ValidationError(
                    {"total_area_sqft": f"Sum of floor total area ({new_total}) exceeds tower total area ({tower_total}). Remaining: {tower_total - total_sum}."}
                )
            if tower_leasable is not None and new_leasable > tower_leasable:
                raise serializers.ValidationError(
                    {"leasable_area_sqft": f"Sum of floor leasable area ({new_leasable}) exceeds tower leasable area ({tower_leasable}). Remaining: {tower_leasable - leasable_sum}."}
                )
            # Prevent remaining_leasable > remaining_total for tower
            if tower_total is not None and tower_leasable is not None:
                remaining_total = tower_total - new_total
                remaining_leasable = tower_leasable - new_leasable
                if remaining_leasable > remaining_total:
                    raise serializers.ValidationError(
                        {
                            "leasable_area_sqft": (
                                f"Cannot save: remaining leasable ({remaining_leasable}) would exceed remaining total ({remaining_total}). "
                                "Adjust floor total and leasable so that the tower's remaining leasable does not exceed its remaining total."
                            )
                        }
                    )

        return attrs

    def get_remaining_total_area_sqft(self, obj):
        total = obj.total_area_sqft or Decimal("0")
        used = obj.units.filter(is_active=True).aggregate(s=Sum("builtup_area_sqft"))["s"] or Decimal("0")
        return total - used

    def get_remaining_leasable_area_sqft(self, obj):
        total = obj.leasable_area_sqft or Decimal("0")
        used = obj.units.filter(is_active=True).aggregate(s=Sum("leasable_area_sqft"))["s"] or Decimal("0")
        remaining_leasable = total - used
        remaining_total = self.get_remaining_total_area_sqft(obj)
        return min(remaining_leasable, remaining_total)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["remaining_total_area_sqft"] = self.get_remaining_total_area_sqft(instance)
        data["remaining_leasable_area_sqft"] = self.get_remaining_leasable_area_sqft(instance)
        return data

    class Meta:
        model = models.Floor
        fields = "__all__"
        read_only_fields = ("id", "scope", "created_at", "updated_at", "created_by", "updated_by", "is_active", "deleted_at")
        extra_kwargs = {
            "total_area_sqft": {"required": True},
            "leasable_area_sqft": {"required": True},
        }


class UnitSerializer(serializers.ModelSerializer):
    def validate(self, attrs):
        attrs = super().validate(attrs)
        floor = attrs.get("floor") or getattr(self.instance, "floor", None)
        builtup_area = attrs.get("builtup_area_sqft", getattr(self.instance, "builtup_area_sqft", None))
        leasable_area = attrs.get("leasable_area_sqft", getattr(self.instance, "leasable_area_sqft", None))

        if builtup_area is None:
            raise serializers.ValidationError({"builtup_area_sqft": "This field is required."})
        if leasable_area is None:
            raise serializers.ValidationError({"leasable_area_sqft": "This field is required."})
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
            builtup_sum = agg.get("builtup_sum") or Decimal("0")
            leasable_sum = agg.get("leasable_sum") or Decimal("0")
            new_builtup = builtup_sum + builtup_area
            new_leasable = leasable_sum + leasable_area
            floor_total = floor.total_area_sqft
            floor_leasable = floor.leasable_area_sqft
            if floor_total is not None and new_builtup > floor_total:
                raise serializers.ValidationError(
                    {"builtup_area_sqft": f"Sum of unit built-up area ({new_builtup}) exceeds floor total area ({floor_total}). Remaining: {floor_total - builtup_sum}."}
                )
            if floor_leasable is not None and new_leasable > floor_leasable:
                raise serializers.ValidationError(
                    {"leasable_area_sqft": f"Sum of unit leasable area ({new_leasable}) exceeds floor leasable area ({floor_leasable}). Remaining: {floor_leasable - leasable_sum}."}
                )
            # Prevent remaining_leasable > remaining_total for floor
            floor_total = floor.total_area_sqft
            if floor_total is not None and floor_leasable is not None:
                remaining_total = floor_total - new_builtup
                remaining_leasable = floor_leasable - new_leasable
                if remaining_leasable > remaining_total:
                    raise serializers.ValidationError(
                        {
                            "leasable_area_sqft": (
                                f"Cannot save: remaining leasable ({remaining_leasable}) would exceed remaining total ({remaining_total}). "
                                "Adjust unit built-up and leasable so that the floor's remaining leasable does not exceed its remaining total."
                            )
                        }
                    )

        return attrs

    class Meta:
        model = models.Unit
        fields = "__all__"
        read_only_fields = ("id", "scope", "created_at", "updated_at", "created_by", "updated_by", "is_active", "deleted_at")
        extra_kwargs = {
            "builtup_area_sqft": {"required": True},
            "leasable_area_sqft": {"required": True},
        }


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
