from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Sum, Count, Q
from django.utils import timezone
from decimal import Decimal

from apps.core.viewsets import ScopedViewSet
from . import models, serializers


class AgeingBucketViewSet(ScopedViewSet):
    """
    ViewSet for ageing bucket configuration.

    Endpoints:
    - GET /ageing-buckets/ - List all ageing buckets
    - POST /ageing-buckets/ - Create ageing bucket
    - GET /ageing-buckets/{id}/ - Get bucket details
    - PATCH /ageing-buckets/{id}/ - Update bucket
    - DELETE /ageing-buckets/{id}/ - Delete bucket
    - POST /ageing-buckets/initialize-defaults/ - Create default buckets
    """

    queryset = models.AgeingBucket.objects.all()
    serializer_class = serializers.AgeingBucketSerializer

    def get_serializer_class(self):
        if self.action == "list":
            return serializers.AgeingBucketListSerializer
        return serializers.AgeingBucketSerializer

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        serializer.save(scope=scope, created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=False, methods=["post"], url_path="initialize-defaults")
    def initialize_defaults(self, request):
        """Create default ageing buckets for the scope."""
        scope = self.get_active_scope()

        # Check if buckets already exist
        if models.AgeingBucket.objects.filter(scope=scope).exists():
            return Response(
                {"error": "Ageing buckets already exist for this scope"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Create default buckets
        defaults = [
            {"label": "Current", "from_days": 0, "to_days": 30, "sort_order": 1, "color_code": "#10B981"},
            {"label": "31-60 Days", "from_days": 31, "to_days": 60, "sort_order": 2, "color_code": "#F59E0B"},
            {"label": "61-90 Days", "from_days": 61, "to_days": 90, "sort_order": 3, "color_code": "#EF4444"},
            {"label": "90+ Days", "from_days": 91, "to_days": None, "sort_order": 4, "color_code": "#991B1B"},
        ]

        created_buckets = []
        for bucket_data in defaults:
            bucket = models.AgeingBucket.objects.create(
                scope=scope,
                created_by=request.user,
                **bucket_data
            )
            created_buckets.append(bucket)

        serializer = serializers.AgeingBucketListSerializer(created_buckets, many=True)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ARRuleViewSet(ScopedViewSet):
    """
    ViewSet for AR rules.

    Endpoints:
    - GET /ar-rules/ - List all AR rules
    - POST /ar-rules/ - Create AR rule
    - GET /ar-rules/{id}/ - Get rule details
    - PATCH /ar-rules/{id}/ - Update rule
    - DELETE /ar-rules/{id}/ - Delete rule
    - GET /ar-rules/by-agreement/{agreement_id}/ - Get rules for agreement
    """

    queryset = models.ARRule.objects.all()
    serializer_class = serializers.ARRuleSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        agreement_id = self.request.query_params.get("agreement_id")
        if agreement_id:
            queryset = queryset.filter(agreement_id=agreement_id)
        return queryset.select_related("agreement")

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        serializer.save(scope=scope, created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=False, methods=["get"], url_path="by-agreement/(?P<agreement_id>[^/.]+)")
    def by_agreement(self, request, agreement_id=None):
        """Get AR rules for a specific agreement."""
        scope = self.get_active_scope()
        try:
            ar_rule = models.ARRule.objects.get(
                agreement_id=agreement_id,
                scope=scope
            )
            serializer = self.get_serializer(ar_rule)
            return Response(serializer.data)
        except models.ARRule.DoesNotExist:
            return Response(
                {"error": "AR rules not found for this agreement"},
                status=status.HTTP_404_NOT_FOUND
            )


class InvoiceViewSet(ScopedViewSet):
    """
    ViewSet for invoices.

    Endpoints:
    - GET /invoices/ - List all invoices
    - POST /invoices/ - Create invoice
    - GET /invoices/{id}/ - Get invoice details
    - PATCH /invoices/{id}/ - Update invoice
    - DELETE /invoices/{id}/ - Delete invoice
    - POST /invoices/{id}/send/ - Send invoice
    - POST /invoices/{id}/dispute/ - Mark as disputed
    - POST /invoices/{id}/resolve-dispute/ - Resolve dispute
    - GET /invoices/overdue/ - List overdue invoices
    - GET /invoices/summary/ - Get invoice summary stats
    """

    queryset = models.Invoice.objects.all()
    serializer_class = serializers.InvoiceSerializer

    def get_serializer_class(self):
        if self.action == "list":
            return serializers.InvoiceListSerializer
        if self.action == "retrieve":
            return serializers.InvoiceDetailSerializer
        if self.action == "create":
            return serializers.InvoiceCreateSerializer
        return serializers.InvoiceSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by agreement
        agreement_id = self.request.query_params.get("agreement_id")
        if agreement_id:
            queryset = queryset.filter(agreement_id=agreement_id)

        # Filter by status
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Filter by invoice type
        invoice_type = self.request.query_params.get("invoice_type")
        if invoice_type:
            queryset = queryset.filter(invoice_type=invoice_type)

        # Filter by date range
        from_date = self.request.query_params.get("from_date")
        to_date = self.request.query_params.get("to_date")
        if from_date:
            queryset = queryset.filter(invoice_date__gte=from_date)
        if to_date:
            queryset = queryset.filter(invoice_date__lte=to_date)

        # Filter overdue
        if self.request.query_params.get("overdue") == "true":
            today = timezone.now().date()
            queryset = queryset.filter(
                due_date__lt=today,
                balance_due__gt=0
            )

        return queryset.select_related("agreement", "agreement__tenant")

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        serializer.save(scope=scope, created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        """Send invoice to tenant."""
        invoice = self.get_object()
        if invoice.status == models.Invoice.InvoiceStatus.DRAFT:
            invoice.status = models.Invoice.InvoiceStatus.SENT
            invoice.save()
        serializer = self.get_serializer(invoice)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def dispute(self, request, pk=None):
        """Mark invoice as disputed."""
        invoice = self.get_object()
        invoice.is_disputed = True
        invoice.dispute_reason = request.data.get("reason", "")
        invoice.disputed_at = timezone.now()
        invoice.disputed_by = request.user
        invoice.status = models.Invoice.InvoiceStatus.DISPUTED
        invoice.save()
        serializer = self.get_serializer(invoice)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="resolve-dispute")
    def resolve_dispute(self, request, pk=None):
        """Resolve invoice dispute."""
        invoice = self.get_object()
        invoice.is_disputed = False
        invoice.status = models.Invoice.InvoiceStatus.PENDING
        if invoice.balance_due <= 0:
            invoice.status = models.Invoice.InvoiceStatus.PAID
        invoice.save()
        serializer = self.get_serializer(invoice)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def overdue(self, request):
        """List overdue invoices."""
        scope = self.get_active_scope()
        today = timezone.now().date()
        queryset = models.Invoice.objects.filter(
            scope=scope,
            due_date__lt=today,
            balance_due__gt=0
        ).select_related("agreement", "agreement__tenant")

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = serializers.InvoiceListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = serializers.InvoiceListSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Get invoice summary statistics."""
        scope = self.get_active_scope()
        today = timezone.now().date()

        queryset = models.Invoice.objects.filter(scope=scope)

        stats = queryset.aggregate(
            total_invoiced=Sum("total_amount"),
            total_paid=Sum("amount_paid"),
            total_outstanding=Sum("balance_due"),
        )

        overdue_stats = queryset.filter(
            due_date__lt=today,
            balance_due__gt=0
        ).aggregate(
            total_overdue=Sum("balance_due"),
            overdue_count=Count("id"),
        )

        disputed_stats = queryset.filter(
            is_disputed=True
        ).aggregate(
            disputed_amount=Sum("balance_due"),
            disputed_count=Count("id"),
        )

        return Response({
            "total_invoiced": float(stats["total_invoiced"] or 0),
            "total_paid": float(stats["total_paid"] or 0),
            "total_outstanding": float(stats["total_outstanding"] or 0),
            "total_overdue": float(overdue_stats["total_overdue"] or 0),
            "overdue_count": overdue_stats["overdue_count"] or 0,
            "disputed_amount": float(disputed_stats["disputed_amount"] or 0),
            "disputed_count": disputed_stats["disputed_count"] or 0,
        })


class PaymentViewSet(ScopedViewSet):
    """
    ViewSet for payments.

    Endpoints:
    - GET /payments/ - List all payments
    - POST /payments/ - Record payment
    - GET /payments/{id}/ - Get payment details
    - PATCH /payments/{id}/ - Update payment
    - DELETE /payments/{id}/ - Delete payment
    - POST /payments/{id}/reverse/ - Reverse payment
    """

    queryset = models.Payment.objects.all()
    serializer_class = serializers.PaymentSerializer

    def get_serializer_class(self):
        if self.action == "list":
            return serializers.PaymentListSerializer
        if self.action == "retrieve":
            return serializers.PaymentDetailSerializer
        return serializers.PaymentSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by invoice
        invoice_id = self.request.query_params.get("invoice_id")
        if invoice_id:
            queryset = queryset.filter(invoice_id=invoice_id)

        # Filter by payment method
        payment_method = self.request.query_params.get("payment_method")
        if payment_method:
            queryset = queryset.filter(payment_method=payment_method)

        # Filter by date range
        from_date = self.request.query_params.get("from_date")
        to_date = self.request.query_params.get("to_date")
        if from_date:
            queryset = queryset.filter(payment_date__gte=from_date)
        if to_date:
            queryset = queryset.filter(payment_date__lte=to_date)

        return queryset.select_related("invoice", "invoice__agreement")

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        payment = serializer.save(scope=scope, created_by=self.request.user)

        # Update invoice amount_paid
        invoice = payment.invoice
        total_paid = invoice.payments.filter(
            status=models.Payment.PaymentStatus.CONFIRMED
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

        invoice.amount_paid = total_paid
        if invoice.balance_due <= 0:
            invoice.status = models.Invoice.InvoiceStatus.PAID
        elif invoice.amount_paid > 0:
            invoice.status = models.Invoice.InvoiceStatus.PARTIALLY_PAID
        invoice.save()

    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        """Reverse a payment."""
        payment = self.get_object()
        payment.status = models.Payment.PaymentStatus.REVERSED
        payment.save()

        # Update invoice
        invoice = payment.invoice
        total_paid = invoice.payments.filter(
            status=models.Payment.PaymentStatus.CONFIRMED
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

        invoice.amount_paid = total_paid
        if invoice.amount_paid == 0:
            invoice.status = models.Invoice.InvoiceStatus.PENDING
        elif invoice.balance_due > 0:
            invoice.status = models.Invoice.InvoiceStatus.PARTIALLY_PAID
        invoice.save()

        serializer = self.get_serializer(payment)
        return Response(serializer.data)


class CreditNoteViewSet(ScopedViewSet):
    """
    ViewSet for credit notes.

    Endpoints:
    - GET /credit-notes/ - List all credit notes
    - POST /credit-notes/ - Create credit note
    - GET /credit-notes/{id}/ - Get credit note details
    - PATCH /credit-notes/{id}/ - Update credit note
    - DELETE /credit-notes/{id}/ - Delete credit note
    - POST /credit-notes/{id}/approve/ - Approve credit note
    - POST /credit-notes/{id}/reject/ - Reject credit note
    - POST /credit-notes/{id}/apply/ - Apply credit note to invoice
    """

    queryset = models.CreditNote.objects.all()
    serializer_class = serializers.CreditNoteSerializer

    def get_serializer_class(self):
        if self.action == "list":
            return serializers.CreditNoteListSerializer
        if self.action == "retrieve":
            return serializers.CreditNoteDetailSerializer
        return serializers.CreditNoteSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by invoice
        invoice_id = self.request.query_params.get("invoice_id")
        if invoice_id:
            queryset = queryset.filter(invoice_id=invoice_id)

        # Filter by status
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset.select_related("invoice", "invoice__agreement", "approved_by")

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        serializer.save(scope=scope, created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        """Approve credit note."""
        credit_note = self.get_object()
        credit_note.status = models.CreditNote.CreditNoteStatus.APPROVED
        credit_note.approved_by = request.user
        credit_note.approved_at = timezone.now()
        credit_note.save()
        serializer = self.get_serializer(credit_note)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        """Reject credit note."""
        credit_note = self.get_object()
        credit_note.status = models.CreditNote.CreditNoteStatus.REJECTED
        credit_note.rejection_reason = request.data.get("reason", "")
        credit_note.save()
        serializer = self.get_serializer(credit_note)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def apply(self, request, pk=None):
        """Apply credit note to invoice."""
        credit_note = self.get_object()

        if credit_note.status != models.CreditNote.CreditNoteStatus.APPROVED:
            return Response(
                {"error": "Credit note must be approved before applying"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Apply to invoice
        invoice = credit_note.invoice
        invoice.amount_paid += credit_note.amount
        if invoice.balance_due <= 0:
            invoice.status = models.Invoice.InvoiceStatus.PAID
        invoice.save()

        credit_note.status = models.CreditNote.CreditNoteStatus.APPLIED
        credit_note.applied_at = timezone.now()
        credit_note.save()

        serializer = self.get_serializer(credit_note)
        return Response(serializer.data)


class InvoiceScheduleViewSet(ScopedViewSet):
    """
    ViewSet for invoice schedules.

    Endpoints:
    - GET /invoice-schedules/ - List all schedules
    - POST /invoice-schedules/ - Create schedule
    - GET /invoice-schedules/{id}/ - Get schedule details
    - PATCH /invoice-schedules/{id}/ - Update schedule
    - DELETE /invoice-schedules/{id}/ - Delete schedule
    - POST /invoice-schedules/{id}/generate/ - Generate invoice now
    """

    queryset = models.InvoiceSchedule.objects.all()
    serializer_class = serializers.InvoiceScheduleSerializer

    def get_serializer_class(self):
        if self.action == "list":
            return serializers.InvoiceScheduleListSerializer
        return serializers.InvoiceScheduleSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by agreement
        agreement_id = self.request.query_params.get("agreement_id")
        if agreement_id:
            queryset = queryset.filter(agreement_id=agreement_id)

        # Filter by active status
        is_active = self.request.query_params.get("is_active")
        if is_active == "true":
            queryset = queryset.filter(is_active=True)
        elif is_active == "false":
            queryset = queryset.filter(is_active=False)

        return queryset.select_related("agreement")

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        serializer.save(scope=scope, created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=True, methods=["post"])
    def generate(self, request, pk=None):
        """Generate invoice from schedule immediately."""
        schedule = self.get_object()

        # Create invoice based on schedule
        invoice_number = f"INV-{timezone.now().strftime('%Y%m%d')}-{schedule.id}"
        today = timezone.now().date()

        invoice = models.Invoice.objects.create(
            scope=schedule.scope,
            agreement=schedule.agreement,
            invoice_number=invoice_number,
            invoice_type=schedule.invoice_type,
            status=models.Invoice.InvoiceStatus.PENDING,
            invoice_date=today,
            due_date=today,  # Adjust based on billing rules
            subtotal=schedule.amount,
            tax_amount=schedule.amount * (schedule.tax_rate / 100),
            total_amount=schedule.amount + (schedule.amount * (schedule.tax_rate / 100)),
            amount_paid=Decimal("0"),
            balance_due=schedule.amount + (schedule.amount * (schedule.tax_rate / 100)),
            created_by=request.user,
        )

        # Update schedule
        schedule.last_generated_date = today
        schedule.save()

        return Response(
            serializers.InvoiceSerializer(invoice).data,
            status=status.HTTP_201_CREATED
        )


class ARSummaryViewSet(ScopedViewSet):
    """
    ViewSet for AR summaries.

    Endpoints:
    - GET /ar-summaries/ - List all summaries
    - GET /ar-summaries/{id}/ - Get summary details
    - GET /ar-summaries/by-agreement/{agreement_id}/ - Get summary for agreement
    - POST /ar-summaries/refresh/{agreement_id}/ - Refresh summary for agreement
    - GET /ar-summaries/overall/ - Get overall AR summary
    """

    queryset = models.ARSummary.objects.all()
    serializer_class = serializers.ARSummarySerializer

    def get_serializer_class(self):
        if self.action == "retrieve":
            return serializers.ARSummaryDetailSerializer
        return serializers.ARSummarySerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.select_related("agreement", "agreement__tenant")

    @action(detail=False, methods=["get"], url_path="by-agreement/(?P<agreement_id>[^/.]+)")
    def by_agreement(self, request, agreement_id=None):
        """Get AR summary for a specific agreement."""
        scope = self.get_active_scope()
        try:
            summary = models.ARSummary.objects.get(
                agreement_id=agreement_id,
                scope=scope
            )
            serializer = serializers.ARSummaryDetailSerializer(summary)
            return Response(serializer.data)
        except models.ARSummary.DoesNotExist:
            return Response(
                {"error": "AR summary not found for this agreement"},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=False, methods=["post"], url_path="refresh/(?P<agreement_id>[^/.]+)")
    def refresh(self, request, agreement_id=None):
        """Refresh AR summary for a specific agreement."""
        scope = self.get_active_scope()
        today = timezone.now().date()

        # Get or create summary
        summary, created = models.ARSummary.objects.get_or_create(
            agreement_id=agreement_id,
            scope=scope,
            defaults={"created_by": request.user}
        )

        # Calculate totals from invoices
        invoices = models.Invoice.objects.filter(
            agreement_id=agreement_id,
            scope=scope
        )

        totals = invoices.aggregate(
            total_invoiced=Sum("total_amount"),
            total_paid=Sum("amount_paid"),
            total_outstanding=Sum("balance_due"),
        )

        # Calculate overdue
        overdue_invoices = invoices.filter(
            due_date__lt=today,
            balance_due__gt=0
        )
        total_overdue = overdue_invoices.aggregate(
            total=Sum("balance_due")
        )["total"] or Decimal("0")

        # Calculate ageing buckets
        current = overdue_invoices.filter(
            due_date__gte=today - timezone.timedelta(days=30)
        ).aggregate(total=Sum("balance_due"))["total"] or Decimal("0")

        bucket_30_60 = overdue_invoices.filter(
            due_date__lt=today - timezone.timedelta(days=30),
            due_date__gte=today - timezone.timedelta(days=60)
        ).aggregate(total=Sum("balance_due"))["total"] or Decimal("0")

        bucket_60_90 = overdue_invoices.filter(
            due_date__lt=today - timezone.timedelta(days=60),
            due_date__gte=today - timezone.timedelta(days=90)
        ).aggregate(total=Sum("balance_due"))["total"] or Decimal("0")

        bucket_90_plus = overdue_invoices.filter(
            due_date__lt=today - timezone.timedelta(days=90)
        ).aggregate(total=Sum("balance_due"))["total"] or Decimal("0")

        # Counts
        open_count = invoices.filter(
            balance_due__gt=0
        ).count()
        overdue_count = overdue_invoices.count()
        disputed_count = invoices.filter(is_disputed=True).count()

        # Update summary
        summary.total_invoiced = totals["total_invoiced"] or Decimal("0")
        summary.total_paid = totals["total_paid"] or Decimal("0")
        summary.total_outstanding = totals["total_outstanding"] or Decimal("0")
        summary.total_overdue = total_overdue
        summary.current_bucket = current
        summary.bucket_30_60 = bucket_30_60
        summary.bucket_60_90 = bucket_60_90
        summary.bucket_90_plus = bucket_90_plus
        summary.open_invoice_count = open_count
        summary.overdue_invoice_count = overdue_count
        summary.disputed_invoice_count = disputed_count
        summary.updated_by = request.user
        summary.save()

        serializer = serializers.ARSummaryDetailSerializer(summary)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def overall(self, request):
        """Get overall AR summary across all agreements."""
        scope = self.get_active_scope()
        today = timezone.now().date()

        invoices = models.Invoice.objects.filter(scope=scope)

        totals = invoices.aggregate(
            total_invoiced=Sum("total_amount"),
            total_paid=Sum("amount_paid"),
            total_outstanding=Sum("balance_due"),
        )

        overdue_stats = invoices.filter(
            due_date__lt=today,
            balance_due__gt=0
        ).aggregate(
            total_overdue=Sum("balance_due"),
            overdue_count=Count("id"),
        )

        disputed_stats = invoices.filter(
            is_disputed=True
        ).aggregate(
            disputed_amount=Sum("balance_due"),
            disputed_count=Count("id"),
        )

        # Ageing buckets
        overdue_invoices = invoices.filter(
            due_date__lt=today,
            balance_due__gt=0
        )

        ageing = {
            "current": float(overdue_invoices.filter(
                due_date__gte=today - timezone.timedelta(days=30)
            ).aggregate(total=Sum("balance_due"))["total"] or 0),
            "30_60": float(overdue_invoices.filter(
                due_date__lt=today - timezone.timedelta(days=30),
                due_date__gte=today - timezone.timedelta(days=60)
            ).aggregate(total=Sum("balance_due"))["total"] or 0),
            "60_90": float(overdue_invoices.filter(
                due_date__lt=today - timezone.timedelta(days=60),
                due_date__gte=today - timezone.timedelta(days=90)
            ).aggregate(total=Sum("balance_due"))["total"] or 0),
            "90_plus": float(overdue_invoices.filter(
                due_date__lt=today - timezone.timedelta(days=90)
            ).aggregate(total=Sum("balance_due"))["total"] or 0),
        }

        return Response({
            "total_invoiced": float(totals["total_invoiced"] or 0),
            "total_paid": float(totals["total_paid"] or 0),
            "total_outstanding": float(totals["total_outstanding"] or 0),
            "total_overdue": float(overdue_stats["total_overdue"] or 0),
            "overdue_count": overdue_stats["overdue_count"] or 0,
            "disputed_amount": float(disputed_stats["disputed_amount"] or 0),
            "disputed_count": disputed_stats["disputed_count"] or 0,
            "ageing": ageing,
        })


class LeaseRulesViewSet(ScopedViewSet):
    """
    ViewSet for lease-level billing and AR rules.

    Endpoints:
    - GET /lease-rules/{agreement_id}/ - Get all rules for a lease
    - PATCH /lease-rules/{agreement_id}/ - Update rules for a lease
    """

    from apps.leases.models import Agreement
    queryset = Agreement.objects.all()

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.select_related(
            "billing", "escalation"
        ).prefetch_related("ar_rules")

    @action(detail=True, methods=["get", "patch"])
    def rules(self, request, pk=None):
        """Get or update all rules for a lease."""
        agreement = self.get_object()
        scope = self.get_active_scope()

        if request.method == "GET":
            # Get billing rules from leases app
            from apps.leases.serializers import LeaseBillingSerializer, LeaseEscalationSerializer

            billing_data = None
            if hasattr(agreement, "billing"):
                billing_data = LeaseBillingSerializer(agreement.billing).data

            escalation_data = None
            if hasattr(agreement, "escalation"):
                escalation_data = LeaseEscalationSerializer(agreement.escalation).data

            ar_rules_data = None
            try:
                ar_rules_data = serializers.ARRuleSerializer(agreement.ar_rules).data
            except models.ARRule.DoesNotExist:
                pass

            # Get ageing buckets for scope
            ageing_buckets = models.AgeingBucket.objects.filter(scope=scope)
            ageing_data = serializers.AgeingBucketListSerializer(ageing_buckets, many=True).data

            return Response({
                "billing": billing_data,
                "escalation": escalation_data,
                "ar_rules": ar_rules_data,
                "ageing_buckets": ageing_data,
            })

        elif request.method == "PATCH":
            from apps.leases import models as lease_models
            from apps.leases.serializers import LeaseBillingSerializer, LeaseEscalationSerializer

            data = request.data

            # Update billing rules
            if "billing" in data:
                billing_instance, _ = lease_models.LeaseBilling.objects.update_or_create(
                    agreement=agreement,
                    defaults={
                        "scope": scope,
                        "updated_by": request.user,
                        **{k: v for k, v in data["billing"].items()
                           if k not in ["id", "scope", "agreement", "created_at", "updated_at",
                                        "created_by", "updated_by", "is_active", "deleted_at"]}
                    }
                )

            # Update escalation rules
            if "escalation" in data:
                escalation_instance, _ = lease_models.LeaseEscalation.objects.update_or_create(
                    agreement=agreement,
                    defaults={
                        "scope": scope,
                        "updated_by": request.user,
                        **{k: v for k, v in data["escalation"].items()
                           if k not in ["id", "scope", "agreement", "created_at", "updated_at",
                                        "created_by", "updated_by", "is_active", "deleted_at"]}
                    }
                )

            # Update AR rules
            if "ar_rules" in data:
                ar_instance, _ = models.ARRule.objects.update_or_create(
                    agreement=agreement,
                    defaults={
                        "scope": scope,
                        "updated_by": request.user,
                        **{k: v for k, v in data["ar_rules"].items()
                           if k not in ["id", "scope", "agreement", "created_at", "updated_at",
                                        "created_by", "updated_by", "is_active", "deleted_at"]}
                    }
                )

            # Return updated data
            return self.rules(request._request, pk=pk)

        return Response({"error": "Method not allowed"}, status=status.HTTP_405_METHOD_NOT_ALLOWED)
