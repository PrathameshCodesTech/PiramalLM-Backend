from rest_framework import serializers

from apps.approvals.models import ApprovalLevel, ApprovalRule, ApprovalRuleLog
from apps.accounts.models import TenantScope


# ── ApprovalRuleLog ────────────────────────────────────────────────────────

class ApprovalRuleLogSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = ApprovalRuleLog
        fields = ["id", "action", "detail", "user_name", "timestamp"]
        read_only_fields = fields

    def get_user_name(self, obj):
        if obj.user:
            return obj.user.get_full_name() or obj.user.username
        return "System"


# ── ApprovalLevel ──────────────────────────────────────────────────────────

class ApprovalLevelSerializer(serializers.ModelSerializer):
    role_name = serializers.CharField(source="role.name", read_only=True)
    role_code = serializers.CharField(source="role.code", read_only=True)

    class Meta:
        model = ApprovalLevel
        fields = [
            "id", "level", "role", "role_name", "role_code",
            "approval_required", "sla_hours",
        ]

    def validate_level(self, val):
        if val < 1 or val > 10:
            raise serializers.ValidationError("Level must be between 1 and 10.")
        return val


class ApprovalLevelWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApprovalLevel
        fields = [
            "id", "level", "role", "approval_required",
            "sla_hours",
        ]


# ── ApprovalRule ───────────────────────────────────────────────────────────

class ApprovalRuleSerializer(serializers.ModelSerializer):
    """Full serializer — includes nested levels and logs."""
    levels = ApprovalLevelSerializer(many=True, read_only=True)
    logs = ApprovalRuleLogSerializer(many=True, read_only=True)
    label = serializers.SerializerMethodField()
    total_sla_hours = serializers.SerializerMethodField()

    class Meta:
        model = ApprovalRule
        fields = [
            "id", "name", "status", "label",
            # Conditions
            "lease_value_min", "lease_value_max",
            "tenant_types",
            "lease_term_min_months", "lease_term_max_months",
            # SLA
            "overall_sla_hours", "total_sla_hours",
            # Related
            "levels", "logs",
            # Audit
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "label", "total_sla_hours", "created_at", "updated_at"]

    def get_label(self, obj):
        return obj.get_label()

    def get_total_sla_hours(self, obj):
        return sum(lvl.sla_hours for lvl in obj.levels.all())


class ApprovalRuleListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for the rules table list view."""
    levels = ApprovalLevelSerializer(many=True, read_only=True)
    label = serializers.SerializerMethodField()
    l1_approver = serializers.SerializerMethodField()
    l2_approver = serializers.SerializerMethodField()
    l3_approver = serializers.SerializerMethodField()
    total_sla_hours = serializers.SerializerMethodField()

    class Meta:
        model = ApprovalRule
        fields = [
            "id", "name", "status", "label",
            "lease_value_min", "lease_value_max",
            "tenant_types",
            "lease_term_min_months", "lease_term_max_months",
            "overall_sla_hours", "total_sla_hours",
            "l1_approver", "l2_approver", "l3_approver",
            "levels",
            "created_at",
        ]

    def get_label(self, obj):
        return obj.get_label()

    def _approver_at(self, obj, level):
        lvl = next((l for l in obj.levels.all() if l.level == level), None)
        if lvl:
            return {"role_name": lvl.role.name, "sla_hours": lvl.sla_hours}
        return None

    def get_l1_approver(self, obj):
        return self._approver_at(obj, 1)

    def get_l2_approver(self, obj):
        return self._approver_at(obj, 2)

    def get_l3_approver(self, obj):
        return self._approver_at(obj, 3)

    def get_total_sla_hours(self, obj):
        return sum(lvl.sla_hours for lvl in obj.levels.all())


class ApprovalRuleWriteSerializer(serializers.ModelSerializer):
    """
    Write serializer — accepts nested levels for create/update.
    Levels are replaced atomically on each save.
    Scope is optional here — ScopedViewSet.perform_create injects it from the X-Scope-ID header.
    """
    levels = ApprovalLevelWriteSerializer(many=True, required=False)
    scope = serializers.PrimaryKeyRelatedField(
        queryset=TenantScope.objects.all(),
        required=False,
    )

    class Meta:
        model = ApprovalRule
        fields = [
            "scope", "name", "status",
            "lease_value_min", "lease_value_max",
            "tenant_types",
            "lease_term_min_months", "lease_term_max_months",
            "overall_sla_hours",
            "levels",
        ]

    def validate_tenant_types(self, val):
        valid = [c[0] for c in ApprovalRule.TenantType.choices]
        for t in val:
            if t not in valid:
                raise serializers.ValidationError(f"'{t}' is not a valid tenant type.")
        return val

    def validate(self, data):
        lo = data.get("lease_value_min")
        hi = data.get("lease_value_max")
        if lo is not None and hi is not None and lo >= hi:
            raise serializers.ValidationError(
                "lease_value_min must be less than lease_value_max."
            )
        tm_lo = data.get("lease_term_min_months")
        tm_hi = data.get("lease_term_max_months")
        if tm_lo is not None and tm_hi is not None and tm_lo >= tm_hi:
            raise serializers.ValidationError(
                "lease_term_min_months must be less than lease_term_max_months."
            )
        return data

    def _save_levels(self, rule, levels_data):
        if levels_data is None:
            return
        # Replace all levels
        rule.levels.all().delete()
        for ld in levels_data:
            ApprovalLevel.objects.create(rule=rule, **ld)

    def create(self, validated_data):
        levels_data = validated_data.pop("levels", None)
        rule = super().create(validated_data)
        self._save_levels(rule, levels_data)
        user = self.context["request"].user if self.context.get("request") else None
        ApprovalRuleLog.objects.create(
            rule=rule,
            user=user,
            action=ApprovalRuleLog.Action.CREATED,
            detail=f"Rule '{rule.name}' created.",
        )
        return rule

    def update(self, instance, validated_data):
        levels_data = validated_data.pop("levels", None)
        rule = super().update(instance, validated_data)
        self._save_levels(rule, levels_data)
        user = self.context["request"].user if self.context.get("request") else None
        ApprovalRuleLog.objects.create(
            rule=rule,
            user=user,
            action=ApprovalRuleLog.Action.UPDATED,
            detail=f"Rule '{rule.name}' updated.",
        )
        return rule


# ── Simulator ─────────────────────────────────────────────────────────────

class SimulateSerializer(serializers.Serializer):
    lease_value = serializers.DecimalField(
        max_digits=14, decimal_places=2, required=False, allow_null=True
    )
    tenant_type = serializers.ChoiceField(
        choices=ApprovalRule.TenantType.choices, required=False, allow_null=True
    )
    lease_term_months = serializers.IntegerField(
        required=False, allow_null=True, min_value=1
    )
