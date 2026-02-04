from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.core.models import AuditModel, TenantModel


class OwnershipType(models.TextChoices):
    OWN = "OWN", "Own"
    JOINT_VENTURE = "JOINT_VENTURE", "Joint Venture"
    LEASED_IN = "LEASED_IN", "Leased-In"


class Amenity(TenantModel):
    name = models.CharField(max_length=120)
    code = models.SlugField(max_length=80)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["scope", "code"], name="uq_amenity_scope_code"),
        ]

    def __str__(self):
        return self.name


class Room(TenantModel):
    name = models.CharField(max_length=120)
    code = models.SlugField(max_length=80)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["scope", "code"], name="uq_room_scope_code"),
        ]

    def __str__(self):
        return self.name


class Site(TenantModel):
    class SiteType(models.TextChoices):
        RESIDENTIAL = "RESIDENTIAL", "Residential"
        COMMERCIAL = "COMMERCIAL", "Commercial"
        MIXED = "MIXED", "Mixed"

    class ManagementFeeType(models.TextChoices):
        PERCENTAGE = "PERCENTAGE", "Percentage"
        AMOUNT = "AMOUNT", "Amount"

    name = models.CharField(max_length=150)
    code = models.SlugField(max_length=80)
    image = models.ImageField(upload_to="sites/images/", null=True, blank=True)

    address_line1 = models.CharField(max_length=255, blank=True)
    address_line2 = models.CharField(max_length=255, blank=True)
    landmark = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120, blank=True)
    state = models.CharField(max_length=120, blank=True)
    country = models.CharField(max_length=120, blank=True, default="India")
    pincode = models.CharField(max_length=10, blank=True, db_index=True)

    site_type = models.CharField(max_length=20, choices=SiteType.choices, default=SiteType.RESIDENTIAL)
    base_rate_sqft = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Default base rent rate per sqft for this site (used as fallback).",
    )
    leasable_area_sqft = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    total_builtup_area_sqft = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    common_area_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    common_area_sqft = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    title = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    building_street = models.CharField(max_length=255, blank=True)
    ownership_type = models.CharField(max_length=20, choices=OwnershipType.choices, default=OwnershipType.OWN)
    management_fee_type = models.CharField(
        max_length=20, choices=ManagementFeeType.choices, default=ManagementFeeType.PERCENTAGE
    )
    management_fee_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    contract_start_date = models.DateField(null=True, blank=True)
    contract_end_date = models.DateField(null=True, blank=True)
    terms_and_conditions = models.TextField(blank=True)

    amenities = models.ManyToManyField("Amenity", through="SiteAmenity", related_name="sites", blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["scope", "code"], name="uq_site_scope_code"),
        ]

    def clean(self):
        if self.leasable_area_sqft and self.total_builtup_area_sqft and self.leasable_area_sqft > self.total_builtup_area_sqft:
            raise ValidationError("leasable_area_sqft cannot be greater than total_builtup_area_sqft.")

        if self.common_area_percent is not None and (self.common_area_percent < 0 or self.common_area_percent > 100):
            raise ValidationError("common_area_percent must be between 0 and 100.")

        if self.common_area_sqft is not None and self.common_area_sqft < 0:
            raise ValidationError("common_area_sqft must be >= 0.")
        if self.contract_start_date and self.contract_end_date:
            if self.contract_end_date < self.contract_start_date:
                raise ValidationError("contract_end_date cannot be before contract_start_date.")

    def __str__(self):
        return f"{self.scope} / {self.name}"


class SiteAmenity(AuditModel):
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="site_amenities")
    amenity = models.ForeignKey(Amenity, on_delete=models.CASCADE, related_name="amenity_sites")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["site", "amenity"], name="uq_site_amenity"),
        ]


class Tower(TenantModel):
    class BuildingType(models.TextChoices):
        RESIDENTIAL = "RESIDENTIAL", "Residential"
        COMMERCIAL = "COMMERCIAL", "Commercial"
        MIXED = "MIXED", "Mixed"
        OFFICE = "OFFICE", "Office"
        RETAIL = "RETAIL", "Retail"
        WAREHOUSE = "WAREHOUSE", "Warehouse"

    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="towers")
    name = models.CharField(max_length=120)
    code = models.SlugField(max_length=80)

    building_type = models.CharField(max_length=30, choices=BuildingType.choices, blank=True)
    total_floors = models.PositiveIntegerField(null=True, blank=True)
    total_area_sqft = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    leasable_area_sqft = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    completion_date = models.DateField(null=True, blank=True)
    occupancy_date = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["site", "code"], name="uq_tower_site_code"),
        ]
        indexes = [
            models.Index(fields=["site", "code"]),
            models.Index(fields=["site", "name"]),
        ]

    def clean(self):
        super().clean()
        if self.site_id and self.scope_id and self.site.scope_id != self.scope_id:
            raise ValidationError("Tower.scope must match Tower.site.scope.")
        if self.leasable_area_sqft is not None and self.total_area_sqft is not None:
            if self.leasable_area_sqft > self.total_area_sqft:
                raise ValidationError("Tower leasable_area_sqft cannot be greater than total_area_sqft.")
        if self.completion_date and self.occupancy_date:
            if self.occupancy_date < self.completion_date:
                raise ValidationError("occupancy_date cannot be before completion_date.")
        if self.total_floors is not None and self.total_floors < 1:
            raise ValidationError("total_floors must be >= 1.")

    def __str__(self):
        return f"{self.site} / {self.name}"


class Floor(TenantModel):
    class FloorStatus(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Available"
        LEASED = "LEASED", "Leased"
        MAINTENANCE = "MAINTENANCE", "Maintenance"

    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="floors")
    tower = models.ForeignKey(Tower, on_delete=models.CASCADE, related_name="floors")

    number = models.IntegerField()
    label = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=20, choices=FloorStatus.choices, default=FloorStatus.AVAILABLE)

    total_area_sqft = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    leasable_area_sqft = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    cam_area_sqft = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    floor_type = models.CharField(max_length=50, blank=True)
    allowed_use = models.CharField(max_length=80, blank=True)
    leasing_type = models.CharField(max_length=80, blank=True)
    max_units_allowed = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tower", "number"], name="uq_floor_tower_number"),
            models.CheckConstraint(
                condition=Q(total_area_sqft__isnull=True) | Q(total_area_sqft__gte=0),
                name="ck_floor_total_gte_0",
            ),
            models.CheckConstraint(
                condition=Q(leasable_area_sqft__isnull=True) | Q(leasable_area_sqft__gte=0),
                name="ck_floor_leasable_gte_0",
            ),
            models.CheckConstraint(
                condition=Q(cam_area_sqft__isnull=True) | Q(cam_area_sqft__gte=0),
                name="ck_floor_cam_gte_0",
            ),
            models.CheckConstraint(
                condition=(
                    Q(total_area_sqft__isnull=True)
                    | Q(leasable_area_sqft__isnull=True)
                    | Q(leasable_area_sqft__lte=F("total_area_sqft"))
                ),
                name="ck_floor_leasable_lte_total",
            ),
            models.CheckConstraint(
                condition=(
                    Q(total_area_sqft__isnull=True)
                    | Q(cam_area_sqft__isnull=True)
                    | Q(cam_area_sqft__lte=F("total_area_sqft"))
                ),
                name="ck_floor_cam_lte_total",
            ),
        ]

    def clean(self):
        super().clean()

        if self.tower_id and self.site_id and self.tower.site_id != self.site_id:
            raise ValidationError("Floor.site must match Floor.tower.site.")
        if self.site_id and self.scope_id and self.site.scope_id != self.scope_id:
            raise ValidationError("Floor.scope must match Floor.site.scope.")

        if self.total_area_sqft is not None and self.total_area_sqft < 0:
            raise ValidationError("total_area_sqft must be >= 0")

        if self.leasable_area_sqft is not None and self.leasable_area_sqft < 0:
            raise ValidationError("leasable_area_sqft must be >= 0")

        if self.cam_area_sqft is not None and self.cam_area_sqft < 0:
            raise ValidationError("cam_area_sqft must be >= 0")

        if self.total_area_sqft is not None and self.leasable_area_sqft is not None:
            if self.leasable_area_sqft > self.total_area_sqft:
                raise ValidationError("leasable_area_sqft cannot be greater than total_area_sqft")

        if self.total_area_sqft is not None and self.cam_area_sqft is not None:
            if self.cam_area_sqft > self.total_area_sqft:
                raise ValidationError("cam_area_sqft cannot be greater than total_area_sqft")


class Unit(TenantModel):
    class UnitType(models.TextChoices):
        RESIDENTIAL = "RESIDENTIAL", "Residential"
        COMMERCIAL = "COMMERCIAL", "Commercial"
        WAREHOUSE = "WAREHOUSE", "Warehouse"

    class UnitStatus(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Available"
        LEASED = "LEASED", "Leased"
        MAINTENANCE = "MAINTENANCE", "Maintenance"
        HOLD = "HOLD", "Hold"

    floor = models.ForeignKey(Floor, on_delete=models.CASCADE, related_name="units")

    unit_no = models.CharField(max_length=50)
    unit_type = models.CharField(max_length=20, choices=UnitType.choices)

    status = models.CharField(max_length=20, choices=UnitStatus.choices, default=UnitStatus.AVAILABLE)

    leasable_area_sqft = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    builtup_area_sqft = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    base_rent_default = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    cam_default = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    security_deposit_default = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    layout_notes = models.CharField(max_length=255, blank=True)

    form_version = models.ForeignKey(
        "FormTemplateVersion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="units",
    )
    custom_data = models.JSONField(default=dict, blank=True)

    amenities = models.ManyToManyField(Amenity, through="UnitAmenity", related_name="units", blank=True)
    is_divisible = models.BooleanField(
        default=False,
        help_text="If true, this unit can be leased partially (by sqft).",
        db_index=True,
    )
    min_divisible_area_sqft = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Optional: minimum chunk size allowed when partially leasing.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["floor", "unit_no"], name="uq_unit_floor_unitno"),
        ]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["unit_type"]),
        ]

    def clean(self):
        if self.floor_id and self.scope_id and self.floor.scope_id != self.scope_id:
            raise ValidationError("Unit.scope must match Unit.floor.scope.")
        if self.leasable_area_sqft and self.builtup_area_sqft and self.leasable_area_sqft > self.builtup_area_sqft:
            raise ValidationError("leasable_area_sqft cannot be greater than builtup_area_sqft.")

    def __str__(self):
        return f"{self.floor} / {self.unit_no}"


class UnitAreaReservation(TenantModel):
    """
    Stores reserved/leased area against a unit from external service (LeaseService).
    Active rows mean area is reserved and not available for other leases.
    """

    class Source(models.TextChoices):
        LEASE_SERVICE = "LEASE_SERVICE", "Lease Service"

    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="area_reservations")

    source = models.CharField(max_length=30, choices=Source.choices, default=Source.LEASE_SERVICE, db_index=True)

    source_scope_type = models.CharField(max_length=20, blank=True, db_index=True)
    source_scope_id = models.BigIntegerField(null=True, blank=True, db_index=True)

    lease_id = models.BigIntegerField(db_index=True)
    key = models.CharField(max_length=80, db_index=True)  # e.g. "alloc:123" (allocation.id)

    reserved_area_sqft = models.DecimalField(max_digits=14, decimal_places=2)

    reserved_at = models.DateTimeField(default=timezone.now, db_index=True)
    released_at = models.DateTimeField(null=True, blank=True)

    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["unit", "source", "lease_id", "key"],
                name="uq_unit_reserve_once",
            ),
            models.CheckConstraint(
                condition=Q(reserved_area_sqft__gt=0),
                name="ck_reserved_area_gt_0",
            ),
        ]
        indexes = [
            models.Index(fields=["unit", "is_active"]),
            models.Index(fields=["lease_id", "is_active"]),
        ]

    def clean(self):
        if self.unit_id and self.scope_id and self.unit.scope_id != self.scope_id:
            raise ValidationError("UnitAreaReservation.scope must match Unit.scope.")
        if self.reserved_area_sqft is None or self.reserved_area_sqft <= 0:
            raise ValidationError("reserved_area_sqft must be > 0")

    def __str__(self):
        return f"RESERVE unit={self.unit_id} lease={self.lease_id} {self.reserved_area_sqft} ({self.key})"


class UnitAmenity(AuditModel):
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="unit_amenities")
    amenity = models.ForeignKey(Amenity, on_delete=models.CASCADE, related_name="amenity_units")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["unit", "amenity"], name="uq_unit_amenity"),
        ]


class UnitRoom(TenantModel):
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="unit_rooms")
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="room_units")

    quantity = models.PositiveSmallIntegerField(default=1)
    area_sqft = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["unit", "room"], name="uq_unit_room"),
        ]

    def clean(self):
        if self.unit_id and self.scope_id and self.unit.scope_id != self.scope_id:
            raise ValidationError("UnitRoom.scope must match Unit.scope.")
        if self.quantity < 1:
            raise ValidationError("quantity must be >= 1")
        if self.unit and self.unit.unit_type != "RESIDENTIAL":
            raise ValidationError("UnitRoom can be added only for RESIDENTIAL units.")


class AssetCategory(TenantModel):
    """
    Master list of asset categories (e.g. Bed, Bath, Appliances, Furniture).
    Company-wide; same list across all sites/units.
    """

    name = models.CharField(max_length=120)
    code = models.SlugField(max_length=80)
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name_plural = "Asset categories"
        constraints = [
            models.UniqueConstraint(fields=["scope", "code"], name="uq_assetcategory_scope_code"),
        ]

    def __str__(self):
        return self.name


class AssetItem(TenantModel):
    """
    Master list of asset types (e.g. Double Bed, AC 1.5T, Sofa).
    Company-wide; same list across all sites/units.
    """

    category = models.ForeignKey(AssetCategory, on_delete=models.CASCADE, related_name="items")
    name = models.CharField(max_length=120)
    code = models.SlugField(max_length=80)
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["category", "code"], name="uq_assetitem_category_code"),
        ]
        indexes = [
            models.Index(fields=["category"]),
        ]

    def clean(self):
        if self.category_id and self.scope_id and self.category.scope_id != self.scope_id:
            raise ValidationError("AssetItem.scope must match AssetCategory.scope.")

    def __str__(self):
        return f"{self.category.name} / {self.name}"


class UnitAsset(TenantModel):
    """
    Assets assigned to a unit (what comes with the unit on lease).
    Links Unit to AssetItem with quantity; optional condition/notes.
    """

    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="unit_assets")
    asset_item = models.ForeignKey(AssetItem, on_delete=models.PROTECT, related_name="unit_assets")
    quantity = models.PositiveIntegerField(default=1)
    condition = models.CharField(max_length=80, blank=True, help_text="e.g. New, Good, Fair")
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["unit", "asset_item"], name="uq_unit_asset_item"),
        ]
        indexes = [
            models.Index(fields=["unit"]),
            models.Index(fields=["asset_item"]),
        ]

    def clean(self):
        if self.unit_id and self.scope_id and self.unit.scope_id != self.scope_id:
            raise ValidationError("UnitAsset.scope must match Unit.scope.")
        if self.asset_item_id and self.scope_id and self.asset_item.scope_id != self.scope_id:
            raise ValidationError("UnitAsset.scope must match AssetItem.scope.")
        if self.quantity is not None and self.quantity < 1:
            raise ValidationError("quantity must be >= 1.")

    def __str__(self):
        return f"{self.unit} / {self.asset_item} x{self.quantity}"


class FormTemplate(TenantModel):
    owner_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="owned_form_templates",
    )
    name = models.CharField(max_length=200)
    code = models.SlugField(max_length=80)
    description = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["scope", "code"], name="uq_formtemplate_scope_code"),
        ]

    def __str__(self):
        return self.name


class FormTemplateVersion(TenantModel):
    template = models.ForeignKey(FormTemplate, on_delete=models.CASCADE, related_name="versions")
    version = models.CharField(max_length=30)  # "1.0"
    is_published = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["template", "version"], name="uq_form_template_version"),
        ]

    def clean(self):
        if self.template_id and self.scope_id and self.template.scope_id != self.scope_id:
            raise ValidationError("FormTemplateVersion.scope must match FormTemplate.scope.")


class FormField(TenantModel):
    class FieldType(models.TextChoices):
        TEXT = "TEXT", "Text"
        NUMBER = "NUMBER", "Number"
        DATE = "DATE", "Date"
        SELECT = "SELECT", "Select"
        BOOL = "BOOL", "Boolean"
        ATTACHMENT = "ATTACHMENT", "Attachment"

    class Category(models.TextChoices):
        IDENTITY = "IDENTITY", "Identity"
        AREA_DETAILS = "AREA_DETAILS", "Area Details (Sq Ft)"
        STATUS_AVAILABILITY = "STATUS_AVAILABILITY", "Status & Availability"
        RENT_CHARGES = "RENT_CHARGES", "Rent & Charges"
        FINANCIALS = "FINANCIALS", "Financials"
        PHYSICAL = "PHYSICAL", "Physical Attributes"
        AMENITIES = "AMENITIES", "Amenities"
        LOCATION = "LOCATION", "Location"
        NOTES_ATTACHMENTS = "NOTES_ATTACHMENTS", "Notes & Attachments"
        BENCHMARK_ANALYTICS = "BENCHMARK_ANALYTICS", "Benchmark & Analytics"

    version = models.ForeignKey(FormTemplateVersion, on_delete=models.CASCADE, related_name="fields")

    category = models.CharField(
        max_length=40,
        choices=Category.choices,
        default=Category.IDENTITY,
        db_index=True,
    )

    key = models.SlugField(max_length=80)
    label = models.CharField(max_length=120)
    field_type = models.CharField(max_length=20, choices=FieldType.choices)

    required = models.BooleanField(default=False)
    options = models.JSONField(default=list, blank=True)
    help_text = models.CharField(max_length=255, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    is_system_field = models.BooleanField(
        default=False,
        help_text="System fields are compulsory and cannot be removed/modified via bulk",
        db_index=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["version", "key"], name="uq_formfield_version_key"),
        ]
        indexes = [
            models.Index(fields=["version", "sort_order"]),
            models.Index(fields=["category", "sort_order", "id"]),
        ]
        ordering = ["category", "sort_order", "id"]

    def clean(self):
        if self.version_id and self.scope_id and self.version.scope_id != self.scope_id:
            raise ValidationError("FormField.scope must match FormTemplateVersion.scope.")


class SiteUnitFormConfig(TenantModel):
    """
    Which unit form applies per site (optionally per unit_type)
    """

    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="unit_form_configs")
    unit_type = models.CharField(max_length=20, choices=Unit.UnitType.choices, null=True, blank=True)
    form_version = models.ForeignKey(FormTemplateVersion, on_delete=models.PROTECT, related_name="site_configs")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["site", "unit_type"], name="uq_site_unit_type_form"),
        ]

    def clean(self):
        if self.site_id and self.scope_id and self.site.scope_id != self.scope_id:
            raise ValidationError("SiteUnitFormConfig.scope must match Site.scope.")
        if self.form_version_id and self.scope_id and self.form_version.scope_id != self.scope_id:
            raise ValidationError("SiteUnitFormConfig.scope must match FormTemplateVersion.scope.")


class Landlord(TenantModel):
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="landlords")
    name = models.CharField(max_length=200)
    code = models.SlugField(max_length=80)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["site", "code"], name="uq_landlord_site_code"),
        ]

    def clean(self):
        if self.site_id and self.scope_id and self.site.scope_id != self.scope_id:
            raise ValidationError("Landlord.scope must match Site.scope.")

    def __str__(self):
        return self.name


class LandlordContact(TenantModel):
    landlord = models.ForeignKey(Landlord, on_delete=models.CASCADE, related_name="contacts")
    first_name = models.CharField(max_length=120, blank=True)
    last_name = models.CharField(max_length=120, blank=True)
    designation = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    mobile = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    is_primary = models.BooleanField(default=False)

    def clean(self):
        if self.landlord_id and self.scope_id and self.landlord.scope_id != self.scope_id:
            raise ValidationError("LandlordContact.scope must match Landlord.scope.")


class SiteAttachment(TenantModel):
    class AttachmentType(models.TextChoices):
        PHOTO = "PHOTO", "Photo"
        DOC = "DOC", "Document"

    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="attachments")
    attachment_type = models.CharField(max_length=10, choices=AttachmentType.choices, default=AttachmentType.DOC)
    title = models.CharField(max_length=200, blank=True)
    file = models.FileField(upload_to="sites/attachments/")

    def clean(self):
        if self.site_id and self.scope_id and self.site.scope_id != self.scope_id:
            raise ValidationError("SiteAttachment.scope must match Site.scope.")
