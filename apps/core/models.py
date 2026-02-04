from django.conf import settings
from django.db import models
from django.utils import timezone


class ScopedQuerySet(models.QuerySet):
    def for_scope(self, scope):
        return self.filter(scope=scope)

    def active(self):
        return self.filter(is_active=True, deleted_at__isnull=True)


class AuditModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_%(class)s_set",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_%(class)s_set",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = ScopedQuerySet.as_manager()

    class Meta:
        abstract = True

    def soft_delete(self, using=None, keep_parents=False):
        self.is_active = False
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_active", "deleted_at"])


class TenantModel(AuditModel):
    scope = models.ForeignKey(
        "accounts.TenantScope",
        on_delete=models.CASCADE,
        related_name="%(class)s_set",
        db_index=True,
    )

    objects = ScopedQuerySet.as_manager()

    class Meta:
        abstract = True
