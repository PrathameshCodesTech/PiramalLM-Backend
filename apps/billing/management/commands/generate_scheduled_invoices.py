"""
Management command: generate_scheduled_invoices
================================================
Runs nightly to generate Invoices for all due InvoiceSchedules.

Steps per schedule:
  1. Calculate escalated rent if agreement has a LeaseEscalation
  2. Resolve CAM line items (Lease CAM override > Site CAM config)
  3. Create Invoice + InvoiceLineItem records
  4. Advance next_scheduled_date (or deactivate for ONE_TIME)
"""

import calendar
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Q

from apps.billing.cam_engine import get_cam_line_items_for_schedule
from apps.billing.models import (
    Invoice,
    InvoiceLineItem,
    InvoiceSchedule,
    SiteBillingConfig,
)


def _add_months(dt, months):
    """Add months to a date, clamping to the last valid day of the result month."""
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def _get_escalated_amount(schedule):
    """
    Return the schedule amount with escalation applied if available.
    Reads escalation values directly from LeaseEscalation (the agreement's
    own saved record). Template is a reference only; its values were copied
    into LeaseEscalation at selection time.
    """
    base_amount = schedule.amount

    try:
        escalation = schedule.agreement.escalation
    except Exception:
        return base_amount

    start_date = None
    try:
        start_date = schedule.agreement.term_dates.start_date
    except Exception:
        pass
    if not start_date:
        start_date = schedule.start_date
    if not start_date:
        return base_amount

    today = date.today()

    esc_type = escalation.escalation_type
    esc_value = escalation.escalation_value
    freq_months = escalation.escalation_frequency_months

    if esc_type == "FIXED_PERCENT" and esc_value:
        months_elapsed = (today - start_date).days / 30.4375
        periods = int(months_elapsed / freq_months)
        if periods > 0:
            multiplier = (1 + esc_value / 100) ** periods
            return base_amount * multiplier

    return base_amount


def _resolve_invoice_number_and_due_date(schedule, today):
    """
    Try to get invoice number from SiteBillingConfig (uses configured pattern +
    counter). Falls back to a simple timestamp-based number.
    Due date is derived from the site's default_payment_term.
    """
    invoice_number = f"INV-{today.strftime('%Y%m%d')}-{schedule.id}"
    due_date = today + timedelta(days=30)

    site = getattr(schedule.agreement, "site", None)
    if site:
        try:
            config = SiteBillingConfig.objects.get(site=site, scope=schedule.scope)
            invoice_number = config.get_next_invoice_number()
            term_days_map = {
                "DUE_ON_RECEIPT": 0,
                "NET_7": 7,
                "NET_15": 15,
                "NET_30": 30,
                "NET_45": 45,
                "NET_60": 60,
            }
            days = term_days_map.get(config.default_payment_term, 30)
            due_date = today + timedelta(days=days)
        except SiteBillingConfig.DoesNotExist:
            pass

    return invoice_number, due_date


def _advance_schedule(schedule, today):
    """
    Move next_scheduled_date forward by one frequency interval.
    ONE_TIME schedules are deactivated after generation.
    """
    freq_months_map = {
        InvoiceSchedule.ScheduleFrequency.MONTHLY: 1,
        InvoiceSchedule.ScheduleFrequency.QUARTERLY: 3,
        InvoiceSchedule.ScheduleFrequency.HALF_YEARLY: 6,
        InvoiceSchedule.ScheduleFrequency.ANNUALLY: 12,
        InvoiceSchedule.ScheduleFrequency.ONE_TIME: None,
    }
    months = freq_months_map.get(schedule.frequency)

    if months is None:
        schedule.is_active = False
        schedule.last_generated_date = today
        schedule.save(update_fields=["is_active", "last_generated_date"])
    else:
        next_date = _add_months(schedule.next_scheduled_date, months)
        schedule.last_generated_date = today
        schedule.next_scheduled_date = next_date
        schedule.save(update_fields=["last_generated_date", "next_scheduled_date"])


def _get_site_billing_config(schedule):
    """Return the SiteBillingConfig for the schedule's site, or None."""
    try:
        return schedule.agreement.site.billing_config
    except (AttributeError, SiteBillingConfig.DoesNotExist):
        return None


def _compute_gst_split(tax_amount, schedule):
    """Return (cgst, sgst, igst, gst_type) based on the site's SiteBillingConfig.

    Checks state_tax_rules first (per-state override), then falls back to
    the site-level gst_split_logic.
    """
    config = _get_site_billing_config(schedule)
    split_logic = SiteBillingConfig.GSTSplitLogic.IGST

    if config:
        # Check state-level override rules first
        site_state = getattr(schedule.agreement.site, "state", "") or ""
        if site_state and config.state_tax_rules:
            for rule in config.state_tax_rules:
                if rule.get("state", "").upper() == site_state.upper():
                    split_logic = rule.get("split", config.gst_split_logic)
                    break
            else:
                split_logic = config.gst_split_logic
        else:
            split_logic = config.gst_split_logic

    if split_logic == SiteBillingConfig.GSTSplitLogic.CGST_SGST:
        half = (tax_amount / 2).quantize(Decimal("0.01"))
        return half, tax_amount - half, Decimal("0"), "CGST_SGST"
    else:
        return Decimal("0"), Decimal("0"), tax_amount, "IGST"


def _generate_invoice(schedule, today):
    """Core logic: create Invoice + line items for one InvoiceSchedule."""
    config = _get_site_billing_config(schedule)

    # Group 3: use site's default_gst_rate as the effective tax rate
    effective_tax_rate = schedule.tax_rate
    if config and config.default_gst_rate is not None:
        effective_tax_rate = config.default_gst_rate

    amount = _get_escalated_amount(schedule)
    tax_amt = amount * (effective_tax_rate / 100)
    total = amount + tax_amt

    invoice_number, due_date = _resolve_invoice_number_and_due_date(schedule, today)

    cgst, sgst, igst, gst_type = _compute_gst_split(tax_amt, schedule)

    # Group 5: is_gst_invoice from site config flag; billing_address if override enabled
    is_gst_invoice = config.default_gst_invoice_flag if config else True
    billing_address = ""
    if config and config.billing_address_override:
        tenant = getattr(schedule.agreement, "tenant", None)
        if tenant:
            parts = filter(None, [
                getattr(tenant, "address", ""),
                getattr(tenant, "city", ""),
                getattr(tenant, "state", ""),
                getattr(tenant, "pincode", ""),
            ])
            billing_address = ", ".join(parts)

    invoice = Invoice.objects.create(
        scope=schedule.scope,
        agreement=schedule.agreement,
        invoice_number=invoice_number,
        invoice_type=schedule.invoice_type,
        status=Invoice.InvoiceStatus.PENDING,
        invoice_date=today,
        due_date=due_date,
        subtotal=amount,
        tax_amount=tax_amt,
        cgst_amount=cgst,
        sgst_amount=sgst,
        igst_amount=igst,
        gst_type=gst_type,
        total_amount=total,
        amount_paid=Decimal("0"),
        balance_due=total,
        period_start=schedule.next_scheduled_date,
        period_end=today,
        is_gst_invoice=is_gst_invoice,
        billing_address=billing_address,
    )

    line_type_map = {
        Invoice.InvoiceType.RENT: InvoiceLineItem.LineItemType.BASE_RENT,
        Invoice.InvoiceType.CAM: InvoiceLineItem.LineItemType.CAM,
        Invoice.InvoiceType.UTILITY: InvoiceLineItem.LineItemType.UTILITY,
    }
    item_type = line_type_map.get(schedule.invoice_type, InvoiceLineItem.LineItemType.OTHER)

    InvoiceLineItem.objects.create(
        invoice=invoice,
        scope=schedule.scope,
        item_type=item_type,
        description=schedule.schedule_name,
        quantity=Decimal("1"),
        unit_price=amount,
        tax_rate=schedule.tax_rate,
    )

    cam_items = get_cam_line_items_for_schedule(
        schedule=schedule,
        base_rent_amount=amount,
    )
    if cam_items:
        extra_subtotal = Decimal("0")
        extra_tax = Decimal("0")
        for item in cam_items:
            tax_rate = item.get("tax_rate")
            if tax_rate is None:
                tax_rate = (
                    item["gst_amount"] / item["amount"] * 100
                    if item["amount"] else Decimal("0")
                )

            InvoiceLineItem.objects.create(
                invoice=invoice,
                scope=schedule.scope,
                item_type=InvoiceLineItem.LineItemType.CAM,
                description=item["description"],
                quantity=Decimal("1"),
                unit_price=item["amount"],
                tax_rate=tax_rate,
                cam_component=item.get("cam_component"),
            )
            extra_subtotal += item["amount"]
            extra_tax += item["gst_amount"]

        invoice.subtotal += extra_subtotal
        invoice.tax_amount += extra_tax
        invoice.total_amount += extra_subtotal + extra_tax
        invoice.balance_due += extra_subtotal + extra_tax
        # Recompute GST split on the final tax_amount
        cgst, sgst, igst, gst_type = _compute_gst_split(invoice.tax_amount, schedule)
        invoice.cgst_amount = cgst
        invoice.sgst_amount = sgst
        invoice.igst_amount = igst
        invoice.gst_type = gst_type
        invoice.save(update_fields=[
            "subtotal", "tax_amount", "total_amount", "balance_due",
            "cgst_amount", "sgst_amount", "igst_amount", "gst_type",
        ])

    _advance_schedule(schedule, today)
    return invoice


class Command(BaseCommand):
    help = "Generate invoices for all InvoiceSchedules due today or earlier"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview what would be generated without creating any records",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        today = date.today()

        due_schedules = InvoiceSchedule.objects.filter(
            is_active=True,
            next_scheduled_date__lte=today,
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=today)
        ).select_related(
            "agreement",
            "agreement__site",
            "agreement__site__billing_config",
            "agreement__term_dates",
            "agreement__financials",
            "agreement__escalation",
            "agreement__escalation__template",
            "scope",
        )

        total = due_schedules.count()
        self.stdout.write(f"Found {total} schedule(s) due for generation")

        created = 0
        skipped = 0
        errors = 0
        for schedule in due_schedules:
            # Group 4: skip sites configured for MANUAL invoice generation
            site_config = _get_site_billing_config(schedule)
            if site_config and site_config.generation_mode == SiteBillingConfig.InvoiceGenerationMode.MANUAL:
                self.stdout.write(
                    f"  [SKIP] {schedule.schedule_name} — site '{schedule.agreement.site.name}' "
                    f"is set to MANUAL generation"
                )
                skipped += 1
                continue

            # Group 4: respect site-level generation_day_of_month override
            if site_config and site_config.generation_day_of_month:
                if today.day != site_config.generation_day_of_month:
                    self.stdout.write(
                        f"  [SKIP] {schedule.schedule_name} — site configured to generate "
                        f"on day {site_config.generation_day_of_month}, today is day {today.day}"
                    )
                    skipped += 1
                    continue

            if dry_run:
                self.stdout.write(
                    f"  [DRY RUN] Would generate: {schedule.schedule_name} "
                    f"(agreement {schedule.agreement.lease_id}, "
                    f"due {schedule.next_scheduled_date})"
                )
                created += 1
                continue

            try:
                inv = _generate_invoice(schedule, today)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  Created {inv.invoice_number} for {schedule.agreement.lease_id}"
                    )
                )
                created += 1
            except Exception as exc:
                errors += 1
                self.stderr.write(
                    self.style.ERROR(
                        f"  Error for schedule {schedule.id} "
                        f"({schedule.schedule_name}): {exc}"
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. Created: {created}, Skipped: {skipped}, Errors: {errors}"
            )
        )
