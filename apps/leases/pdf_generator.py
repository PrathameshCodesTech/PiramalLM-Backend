"""
PDF Generation for Lease Agreements.

Provides functions to render a full agreement (or a single section) as
HTML and optionally convert that HTML to a PDF using xhtml2pdf.
"""

from io import BytesIO
from datetime import date
from decimal import Decimal

from django.template.loader import render_to_string
from django.db.models import Sum


def _safe_attr(obj, attr, default=""):
    """Safely get an attribute from an object."""
    if obj is None:
        return default
    val = getattr(obj, attr, default)
    return val if val is not None else default


def _fmt_currency(value, currency="INR"):
    """Format a numeric value as currency string."""
    if value is None:
        return "—"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    symbol = "₹" if currency == "INR" else currency + " "
    return f"{symbol}{num:,.2f}"


def _fmt_date(value):
    if value is None:
        return "—"
    if isinstance(value, str):
        return value
    return value.strftime("%d %B %Y")


def _fmt_area(value):
    if value is None:
        return "—"
    return f"{float(value):,.2f} sq ft"


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

def _get_scope_hierarchy(agreement):
    """Resolve org/company/entity names from the agreement scope."""
    scope = agreement.scope
    hierarchy = scope.get_hierarchy_path() if hasattr(scope, "get_hierarchy_path") else {}
    org = hierarchy.get("org")
    company = hierarchy.get("company")
    entity = hierarchy.get("entity")
    return {
        "org_name": _safe_attr(org, "legal_name") or _safe_attr(org, "name"),
        "org_address": _safe_attr(org, "address"),
        "org_city": _safe_attr(org, "city"),
        "org_state": _safe_attr(org, "state"),
        "org_country": _safe_attr(org, "country"),
        "org_registration": _safe_attr(org, "registration_number"),
        "org_tax_id": _safe_attr(org, "tax_id"),
        "company_name": _safe_attr(company, "legal_name") or _safe_attr(company, "name"),
        "entity_name": _safe_attr(entity, "legal_name") or _safe_attr(entity, "name"),
    }


def _get_tenant_info(agreement):
    tenant = agreement.tenant
    contact = agreement.primary_contact
    return {
        "legal_name": _safe_attr(tenant, "legal_name"),
        "trade_name": _safe_attr(tenant, "trade_name"),
        "registration_number": _safe_attr(tenant, "registration_number"),
        "tax_id": _safe_attr(tenant, "tax_id") or _safe_attr(tenant, "gst_number"),
        "address": _safe_attr(tenant, "address"),
        "city": _safe_attr(tenant, "city"),
        "state": _safe_attr(tenant, "state"),
        "country": _safe_attr(tenant, "country"),
        "contact_name": (
            f"{_safe_attr(contact, 'first_name')} {_safe_attr(contact, 'last_name')}".strip()
            if contact else "—"
        ),
        "contact_email": _safe_attr(contact, "email"),
        "contact_phone": _safe_attr(contact, "phone") or _safe_attr(contact, "mobile"),
    }


def _get_site_info(agreement):
    site = agreement.site
    return {
        "name": _safe_attr(site, "name"),
        "code": _safe_attr(site, "code"),
        "address": _safe_attr(site, "address"),
        "city": _safe_attr(site, "city"),
        "state": _safe_attr(site, "state"),
        "country": _safe_attr(site, "country"),
        "site_type": _safe_attr(site, "site_type"),
    }


def _get_allocations(agreement):
    allocs = agreement.unit_allocations.filter(is_active=True).select_related(
        "site", "tower", "floor", "unit"
    ).order_by("allocation_level", "created_at")
    rows = []
    for a in allocs:
        target = a.site or a.tower or a.floor or a.unit
        label = str(target) if target else "—"
        rows.append({
            "level": a.allocation_level,
            "label": label,
            "mode": a.allocation_mode,
            "area": _fmt_area(a.allocated_area_sqft),
            "area_raw": float(a.allocated_area_sqft or 0),
            "rent": _fmt_currency(a.monthly_rent),
        })
    total_area = allocs.aggregate(t=Sum("allocated_area_sqft"))["t"] or 0
    return rows, float(total_area)


def _get_term_dates(agreement):
    try:
        td = agreement.term_dates
    except Exception:
        return None
    if td is None:
        return None
    return {
        "commencement_date": _fmt_date(td.commencement_date),
        "expiry_date": _fmt_date(td.expiry_date),
        "initial_term_months": td.initial_term_months,
        "lock_in_start": _fmt_date(td.lock_in_start_date),
        "lock_in_end": _fmt_date(td.lock_in_end_date),
        "lock_in_months": td.lock_in_months,
        "notice_renewal_days": td.notice_renewal_days,
        "notice_landlord_days": td.notice_landlord_days,
        "notice_tenant_days": td.notice_tenant_days,
    }


def _get_financials(agreement, total_area):
    try:
        f = agreement.financials
    except Exception:
        return None
    if f is None:
        return None
    return {
        "base_rent_monthly": _fmt_currency(f.base_rent_monthly),
        "rate_per_sqft": _fmt_currency(f.rate_per_sqft_monthly),
        "annual_rent": _fmt_currency(f.annual_rent),
        "billing_frequency": f.get_billing_frequency_display() if hasattr(f, "get_billing_frequency_display") else f.billing_frequency,
        "payment_due_date": f.get_payment_due_date_display() if hasattr(f, "get_payment_due_date_display") else f.payment_due_date,
        "first_rent_due": _fmt_date(f.first_rent_due_date),
        "currency": f.currency,
        "total_area": _fmt_area(total_area),
    }


def _get_escalation(agreement):
    try:
        e = agreement.escalation
    except Exception:
        return None
    if e is None:
        return None
    return {
        "type": e.get_escalation_type_display() if hasattr(e, "get_escalation_type_display") else e.escalation_type,
        "value": e.escalation_value,
        "frequency_months": e.escalation_frequency_months,
        "first_escalation_months": e.first_escalation_months,
        "cap": e.cap_percentage,
        "floor": e.floor_percentage,
        "apply_to_cam": e.apply_to_cam,
        "apply_to_parking": e.apply_to_parking,
        "template_name": _safe_attr(e.template, "name") if e.template else None,
    }


def _get_cam(agreement):
    try:
        c = agreement.cam
    except Exception:
        return None
    if c is None:
        return None
    return {
        "basis": c.get_allocation_basis_display() if hasattr(c, "get_allocation_basis_display") else c.allocation_basis,
        "per_sqft": _fmt_currency(c.per_sqft_monthly),
        "fixed": _fmt_currency(c.fixed_amount_monthly),
        "percentage": c.percentage_value,
        "monthly_total": _fmt_currency(c.monthly_total),
    }


def _get_deposit(agreement):
    try:
        d = agreement.deposit
    except Exception:
        return None
    if d is None:
        return None
    return {
        "amount": _fmt_currency(d.amount),
        "months_equivalent": d.months_equivalent,
        "held_by": d.held_by,
        "refund_conditions": d.refund_conditions,
        "interest_bearing": d.interest_bearing,
        "interest_rate": d.interest_rate,
    }


def _get_rent_free(agreement):
    try:
        rf = agreement.rent_free
    except Exception:
        return None
    if rf is None:
        return None
    return {
        "start_date": _fmt_date(rf.rent_free_start_date),
        "days": rf.rent_free_days,
        "end_date": _fmt_date(rf.rent_free_end_date),
        "extended_days": rf.extended_buffer_days,
        "extended_charge_percent": rf.extended_buffer_charge_percent,
        "fitout_start": _fmt_date(rf.fitout_start_date),
        "fitout_end": _fmt_date(rf.fitout_end_date),
        "cam_during_fitout": rf.cam_during_fitout,
    }


def _get_termination(agreement):
    try:
        t = agreement.termination
    except Exception:
        return None
    if t is None:
        return None
    return {
        "tenant_early_exit": t.tenant_early_exit_permitted,
        "tenant_notice_days": t.tenant_notice_days,
        "tenant_penalty": t.get_tenant_penalty_display(),
        "tenant_conditions": t.tenant_exit_conditions,
        "landlord_early_termination": t.landlord_early_termination_permitted,
        "landlord_notice_days": t.landlord_notice_days,
        "landlord_compensation": t.get_landlord_compensation_display(),
        "landlord_relocation": t.landlord_relocation_assistance,
        "break_clause": t.break_clause_enabled,
        "break_date": _fmt_date(t.break_date),
        "break_notice_days": t.break_notice_days,
        "cause_events": t.termination_for_cause_events,
        "cure_period_days": t.cure_period_days,
        "clause_text": t.termination_clause,
    }


def _get_renewal(agreement):
    try:
        r = agreement.renewal_option
    except Exception:
        return None
    if r is None:
        return None
    return {
        "pre_notice_days": r.pre_renewal_notice_days,
        "auto_renewal": r.auto_renewal_enabled,
        "auto_term_months": r.auto_renewal_term_months,
        "max_cycles": r.max_renewal_cycles,
        "cycles": r.renewal_cycles,
        "notes": r.renewal_notes,
    }


def _get_insurance(agreement):
    try:
        ins = agreement.insurance_requirement
    except Exception:
        return None
    if ins is None:
        return None
    return {
        "restore_condition": ins.get_restore_condition_display() if hasattr(ins, "get_restore_condition_display") else ins.restore_condition,
        "restore_details": ins.restore_details,
        "reinstatement_deposit": _fmt_currency(ins.reinstatement_deposit),
        "reinstatement_days": ins.reinstatement_timeline_days,
        "public_liability": ins.public_liability_required,
        "public_liability_coverage": _fmt_currency(ins.public_liability_coverage),
        "property_insurance": ins.property_insurance_required,
        "property_coverage": _fmt_currency(ins.property_insurance_coverage),
        "business_interruption": ins.business_interruption_required,
        "landlord_additional_insured": ins.landlord_additional_insured,
        "indemnity_notes": ins.indemnity_notes,
    }


def _get_dispute(agreement):
    try:
        d = agreement.dispute_resolution
    except Exception:
        return None
    if d is None:
        return None
    return {
        "mechanism": d.get_dispute_mechanism_display() if hasattr(d, "get_dispute_mechanism_display") else d.dispute_mechanism,
        "arbitration_seat": d.arbitration_seat,
        "arbitration_rules": d.arbitration_rules,
        "arbitration_language": d.arbitration_language,
        "num_arbitrators": d.number_of_arbitrators,
        "mediation_first": d.mediation_required_first,
        "mediation_days": d.mediation_period_days,
        "governing_law_country": d.governing_law_country,
        "governing_law_state": d.governing_law_state,
        "jurisdiction": d.jurisdiction_court,
        "exclusive_jurisdiction": d.exclusive_jurisdiction,
        "summary": d.dispute_summary,
    }


def _get_sublet_signage(agreement):
    try:
        s = agreement.sublet_signage
    except Exception:
        return None
    if s is None:
        return None
    return {
        "sublet_permission": s.get_sublet_permission_display() if hasattr(s, "get_sublet_permission_display") else s.sublet_permission,
        "max_sublet_pct": s.max_sublet_percentage,
        "sublet_restrictions": s.sublet_restrictions,
        "signage_permitted": s.signage_permitted,
        "signage_locations": s.signage_locations,
        "signage_specs": s.signage_specifications,
    }


def _get_exclusivity(agreement):
    try:
        ex = agreement.exclusivity
    except Exception:
        return None
    if ex is None:
        return None
    return {
        "exclusive_use": ex.exclusive_use_granted,
        "category": ex.exclusive_category,
        "radius": ex.exclusive_radius,
        "exceptions": ex.exclusive_exceptions,
        "non_compete": ex.non_compete_enabled,
        "non_compete_months": ex.non_compete_duration_months,
        "non_compete_km": ex.non_compete_radius_km,
    }


def _get_sections_with_clauses(agreement):
    """Get the agreement structure sections with linked clauses."""
    structure = agreement.structure
    if not structure:
        return None, []

    from apps.clauses.models import ClauseUsage

    root_sections = structure.sections.filter(
        parent__isnull=True, is_active=True
    ).order_by("sort_order", "name")

    clause_usages = ClauseUsage.objects.filter(
        agreement=agreement, is_active=True
    ).select_related("clause", "clause_version", "section")

    usage_by_section = {}
    for cu in clause_usages:
        sid = cu.section_id
        if sid not in usage_by_section:
            usage_by_section[sid] = []
        body = cu.custom_body_text or ""
        if not body and cu.clause_version:
            body = cu.clause_version.body_text or ""
        usage_by_section[sid].append({
            "clause_title": cu.clause.title,
            "clause_id": cu.clause.clause_id,
            "version": cu.clause_version.version_label if cu.clause_version else "",
            "body_text": body,
        })

    def _build_section_tree(sections):
        result = []
        for sec in sections:
            children_qs = sec.children.filter(is_active=True).order_by("sort_order", "name")
            result.append({
                "id": sec.id,
                "name": sec.name,
                "description": sec.description,
                "clauses": usage_by_section.get(sec.id, []),
                "children": _build_section_tree(children_qs),
            })
        return result

    sections_tree = _build_section_tree(root_sections)
    return structure.name, sections_tree


def _get_single_section_data(agreement, section_id):
    """Get data for a single section."""
    from apps.leases.models import AgreementSection
    from apps.clauses.models import ClauseUsage

    try:
        section = AgreementSection.objects.get(pk=section_id, is_active=True)
    except AgreementSection.DoesNotExist:
        return None

    clause_usages = ClauseUsage.objects.filter(
        agreement=agreement, section=section, is_active=True
    ).select_related("clause", "clause_version")

    clauses = []
    for cu in clause_usages:
        body = cu.custom_body_text or ""
        if not body and cu.clause_version:
            body = cu.clause_version.body_text or ""
        clauses.append({
            "clause_title": cu.clause.title,
            "clause_id": cu.clause.clause_id,
            "version": cu.clause_version.version_label if cu.clause_version else "",
            "body_text": body,
        })

    children_qs = section.children.filter(is_active=True).order_by("sort_order", "name")
    child_sections = []
    for child in children_qs:
        child_clauses = ClauseUsage.objects.filter(
            agreement=agreement, section=child, is_active=True
        ).select_related("clause", "clause_version")
        child_clause_list = []
        for cu in child_clauses:
            body = cu.custom_body_text or ""
            if not body and cu.clause_version:
                body = cu.clause_version.body_text or ""
            child_clause_list.append({
                "clause_title": cu.clause.title,
                "clause_id": cu.clause.clause_id,
                "version": cu.clause_version.version_label if cu.clause_version else "",
                "body_text": body,
            })
        child_sections.append({
            "id": child.id,
            "name": child.name,
            "description": child.description,
            "clauses": child_clause_list,
            "children": [],
        })

    return {
        "id": section.id,
        "name": section.name,
        "description": section.description,
        "clauses": clauses,
        "children": child_sections,
        "structure_name": section.structure.name,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_agreement_context(agreement, section_id=None):
    """
    Build the full template context dict for an agreement PDF/HTML.

    If *section_id* is provided, only that section's data is included.
    """
    from apps.leases.models import Agreement

    agreement = (
        Agreement.objects.select_related(
            "tenant", "site", "primary_contact", "scope", "structure",
        ).prefetch_related(
            "unit_allocations",
            "unit_allocations__site",
            "unit_allocations__tower",
            "unit_allocations__floor",
            "unit_allocations__unit",
        ).get(pk=agreement.pk)
    )

    allocations, total_area = _get_allocations(agreement)
    hierarchy = _get_scope_hierarchy(agreement)
    landlord_name = hierarchy["entity_name"] or hierarchy["company_name"] or hierarchy["org_name"] or "[Landlord]"

    ctx = {
        "agreement": agreement,
        "lease_id": agreement.lease_id,
        "version": agreement.version_number,
        "status": agreement.status,
        "agreement_type": agreement.get_agreement_type_display(),
        "is_draft": agreement.status == Agreement.Status.DRAFT,
        "generated_date": date.today().strftime("%d %B %Y"),

        # Parties
        "landlord": {
            "name": landlord_name,
            "entity": hierarchy["entity_name"],
            "company": hierarchy["company_name"],
            "org": hierarchy["org_name"],
            "address": hierarchy["org_address"],
            "city": hierarchy["org_city"],
            "state": hierarchy["org_state"],
            "country": hierarchy["org_country"],
            "registration": hierarchy["org_registration"],
            "tax_id": hierarchy["org_tax_id"],
        },
        "tenant": _get_tenant_info(agreement),
        "site": _get_site_info(agreement),
        "landlord_entity_override": agreement.landlord_entity,

        # Allocations
        "allocations": allocations,
        "total_area": _fmt_area(total_area),
        "total_area_raw": total_area,

        # Terms
        "term_dates": _get_term_dates(agreement),
        "financials": _get_financials(agreement, total_area),
        "escalation": _get_escalation(agreement),
        "cam": _get_cam(agreement),
        "deposit": _get_deposit(agreement),
        "rent_free": _get_rent_free(agreement),

        # Legal clauses
        "termination": _get_termination(agreement),
        "renewal": _get_renewal(agreement),
        "insurance": _get_insurance(agreement),
        "dispute": _get_dispute(agreement),
        "sublet_signage": _get_sublet_signage(agreement),
        "exclusivity": _get_exclusivity(agreement),
    }

    if section_id:
        section_data = _get_single_section_data(agreement, section_id)
        ctx["single_section"] = section_data
        ctx["structure_name"] = section_data["structure_name"] if section_data else None
        ctx["sections"] = [section_data] if section_data else []
    else:
        structure_name, sections = _get_sections_with_clauses(agreement)
        ctx["structure_name"] = structure_name
        ctx["sections"] = sections

    return ctx


def render_agreement_html(agreement, section_id=None):
    """Render the agreement as HTML string."""
    ctx = build_agreement_context(agreement, section_id=section_id)
    template = "leases/section_pdf.html" if section_id else "leases/agreement_pdf.html"
    return render_to_string(template, ctx)


def render_agreement_pdf(agreement, section_id=None):
    """Render the agreement as a PDF bytes buffer."""
    from xhtml2pdf import pisa

    html = render_agreement_html(agreement, section_id=section_id)
    buf = BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=buf, encoding="utf-8")
    if pisa_status.err:
        raise RuntimeError(f"PDF generation failed with {pisa_status.err} errors")
    buf.seek(0)
    return buf
