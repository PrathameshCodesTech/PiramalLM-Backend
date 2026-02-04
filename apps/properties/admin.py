from django.contrib import admin

from apps.properties import models


@admin.register(models.Amenity)
class AmenityAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "code", "scope", "is_active")
    search_fields = ("name", "code")
    list_filter = ("scope", "is_active")


@admin.register(models.Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "code", "scope", "is_active")
    search_fields = ("name", "code")
    list_filter = ("scope", "is_active")


@admin.register(models.Site)
class SiteAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "code", "site_type", "scope", "city", "is_active")
    search_fields = ("name", "code", "city")
    list_filter = ("scope", "site_type", "is_active")


@admin.register(models.SiteAmenity)
class SiteAmenityAdmin(admin.ModelAdmin):
    list_display = ("id", "site", "amenity")
    list_filter = ("site", "amenity")


@admin.register(models.Tower)
class TowerAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "code", "site", "scope", "building_type", "total_floors", "is_active")
    search_fields = ("name", "code")
    list_filter = ("site", "building_type", "scope", "is_active")


@admin.register(models.Floor)
class FloorAdmin(admin.ModelAdmin):
    list_display = ("id", "tower", "number", "status", "site", "scope", "is_active")
    list_filter = ("tower", "status", "scope", "is_active")


@admin.register(models.Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ("id", "unit_no", "unit_type", "status", "floor", "scope", "is_active")
    search_fields = ("unit_no",)
    list_filter = ("unit_type", "status", "scope", "is_active")


@admin.register(models.UnitAreaReservation)
class UnitAreaReservationAdmin(admin.ModelAdmin):
    list_display = ("id", "unit", "lease_id", "reserved_area_sqft", "reserved_at", "scope", "is_active")
    list_filter = ("scope", "is_active")


@admin.register(models.UnitAmenity)
class UnitAmenityAdmin(admin.ModelAdmin):
    list_display = ("id", "unit", "amenity")
    list_filter = ("unit", "amenity")


@admin.register(models.UnitRoom)
class UnitRoomAdmin(admin.ModelAdmin):
    list_display = ("id", "unit", "room", "quantity", "scope")
    list_filter = ("unit", "room", "scope")


@admin.register(models.AssetCategory)
class AssetCategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "code", "scope", "is_active")
    search_fields = ("name", "code")
    list_filter = ("scope", "is_active")


@admin.register(models.AssetItem)
class AssetItemAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "code", "category", "scope", "is_active")
    search_fields = ("name", "code")
    list_filter = ("category", "scope", "is_active")


@admin.register(models.UnitAsset)
class UnitAssetAdmin(admin.ModelAdmin):
    list_display = ("id", "unit", "asset_item", "quantity", "scope")
    list_filter = ("unit", "asset_item", "scope")


@admin.register(models.FormTemplate)
class FormTemplateAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "code", "scope", "is_active")
    search_fields = ("name", "code")
    list_filter = ("scope", "is_active")


@admin.register(models.FormTemplateVersion)
class FormTemplateVersionAdmin(admin.ModelAdmin):
    list_display = ("id", "template", "version", "is_published", "scope", "is_active")
    list_filter = ("template", "is_published", "scope", "is_active")


@admin.register(models.FormField)
class FormFieldAdmin(admin.ModelAdmin):
    list_display = ("id", "version", "key", "label", "category", "scope")
    list_filter = ("version", "category", "scope")
    search_fields = ("key", "label")


@admin.register(models.SiteUnitFormConfig)
class SiteUnitFormConfigAdmin(admin.ModelAdmin):
    list_display = ("id", "site", "unit_type", "form_version", "scope")
    list_filter = ("site", "unit_type", "scope")
