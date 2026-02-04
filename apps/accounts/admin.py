from django.contrib import admin

from apps.accounts import models


@admin.register(models.Org)
class OrgAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "code", "is_active", "created_at")
    search_fields = ("name", "code")


@admin.register(models.Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "code", "org", "is_active", "created_at")
    search_fields = ("name", "code")
    list_filter = ("org", "is_active")


@admin.register(models.Entity)
class EntityAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "code", "company", "is_active", "created_at")
    search_fields = ("name", "code")
    list_filter = ("company", "is_active")


@admin.register(models.TenantScope)
class TenantScopeAdmin(admin.ModelAdmin):
    list_display = ("id", "scope_type", "name", "code", "org", "company", "entity", "site", "is_active", "created_at")
    search_fields = ("name", "code")
    list_filter = ("scope_type", "is_active")


@admin.register(models.Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ("id", "code", "name")
    search_fields = ("code", "name")


@admin.register(models.Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("id", "scope", "code", "name", "is_system", "is_active")
    search_fields = ("code", "name")
    list_filter = ("scope", "is_system", "is_active")


@admin.register(models.RolePermission)
class RolePermissionAdmin(admin.ModelAdmin):
    list_display = ("id", "role", "permission")
    list_filter = ("role", "permission")


@admin.register(models.ScopeMembership)
class ScopeMembershipAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "scope", "role", "is_active", "created_at")
    list_filter = ("scope", "role", "is_active")
    search_fields = ("user__username", "user__email")


@admin.register(models.UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "role", "active_scope", "phone")
    search_fields = ("user__username", "user__email")
    list_filter = ("role",)


@admin.register(models.UserCredential)
class UserCredentialAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "scope", "created_at")
    search_fields = ("user__username", "user__email")
    list_filter = ("scope",)


@admin.register(models.UserScope)
class UserScopeAdmin(admin.ModelAdmin):
    list_display = (
        "id", "user", "scope", "can_view", "can_create",
        "can_edit", "can_delete", "is_active", "created_at"
    )
    search_fields = ("user__username", "user__email", "scope__name")
    list_filter = ("scope__scope_type", "is_active", "can_view", "can_create", "can_edit", "can_delete")
    raw_id_fields = ("user", "scope")
