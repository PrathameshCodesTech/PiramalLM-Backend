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
    list_display = ("id", "scope_type", "name", "code", "linked_to", "roles_count", "is_active", "created_at")
    search_fields = ("name", "code")
    list_filter = ("scope_type", "is_active")

    @admin.display(description="Linked To")
    def linked_to(self, obj):
        if obj.org:
            return f"Org: {obj.org.name}"
        elif obj.company:
            return f"Company: {obj.company.name}"
        elif obj.entity:
            return f"Entity: {obj.entity.name}"
        elif obj.site:
            return f"Site: {obj.site.name}"
        return "-"

    @admin.display(description="Roles")
    def roles_count(self, obj):
        return obj.roles.count()


@admin.register(models.Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("id", "scope_type", "scope_name", "code", "name", "is_system", "is_active")
    search_fields = ("code", "name", "scope__name")
    list_filter = ("scope__scope_type", "is_system", "is_active")

    @admin.display(description="Scope Type")
    def scope_type(self, obj):
        return obj.scope.scope_type if obj.scope else "-"

    @admin.display(description="Scope Name")
    def scope_name(self, obj):
        return obj.scope.name if obj.scope else "-"


@admin.register(models.ScopeMembership)
class ScopeMembershipAdmin(admin.ModelAdmin):
    list_display = ("id", "user_email", "scope_type", "scope_name", "role_code", "is_active", "created_at")
    list_filter = ("scope__scope_type", "scope", "role", "is_active")
    search_fields = ("user__username", "user__email", "scope__name", "role__code")

    @admin.display(description="User")
    def user_email(self, obj):
        return obj.user.email if obj.user else "-"

    @admin.display(description="Scope Type")
    def scope_type(self, obj):
        return obj.scope.scope_type if obj.scope else "-"

    @admin.display(description="Scope Name")
    def scope_name(self, obj):
        return obj.scope.name if obj.scope else "-"

    @admin.display(description="Role")
    def role_code(self, obj):
        return obj.role.code if obj.role else "-"


@admin.register(models.UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "phone")
    search_fields = ("user__username", "user__email")

