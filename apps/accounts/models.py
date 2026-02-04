from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.models import AuditModel


class Org(AuditModel):
    name = models.CharField(max_length=200)
    code = models.SlugField(max_length=80, unique=True)

    def __str__(self):
        return self.name


class Company(AuditModel):
    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="companies")
    name = models.CharField(max_length=200)
    code = models.SlugField(max_length=80)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["org", "code"], name="uq_company_org_code"),
        ]

    def __str__(self):
        return self.name


class Entity(AuditModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="entities")
    name = models.CharField(max_length=200)
    code = models.SlugField(max_length=80)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uq_entity_company_code"),
        ]

    def __str__(self):
        return self.name


class TenantScope(AuditModel):
    class ScopeType(models.TextChoices):
        ORG = "ORG", "Org"
        COMPANY = "COMPANY", "Company"
        ENTITY = "ENTITY", "Entity"
        SITE = "SITE", "Site"

    scope_type = models.CharField(max_length=20, choices=ScopeType.choices)
    org = models.ForeignKey(Org, null=True, blank=True, on_delete=models.CASCADE, related_name="scopes")
    company = models.ForeignKey(Company, null=True, blank=True, on_delete=models.CASCADE, related_name="scopes")
    entity = models.ForeignKey(Entity, null=True, blank=True, on_delete=models.CASCADE, related_name="scopes")
    site = models.ForeignKey(
        "properties.Site",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="scopes"
    )
    name = models.CharField(max_length=200)
    code = models.SlugField(max_length=80)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(org__isnull=False, company__isnull=True, entity__isnull=True, site__isnull=True)
                    | Q(org__isnull=True, company__isnull=False, entity__isnull=True, site__isnull=True)
                    | Q(org__isnull=True, company__isnull=True, entity__isnull=False, site__isnull=True)
                    | Q(org__isnull=True, company__isnull=True, entity__isnull=True, site__isnull=False)
                ),
                name="ck_scope_exactly_one_ref",
            ),
            models.UniqueConstraint(fields=["scope_type", "code"], name="uq_scope_type_code"),
        ]

    def clean(self):
        refs = [bool(self.org_id), bool(self.company_id), bool(self.entity_id), bool(self.site_id)]
        if sum(refs) != 1:
            raise ValidationError("TenantScope must link to exactly one of org/company/entity/site.")

    def __str__(self):
        return f"{self.scope_type} / {self.name}"

    def get_hierarchy_path(self):
        """Returns the full hierarchy path for this scope."""
        if self.scope_type == self.ScopeType.SITE and self.site:
            return {
                "site": self.site,
                "entity": getattr(self.site, "entity", None),
                "company": getattr(getattr(self.site, "entity", None), "company", None) if hasattr(self.site, "entity") else None,
                "org": None,
            }
        elif self.scope_type == self.ScopeType.ENTITY and self.entity:
            return {
                "site": None,
                "entity": self.entity,
                "company": self.entity.company,
                "org": self.entity.company.org,
            }
        elif self.scope_type == self.ScopeType.COMPANY and self.company:
            return {
                "site": None,
                "entity": None,
                "company": self.company,
                "org": self.company.org,
            }
        elif self.scope_type == self.ScopeType.ORG and self.org:
            return {
                "site": None,
                "entity": None,
                "company": None,
                "org": self.org,
            }
        return {}


class ScopeMembership(AuditModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="scope_memberships")
    scope = models.ForeignKey(TenantScope, on_delete=models.CASCADE, related_name="memberships")
    role = models.ForeignKey("Role", on_delete=models.PROTECT, related_name="memberships")
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "scope"], name="uq_membership_user_scope"),
        ]

    def __str__(self):
        return f"{self.user_id} -> {self.scope_id} ({self.role.code})"


class UserProfile(AuditModel):
    class UserRole(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        MANAGER = "MANAGER", "Manager"
        BROKER = "BROKER", "Broker"
        TENANT = "TENANT", "Tenant"
        VIEWER = "VIEWER", "Viewer"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    active_scope = models.ForeignKey(
        TenantScope,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="active_users",
    )
    role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.VIEWER,
        help_text="User's primary role in the system"
    )
    profile_json = models.JSONField(
        default=dict,
        blank=True,
        help_text="Custom profile data as JSON"
    )
    phone = models.CharField(max_length=20, blank=True)
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)

    def __str__(self):
        return f"Profile {self.user_id}"


class Permission(AuditModel):
    code = models.SlugField(max_length=120, unique=True)
    name = models.CharField(max_length=200)
    description = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return self.code


class Role(AuditModel):
    scope = models.ForeignKey(TenantScope, on_delete=models.CASCADE, related_name="roles")
    name = models.CharField(max_length=200)
    code = models.SlugField(max_length=80)
    is_system = models.BooleanField(default=False)
    permissions = models.ManyToManyField(Permission, through="RolePermission", related_name="roles")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["scope", "code"], name="uq_role_scope_code"),
        ]

    def __str__(self):
        return f"{self.scope_id}:{self.code}"


class UserCredential(AuditModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="credentials")
    scope = models.ForeignKey(TenantScope, on_delete=models.CASCADE, related_name="user_credentials")
    password_plain = models.CharField(max_length=256)

    class Meta:
        indexes = [
            models.Index(fields=["scope", "user"]),
        ]

    def __str__(self):
        return f"{self.user_id} / {self.scope_id}"


class RolePermission(AuditModel):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="role_permissions")
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, related_name="permission_roles")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["role", "permission"], name="uq_role_permission"),
        ]


class UserScope(AuditModel):
    """
    Granular user permissions at scope level (ORG, COMPANY, ENTITY, or SITE).
    This allows assigning users to specific scopes with fine-grained permissions.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="user_scopes"
    )
    scope = models.ForeignKey(
        TenantScope,
        on_delete=models.CASCADE,
        related_name="user_scopes"
    )

    # Granular permissions
    can_view = models.BooleanField(default=True)
    can_create = models.BooleanField(default=False)
    can_edit = models.BooleanField(default=False)
    can_delete = models.BooleanField(default=False)

    # Status
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        verbose_name = "User Scope"
        verbose_name_plural = "User Scopes"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "scope"],
                name="uq_user_scope"
            ),
        ]
        indexes = [
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["scope", "is_active"]),
        ]

    def __str__(self):
        perms = []
        if self.can_view:
            perms.append("V")
        if self.can_create:
            perms.append("C")
        if self.can_edit:
            perms.append("E")
        if self.can_delete:
            perms.append("D")
        return f"{self.user} -> {self.scope.name} [{'/'.join(perms)}]"

    @property
    def scope_type(self):
        return self.scope.scope_type if self.scope else None

    @property
    def scope_name(self):
        return self.scope.name if self.scope else None

    def has_permission(self, action):
        """Check if user has specific permission."""
        action_map = {
            "view": self.can_view,
            "create": self.can_create,
            "edit": self.can_edit,
            "delete": self.can_delete,
        }
        return self.is_active and action_map.get(action, False)
