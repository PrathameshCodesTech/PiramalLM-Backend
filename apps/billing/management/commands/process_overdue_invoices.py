"""
Management command: process_overdue_invoices
=============================================
Runs nightly to:
  1. Mark Invoices as OVERDUE when past their due_date and still have a balance
  2. Call the billing rules engine for each OVERDUE invoice so late-fee rules
     can fire (AUTO mode creates a new LATE_FEE Invoice; MANUAL mode creates
     a PendingAction for the user to review)
"""

from datetime import date

from django.core.management.base import BaseCommand

from apps.billing.models import Invoice
from apps.billing.engines import RulesEngine


_ELIGIBLE_STATUSES = [
    Invoice.InvoiceStatus.PENDING,
    Invoice.InvoiceStatus.SENT,
    Invoice.InvoiceStatus.PARTIALLY_PAID,
]


class Command(BaseCommand):
    help = "Mark overdue invoices and evaluate billing rules for late fees"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview changes without writing to the database",
        )
        parser.add_argument(
            "--skip-rules",
            action="store_true",
            help="Only mark invoices OVERDUE; skip the billing rules check",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        skip_rules = options["skip_rules"]
        today = date.today()

        # ── Step 1: mark eligible invoices as OVERDUE ───────────────────────
        overdue_qs = Invoice.objects.filter(
            due_date__lt=today,
            balance_due__gt=0,
            status__in=_ELIGIBLE_STATUSES,
        )

        if dry_run:
            count = overdue_qs.count()
            self.stdout.write(f"[DRY RUN] Would mark {count} invoice(s) as OVERDUE")
        else:
            updated = overdue_qs.update(status=Invoice.InvoiceStatus.OVERDUE)
            self.stdout.write(self.style.SUCCESS(f"Marked {updated} invoice(s) as OVERDUE"))

        if skip_rules:
            self.stdout.write("Skipping billing rules (--skip-rules flag set)")
            return

        # ── Step 2: evaluate billing rules for all currently-OVERDUE invoices ──
        all_overdue = Invoice.objects.filter(
            due_date__lt=today,
            balance_due__gt=0,
            status=Invoice.InvoiceStatus.OVERDUE,
        ).select_related(
            "agreement",
            "agreement__financials",
            "agreement__site",
            "scope",
        )

        checked = 0
        errors = 0
        for invoice in all_overdue:
            if dry_run:
                overdue_days = (today - invoice.due_date).days
                self.stdout.write(
                    f"  [DRY RUN] Would check rules for {invoice.invoice_number} "
                    f"({overdue_days}d overdue, balance ₹{invoice.balance_due})"
                )
                checked += 1
                continue

            try:
                RulesEngine.check_billing_rules(invoice, invoice.scope, user=None)
                checked += 1
            except Exception as exc:
                errors += 1
                self.stderr.write(
                    self.style.ERROR(
                        f"  Error checking billing rules for invoice "
                        f"{invoice.invoice_number} (id={invoice.id}): {exc}"
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. Rules checked: {checked}, Errors: {errors}"
            )
        )
