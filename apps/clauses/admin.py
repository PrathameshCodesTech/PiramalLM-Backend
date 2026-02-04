from django.contrib import admin
from . import models


@admin.register(models.ClauseCategory)
class ClauseCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    ordering = ("sort_order", "name")


@admin.register(models.Clause)
class ClauseAdmin(admin.ModelAdmin):
    list_display = (
        "clause_id", "title", "category", "applies_to",
        "status", "version_label", "owner", "updated_at"
    )
    list_filter = ("status", "applies_to", "category")
    search_fields = ("clause_id", "title")
    date_hierarchy = "created_at"
    ordering = ("-updated_at",)


@admin.register(models.ClauseVersion)
class ClauseVersionAdmin(admin.ModelAdmin):
    list_display = (
        "clause", "version_label", "version_status",
        "bump_type", "created_at", "created_by"
    )
    list_filter = ("version_status", "bump_type")
    search_fields = ("clause__clause_id", "clause__title", "change_summary")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)


@admin.register(models.ClauseDocument)
class ClauseDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "name", "document_type", "file_size",
        "uploaded_by", "created_at"
    )
    list_filter = ("document_type",)
    search_fields = ("name",)
    date_hierarchy = "created_at"
    ordering = ("-created_at",)


@admin.register(models.ClauseDocumentLink)
class ClauseDocumentLinkAdmin(admin.ModelAdmin):
    list_display = ("document", "clause", "created_at")
    search_fields = ("document__name", "clause__title")
    ordering = ("-created_at",)


@admin.register(models.ClauseUsage)
class ClauseUsageAdmin(admin.ModelAdmin):
    list_display = (
        "clause", "agreement", "clause_version", "created_at"
    )
    search_fields = ("clause__title", "agreement__lease_id")
    ordering = ("-created_at",)
