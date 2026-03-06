from decimal import Decimal, ROUND_HALF_UP

from apps.billing.models import Invoice
from apps.leases.models import LeaseCAM
from apps.properties.models import CAMComponent, SiteCAMConfig


MONEY_Q = Decimal("0.01")
HUNDRED = Decimal("100")


def _to_decimal(value, default=Decimal("0")):
    if value in (None, ""):
        return default
    return Decimal(str(value))


def _to_money(value):
    return _to_decimal(value).quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _get_allocations(agreement):
    return list(
        agreement.unit_allocations.filter(is_active=True).only(
            "id", "allocated_area_sqft", "unit_id", "floor_id", "tower_id", "site_id"
        )
    )


def _common_area_multiplier(site):
    pct = _to_decimal(getattr(site, "common_area_percent", None))
    if pct < 0:
        pct = Decimal("0")
    return Decimal("1") + (pct / HUNDRED)


def _allocation_area_for_basis(allocation, area_basis, site):
    area = _to_decimal(allocation.allocated_area_sqft)
    if area_basis == CAMComponent.AreaBasis.CHARGEABLE_AREA:
        return area * _common_area_multiplier(site)
    # Until dedicated carpet/super-builtup allocation snapshots are added,
    # all remaining bases use allocated area deterministically.
    return area


def _total_area_for_basis(allocations, area_basis, site):
    total = Decimal("0")
    for allocation in allocations:
        total += _allocation_area_for_basis(allocation, area_basis, site)
    return total


def _allocated_unit_count(allocations):
    unit_ids = {a.unit_id for a in allocations if getattr(a, "unit_id", None)}
    if unit_ids:
        return len(unit_ids)
    return len(allocations)


def _lease_cam_has_values(cam):
    return any(
        value is not None
        for value in (
            cam.monthly_total,
            cam.per_sqft_monthly,
            cam.fixed_amount_monthly,
            cam.percentage_value,
        )
    )


def _build_lease_cam_line_item(agreement, base_rent_amount, tax_rate):
    try:
        cam = agreement.cam
    except LeaseCAM.DoesNotExist:
        return None

    if not cam.is_active or not _lease_cam_has_values(cam):
        return None

    base_amount = None
    if cam.monthly_total is not None:
        base_amount = _to_decimal(cam.monthly_total)
    elif cam.allocation_basis == LeaseCAM.CAMBasis.PRO_RATA:
        if cam.per_sqft_monthly is None:
            raise ValueError("Lease CAM PRO_RATA requires per_sqft_monthly or monthly_total.")
        allocations = _get_allocations(agreement)
        if not allocations:
            return None
        area = _total_area_for_basis(
            allocations,
            CAMComponent.AreaBasis.LEASABLE_AREA,
            agreement.site,
        )
        base_amount = area * _to_decimal(cam.per_sqft_monthly)
    elif cam.allocation_basis == LeaseCAM.CAMBasis.FIXED:
        value = cam.fixed_amount_monthly if cam.fixed_amount_monthly is not None else cam.monthly_total
        if value is None:
            raise ValueError("Lease CAM FIXED requires fixed_amount_monthly or monthly_total.")
        base_amount = _to_decimal(value)
    elif cam.allocation_basis == LeaseCAM.CAMBasis.PERCENTAGE:
        if cam.percentage_value is None:
            raise ValueError("Lease CAM PERCENTAGE requires percentage_value.")
        base_amount = _to_decimal(base_rent_amount) * (_to_decimal(cam.percentage_value) / HUNDRED)

    if base_amount is None or base_amount <= 0:
        return None

    tax_rate_dec = _to_decimal(tax_rate)
    gst_amount = base_amount * (tax_rate_dec / HUNDRED)
    return {
        "description": "CAM - Lease Override",
        "amount": _to_money(base_amount),
        "gst_amount": _to_money(gst_amount),
        "tax_rate": _to_money(tax_rate_dec),
        "cam_component": None,
        "source": "LEASE_CAM",
    }


def _build_site_cam_line_items(agreement, scope):
    if not agreement.site_id:
        return []

    allocations = _get_allocations(agreement)
    if not allocations:
        return []

    unit_count = _allocated_unit_count(allocations)
    site = agreement.site
    configs = SiteCAMConfig.objects.filter(
        site=site,
        is_active=True,
        scope=scope,
    ).select_related("component")

    items = []
    for config in configs:
        area_basis = config.get_effective_area_basis()
        area = _total_area_for_basis(allocations, area_basis, site)
        base_charge, gst_amount, _ = config.calculate_charge(
            area_sqft=area,
            unit_count=unit_count,
        )
        base_charge = _to_money(base_charge)
        gst_amount = _to_money(gst_amount)
        if base_charge <= 0:
            continue
        tax_rate = (gst_amount / base_charge * HUNDRED) if base_charge else Decimal("0")
        items.append(
            {
                "description": f"CAM - {config.component.name}",
                "amount": base_charge,
                "gst_amount": gst_amount,
                "tax_rate": _to_money(tax_rate),
                "cam_component": config.component,
                "source": "SITE_CAM_CONFIG",
                "area_basis": area_basis,
            }
        )
    return items


def get_cam_line_items_for_schedule(schedule, base_rent_amount):
    """
    Resolve CAM charge lines for a RENT schedule with strict precedence:
    Lease CAM override > Site CAM component configuration.
    """
    if schedule.invoice_type != Invoice.InvoiceType.RENT:
        return []

    lease_override = _build_lease_cam_line_item(
        agreement=schedule.agreement,
        base_rent_amount=base_rent_amount,
        tax_rate=schedule.tax_rate,
    )
    if lease_override:
        return [lease_override]

    return _build_site_cam_line_items(
        agreement=schedule.agreement,
        scope=schedule.scope,
    )
