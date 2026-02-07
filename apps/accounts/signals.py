"""
Signals to auto-create TenantScope when Org/Company/Entity is created,
and to auto-seed default roles when a TenantScope is created.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.accounts.models import Company, Entity, Org, TenantScope
from apps.accounts.role_utils import seed_roles_for_scope


@receiver(post_save, sender=Org)
def create_org_scope(sender, instance, created, **kwargs):
    """Auto-create TenantScope when Org is created."""
    if created:
        TenantScope.objects.get_or_create(
            org=instance,
            scope_type=TenantScope.ScopeType.ORG,
            defaults={
                "name": instance.name,
                "code": f"org-{instance.code}",
            }
        )


@receiver(post_save, sender=Company)
def create_company_scope(sender, instance, created, **kwargs):
    """Auto-create TenantScope when Company is created."""
    if created:
        TenantScope.objects.get_or_create(
            company=instance,
            scope_type=TenantScope.ScopeType.COMPANY,
            defaults={
                "name": instance.name,
                "code": f"company-{instance.code}",
            }
        )


@receiver(post_save, sender=Entity)
def create_entity_scope(sender, instance, created, **kwargs):
    """Auto-create TenantScope when Entity is created."""
    if created:
        TenantScope.objects.get_or_create(
            entity=instance,
            scope_type=TenantScope.ScopeType.ENTITY,
            defaults={
                "name": instance.name,
                "code": f"entity-{instance.code}",
            }
        )


@receiver(post_save, sender=TenantScope)
def seed_roles_for_new_scope(sender, instance, created, **kwargs):
    """Auto-seed default roles (admin, manager, staff, viewer) when TenantScope is created."""
    if created:
        seed_roles_for_scope(instance)
