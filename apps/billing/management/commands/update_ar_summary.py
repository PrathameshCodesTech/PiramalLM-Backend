"""
Management command: update_ar_summary
======================================
Runs nightly to rebuild ARSummary for every active lease agreement.

Ageing logic:
  - Reference date: invoice_date or due_date, per AgeingConfig.reference_date
  - Buckets: reads AgeingBucket records for the scope; falls back to 0-30/31-60/61-90/91+ defaults
  - Disputed invoices: excluded by default unless AgeingConfig.include_disputed_in_standard_ageing
"""

from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Q, Sum

from apps.billing.models import AgeingBucket, AgeingConfig, ARSummary, Invoice


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_ageing_config(scope):
    """Return the AgeingConfig for a scope, or None."""
    try:
        return AgeingConfig.objects.get(scope=scope)
    except AgeingConfig.DoesNotExist:
        return None


def _get_ageing_buckets(scope):
    """
    Return active AgeingBucket records for the scope, sorted by from_days.
    Returns None when no custom buckets are configured so callers can fall back
    to the hardcoded 30/60/90-day defaults.
    """
    buckets = list(
        AgeingBucket.objects.filter(scope=scope, status="ACTIVE")
        .order_by("sort_order", "from_days")
    )
    return buckets if buckets else None


def _bucket_index_for_days(days_aged, buckets):
    """
    Return the 0-based index of the bucket the invoice falls into.
    The last bucket is always open-ended (catches anything >= its from_days).
    """
    for i, bucket in enumerate(buckets):
        if bucket.to_days is None:
            # Open-ended bucket — catches everything from here
            return i
        if days_aged <= bucket.to_days:
            return i
    # Overflow → put in last bucket
    return len(buckets) - 1


def _update_agreement_summary(agreement, today):
    """Calculate and upsert the ARSummary for one agreement."""
    scope = agreement.scope
    ageing_cfg = _get_ageing_config(scope)

    use_due_date = ageing_cfg and ageing_cfg.reference_date == AgeingConfig.ReferenceDateType.DUE_DATE
    include_disputed = bool(ageing_cfg and ageing_cfg.include_disputed_in_standard_ageing)

    # Invoices that count as "open" (exclude PAID, CANCELLED, WRITTEN_OFF)
    open_statuses = [
        Invoice.InvoiceStatus.PENDING,
        Invoice.InvoiceStatus.SENT,
        Invoice.InvoiceStatus.PARTIALLY_PAID,
        Invoice.InvoiceStatus.OVERDUE,
        Invoice.InvoiceStatus.DISPUTED,
    ]
    invoices_qs = Invoice.objects.filter(agreement=agreement, status__in=open_statuses)

    if not include_disputed:
        invoices_qs = invoices_qs.exclude(status=Invoice.InvoiceStatus.DISPUTED)

    # Aggregate totals
    agg = invoices_qs.aggregate(
        total_invoiced=Sum("total_amount"),
        total_paid=Sum("amount_paid"),
        total_outstanding=Sum("balance_due"),
    )
    total_invoiced = agg["total_invoiced"] or Decimal("0")
    total_paid = agg["total_paid"] or Decimal("0")
    total_outstanding = agg["total_outstanding"] or Decimal("0")

    overdue_agg = invoices_qs.filter(
        due_date__lt=today, balance_due__gt=0
    ).aggregate(overdue=Sum("balance_due"))
    total_overdue = overdue_agg["overdue"] or Decimal("0")

    # Load custom buckets for this scope (or fall back to hardcoded 30/60/90)
    db_buckets = _get_ageing_buckets(scope)

    # Bucket accumulators mapped to the 4 fixed ARSummary columns:
    #   [0] current_bucket  [1] bucket_30_60  [2] bucket_60_90  [3] bucket_90_plus
    bucket_amounts = [Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0")]

    open_count = 0
    overdue_count = 0
    disputed_count = 0

    for inv in invoices_qs.filter(balance_due__gt=0):
        ref_date = inv.due_date if use_due_date else inv.invoice_date
        days_aged = (today - ref_date).days
        balance = inv.balance_due

        open_count += 1
        if inv.status == Invoice.InvoiceStatus.DISPUTED:
            disputed_count += 1
        if inv.due_date < today and balance > 0:
            overdue_count += 1

        if db_buckets:
            # Use DB-configured bucket boundaries
            raw_idx = _bucket_index_for_days(days_aged, db_buckets)
            # Clamp to 4 fixed columns: 0/1/2, and everything ≥3 goes to bucket_90_plus
            col_idx = min(raw_idx, 3)
            bucket_amounts[col_idx] += balance
        else:
            # Fall back to hardcoded 30/60/90-day boundaries
            if days_aged <= 30:
                bucket_amounts[0] += balance
            elif days_aged <= 60:
                bucket_amounts[1] += balance
            elif days_aged <= 90:
                bucket_amounts[2] += balance
            else:
                bucket_amounts[3] += balance

    # Also count disputed invoices even when excluded from ageing
    if not include_disputed:
        disputed_count = Invoice.objects.filter(
            agreement=agreement,
            status=Invoice.InvoiceStatus.DISPUTED,
        ).count()

    ARSummary.objects.update_or_create(
        agreement=agreement,
        defaults={
            "scope": scope,
            "total_invoiced": total_invoiced,
            "total_paid": total_paid,
            "total_outstanding": total_outstanding,
            "total_overdue": total_overdue,
            "current_bucket": bucket_amounts[0],
            "bucket_30_60": bucket_amounts[1],
            "bucket_60_90": bucket_amounts[2],
            "bucket_90_plus": bucket_amounts[3],
            "open_invoice_count": open_count,
            "overdue_invoice_count": overdue_count,
            "disputed_invoice_count": disputed_count,
        },
    )


class Command(BaseCommand):
    help = "Rebuild ARSummary cache for all lease agreements that have invoices"

    def add_arguments(self, parser):
        parser.add_argument(
            "--agreement-id",
            type=int,
            help="Only refresh the AR summary for a specific agreement ID",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show which agreements would be updated without writing anything",
        )

    def handle(self, *args, **options):
        from apps.leases.models import Agreement

        today = date.today()
        dry_run = options["dry_run"]
        agreement_id = options.get("agreement_id")

        if agreement_id:
            qs = Agreement.objects.filter(id=agreement_id).select_related("scope")
        else:
            # Only process agreements that actually have invoices
            qs = Agreement.objects.filter(
                invoices__isnull=False
            ).distinct().select_related("scope")

        total = qs.count()
        self.stdout.write(f"Processing {total} agreement(s)…")

        updated = 0
        errors = 0
        for agreement in qs:
            if dry_run:
                self.stdout.write(
                    f"  [DRY RUN] Would refresh AR summary for "
                    f"agreement {agreement.id} ({agreement.lease_id})"
                )
                updated += 1
                continue

            try:
                _update_agreement_summary(agreement, today)
                updated += 1
            except Exception as exc:
                errors += 1
                self.stderr.write(
                    self.style.ERROR(
                        f"  Error for agreement {agreement.id} "
                        f"({agreement.lease_id}): {exc}"
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. Updated: {updated}, Errors: {errors}"
            )
        )
