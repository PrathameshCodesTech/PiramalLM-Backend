from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Sum
from rest_framework import serializers
from apps.tenants.serializers import TenantCompanyListSerializer, TenantContactSerializer
from . import models


# ===================== Escalation Template Serializers =====================

class EscalationTemplateSerializer(serializers.ModelSerializer):
    """Full serializer for EscalationTemplate create/update."""

    def validate(self, attrs):
        instance = self.instance

        def get_value(field, default=None):
            if field in attrs:
                return attrs.get(field)
            if instance is not None:
                return getattr(instance, field)
            return default

        escalation_type = get_value(
            "escalation_type",
            models.EscalationTemplate.EscalationType.FIXED_PERCENT,
        )
        escalation_percentage = get_value("escalation_percentage")
        index_name = (get_value("index_name") or "").strip()
        index_base_value = get_value("index_base_value")
        step_schedule = get_value("step_schedule", [])
        cap_percentage = get_value("cap_percentage")
        floor_percentage = get_value("floor_percentage")

        errors = {}

        if escalation_type == models.EscalationTemplate.EscalationType.FIXED_PERCENT:
            if escalation_percentage is None:
                errors["escalation_percentage"] = "Escalation % is required for FIXED_PERCENT templates."
            attrs["index_name"] = ""
            attrs["index_base_value"] = None
            attrs["step_schedule"] = []

        elif escalation_type == models.EscalationTemplate.EscalationType.INDEX_LINKED:
            if not index_name:
                errors["index_name"] = "Index name is required for INDEX_LINKED templates."
            if index_base_value is None:
                errors["index_base_value"] = "Index base value is required for INDEX_LINKED templates."
            attrs["index_name"] = index_name
            attrs["escalation_percentage"] = None
            attrs["step_schedule"] = []

        elif escalation_type == models.EscalationTemplate.EscalationType.STEP_WISE:
            if not isinstance(step_schedule, list) or len(step_schedule) == 0:
                errors["step_schedule"] = "Provide at least one step for STEP_WISE templates."
            else:
                parsed_steps = []
                years_seen = set()
                for idx, step in enumerate(step_schedule):
                    if not isinstance(step, dict):
                        errors["step_schedule"] = f"Step #{idx + 1} must be an object."
                        continue
                    try:
                        year = int(step.get("year"))
                    except (TypeError, ValueError):
                        errors["step_schedule"] = f"Step #{idx + 1}: 'year' must be an integer."
                        continue
                    try:
                        percentage = float(step.get("percentage"))
                    except (TypeError, ValueError):
                        errors["step_schedule"] = f"Step #{idx + 1}: 'percentage' must be a number."
                        continue

                    if year < 1:
                        errors["step_schedule"] = f"Step #{idx + 1}: 'year' must be >= 1."
                    if percentage < 0 or percentage > 100:
                        errors["step_schedule"] = f"Step #{idx + 1}: 'percentage' must be between 0 and 100."
                    if year in years_seen:
                        errors["step_schedule"] = f"Duplicate year '{year}' in step schedule."
                    years_seen.add(year)
                    parsed_steps.append({"year": year, "percentage": percentage})

                if "step_schedule" not in errors:
                    attrs["step_schedule"] = sorted(parsed_steps, key=lambda x: x["year"])

            attrs["escalation_percentage"] = None
            attrs["index_name"] = ""
            attrs["index_base_value"] = None

        if cap_percentage is not None and floor_percentage is not None and floor_percentage > cap_percentage:
            errors["floor_percentage"] = "Floor % cannot be greater than Cap %."

        if errors:
            raise serializers.ValidationError(errors)

        return attrs

    class Meta:
        model = models.EscalationTemplate
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )


class EscalationTemplateListSerializer(serializers.ModelSerializer):
    """List serializer for EscalationTemplate."""

    class Meta:
        model = models.EscalationTemplate
        fields = (
            "id", "name", "description", "escalation_type",
            "escalation_percentage", "index_name", "index_base_value", "step_schedule",
            "frequency", "first_escalation_months",
            "cap_percentage", "floor_percentage",
            "apply_to_cam", "apply_to_parking",
            "status", "applicability", "scope", "created_at"
        )


class EscalationTemplateDetailSerializer(serializers.ModelSerializer):
    """Detail serializer for EscalationTemplate."""

    class Meta:
        model = models.EscalationTemplate
        fields = "__all__"


# ===================== Agreement Structure Serializers =====================

class AgreementSectionSerializer(serializers.ModelSerializer):
    """Serializer for AgreementSection."""

    class Meta:
        model = models.AgreementSection
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )


class AgreementSectionListSerializer(serializers.ModelSerializer):
    """Lightweight list serializer for sections."""

    class Meta:
        model = models.AgreementSection
        fields = ("id", "name", "description", "sort_order", "parent")


class AgreementSectionTreeSerializer(serializers.ModelSerializer):
    """Recursive serializer for section tree."""
    children = serializers.SerializerMethodField()

    class Meta:
        model = models.AgreementSection
        fields = ("id", "name", "description", "sort_order", "parent", "children")

    def get_children(self, obj):
        children = obj.children.all().order_by("sort_order", "name")
        return AgreementSectionTreeSerializer(children, many=True).data


class AgreementStructureSerializer(serializers.ModelSerializer):
    """Full serializer for AgreementStructure."""

    class Meta:
        model = models.AgreementStructure
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )


class AgreementStructureListSerializer(serializers.ModelSerializer):
    """List serializer for AgreementStructure."""
    sections_count = serializers.SerializerMethodField()

    class Meta:
        model = models.AgreementStructure
        fields = ("id", "name", "description", "is_default", "sections_count", "scope")

    def get_sections_count(self, obj):
        return obj.sections.count()


class AgreementStructureDetailSerializer(serializers.ModelSerializer):
    """Detail serializer with nested sections."""
    sections = AgreementSectionTreeSerializer(many=True, read_only=True)

    class Meta:
        model = models.AgreementStructure
        fields = "__all__"

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Only include root sections (parent is null) in tree
        data["sections"] = AgreementSectionTreeSerializer(
            instance.sections.filter(parent__isnull=True).order_by("sort_order", "name"),
            many=True
        ).data
        return data


# ===================== Term Serializers =====================

class LeaseTermDatesSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.LeaseTermDates
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )
        extra_kwargs = {
            "agreement": {"required": False},
        }


class LeaseRentFreeSerializer(serializers.ModelSerializer):
    def validate(self, attrs):
        start_date = attrs.get("rent_free_start_date")
        rent_free_days = attrs.get("rent_free_days")
        extended_days = attrs.get("extended_buffer_days")
        extended_percent = attrs.get("extended_buffer_charge_percent")

        if start_date is None and self.instance is not None:
            start_date = self.instance.rent_free_start_date
        if rent_free_days is None and self.instance is not None:
            rent_free_days = self.instance.rent_free_days

        if start_date and rent_free_days:
            attrs["rent_free_end_date"] = start_date + timedelta(days=int(rent_free_days) - 1)
        elif "rent_free_days" in attrs and not rent_free_days:
            attrs["rent_free_end_date"] = None

        if extended_days and extended_percent in [None, ""]:
            attrs["extended_buffer_charge_percent"] = Decimal("50.00")

        return attrs

    class Meta:
        model = models.LeaseRentFree
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )
        extra_kwargs = {
            "agreement": {"required": False},
        }


class LeaseFinancialsSerializer(serializers.ModelSerializer):
    def validate(self, attrs):
        base_rent = attrs.get("base_rent_monthly")
        if base_rent not in [None, ""]:
            attrs["annual_rent"] = (Decimal(base_rent) * Decimal("12")).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
        return attrs

    class Meta:
        model = models.LeaseFinancials
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )
        extra_kwargs = {
            "agreement": {"required": False},
        }


class LeaseEscalationSerializer(serializers.ModelSerializer):
    TEMPLATE_TYPE_TO_LEASE_TYPE = {
        models.EscalationTemplate.EscalationType.FIXED_PERCENT: models.LeaseEscalation.EscalationType.FIXED_PERCENT,
        models.EscalationTemplate.EscalationType.INDEX_LINKED: models.LeaseEscalation.EscalationType.CPI_INDEX,
        models.EscalationTemplate.EscalationType.STEP_WISE: models.LeaseEscalation.EscalationType.STEP_UP,
    }
    TEMPLATE_FREQUENCY_TO_MONTHS = {
        models.EscalationTemplate.Frequency.ANNUAL: 12,
        models.EscalationTemplate.Frequency.EVERY_2_YEARS: 24,
        models.EscalationTemplate.Frequency.EVERY_3_YEARS: 36,
        models.EscalationTemplate.Frequency.EVERY_5_YEARS: 60,
    }

    def _apply_template_values(self, attrs, template):
        attrs["use_template_values"] = True
        attrs["escalation_type"] = self.TEMPLATE_TYPE_TO_LEASE_TYPE.get(
            template.escalation_type,
            models.LeaseEscalation.EscalationType.FIXED_PERCENT,
        )
        attrs["escalation_value"] = template.escalation_percentage
        attrs["escalation_frequency_months"] = self.TEMPLATE_FREQUENCY_TO_MONTHS.get(
            template.frequency,
            12,
        )
        attrs["first_escalation_months"] = template.first_escalation_months
        attrs["apply_to_cam"] = template.apply_to_cam
        attrs["apply_to_parking"] = template.apply_to_parking
        attrs["cap_percentage"] = template.cap_percentage
        attrs["floor_percentage"] = template.floor_percentage

        if template.escalation_type == models.EscalationTemplate.EscalationType.INDEX_LINKED:
            attrs["index_name"] = template.index_name
            attrs["index_base_value"] = template.index_base_value
        if template.escalation_type == models.EscalationTemplate.EscalationType.STEP_WISE:
            attrs["step_schedule"] = template.step_schedule

    def validate(self, attrs):
        template = attrs.get("template")
        use_template_values = attrs.get("use_template_values")

        if template is None and self.instance is not None:
            template = self.instance.template
        if use_template_values is None and self.instance is not None:
            use_template_values = self.instance.use_template_values

        # If a template is selected in payload, prefer template-driven values.
        if attrs.get("template") is not None:
            self._apply_template_values(attrs, attrs["template"])
            return attrs

        if use_template_values and template is None:
            raise serializers.ValidationError({"template": "Template is required when using template values."})

        if use_template_values and template is not None:
            self._apply_template_values(attrs, template)

        return attrs

    class Meta:
        model = models.LeaseEscalation
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )
        extra_kwargs = {
            "agreement": {"required": False},
        }


class LeaseCAMSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.LeaseCAM
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )
        extra_kwargs = {
            "agreement": {"required": False},
        }


class LeaseDepositSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.LeaseDeposit
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )
        extra_kwargs = {
            "agreement": {"required": False},
        }


class LeaseBillingSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.LeaseBilling
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )
        extra_kwargs = {
            "agreement": {"required": False},
        }


class LeaseTerminationSerializer(serializers.ModelSerializer):
    tenant_penalty_display = serializers.SerializerMethodField()
    landlord_compensation_display = serializers.SerializerMethodField()

    class Meta:
        model = models.LeaseTermination
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )
        extra_kwargs = {
            "agreement": {"required": False},
        }

    def get_tenant_penalty_display(self, obj):
        return obj.get_tenant_penalty_display()

    def get_landlord_compensation_display(self, obj):
        return obj.get_landlord_compensation_display()


# ===================== Clause Configuration Serializers =====================

class LeaseRenewalOptionSerializer(serializers.ModelSerializer):
    current_cycle_config = serializers.SerializerMethodField()
    next_cycle_config = serializers.SerializerMethodField()

    class Meta:
        model = models.LeaseRenewalOption
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )

    def get_current_cycle_config(self, obj):
        return obj.get_current_cycle_config()

    def get_next_cycle_config(self, obj):
        return obj.get_next_cycle_config()


class LeaseSubletSignageSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.LeaseSubletSignage
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )


class LeaseExclusivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = models.LeaseExclusivity
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )


class LeaseInsuranceRequirementSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.LeaseInsuranceRequirement
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )


class LeaseDisputeResolutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.LeaseDisputeResolution
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )


# ===================== Amendment Serializers =====================

class AmendmentApprovalSerializer(serializers.ModelSerializer):
    approver_name = serializers.SerializerMethodField()

    class Meta:
        model = models.AmendmentApproval
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )

    def get_approver_name(self, obj):
        if obj.approver:
            return obj.approver.get_full_name() or obj.approver.email
        return None


class AmendmentAttachmentSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = models.AmendmentAttachment
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at",
            "file_size", "uploaded_by"
        )

    def get_uploaded_by_name(self, obj):
        if obj.uploaded_by:
            return obj.uploaded_by.get_full_name() or obj.uploaded_by.email
        return None

    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None


class LeaseAmendmentListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""
    agreement_lease_id = serializers.CharField(source="agreement.lease_id", read_only=True)

    class Meta:
        model = models.LeaseAmendment
        fields = (
            "id", "amendment_id", "agreement", "agreement_lease_id",
            "amendment_type", "title", "previous_version", "new_version",
            "amendment_date", "effective_from", "approval_status", "created_at"
        )


class LeaseAmendmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.LeaseAmendment
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at",
            "amendment_id"
        )


class LeaseAmendmentDetailSerializer(serializers.ModelSerializer):
    """Full detail serializer with approvals and attachments."""
    agreement_lease_id = serializers.CharField(source="agreement.lease_id", read_only=True)
    approvals = AmendmentApprovalSerializer(many=True, read_only=True)
    attachments = AmendmentAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = models.LeaseAmendment
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )


class LeaseAmendmentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating amendments."""

    class Meta:
        model = models.LeaseAmendment
        fields = (
            "agreement", "amendment_type", "title", "previous_version",
            "new_version", "is_major_version", "amendment_date", "effective_from",
            "effective_to", "changes_summary", "description", "reason", "initiated_by"
        )


# ===================== Linked Document Serializers =====================

class DocumentApprovalSerializer(serializers.ModelSerializer):
    approver_name = serializers.SerializerMethodField()

    class Meta:
        model = models.DocumentApproval
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )

    def get_approver_name(self, obj):
        if obj.approver:
            return obj.approver.get_full_name() or obj.approver.email
        return None


class LeaseLinkedDocumentListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""
    uploaded_by_name = serializers.SerializerMethodField()
    is_expiring_soon = serializers.ReadOnlyField()
    is_expired = serializers.ReadOnlyField()

    class Meta:
        model = models.LeaseLinkedDocument
        fields = (
            "id", "agreement", "title", "category", "status",
            "version", "document_date", "expiry_date", "requires_renewal",
            "is_expiring_soon", "is_expired", "uploaded_by_name", "created_at"
        )

    def get_uploaded_by_name(self, obj):
        if obj.uploaded_by:
            return obj.uploaded_by.get_full_name() or obj.uploaded_by.email
        return None


class LeaseLinkedDocumentSerializer(serializers.ModelSerializer):
    is_expiring_soon = serializers.ReadOnlyField()
    is_expired = serializers.ReadOnlyField()
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = models.LeaseLinkedDocument
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at",
            "file_size", "uploaded_by"
        )

    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None


class LeaseLinkedDocumentDetailSerializer(serializers.ModelSerializer):
    """Full detail serializer with approvals."""
    is_expiring_soon = serializers.ReadOnlyField()
    is_expired = serializers.ReadOnlyField()
    file_url = serializers.SerializerMethodField()
    uploaded_by_name = serializers.SerializerMethodField()
    approvals = DocumentApprovalSerializer(many=True, read_only=True)

    class Meta:
        model = models.LeaseLinkedDocument
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )

    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None

    def get_uploaded_by_name(self, obj):
        if obj.uploaded_by:
            return obj.uploaded_by.get_full_name() or obj.uploaded_by.email
        return None


# ===================== Allocation Serializers =====================

class UnitAllocationSerializer(serializers.ModelSerializer):
    target_type = serializers.SerializerMethodField()
    target_details = serializers.SerializerMethodField()
    site_details = serializers.SerializerMethodField()
    tower_details = serializers.SerializerMethodField()
    floor_details = serializers.SerializerMethodField()
    unit_details = serializers.SerializerMethodField()

    class Meta:
        model = models.UnitAllocation
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )

    def get_unit_details(self, obj):
        if obj.unit:
            return {
                "id": obj.unit.id,
                "unit_no": obj.unit.unit_no,
                "unit_type": obj.unit.unit_type,
                "leasable_area_sqft": obj.unit.leasable_area_sqft,
                "builtup_area_sqft": obj.unit.builtup_area_sqft,
            }
        return None

    def get_site_details(self, obj):
        if obj.site:
            return {
                "id": obj.site.id,
                "name": obj.site.name,
                "code": obj.site.code,
                "leasable_area_sqft": obj.site.leasable_area_sqft,
            }
        return None

    def get_tower_details(self, obj):
        if obj.tower:
            return {
                "id": obj.tower.id,
                "name": obj.tower.name,
                "code": obj.tower.code,
                "site_id": obj.tower.site_id,
                "leasable_area_sqft": obj.tower.leasable_area_sqft,
            }
        return None

    def get_floor_details(self, obj):
        if obj.floor:
            return {
                "id": obj.floor.id,
                "number": obj.floor.number,
                "label": obj.floor.label,
                "tower_id": obj.floor.tower_id,
                "site_id": obj.floor.site_id,
                "leasable_area_sqft": obj.floor.leasable_area_sqft,
            }
        return None

    def get_target_type(self, obj):
        return obj.allocation_level

    def get_target_details(self, obj):
        if obj.allocation_level == models.UnitAllocation.AllocationLevel.SITE:
            return self.get_site_details(obj)
        if obj.allocation_level == models.UnitAllocation.AllocationLevel.TOWER:
            return self.get_tower_details(obj)
        if obj.allocation_level == models.UnitAllocation.AllocationLevel.FLOOR:
            return self.get_floor_details(obj)
        return self.get_unit_details(obj)


class UnitAllocationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.UnitAllocation
        fields = (
            "allocation_level",
            "site",
            "tower",
            "floor",
            "unit",
            "allocation_mode",
            "allocated_area_sqft",
            "monthly_rent",
        )


# ===================== Document & Note Serializers =====================

class LeaseDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.LeaseDocument
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at",
            "file_size", "mime_type"
        )


class LeaseNoteSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = models.LeaseNote
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.email
        return None


# ===================== Agreement Serializers =====================

class AgreementListSerializer(serializers.ModelSerializer):
    """Minimal serializer for list views."""

    tenant_name = serializers.SerializerMethodField()
    site_name = serializers.SerializerMethodField()
    total_allocated_area = serializers.SerializerMethodField()
    monthly_rent = serializers.SerializerMethodField()

    class Meta:
        model = models.Agreement
        fields = (
            "id", "lease_id", "version_number", "status", "agreement_type",
            "tenant", "tenant_name", "site", "site_name", "landlord_entity",
            "total_allocated_area", "monthly_rent", "created_at"
        )

    def get_tenant_name(self, obj):
        return obj.tenant.legal_name if obj.tenant else None

    def get_site_name(self, obj):
        return obj.site.name if obj.site else None

    def get_total_allocated_area(self, obj):
        return sum(
            alloc.allocated_area_sqft or 0
            for alloc in obj.unit_allocations.filter(is_active=True)
        )

    def get_monthly_rent(self, obj):
        try:
            financials = obj.financials
        except models.LeaseFinancials.DoesNotExist:
            return None
        if financials.base_rent_monthly is not None:
            return financials.base_rent_monthly
        if financials.rate_per_sqft_monthly is None:
            return None
        total_area = obj.unit_allocations.filter(is_active=True).aggregate(
            total=Sum("allocated_area_sqft")
        )["total"] or Decimal("0")
        return (Decimal(total_area) * Decimal(financials.rate_per_sqft_monthly)).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )


class AgreementSerializer(serializers.ModelSerializer):
    """Standard serializer for CRUD operations."""

    class Meta:
        model = models.Agreement
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )


class AgreementDetailSerializer(serializers.ModelSerializer):
    """Full detail serializer with nested terms."""

    tenant_details = TenantCompanyListSerializer(source="tenant", read_only=True)
    primary_contact_details = TenantContactSerializer(source="primary_contact", read_only=True)
    site_details = serializers.SerializerMethodField()

    # Nested terms (OneToOne relations)
    term_dates = LeaseTermDatesSerializer(read_only=True)
    rent_free = LeaseRentFreeSerializer(read_only=True)
    financials = LeaseFinancialsSerializer(read_only=True)
    escalation = LeaseEscalationSerializer(read_only=True)
    cam = LeaseCAMSerializer(read_only=True)
    deposit = LeaseDepositSerializer(read_only=True)
    billing = LeaseBillingSerializer(read_only=True)
    termination = LeaseTerminationSerializer(read_only=True)

    # Clause Configuration (OneToOne relations)
    renewal_option = serializers.SerializerMethodField()
    sublet_signage = serializers.SerializerMethodField()
    exclusivity = serializers.SerializerMethodField()
    insurance_requirement = serializers.SerializerMethodField()
    dispute_resolution = serializers.SerializerMethodField()

    # Collections
    unit_allocations = UnitAllocationSerializer(many=True, read_only=True)
    documents = LeaseDocumentSerializer(many=True, read_only=True)
    notes_list = LeaseNoteSerializer(many=True, read_only=True)

    # Amendment & Document collections
    amendments = serializers.SerializerMethodField()
    linked_documents = serializers.SerializerMethodField()

    # Computed fields
    total_allocated_area = serializers.SerializerMethodField()
    total_monthly_rent = serializers.SerializerMethodField()

    class Meta:
        model = models.Agreement
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )

    def get_site_details(self, obj):
        if obj.site:
            return {
                "id": obj.site.id,
                "name": obj.site.name,
                "address": getattr(obj.site, "address", ""),
                "city": getattr(obj.site, "city", ""),
            }
        return None

    def get_total_allocated_area(self, obj):
        return sum(
            float(alloc.allocated_area_sqft or 0)
            for alloc in obj.unit_allocations.filter(is_active=True)
        )

    def get_total_monthly_rent(self, obj):
        try:
            financials = obj.financials
            if financials.base_rent_monthly is not None:
                base = float(financials.base_rent_monthly or 0)
            elif financials.rate_per_sqft_monthly is not None:
                total_area = obj.unit_allocations.filter(is_active=True).aggregate(
                    total=Sum("allocated_area_sqft")
                )["total"] or Decimal("0")
                base = float(
                    (Decimal(total_area) * Decimal(financials.rate_per_sqft_monthly)).quantize(
                        Decimal("0.01"),
                        rounding=ROUND_HALF_UP,
                    )
                )
            else:
                base = 0
            cam = float(obj.cam.monthly_total or 0) if hasattr(obj, "cam") else 0
            return base + cam
        except (models.LeaseFinancials.DoesNotExist, models.LeaseCAM.DoesNotExist):
            return 0

    def get_renewal_option(self, obj):
        try:
            return LeaseRenewalOptionSerializer(obj.renewal_option).data
        except models.LeaseRenewalOption.DoesNotExist:
            return None

    def get_sublet_signage(self, obj):
        try:
            return LeaseSubletSignageSerializer(obj.sublet_signage).data
        except models.LeaseSubletSignage.DoesNotExist:
            return None

    def get_exclusivity(self, obj):
        try:
            return LeaseExclusivitySerializer(obj.exclusivity).data
        except models.LeaseExclusivity.DoesNotExist:
            return None

    def get_insurance_requirement(self, obj):
        try:
            return LeaseInsuranceRequirementSerializer(obj.insurance_requirement).data
        except models.LeaseInsuranceRequirement.DoesNotExist:
            return None

    def get_dispute_resolution(self, obj):
        try:
            return LeaseDisputeResolutionSerializer(obj.dispute_resolution).data
        except models.LeaseDisputeResolution.DoesNotExist:
            return None

    def get_amendments(self, obj):
        amendments = obj.amendments.all().order_by("-amendment_date")[:5]
        return LeaseAmendmentListSerializer(amendments, many=True).data

    def get_linked_documents(self, obj):
        docs = obj.linked_documents.all()[:10]
        return LeaseLinkedDocumentListSerializer(docs, many=True).data


# ===================== Bundle Serializers =====================

class LeaseTermsBundleSerializer(serializers.Serializer):
    """
    Serializer for updating all lease terms at once.
    Used by the /agreements/{id}/bundle/ endpoint.
    """

    # Core Terms
    term_dates = LeaseTermDatesSerializer(required=False)
    rent_free = LeaseRentFreeSerializer(required=False)
    financials = LeaseFinancialsSerializer(required=False)
    escalation = LeaseEscalationSerializer(required=False)
    cam = LeaseCAMSerializer(required=False)
    deposit = LeaseDepositSerializer(required=False)
    billing = LeaseBillingSerializer(required=False)
    termination = LeaseTerminationSerializer(required=False)
    unit_allocations = UnitAllocationCreateSerializer(many=True, required=False)

    # Clause Configuration
    renewal_option = LeaseRenewalOptionSerializer(required=False)
    sublet_signage = LeaseSubletSignageSerializer(required=False)
    exclusivity = LeaseExclusivitySerializer(required=False)
    insurance_requirement = LeaseInsuranceRequirementSerializer(required=False)
    dispute_resolution = LeaseDisputeResolutionSerializer(required=False)

    def update_or_create_term(self, agreement, model_class, data, scope, user):
        """Helper to update or create a term model."""
        if data is None:
            return None

        # Remove read-only fields
        data.pop("id", None)
        data.pop("scope", None)
        data.pop("agreement", None)
        data.pop("created_at", None)
        data.pop("updated_at", None)
        data.pop("created_by", None)
        data.pop("updated_by", None)
        data.pop("is_active", None)
        data.pop("deleted_at", None)

        instance, created = model_class.objects.update_or_create(
            agreement=agreement,
            defaults={**data, "scope": scope, "updated_by": user}
        )
        if created:
            instance.created_by = user
            instance.save(update_fields=["created_by"])
        return instance

    def save(self, agreement, scope, user):
        """Save all terms for the agreement."""
        data = self.validated_data

        # Update each term model
        if "term_dates" in data:
            self.update_or_create_term(
                agreement, models.LeaseTermDates, data["term_dates"], scope, user
            )

        if "rent_free" in data:
            self.update_or_create_term(
                agreement, models.LeaseRentFree, data["rent_free"], scope, user
            )

        if "financials" in data:
            financials_data = dict(data["financials"])
            if (
                financials_data.get("base_rent_monthly") in [None, ""]
                and financials_data.get("rate_per_sqft_monthly") not in [None, ""]
            ):
                total_area = agreement.unit_allocations.filter(is_active=True).aggregate(
                    total=Sum("allocated_area_sqft")
                )["total"] or Decimal("0")
                if total_area > 0:
                    financials_data["base_rent_monthly"] = (
                        Decimal(total_area) * Decimal(financials_data["rate_per_sqft_monthly"])
                    ).quantize(
                        Decimal("0.01"),
                        rounding=ROUND_HALF_UP,
                    )

            effective_base = financials_data.get("base_rent_monthly")
            if effective_base in [None, ""]:
                try:
                    existing_financials = agreement.financials
                    effective_base = existing_financials.base_rent_monthly
                except models.LeaseFinancials.DoesNotExist:
                    effective_base = None

            if effective_base not in [None, ""]:
                financials_data["annual_rent"] = (
                    Decimal(effective_base) * Decimal("12")
                ).quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP,
                )

            self.update_or_create_term(
                agreement, models.LeaseFinancials, financials_data, scope, user
            )

        if "escalation" in data:
            self.update_or_create_term(
                agreement, models.LeaseEscalation, data["escalation"], scope, user
            )

        if "cam" in data:
            self.update_or_create_term(
                agreement, models.LeaseCAM, data["cam"], scope, user
            )

        if "deposit" in data:
            self.update_or_create_term(
                agreement, models.LeaseDeposit, data["deposit"], scope, user
            )

        if "billing" in data:
            self.update_or_create_term(
                agreement, models.LeaseBilling, data["billing"], scope, user
            )

        if "termination" in data:
            self.update_or_create_term(
                agreement, models.LeaseTermination, data["termination"], scope, user
            )

        # Handle unit allocations
        if "unit_allocations" in data:
            # Clear existing allocations
            agreement.unit_allocations.all().delete()
            # Create new allocations
            for alloc_data in data["unit_allocations"]:
                models.UnitAllocation.objects.create(
                    agreement=agreement,
                    scope=scope,
                    created_by=user,
                    **alloc_data
                )

        # Handle clause configuration models
        if "renewal_option" in data:
            self.update_or_create_term(
                agreement, models.LeaseRenewalOption, data["renewal_option"], scope, user
            )

        if "sublet_signage" in data:
            self.update_or_create_term(
                agreement, models.LeaseSubletSignage, data["sublet_signage"], scope, user
            )

        if "exclusivity" in data:
            self.update_or_create_term(
                agreement, models.LeaseExclusivity, data["exclusivity"], scope, user
            )

        if "insurance_requirement" in data:
            self.update_or_create_term(
                agreement, models.LeaseInsuranceRequirement, data["insurance_requirement"], scope, user
            )

        if "dispute_resolution" in data:
            self.update_or_create_term(
                agreement, models.LeaseDisputeResolution, data["dispute_resolution"], scope, user
            )

        return agreement


class AgreementCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating a new agreement with optional initial terms.
    """

    terms = LeaseTermsBundleSerializer(required=False, write_only=True)

    class Meta:
        model = models.Agreement
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )

    def create(self, validated_data):
        terms_data = validated_data.pop("terms", None)
        agreement = super().create(validated_data)

        if terms_data:
            terms_serializer = LeaseTermsBundleSerializer(data=terms_data)
            terms_serializer.is_valid(raise_exception=True)
            terms_serializer.save(
                agreement=agreement,
                scope=agreement.scope,
                user=self.context["request"].user
            )

        return agreement
