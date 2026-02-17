from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation


TWOPLACES = Decimal("0.01")


def _to_decimal(value):
    if value in [None, ""]:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _to_int(value, default=0):
    if value in [None, ""]:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_date(value):
    if value in [None, ""]:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _days_in_month(day):
    return monthrange(day.year, day.month)[1]


def _round2(value):
    return value.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _to_float_or_none(value):
    if value is None:
        return None
    return float(_round2(value))


def _add_years_safe(day, years):
    try:
        return day.replace(year=day.year + years)
    except ValueError:
        # Handle Feb 29 -> Feb 28 for non-leap year
        return day.replace(month=2, day=28, year=day.year + years)


def _sum_daily_charges(
    start_day,
    end_day,
    monthly_base_rent,
    commencement_day,
    primary_buffer_days,
    extended_buffer_days,
    extended_buffer_charge_percent,
):
    gross = Decimal("0")
    charged = Decimal("0")
    primary_concession = Decimal("0")
    extended_concession = Decimal("0")

    day = start_day
    while day <= end_day:
        daily_base = monthly_base_rent / Decimal(_days_in_month(day))
        day_offset = (day - commencement_day).days

        if day_offset < primary_buffer_days:
            charge_factor = Decimal("0")
            phase = "PRIMARY_BUFFER"
        elif day_offset < (primary_buffer_days + extended_buffer_days):
            charge_factor = extended_buffer_charge_percent / Decimal("100")
            phase = "EXTENDED_BUFFER"
        else:
            charge_factor = Decimal("1")
            phase = "NORMAL"

        daily_charged = daily_base * charge_factor
        gross += daily_base
        charged += daily_charged

        if phase == "PRIMARY_BUFFER":
            primary_concession += daily_base
        elif phase == "EXTENDED_BUFFER":
            extended_concession += (daily_base - daily_charged)

        day += timedelta(days=1)

    return {
        "gross": _round2(gross),
        "charged": _round2(charged),
        "primary_concession": _round2(primary_concession),
        "extended_concession": _round2(extended_concession),
    }


def resolve_base_rent_monthly(base_rent_monthly, rate_per_sqft_monthly, total_allocated_area_sqft):
    explicit_base = _to_decimal(base_rent_monthly)
    if explicit_base is not None:
        return _round2(explicit_base)

    rate = _to_decimal(rate_per_sqft_monthly)
    area = _to_decimal(total_allocated_area_sqft)
    if rate is None or area is None:
        return None
    if area <= 0:
        return None

    return _round2(rate * area)


def calculate_buffer_summary(
    *,
    commencement_date,
    expiry_date,
    monthly_base_rent,
    primary_buffer_days,
    extended_buffer_days,
    extended_buffer_charge_percent,
    allocated_area_sqft,
):
    commencement = _to_date(commencement_date)
    expiry = _to_date(expiry_date)
    monthly_base = _to_decimal(monthly_base_rent)
    if commencement is None or monthly_base is None or monthly_base <= 0:
        return None

    primary_days = max(0, _to_int(primary_buffer_days, 0))
    extended_days = max(0, _to_int(extended_buffer_days, 0))
    extended_percent = _to_decimal(extended_buffer_charge_percent)
    if extended_percent is None:
        extended_percent = Decimal("0")
    if extended_percent < 0:
        extended_percent = Decimal("0")
    if extended_percent > 100:
        extended_percent = Decimal("100")

    area = _to_decimal(allocated_area_sqft)

    primary_start = commencement if primary_days > 0 else None
    primary_end = (commencement + timedelta(days=primary_days - 1)) if primary_days > 0 else None
    extended_start = (commencement + timedelta(days=primary_days)) if extended_days > 0 else None
    extended_end = (
        extended_start + timedelta(days=extended_days - 1) if extended_days > 0 else None
    )
    first_charge_date = commencement + timedelta(days=primary_days)
    full_charge_date = commencement + timedelta(days=primary_days + extended_days)

    first_year_end = _add_years_safe(commencement, 1) - timedelta(days=1)
    annual_range_end = min(first_year_end, expiry) if expiry else first_year_end
    annual_range_start = commencement
    annual_totals = (
        _sum_daily_charges(
            annual_range_start,
            annual_range_end,
            monthly_base,
            commencement,
            primary_days,
            extended_days,
            extended_percent,
        )
        if annual_range_end >= annual_range_start
        else {
            "gross": Decimal("0"),
            "charged": Decimal("0"),
            "primary_concession": Decimal("0"),
            "extended_concession": Decimal("0"),
        }
    )

    term_range_end = expiry or annual_range_end
    term_totals = (
        _sum_daily_charges(
            commencement,
            term_range_end,
            monthly_base,
            commencement,
            primary_days,
            extended_days,
            extended_percent,
        )
        if term_range_end >= commencement
        else {
            "gross": Decimal("0"),
            "charged": Decimal("0"),
            "primary_concession": Decimal("0"),
            "extended_concession": Decimal("0"),
        }
    )

    first_invoice_end = date(
        first_charge_date.year,
        first_charge_date.month,
        monthrange(first_charge_date.year, first_charge_date.month)[1],
    )
    first_invoice_range_end = min(first_invoice_end, expiry) if expiry else first_invoice_end
    if first_invoice_range_end >= first_charge_date:
        first_invoice_amount = _sum_daily_charges(
            first_charge_date,
            first_invoice_range_end,
            monthly_base,
            commencement,
            primary_days,
            extended_days,
            extended_percent,
        )["charged"]
    else:
        first_invoice_amount = Decimal("0")

    next_cycle_start = first_invoice_range_end + timedelta(days=1)
    next_cycle_end = date(
        next_cycle_start.year,
        next_cycle_start.month,
        monthrange(next_cycle_start.year, next_cycle_start.month)[1],
    )
    next_cycle_range_end = min(next_cycle_end, expiry) if expiry else next_cycle_end
    if next_cycle_range_end >= next_cycle_start:
        next_cycle_amount = _sum_daily_charges(
            next_cycle_start,
            next_cycle_range_end,
            monthly_base,
            commencement,
            primary_days,
            extended_days,
            extended_percent,
        )["charged"]
    else:
        next_cycle_amount = Decimal("0")

    effective_monthly = _round2(annual_totals["charged"] / Decimal("12"))
    effective_rate = (
        _round2(effective_monthly / area)
        if area is not None and area > 0
        else None
    )
    current_daily_base = _round2(monthly_base / Decimal(_days_in_month(commencement)))

    return {
        "primaryBufferDays": primary_days,
        "extendedBufferDays": extended_days,
        "extendedBufferChargePercent": float(_round2(extended_percent)),
        "primaryBufferStartDate": primary_start.isoformat() if primary_start else None,
        "primaryBufferEndDate": primary_end.isoformat() if primary_end else None,
        "extendedBufferStartDate": extended_start.isoformat() if extended_start else None,
        "extendedBufferEndDate": extended_end.isoformat() if extended_end else None,
        "firstChargeDate": first_charge_date.isoformat(),
        "fullChargeDate": full_charge_date.isoformat(),
        "annualGrossRent": _to_float_or_none(annual_totals["gross"]),
        "annualPrimaryBufferConcession": _to_float_or_none(annual_totals["primary_concession"]),
        "annualExtendedBufferConcession": _to_float_or_none(annual_totals["extended_concession"]),
        "annualNetCollectible": _to_float_or_none(annual_totals["charged"]),
        "effectiveMonthlyRent": _to_float_or_none(effective_monthly),
        "effectiveRatePerSqft": _to_float_or_none(effective_rate),
        "termGrossRent": _to_float_or_none(term_totals["gross"]),
        "termPrimaryBufferConcession": _to_float_or_none(term_totals["primary_concession"]),
        "termExtendedBufferConcession": _to_float_or_none(term_totals["extended_concession"]),
        "termNetCollectible": _to_float_or_none(term_totals["charged"]),
        "currentDailyBaseRent": _to_float_or_none(current_daily_base),
        "firstInvoiceAmount": _to_float_or_none(first_invoice_amount),
        "nextCycleAmount": _to_float_or_none(next_cycle_amount),
    }
