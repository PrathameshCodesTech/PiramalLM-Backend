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
            # 1:1 constraints - ensure one TenantScope per Org/Company/Entity/Site
            models.UniqueConstraint(
                fields=["org"],
                condition=Q(org__isnull=False),
                name="uq_scope_one_per_org"
            ),
            models.UniqueConstraint(
                fields=["company"],
                condition=Q(company__isnull=False),
                name="uq_scope_one_per_company"
            ),
            models.UniqueConstraint(
                fields=["entity"],
                condition=Q(entity__isnull=False),
                name="uq_scope_one_per_entity"
            ),
            models.UniqueConstraint(
                fields=["site"],
                condition=Q(site__isnull=False),
                name="uq_scope_one_per_site"
            ),
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

    def get_child_scopes(self):
        """
        Returns all child scopes (including self) based on hierarchy.
        ORG → returns self + all COMPANY scopes + all ENTITY scopes under those companies
        COMPANY → returns self + all ENTITY scopes under this company
        ENTITY → returns self only
        SITE → returns self only
        """
        scope_ids = [self.id]

        if self.scope_type == self.ScopeType.ORG and self.org:
            # Get all companies under this org
            company_ids = list(Company.objects.filter(org=self.org).values_list("id", flat=True))
            # Get company scopes
            company_scope_ids = list(
                TenantScope.objects.filter(
                    company_id__in=company_ids,
                    scope_type=self.ScopeType.COMPANY
                ).values_list("id", flat=True)
            )
            scope_ids.extend(company_scope_ids)

            # Get all entities under those companies
            entity_ids = list(Entity.objects.filter(company_id__in=company_ids).values_list("id", flat=True))
            # Get entity scopes
            entity_scope_ids = list(
                TenantScope.objects.filter(
                    entity_id__in=entity_ids,
                    scope_type=self.ScopeType.ENTITY
                ).values_list("id", flat=True)
            )
            scope_ids.extend(entity_scope_ids)

        elif self.scope_type == self.ScopeType.COMPANY and self.company:
            # Get all entities under this company
            entity_ids = list(Entity.objects.filter(company=self.company).values_list("id", flat=True))
            # Get entity scopes
            entity_scope_ids = list(
                TenantScope.objects.filter(
                    entity_id__in=entity_ids,
                    scope_type=self.ScopeType.ENTITY
                ).values_list("id", flat=True)
            )
            scope_ids.extend(entity_scope_ids)

        return TenantScope.objects.filter(id__in=scope_ids)

    @classmethod
    def get_available_scopes_for_user(cls, user):
        """
        Returns all scopes a user can access (for scope picker dropdown).
        Based on user's highest-level membership, returns that scope + all children.
        """
        from apps.accounts.models import ScopeMembership

        # Get all active memberships for user
        memberships = ScopeMembership.objects.filter(
            user=user,
            is_active=True
        ).select_related("scope")

        if not memberships.exists():
            return cls.objects.none()

        # Find the highest level scope (ORG > COMPANY > ENTITY > SITE)
        level_order = {
            cls.ScopeType.ORG: 1,
            cls.ScopeType.COMPANY: 2,
            cls.ScopeType.ENTITY: 3,
            cls.ScopeType.SITE: 4,
        }

        # Sort by level and get highest (lowest number = highest level)
        sorted_memberships = sorted(
            memberships,
            key=lambda m: level_order.get(m.scope.scope_type, 99)
        )

        # Get the highest level scope
        highest_scope = sorted_memberships[0].scope

        # Return this scope + all its children
        return highest_scope.get_child_scopes()


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


class RolePermission(AuditModel):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="role_permissions")
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, related_name="permission_roles")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["role", "permission"], name="uq_role_permission"),
        ]


