from django.db.models import Avg, Count, Q
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.approvals.models import ApprovalRule, ApprovalRuleLog
from apps.approvals.serializers import (
    ApprovalRuleListSerializer,
    ApprovalRuleSerializer,
    ApprovalRuleWriteSerializer,
    SimulateSerializer,
)
from apps.core.utils import get_active_scope
from apps.core.viewsets import ScopedViewSet


class ApprovalRuleViewSet(ScopedViewSet):
    """
    CRUD + simulate + activate/deactivate + stats endpoints for ApprovalRule.

    List:   GET  /api/v1/approvals/rules/
    Detail: GET  /api/v1/approvals/rules/{id}/
    Create: POST /api/v1/approvals/rules/
    Update: PUT/PATCH /api/v1/approvals/rules/{id}/
    Delete: DELETE /api/v1/approvals/rules/{id}/

    Extras:
      POST /api/v1/approvals/rules/{id}/activate/
      POST /api/v1/approvals/rules/{id}/deactivate/
      POST /api/v1/approvals/rules/simulate/
      GET  /api/v1/approvals/rules/stats/
    """

    queryset = ApprovalRule.objects.prefetch_related("levels__role", "logs__user").all()
    permission_classes = [IsAuthenticated]
    hierarchy_aware = True

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return ApprovalRuleWriteSerializer
        if self.action == "list":
            return ApprovalRuleListSerializer
        return ApprovalRuleSerializer

    # ── Status transitions ──────────────────────────────────────────────────

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        rule = self.get_object()
        if rule.status == ApprovalRule.Status.ACTIVE:
            return Response(
                {"detail": "Rule is already active."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        rule.activate()
        ApprovalRuleLog.objects.create(
            rule=rule,
            user=request.user,
            action=ApprovalRuleLog.Action.ACTIVATED,
            detail=f"Rule '{rule.name}' activated by {request.user}.",
        )
        return Response(ApprovalRuleSerializer(rule, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        rule = self.get_object()
        if rule.status == ApprovalRule.Status.INACTIVE:
            return Response(
                {"detail": "Rule is already inactive."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        rule.deactivate()
        ApprovalRuleLog.objects.create(
            rule=rule,
            user=request.user,
            action=ApprovalRuleLog.Action.DEACTIVATED,
            detail=f"Rule '{rule.name}' deactivated by {request.user}.",
        )
        return Response(ApprovalRuleSerializer(rule, context={"request": request}).data)

    # ── Simulator ───────────────────────────────────────────────────────────

    @action(detail=False, methods=["post"])
    def simulate(self, request):
        """
        Given lease parameters, return which active rule(s) match and the full
        approval path with total expected SLA.

        Request body:
          { lease_value: 7500000, tenant_type: "CORPORATE", lease_term_months: 36 }

        Response:
          { matched_rule: {...}, approval_path: [...], total_sla_hours: 48 }
        """
        ser = SimulateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        lease_value = float(d.get("lease_value") or 0) or None
        tenant_type = d.get("tenant_type")
        lease_term = d.get("lease_term_months")

        # Get active rules in scope
        scope = get_active_scope(request)
        qs = ApprovalRule.objects.filter(
            status=ApprovalRule.Status.ACTIVE,
            is_active=True,
        )
        if scope:
            from apps.accounts.models import TenantScope
            scope_ids = list(scope.get_child_scopes().values_list("id", flat=True))
            qs = qs.filter(scope_id__in=scope_ids)

        matched = None
        for rule in qs.prefetch_related("levels__role"):
            if rule.matches(lease_value, tenant_type, lease_term):
                matched = rule
                break  # First match wins (ordered by lease_value_min)

        if not matched:
            return Response({
                "matched_rule": None,
                "approval_path": [],
                "total_sla_hours": 0,
                "message": "No active approval rule matches the given parameters.",
            })

        levels = list(matched.levels.order_by("level"))
        path = []
        cumulative = 0
        for lvl in levels:
            cumulative += lvl.sla_hours
            path.append({
                "level": lvl.level,
                "role": lvl.role.name,
                "sla_hours": lvl.sla_hours,
                "cumulative_sla_hours": cumulative,
                "approval_required": lvl.approval_required,
                "auto_skip_if_vacant": lvl.allow_auto_skip_if_vacant,
                "label": f"L{lvl.level}: {lvl.role.name} ({lvl.sla_hours}h)",
            })

        total_sla = sum(l["sla_hours"] for l in path)
        path_summary = " → ".join(l["label"] for l in path)

        return Response({
            "matched_rule": ApprovalRuleListSerializer(matched).data,
            "approval_path": path,
            "total_sla_hours": total_sla,
            "path_summary": f"TOTAL {total_sla}h  |  {path_summary}",
        })

    # ── Stats panel ─────────────────────────────────────────────────────────

    @action(detail=False, methods=["get"])
    def stats(self, request):
        """
        Returns aggregate stats for the rules stats panel:
          total_rules, active_rules, avg_sla_hours, bottleneck_count,
          compliance_pct, recent_activity
        """
        scope = get_active_scope(request)
        qs = ApprovalRule.objects.filter(is_active=True)
        if scope:
            scope_ids = list(scope.get_child_scopes().values_list("id", flat=True))
            qs = qs.filter(scope_id__in=scope_ids)

        total = qs.count()
        active = qs.filter(status=ApprovalRule.Status.ACTIVE).count()
        draft = qs.filter(status=ApprovalRule.Status.DRAFT).count()

        # Average SLA across all active rules
        from apps.approvals.models import ApprovalLevel
        avg_result = ApprovalLevel.objects.filter(
            rule__in=qs.filter(status=ApprovalRule.Status.ACTIVE),
        ).aggregate(avg=Avg("sla_hours"))
        avg_sla = round(avg_result["avg"] or 0)

        # Bottleneck = rules where any level's SLA > 72h
        bottleneck_count = ApprovalLevel.objects.filter(
            rule__in=qs.filter(status=ApprovalRule.Status.ACTIVE),
            sla_hours__gt=72,
        ).values("rule").distinct().count()

        # Compliance = active / total * 100 (placeholder — real data needs lease approval records)
        compliance_pct = round((active / total * 100) if total else 100)

        # Recent activity (last 10 log entries across all rules in scope)
        logs = ApprovalRuleLog.objects.filter(
            rule__in=qs
        ).select_related("user", "rule").order_by("-timestamp")[:10]
        activity = [
            {
                "timestamp": log.timestamp,
                "rule_name": log.rule.name,
                "action": log.action,
                "user_name": (log.user.get_full_name() or log.user.username) if log.user else "System",
                "detail": log.detail,
            }
            for log in logs
        ]

        return Response({
            "total_rules": total,
            "active_rules": active,
            "draft_rules": draft,
            "avg_sla_hours": avg_sla,
            "bottleneck_count": bottleneck_count,
            "compliance_pct": compliance_pct,
            "recent_activity": activity,
        })

    # ── Duplicate ────────────────────────────────────────────────────────────

    @action(detail=True, methods=["post"])
    def duplicate(self, request, pk=None):
        """Create a DRAFT copy of this rule."""
        original = self.get_object()
        new_rule = ApprovalRule.objects.create(
            scope=original.scope,
            name=f"{original.name} (Copy)",
            status=ApprovalRule.Status.DRAFT,
            lease_value_min=original.lease_value_min,
            lease_value_max=original.lease_value_max,
            tenant_types=original.tenant_types,
            lease_term_min_months=original.lease_term_min_months,
            lease_term_max_months=original.lease_term_max_months,
            overall_sla_hours=original.overall_sla_hours,
            enable_escalations=original.enable_escalations,
            escalate_after_hours=original.escalate_after_hours,
            escalate_to_role=original.escalate_to_role,
            send_escalation_notification=original.send_escalation_notification,
            parallel_approvals_same_level=original.parallel_approvals_same_level,
            created_by=request.user,
        )
        for lvl in original.levels.order_by("level"):
            new_rule.levels.create(
                level=lvl.level,
                role=lvl.role,
                approval_required=lvl.approval_required,
                sla_hours=lvl.sla_hours,
                allow_auto_skip_if_vacant=lvl.allow_auto_skip_if_vacant,
            )
        ApprovalRuleLog.objects.create(
            rule=new_rule,
            user=request.user,
            action=ApprovalRuleLog.Action.CREATED,
            detail=f"Duplicated from rule '{original.name}' (id={original.id}).",
        )
        return Response(
            ApprovalRuleSerializer(new_rule, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )
