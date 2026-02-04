from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from decimal import Decimal
from apps.core.models import TenantModel


class ClauseCategory(TenantModel):
    """
    Categories for grouping clauses.
    """

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children"
    )

    class Meta:
        verbose_name = "Clause Category"
        verbose_name_plural = "Clause Categories"
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["scope", "name"],
                name="unique_clause_category_name_per_scope"
            )
        ]

    def __str__(self):
        return self.name


class Clause(TenantModel):
    """
    Main clause model representing a legal/operational clause template.
    """

    class AppliesTo(models.TextChoices):
        COMMERCIAL = "COMMERCIAL", "Commercial"
        RESIDENTIAL = "RESIDENTIAL", "Residential"
        ALL = "ALL", "All"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ACTIVE = "ACTIVE", "Active"
        ARCHIVED = "ARCHIVED", "Archived"
        INACTIVE = "INACTIVE", "Inactive"

    # Identification
    clause_id = models.CharField(
        max_length=50,
        help_text="Auto-generated clause identifier"
    )
    title = models.CharField(max_length=255)
    category = models.ForeignKey(
        ClauseCategory,
        on_delete=models.PROTECT,
        related_name="clauses"
    )

    # Classification
    applies_to = models.CharField(
        max_length=20,
        choices=AppliesTo.choices,
        default=AppliesTo.ALL
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT
    )

    # Current version tracking
    current_version = models.PositiveIntegerField(default=1)
    current_minor_version = models.PositiveIntegerField(default=0)

    # Owner
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_clauses"
    )

    class Meta:
        verbose_name = "Clause"
        verbose_name_plural = "Clauses"
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["scope", "clause_id"],
                name="unique_clause_id_per_scope"
            )
        ]

    def __str__(self):
        return f"{self.clause_id} - {self.title}"

    @property
    def version_label(self):
        return f"v{self.current_version}.{self.current_minor_version}"

    def save(self, *args, **kwargs):
        # Auto-generate clause_id if not provided
        if not self.clause_id:
            # Generate ID based on category and count
            count = Clause.objects.filter(scope=self.scope).count() + 1
            self.clause_id = f"CLS-{count:04d}"
        super().save(*args, **kwargs)


class ClauseVersion(TenantModel):
    """
    Version history for a clause. Each amendment creates a new version.
    """

    class BumpType(models.TextChoices):
        MAJOR = "MAJOR", "Major (v1.0 → v2.0)"
        MINOR = "MINOR", "Minor (v1.0 → v1.1)"

    class VersionStatus(models.TextChoices):
        CURRENT = "CURRENT", "Current"
        ARCHIVED = "ARCHIVED", "Archived"

    clause = models.ForeignKey(
        Clause,
        on_delete=models.CASCADE,
        related_name="versions"
    )

    # Version numbers
    major_version = models.PositiveIntegerField(default=1)
    minor_version = models.PositiveIntegerField(default=0)
    version_status = models.CharField(
        max_length=20,
        choices=VersionStatus.choices,
        default=VersionStatus.CURRENT
    )

    # Content
    change_summary = models.TextField(
        blank=True,
        help_text="Summary of changes in this version"
    )
    body_text = models.TextField(
        blank=True,
        help_text="Main clause text content"
    )

    # Dynamic configuration stored as JSON
    config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured clause configuration (renewal, termination, etc.)"
    )

    # Metadata
    bump_type = models.CharField(
        max_length=10,
        choices=BumpType.choices,
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = "Clause Version"
        verbose_name_plural = "Clause Versions"
        ordering = ["-major_version", "-minor_version"]
        constraints = [
            models.UniqueConstraint(
                fields=["clause", "major_version", "minor_version"],
                name="unique_clause_version"
            )
        ]

    def __str__(self):
        return f"{self.clause.clause_id} v{self.major_version}.{self.minor_version}"

    @property
    def version_label(self):
        return f"v{self.major_version}.{self.minor_version}"

    def save(self, *args, **kwargs):
        # Archive previous current version when creating new current
        if self.version_status == self.VersionStatus.CURRENT:
            ClauseVersion.objects.filter(
                clause=self.clause,
                version_status=self.VersionStatus.CURRENT
            ).exclude(pk=self.pk).update(version_status=self.VersionStatus.ARCHIVED)
        super().save(*args, **kwargs)


class ClauseDocument(TenantModel):
    """
    Documents uploaded to the clause library.
    """

    class DocumentType(models.TextChoices):
        PDF = "PDF", "PDF"
        DOCX = "DOCX", "Word Document"
        XLSX = "XLSX", "Excel Spreadsheet"
        IMAGE = "IMAGE", "Image"
        OTHER = "OTHER", "Other"

    # Document details
    name = models.CharField(max_length=255)
    document_type = models.CharField(
        max_length=20,
        choices=DocumentType.choices,
        default=DocumentType.PDF
    )
    file = models.FileField(upload_to="clause_documents/%Y/%m/")
    file_size = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="File size in bytes"
    )
    mime_type = models.CharField(max_length=100, blank=True)

    # Uploader
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_clause_documents"
    )

    class Meta:
        verbose_name = "Clause Document"
        verbose_name_plural = "Clause Documents"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Auto-detect file size if file is provided
        if self.file and not self.file_size:
            self.file_size = self.file.size
        super().save(*args, **kwargs)


class ClauseDocumentLink(TenantModel):
    """
    Many-to-many relationship between documents and clauses.
    A document can be linked to multiple clauses.
    """

    document = models.ForeignKey(
        ClauseDocument,
        on_delete=models.CASCADE,
        related_name="clause_links"
    )
    clause = models.ForeignKey(
        Clause,
        on_delete=models.CASCADE,
        related_name="document_links"
    )

    class Meta:
        verbose_name = "Clause Document Link"
        verbose_name_plural = "Clause Document Links"
        constraints = [
            models.UniqueConstraint(
                fields=["document", "clause"],
                name="unique_document_clause_link"
            )
        ]

    def __str__(self):
        return f"{self.document.name} → {self.clause.title}"


class ClauseUsage(TenantModel):
    """
    Tracks which clauses are used in which lease agreements.
    """

    clause = models.ForeignKey(
        Clause,
        on_delete=models.CASCADE,
        related_name="usages"
    )
    clause_version = models.ForeignKey(
        ClauseVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="usages"
    )
    agreement = models.ForeignKey(
        "leases.Agreement",
        on_delete=models.CASCADE,
        related_name="clause_usages"
    )

    # Override config for this specific usage
    custom_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Custom configuration overrides for this agreement"
    )
    custom_body_text = models.TextField(
        blank=True,
        help_text="Custom body text for this agreement"
    )

    class Meta:
        verbose_name = "Clause Usage"
        verbose_name_plural = "Clause Usages"
        constraints = [
            models.UniqueConstraint(
                fields=["clause", "agreement"],
                name="unique_clause_per_agreement"
            )
        ]

    def __str__(self):
        return f"{self.clause.title} in {self.agreement.lease_id}"