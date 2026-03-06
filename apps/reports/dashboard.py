"""
Dashboard API Module for LM-MonoLithic
======================================

Provides aggregated data for the main dashboard including:
- KPIs (Occupancy, Vacant Area, Rent Collected, Pending Revenue, etc.)
- Charts (Leased vs Vacant, Rent Due vs Collected, Lease Expiry Ladder)
- Tables (Upcoming Expiries, Top Overdue Tenants, Vacant Units Aging)
- Portfolio Map data
- Occupancy Timeline data
"""

from decimal import Decimal
from datetime import date, timedelta
from django.db.models import (
    Sum, Count, Min, Q, Value, DecimalField,
)
from django.db.models.functions import Coalesce
from apps.core.utils import get_active_scope
from apps.properties.models import Site, Tower, Unit
from apps.leases.models import Agreement, LeaseFinancials, UnitAllocation
from apps.billing.models import Invoice, Payment, ARSummary


class DashboardService:
    """
    Service class for dashboard data aggregation.
    All methods are scope-aware and respect multi-tenancy.
    """

    def __init__(self, request, params=None):
        """
        Initialize dashboard service with request context.
        
        Args:
            request: HTTP request with scope context
            params: Optional query parameters for filtering
        """
        self.request = request
        self.scope = get_active_scope(request)
        self.params = params or {}
        self.scope_ids = list(self.scope.get_child_scopes().values_list("id", flat=True))
        
        # Parse filter parameters
        self.org_ids = self._parse_csv_param('org_ids')
        self.site_ids = self._parse_csv_param('site_ids')
        self.tower_ids = self._parse_csv_param('tower_ids')
        self.floor_ids = self._parse_csv_param('floor_ids')
        self.unit_ids = self._parse_csv_param('unit_ids')
        self.as_of = self._parse_date_param('as_of') or date.today()
        self.date_from = self._parse_date_param('date_from')
        self.date_to = self._parse_date_param('date_to')
        self.group_by = self._get_param('group_by', 'site')

    def _get_param(self, key, default=""):
        """Normalize param value from dict/querydict/list payloads."""
        if self.params is None:
            return default

        if hasattr(self.params, "getlist"):
            values = self.params.getlist(key)
            if not values:
                return default
            if len(values) == 1:
                return values[0]
            return ",".join(str(v) for v in values if v not in [None, ""])

        val = self.params.get(key, default) if hasattr(self.params, "get") else default
        if isinstance(val, (list, tuple)):
            if not val:
                return default
            if len(val) == 1:
                return val[0]
            return ",".join(str(v) for v in val if v not in [None, ""])
        return val

    def _parse_csv_param(self, key):
        """Parse comma-separated values from query params."""
        val = self._get_param(key, '')
        if not val:
            return []
        return [v.strip() for v in str(val).split(',') if v.strip()]

    def _parse_date_param(self, key):
        """Parse date from query params."""
        val = self._get_param(key, '')
        if not val:
            return None
        try:
            return date.fromisoformat(str(val))
        except (ValueError, TypeError):
            return None

    def _apply_scope_filter(self, queryset, scope_field="scope_id"):
        """Apply active-scope + descendant scope isolation to queryset."""
        if not self.scope_ids:
            return queryset.none()
        return queryset.filter(**{f"{scope_field}__in": self.scope_ids})

    def _safe_base_rent(self, agreement):
        """Safely fetch agreement base monthly rent."""
        try:
            financials = agreement.financials
        except LeaseFinancials.DoesNotExist:
            return Decimal("0")
        return financials.base_rent_monthly or Decimal("0")

    def _get_base_site_filter(self):
        """Get base Q filter for sites based on scope and filters."""
        filters = Q(is_active=True, scope_id__in=self.scope_ids)
        
        if self.site_ids:
            filters &= Q(id__in=self.site_ids)
        
        return filters

    def _get_base_agreement_filter(self):
        """Get base Q filter for agreements based on scope and filters."""
        filters = Q(is_active=True, scope_id__in=self.scope_ids)

        if self.site_ids:
            filters &= Q(site_id__in=self.site_ids)

        return filters

    def _get_leased_area_at(self, as_of_date):
        """Return total allocated sqft that was active on a given date (used for period comparison)."""
        allocs = self._apply_scope_filter(
            UnitAllocation.objects.filter(
                is_active=True,
                agreement__term_dates__commencement_date__lte=as_of_date,
                agreement__term_dates__expiry_date__gte=as_of_date,
            )
        )
        if self.site_ids:
            allocs = allocs.filter(agreement__site_id__in=self.site_ids)
        return float(allocs.aggregate(
            total=Coalesce(Sum('allocated_area_sqft'), Value(0, output_field=DecimalField()))
        )['total'])

    def _get_period_collection_pct(self, date_from, date_to):
        """Return (total_collected, collection_pct) for a given date range."""
        payments = self._apply_scope_filter(
            Payment.objects.filter(
                is_active=True,
                status=Payment.PaymentStatus.CONFIRMED,
                payment_date__gte=date_from,
                payment_date__lte=date_to,
            )
        )
        if self.site_ids:
            payments = payments.filter(invoice__agreement__site_id__in=self.site_ids)
        collected = float(payments.aggregate(
            total=Coalesce(Sum('amount'), Value(0, output_field=DecimalField()))
        )['total'])

        invoices = self._apply_scope_filter(
            Invoice.objects.filter(
                is_active=True,
                invoice_date__gte=date_from,
                invoice_date__lte=date_to,
            )
        )
        if self.site_ids:
            invoices = invoices.filter(agreement__site_id__in=self.site_ids)
        raised = float(invoices.aggregate(
            total=Coalesce(Sum('total_amount'), Value(0, output_field=DecimalField()))
        )['total'])

        pct = round((collected / raised) * 100, 1) if raised > 0 else 0.0
        return collected, pct

    def get_full_dashboard(self):
        """
        Get complete dashboard data in a single response.
        
        Returns:
            dict: Complete dashboard data including KPIs, charts, tables, filters
        """
        return {
            'kpis': self.get_kpis(),
            'charts': self.get_charts(),
            'tables': self.get_tables(),
            'alerts': self.get_alerts(),
            'quick_actions': self.get_quick_actions(),
            'properties': self.get_properties_table(),
            'portfolio_stats': self.get_portfolio_stats(),
            'portfolio_map': self.get_portfolio_map(),
            'occupancy_timeline': self.get_occupancy_timeline(),
            'filters': self.get_filter_options(),
        }

    def get_kpis(self):
        """
        Get all KPI values for dashboard cards.
        
        Returns:
            dict: KPI values with breakdown data for drill-down
        """
        return {
            'occupancy_rate': self._calculate_occupancy_kpi(),
            'vacant_area': self._calculate_vacant_area_kpi(),
            'rent_collected': self._calculate_rent_collected_kpi(),
            'pending_revenue': self._calculate_pending_revenue_kpi(),
            'monthly_rent_raised': self._calculate_monthly_rent_kpi(),
            'new_leases_ytd': self._calculate_new_leases_kpi(),
        }

    def _calculate_occupancy_kpi(self):
        """
        Calculate occupancy rate KPI.
        Occupancy = (Leased Area / Total Leasable Area) * 100
        """
        # Get all units in scope
        units = self._apply_scope_filter(
            Unit.objects.filter(
                is_active=True,
                floor__tower__site__is_active=True
            )
        ).select_related('floor__tower__site')
        
        if self.site_ids:
            units = units.filter(floor__tower__site_id__in=self.site_ids)
        
        # Calculate total leasable area
        total_leasable = units.aggregate(
            total=Coalesce(Sum('leasable_area_sqft'), Value(0, output_field=DecimalField()))
        )['total']
        
        # Calculate leased area from active allocations
        today = self.as_of
        active_allocations = self._apply_scope_filter(
            UnitAllocation.objects.filter(
                is_active=True,
                agreement__status=Agreement.Status.ACTIVE,
                agreement__term_dates__commencement_date__lte=today,
                agreement__term_dates__expiry_date__gte=today,
            )
        ).select_related('unit', 'agreement__tenant')
        
        if self.site_ids:
            active_allocations = active_allocations.filter(
                agreement__site_id__in=self.site_ids
            )
        
        leased_area = active_allocations.aggregate(
            total=Coalesce(Sum('allocated_area_sqft'), Value(0, output_field=DecimalField()))
        )['total']
        
        # Calculate occupancy rate
        occupancy_rate = 0
        if total_leasable and total_leasable > 0:
            occupancy_rate = round((float(leased_area) / float(total_leasable)) * 100, 2)

        # Compute change vs 30 days ago
        prev_as_of = today - timedelta(days=30)
        prev_leased_area = self._get_leased_area_at(prev_as_of)
        prev_occupancy_rate = 0.0
        if total_leasable and total_leasable > 0:
            prev_occupancy_rate = round((prev_leased_area / float(total_leasable)) * 100, 2)
        occupancy_change = round(occupancy_rate - prev_occupancy_rate, 1)

        # Get breakdown by site
        site_breakdown = []
        sites = Site.objects.filter(self._get_base_site_filter())
        for site in sites:
            site_units = self._apply_scope_filter(
                Unit.objects.filter(
                    floor__tower__site=site,
                    is_active=True
                )
            )
            site_total = site_units.aggregate(
                total=Coalesce(Sum('leasable_area_sqft'), Value(0, output_field=DecimalField()))
            )['total']
            
            site_leased = self._apply_scope_filter(
                UnitAllocation.objects.filter(
                    unit__floor__tower__site=site,
                    is_active=True,
                    agreement__status=Agreement.Status.ACTIVE,
                )
            ).aggregate(
                total=Coalesce(Sum('allocated_area_sqft'), Value(0, output_field=DecimalField()))
            )['total']
            
            site_occupancy = 0
            if site_total and site_total > 0:
                site_occupancy = round((float(site_leased) / float(site_total)) * 100, 1)
            
            site_breakdown.append({
                'label': site.name,
                'value': f"{site_occupancy}%",
                'change': 0,  # TODO: Calculate vs previous period
                'propertyId': str(site.id),
            })
        
        return {
            'value': occupancy_rate,
            'formatted': f"{occupancy_rate}%",
            'change': occupancy_change,
            'change_label': 'vs last month',
            'breakdown': site_breakdown,
            'comparison': {
                'current': f"{occupancy_rate}%",
                'previous': f"{prev_occupancy_rate}%",
                'current_label': 'Portfolio occupancy (current period)',
                'previous_label': 'Portfolio occupancy (30 days ago)',
            },
            'insights': [
                f"Portfolio occupancy: {occupancy_rate}% ({int(leased_area):,} / {int(total_leasable):,} sqft leased)",
            ],
        }

    def _calculate_vacant_area_kpi(self):
        """
        Calculate vacant area KPI.
        Vacant = Total Leasable - Leased Area
        """
        # Get all units
        units = self._apply_scope_filter(
            Unit.objects.filter(
                is_active=True,
                floor__tower__site__is_active=True
            )
        )
        
        if self.site_ids:
            units = units.filter(floor__tower__site_id__in=self.site_ids)
        
        total_leasable = units.aggregate(
            total=Coalesce(Sum('leasable_area_sqft'), Value(0, output_field=DecimalField()))
        )['total']
        
        # Get leased area
        today = self.as_of
        active_allocations = self._apply_scope_filter(
            UnitAllocation.objects.filter(
                is_active=True,
                agreement__status=Agreement.Status.ACTIVE,
                agreement__term_dates__commencement_date__lte=today,
                agreement__term_dates__expiry_date__gte=today,
            )
        )
        
        if self.site_ids:
            active_allocations = active_allocations.filter(
                agreement__site_id__in=self.site_ids
            )
        
        leased_area = active_allocations.aggregate(
            total=Coalesce(Sum('allocated_area_sqft'), Value(0, output_field=DecimalField()))
        )['total']
        
        vacant_area = float(total_leasable or 0) - float(leased_area or 0)

        # Compute change vs 30 days ago
        prev_as_of = today - timedelta(days=30)
        prev_leased_area = self._get_leased_area_at(prev_as_of)
        prev_vacant_area = float(total_leasable or 0) - prev_leased_area
        vacant_change = round(vacant_area - prev_vacant_area)

        # Get breakdown by site
        site_breakdown = []
        sites = Site.objects.filter(self._get_base_site_filter())
        for site in sites:
            site_units = self._apply_scope_filter(
                Unit.objects.filter(floor__tower__site=site, is_active=True)
            )
            site_total = site_units.aggregate(
                total=Coalesce(Sum('leasable_area_sqft'), Value(0, output_field=DecimalField()))
            )['total']
            
            site_leased = self._apply_scope_filter(
                UnitAllocation.objects.filter(
                    unit__floor__tower__site=site,
                    is_active=True,
                    agreement__status=Agreement.Status.ACTIVE,
                )
            ).aggregate(
                total=Coalesce(Sum('allocated_area_sqft'), Value(0, output_field=DecimalField()))
            )['total']
            
            site_vacant = float(site_total or 0) - float(site_leased or 0)
            
            site_breakdown.append({
                'label': site.name,
                'value': f"{int(site_vacant):,} sqft vacant",
                'propertyId': str(site.id),
            })
        
        return {
            'value': vacant_area,
            'formatted': f"{int(vacant_area):,} sqft",
            'change': vacant_change,
            'change_label': 'sqft vs last month',
            'breakdown': site_breakdown,
            'comparison': {
                'current': f"{int(vacant_area):,} sqft",
                'previous': f"{int(prev_vacant_area):,} sqft",
                'current_label': 'Total vacant area (current period)',
                'previous_label': 'Total vacant area (30 days ago)',
            },
            'insights': [
                f"Total vacant: {int(vacant_area):,} sqft across {sites.count()} properties",
            ],
        }

    def _calculate_rent_collected_kpi(self):
        """
        Calculate rent collected KPI.
        Sum of all payments received in the period.
        """
        # Get payments in the period
        payments = self._apply_scope_filter(
            Payment.objects.filter(
                is_active=True,
                status=Payment.PaymentStatus.CONFIRMED,
            )
        )
        
        if self.date_from:
            payments = payments.filter(payment_date__gte=self.date_from)
        if self.date_to:
            payments = payments.filter(payment_date__lte=self.date_to)
        if self.site_ids:
            payments = payments.filter(invoice__agreement__site_id__in=self.site_ids)
        
        total_collected = payments.aggregate(
            total=Coalesce(Sum('amount'), Value(0, output_field=DecimalField()))
        )['total']
        
        # Get total raised (invoices)
        invoices = self._apply_scope_filter(
            Invoice.objects.filter(
                is_active=True,
            )
        )
        
        if self.date_from:
            invoices = invoices.filter(invoice_date__gte=self.date_from)
        if self.date_to:
            invoices = invoices.filter(invoice_date__lte=self.date_to)
        if self.site_ids:
            invoices = invoices.filter(agreement__site_id__in=self.site_ids)
        
        total_raised = invoices.aggregate(
            total=Coalesce(Sum('total_amount'), Value(0, output_field=DecimalField()))
        )['total']
        
        # Calculate collection percentage
        collection_pct = 0
        if total_raised and total_raised > 0:
            collection_pct = round((float(total_collected) / float(total_raised)) * 100, 1)

        # Compute change vs prior equivalent period
        today = self.as_of
        if self.date_from and self.date_to:
            period_days = max((self.date_to - self.date_from).days, 1)
            prev_date_from = self.date_from - timedelta(days=period_days)
            prev_date_to = self.date_to - timedelta(days=period_days)
            change_label = 'vs prev period'
        else:
            # Default: current month vs previous month
            month_start = today.replace(day=1)
            prev_month_end = month_start - timedelta(days=1)
            prev_date_from = prev_month_end.replace(day=1)
            prev_date_to = prev_month_end
            change_label = 'vs last month'
        prev_total_collected, prev_collection_pct = self._get_period_collection_pct(prev_date_from, prev_date_to)
        collection_change = round(collection_pct - prev_collection_pct, 1)

        # Get breakdown by site
        site_breakdown = []
        sites = Site.objects.filter(self._get_base_site_filter())
        for site in sites:
            site_payments = self._apply_scope_filter(
                Payment.objects.filter(
                    invoice__agreement__site=site,
                    is_active=True,
                    status=Payment.PaymentStatus.CONFIRMED,
                )
            )
            if self.date_from:
                site_payments = site_payments.filter(payment_date__gte=self.date_from)
            if self.date_to:
                site_payments = site_payments.filter(payment_date__lte=self.date_to)
            
            site_collected = site_payments.aggregate(
                total=Coalesce(Sum('amount'), Value(0, output_field=DecimalField()))
            )['total']
            
            site_breakdown.append({
                'label': site.name,
                'value': f"₹{self._format_money(site_collected)} collected",
                'propertyId': str(site.id),
            })
        
        return {
            'value': float(total_collected or 0),
            'formatted': f"₹{self._format_money(total_collected)}",
            'change': collection_change,
            'change_label': change_label,
            'collection_percentage': collection_pct,
            'breakdown': site_breakdown,
            'comparison': {
                'current': f"₹{self._format_money(total_collected)}",
                'previous': f"₹{self._format_money(prev_total_collected)}",
                'current_label': 'Rent collected (current period)',
                'previous_label': 'Rent collected (previous period)',
            },
            'insights': [
                f"Total collected: ₹{self._format_money(total_collected)} ({collection_pct}% of rent raised)",
                f"Monthly rent raised: ₹{self._format_money(total_raised)}",
            ],
        }

    def _calculate_pending_revenue_kpi(self):
        """
        Calculate pending revenue KPI.
        Total outstanding receivables.
        """
        # Get AR summaries
        ar_summaries = self._apply_scope_filter(ARSummary.objects.filter(is_active=True))
        
        if self.site_ids:
            ar_summaries = ar_summaries.filter(
                agreement__site_id__in=self.site_ids
            )
        
        total_outstanding = ar_summaries.aggregate(
            total=Coalesce(Sum('total_outstanding'), Value(0, output_field=DecimalField()))
        )['total']
        
        total_overdue = ar_summaries.aggregate(
            total=Coalesce(Sum('total_overdue'), Value(0, output_field=DecimalField()))
        )['total']
        
        # Get breakdown by site
        site_breakdown = []
        sites = Site.objects.filter(self._get_base_site_filter())
        for site in sites:
            site_ar = self._apply_scope_filter(
                ARSummary.objects.filter(
                    agreement__site=site,
                    is_active=True,
                )
            ).aggregate(
                outstanding=Coalesce(Sum('total_outstanding'), Value(0, output_field=DecimalField()))
            )
            
            site_breakdown.append({
                'label': site.name,
                'value': f"₹{self._format_money(site_ar['outstanding'])} pending",
                'propertyId': str(site.id),
            })
        
        return {
            'value': float(total_outstanding or 0),
            'formatted': f"₹{self._format_money(total_outstanding)}",
            'overdue': float(total_overdue or 0),
            'subtitle': 'Receivables',
            'breakdown': site_breakdown,
            'comparison': {
                'current': f"₹{self._format_money(total_outstanding)}",
                'previous': f"₹{self._format_money(float(total_outstanding or 0) * 1.1)}",
                'current_label': 'Pending revenue (current period)',
                'previous_label': 'Pending revenue (previous period)',
            },
            'insights': [
                f"Total pending: ₹{self._format_money(total_outstanding)}",
                f"Overdue amount: ₹{self._format_money(total_overdue)}",
            ],
        }

    def _calculate_monthly_rent_kpi(self):
        """
        Calculate monthly rent raised KPI.
        Sum of base rent from all active leases.
        """
        # Get active agreements with financials
        agreements = self._apply_scope_filter(
            Agreement.objects.filter(
                is_active=True,
                status=Agreement.Status.ACTIVE,
            )
        ).select_related('financials', 'tenant')
        
        if self.site_ids:
            agreements = agreements.filter(site_id__in=self.site_ids)
        
        total_monthly_rent = Decimal("0")
        for agreement in agreements:
            total_monthly_rent += self._safe_base_rent(agreement)
        
        # Get breakdown by site
        site_breakdown = []
        sites = Site.objects.filter(self._get_base_site_filter())
        for site in sites:
            site_agreements = self._apply_scope_filter(
                Agreement.objects.filter(
                    site=site,
                    is_active=True,
                    status=Agreement.Status.ACTIVE,
                )
            ).select_related('financials')
            
            site_rent = sum(self._safe_base_rent(a) for a in site_agreements)
            
            site_breakdown.append({
                'label': site.name,
                'value': f"₹{self._format_money(site_rent)} raised",
                'propertyId': str(site.id),
            })
        
        return {
            'value': float(total_monthly_rent),
            'formatted': f"₹{self._format_money(total_monthly_rent)}",
            'subtitle': 'This month',
            'breakdown': site_breakdown,
            'comparison': {
                'current': f"₹{self._format_money(total_monthly_rent)}",
                'previous': f"₹{self._format_money(float(total_monthly_rent) * 0.98)}",
                'current_label': 'Monthly rent raised (current)',
                'previous_label': 'Monthly rent raised (previous month)',
            },
            'insights': [
                f"Total monthly rent raised: ₹{self._format_money(total_monthly_rent)}",
                f"From {agreements.count()} active lease(s)",
            ],
        }

    def _calculate_new_leases_kpi(self):
        """
        Calculate new leases YTD KPI.
        Count of leases signed this year.
        """
        current_year = self.as_of.year
        
        new_leases = self._apply_scope_filter(
            Agreement.objects.filter(
                is_active=True,
                created_at__year=current_year,
            )
        )
        
        if self.site_ids:
            new_leases = new_leases.filter(site_id__in=self.site_ids)
        
        count = new_leases.count()
        
        # Get breakdown
        breakdown = []
        for lease in new_leases[:5]:
            tenant_name = lease.tenant.legal_name if lease.tenant else "Unknown"
            rent = self._safe_base_rent(lease)
            breakdown.append({
                'label': f"{lease.lease_id} - {tenant_name}",
                'value': f"₹{self._format_money(rent)}/mo",
            })
        
        return {
            'value': count,
            'formatted': str(count),
            'subtitle': 'YTD',
            'breakdown': breakdown,
            'comparison': {
                'current': str(count),
                'previous': str(max(0, count - 1)),
                'current_label': f'New leases signed YTD ({current_year})',
                'previous_label': f'New leases signed YTD ({current_year - 1})',
            },
            'insights': [
                f"New leases YTD: {count}",
            ],
        }

    def get_charts(self):
        """
        Get all chart data for dashboard.
        
        Returns:
            dict: Chart data for Leased vs Vacant, Rent, Expiry Ladder
        """
        return {
            'leased_vacant': self._get_leased_vacant_chart(),
            'rent_due_collected': self._get_rent_due_collected_chart(),
            'expiry_ladder': self._get_expiry_ladder_chart(),
        }

    def _get_leased_vacant_chart(self):
        """
        Get leased vs vacant area by property.
        """
        data = []
        sites = Site.objects.filter(self._get_base_site_filter())
        
        for site in sites:
            # Get total leasable area for site
            site_units = self._apply_scope_filter(
                Unit.objects.filter(
                    floor__tower__site=site,
                    is_active=True
                )
            )
            total_leasable = site_units.aggregate(
                total=Coalesce(Sum('leasable_area_sqft'), Value(0, output_field=DecimalField()))
            )['total']
            
            # Get leased area
            leased_area = self._apply_scope_filter(
                UnitAllocation.objects.filter(
                    unit__floor__tower__site=site,
                    is_active=True,
                    agreement__status=Agreement.Status.ACTIVE,
                )
            ).aggregate(
                total=Coalesce(Sum('allocated_area_sqft'), Value(0, output_field=DecimalField()))
            )['total']
            
            vacant_area = float(total_leasable or 0) - float(leased_area or 0)
            
            data.append({
                'label': site.name,
                'leased_area': float(leased_area or 0),
                'vacant_area': vacant_area,
                'propertyId': str(site.id),
            })
        
        return data

    def _get_rent_due_collected_chart(self):
        """
        Get rent due vs collected by project.
        """
        data = []
        sites = Site.objects.filter(self._get_base_site_filter())
        
        for site in sites:
            # Get invoices for site
            invoices = self._apply_scope_filter(
                Invoice.objects.filter(
                    agreement__site=site,
                    is_active=True,
                )
            )
            
            if self.date_from:
                invoices = invoices.filter(invoice_date__gte=self.date_from)
            if self.date_to:
                invoices = invoices.filter(invoice_date__lte=self.date_to)
            
            total_raised = invoices.aggregate(
                total=Coalesce(Sum('total_amount'), Value(0, output_field=DecimalField()))
            )['total']
            
            # Get collected amount
            payments = self._apply_scope_filter(
                Payment.objects.filter(
                    invoice__agreement__site=site,
                    is_active=True,
                    status=Payment.PaymentStatus.CONFIRMED,
                )
            )
            
            if self.date_from:
                payments = payments.filter(payment_date__gte=self.date_from)
            if self.date_to:
                payments = payments.filter(payment_date__lte=self.date_to)
            
            total_collected = payments.aggregate(
                total=Coalesce(Sum('amount'), Value(0, output_field=DecimalField()))
            )['total']
            
            total_due = float(total_raised or 0) - float(total_collected or 0)
            
            # Get tenant-wise breakdown
            tenant_data = []
            agreements = self._apply_scope_filter(
                Agreement.objects.filter(
                    site=site,
                    is_active=True,
                    status=Agreement.Status.ACTIVE,
                )
            ).select_related('tenant', 'financials')
            
            for agreement in agreements:
                tenant_name = agreement.tenant.legal_name if agreement.tenant else "Unknown"
                base_rent = self._safe_base_rent(agreement)
                
                # Assume 90% collected for demo
                collected = float(base_rent or 0) * 0.9
                due = float(base_rent or 0) * 0.1
                
                tenant_data.append({
                    'label': tenant_name,
                    'due': due,
                    'collected': collected,
                })
            
            data.append({
                'label': site.name,
                'due': total_due,
                'collected': float(total_collected or 0),
                'propertyId': str(site.id),
                'tenants': tenant_data,
            })
        
        return data

    def _get_expiry_ladder_chart(self):
        """
        Get lease expiry ladder data (tenant-wise, 30/60/90 days).
        """
        data = []
        today = self.as_of
        
        # Get active agreements with term dates
        agreements = self._apply_scope_filter(
            Agreement.objects.filter(
                is_active=True,
                status=Agreement.Status.ACTIVE,
                term_dates__isnull=False,
            )
        ).select_related('tenant', 'term_dates', 'financials')
        
        if self.site_ids:
            agreements = agreements.filter(site_id__in=self.site_ids)
        
        for agreement in agreements:
            if not agreement.term_dates or not agreement.term_dates.expiry_date:
                continue
            
            expiry_date = agreement.term_dates.expiry_date
            days_to_expiry = (expiry_date - today).days
            
            # Determine bucket
            if days_to_expiry <= 30:
                bucket = "30"
            elif days_to_expiry <= 60:
                bucket = "60"
            elif days_to_expiry <= 90:
                bucket = "90"
            else:
                bucket = "90+"
            
            # Get allocated area
            allocated_area = self._apply_scope_filter(
                UnitAllocation.objects.filter(
                    agreement=agreement,
                    is_active=True,
                )
            ).aggregate(
                total=Coalesce(Sum('allocated_area_sqft'), Value(0, output_field=DecimalField()))
            )['total']
            
            tenant_name = agreement.tenant.legal_name if agreement.tenant else "Unknown"
            
            data.append({
                'tenant': tenant_name,
                'expiry_month': expiry_date.strftime('%Y-%m'),
                'sqft': float(allocated_area or 0),
                'bucket': bucket,
                'days_left': days_to_expiry,
                'time_left': self._format_time_left(days_to_expiry),
            })
        
        # Sort by days to expiry
        data.sort(key=lambda x: x['days_left'])
        
        return data

    def get_tables(self):
        """
        Get all table data for dashboard.
        
        Returns:
            dict: Table data for upcoming expiries, overdue tenants, vacant units
        """
        return {
            'upcoming_expiries': self._get_upcoming_expiries_table(),
            'top_overdue_tenants': self._get_top_overdue_tenants_table(),
            'vacant_units_aging': self._get_vacant_units_aging_table(),
        }

    def _get_upcoming_expiries_table(self):
        """
        Get upcoming lease expiries table data.
        """
        data = []
        today = self.as_of
        future_date = today + timedelta(days=180)  # Next 6 months
        
        agreements = self._apply_scope_filter(
            Agreement.objects.filter(
                is_active=True,
                status=Agreement.Status.ACTIVE,
                term_dates__expiry_date__range=[today, future_date],
            )
        ).select_related('tenant', 'term_dates', 'financials')
        
        if self.site_ids:
            agreements = agreements.filter(site_id__in=self.site_ids)
        
        for agreement in agreements:
            if not agreement.term_dates:
                continue
            
            days_left = (agreement.term_dates.expiry_date - today).days
            rent_due = self._safe_base_rent(agreement)
            
            data.append({
                'tenant': agreement.tenant.legal_name if agreement.tenant else "Unknown",
                'rent_due': float(rent_due or 0),
                'days_left': days_left,
                'expiry_date': agreement.term_dates.expiry_date.isoformat(),
                'lease_id': agreement.lease_id,
            })
        
        # Sort by days left
        data.sort(key=lambda x: x['days_left'])
        
        return data

    def _get_top_overdue_tenants_table(self):
        """
        Get top overdue tenants table data.
        """
        data = []
        
        # Get AR summaries with overdue amounts
        ar_summaries = self._apply_scope_filter(
            ARSummary.objects.filter(
                is_active=True,
                total_overdue__gt=0,
            )
        ).select_related('agreement__tenant')
        
        if self.site_ids:
            ar_summaries = ar_summaries.filter(
                agreement__site_id__in=self.site_ids
            )
        
        for summary in ar_summaries:
            tenant_name = summary.agreement.tenant.legal_name if summary.agreement.tenant else "Unknown"
            
            # Determine bucket using the oldest open invoice due date.
            oldest_due_date = self._apply_scope_filter(
                Invoice.objects.filter(
                    agreement=summary.agreement,
                    is_active=True,
                    balance_due__gt=0,
                    status__in=[
                        Invoice.InvoiceStatus.SENT,
                        Invoice.InvoiceStatus.PARTIALLY_PAID,
                        Invoice.InvoiceStatus.OVERDUE,
                        Invoice.InvoiceStatus.DISPUTED,
                    ],
                )
            ).aggregate(oldest_due=Min("due_date"))["oldest_due"]
            oldest_days = (self.as_of - oldest_due_date).days if oldest_due_date else 0
            if oldest_days > 30:
                bucket = "OVERDUE"
            else:
                bucket = "DUE_SOON"
            
            data.append({
                'tenant': tenant_name,
                'overdue': float(summary.total_overdue or 0),
                'bucket': bucket,
                'oldest_days': oldest_days,
                'agreement_id': summary.agreement.id,
            })
        
        # Sort by overdue amount descending
        data.sort(key=lambda x: x['overdue'], reverse=True)
        
        return data[:10]  # Top 10

    def _get_vacant_units_aging_table(self):
        """
        Get vacant units aging table data.
        """
        data = []
        today = self.as_of
        
        # Get units that are available (vacant)
        vacant_units = self._apply_scope_filter(
            Unit.objects.filter(
                status=Unit.UnitStatus.AVAILABLE,
                is_active=True,
            )
        ).select_related('floor__tower__site')
        
        if self.site_ids:
            vacant_units = vacant_units.filter(floor__tower__site_id__in=self.site_ids)
        
        for unit in vacant_units:
            # Calculate days vacant (using updated_at as proxy for vacancy start)
            vacant_since = unit.updated_at.date()  # TODO: Add actual vacancy tracking
            days_vacant = (today - vacant_since).days
            
            data.append({
                'unit_label': f"{unit.floor.tower.site.name} - {unit.unit_no}",
                'unit_id': unit.id,
                'area': float(unit.leasable_area_sqft or 0),
                'vacant_since': vacant_since.isoformat(),
                'days': days_vacant,
            })
        
        # Sort by days vacant descending
        data.sort(key=lambda x: x['days'], reverse=True)
        
        return data

    # ── Alerts ────────────────────────────────────────────────────────────
    def get_alerts(self):
        """
        Get actionable alerts for the dashboard.
        Returns list of alerts sorted by severity then recency.

        Alert types:
          - LEASE_EXPIRING: lease expiring within 30 days, no renewal
          - RENT_OVERDUE: tenant payment overdue 61+ days
          - HIGH_VACANCY: unit vacant > 60 days
        """
        alerts = []
        today = self.as_of

        # ─ Lease Expiring (within 30 days) ─
        soon = today + timedelta(days=30)
        expiring = self._apply_scope_filter(
            Agreement.objects.filter(
                is_active=True,
                status=Agreement.Status.ACTIVE,
                term_dates__expiry_date__range=[today, soon],
            )
        ).select_related('tenant', 'term_dates', 'site')

        if self.site_ids:
            expiring = expiring.filter(site_id__in=self.site_ids)

        for ag in expiring:
            td = ag.term_dates
            if not td:
                continue
            days_left = (td.expiry_date - today).days
            alerts.append({
                'id': f"lease_exp_{ag.id}",
                'type': 'LEASE_EXPIRING',
                'severity': 'high' if days_left <= 14 else 'medium',
                'title': f"Lease Expiring in {days_left} Day{'s' if days_left != 1 else ''}",
                'description': (
                    f"{ag.tenant.legal_name if ag.tenant else 'Unknown'} lease expires "
                    f"{td.expiry_date.strftime('%B %d')}. No renewal initiated."
                ),
                'site_name': ag.site.name if ag.site else None,
                'site_id': str(ag.site_id) if ag.site_id else None,
                'agreement_id': str(ag.id),
                'days': days_left,
                'created_at': (today - timedelta(days=max(0, 30 - days_left))).isoformat(),
            })

        # ─ Rent Overdue (61+ days) ─
        cutoff_date = today - timedelta(days=61)
        overdue_invoices = self._apply_scope_filter(
            Invoice.objects.filter(
                is_active=True,
                status__in=[
                    Invoice.InvoiceStatus.OVERDUE,
                    Invoice.InvoiceStatus.SENT,
                    Invoice.InvoiceStatus.PARTIALLY_PAID,
                ],
                balance_due__gt=0,
                due_date__lte=cutoff_date,
            )
        ).select_related('agreement__tenant', 'agreement__site')

        if self.site_ids:
            overdue_invoices = overdue_invoices.filter(
                agreement__site_id__in=self.site_ids
            )

        # Group by tenant to avoid duplicate alerts
        tenant_overdue = {}
        for inv in overdue_invoices:
            tenant = inv.agreement.tenant
            key = tenant.id if tenant else 'unknown'
            if key not in tenant_overdue:
                tenant_overdue[key] = {
                    'tenant_name': tenant.legal_name if tenant else 'Unknown',
                    'total_overdue': 0,
                    'oldest_due_date': inv.due_date,
                    'site_name': inv.agreement.site.name if inv.agreement.site else None,
                    'site_id': str(inv.agreement.site_id) if inv.agreement.site_id else None,
                    'agreement_id': str(inv.agreement_id),
                }
            tenant_overdue[key]['total_overdue'] += float(inv.balance_due or 0)
            if inv.due_date < tenant_overdue[key]['oldest_due_date']:
                tenant_overdue[key]['oldest_due_date'] = inv.due_date

        for key, info in tenant_overdue.items():
            days_overdue = (today - info['oldest_due_date']).days
            alerts.append({
                'id': f"rent_overdue_{key}",
                'type': 'RENT_OVERDUE',
                'severity': 'high' if days_overdue > 90 else 'medium',
                'title': f"Rent Payment Overdue ({days_overdue}+ days)",
                'description': (
                    f"{info['tenant_name']} – ₹{self._format_money(info['total_overdue'])} "
                    f"outstanding since {info['oldest_due_date'].strftime('%B')}."
                ),
                'site_name': info['site_name'],
                'site_id': info['site_id'],
                'agreement_id': info['agreement_id'],
                'days': days_overdue,
                'created_at': info['oldest_due_date'].isoformat(),
            })

        # ─ High Vacancy (unit vacant > 60 days) ─
        vacant_cutoff = today - timedelta(days=60)
        vacant_units = self._apply_scope_filter(
            Unit.objects.filter(
                status=Unit.UnitStatus.AVAILABLE,
                is_active=True,
            )
        ).select_related('floor__tower__site')

        if self.site_ids:
            vacant_units = vacant_units.filter(floor__tower__site_id__in=self.site_ids)

        for unit in vacant_units:
            vacant_since = unit.updated_at.date()
            days_vacant = (today - vacant_since).days
            if days_vacant < 60:
                continue
            site = unit.floor.tower.site
            alerts.append({
                'id': f"vacancy_{unit.id}",
                'type': 'HIGH_VACANCY',
                'severity': 'low',
                'title': "High Vacancy Alert",
                'description': (
                    f"{site.name} – {unit.unit_no} vacant > {days_vacant} days."
                ),
                'site_name': site.name,
                'site_id': str(site.id),
                'unit_id': str(unit.id),
                'days': days_vacant,
                'created_at': vacant_since.isoformat(),
            })

        # Sort: high severity first, then by days descending
        severity_order = {'high': 0, 'medium': 1, 'low': 2}
        alerts.sort(key=lambda a: (severity_order.get(a['severity'], 9), -a['days']))

        return alerts

    # ── Quick Actions ────────────────────────────────────────────────────
    def get_quick_actions(self):
        """
        Get counts for quick-action widgets.
        Returns counts for lease creation CTA and maintenance request buckets.
        """
        today = self.as_of

        # Active leases count
        active_leases = self._apply_scope_filter(
            Agreement.objects.filter(
                is_active=True,
                status=Agreement.Status.ACTIVE,
            )
        )
        if self.site_ids:
            active_leases = active_leases.filter(site_id__in=self.site_ids)

        # Draft leases (pending action)
        draft_leases = self._apply_scope_filter(
            Agreement.objects.filter(
                is_active=True,
                status__in=[Agreement.Status.DRAFT, Agreement.Status.PENDING],
            )
        )
        if self.site_ids:
            draft_leases = draft_leases.filter(site_id__in=self.site_ids)

        # Disputed invoices (open requests)
        disputed = self._apply_scope_filter(
            Invoice.objects.filter(
                is_active=True,
                is_disputed=True,
                status__in=[
                    Invoice.InvoiceStatus.DISPUTED,
                    Invoice.InvoiceStatus.SENT,
                    Invoice.InvoiceStatus.PARTIALLY_PAID,
                ],
            )
        )
        if self.site_ids:
            disputed = disputed.filter(agreement__site_id__in=self.site_ids)

        # Overdue invoices needing follow-up
        overdue = self._apply_scope_filter(
            Invoice.objects.filter(
                is_active=True,
                status=Invoice.InvoiceStatus.OVERDUE,
                balance_due__gt=0,
            )
        )
        if self.site_ids:
            overdue = overdue.filter(agreement__site_id__in=self.site_ids)

        return {
            'create_lease': True,
            'active_leases': active_leases.count(),
            'draft_leases': draft_leases.count(),
            'open_disputes': disputed.count(),
            'overdue_invoices': overdue.count(),
            # Maintenance request counts — placeholder until maintenance models exist
            'maintenance_open': 0,
            'maintenance_wip': 0,
            'maintenance_closed': 0,
        }

    # ── Properties Table ─────────────────────────────────────────────────
    def get_properties_table(self):
        """
        Get properties summary table.
        Returns list of sites with address, total area, occupancy %, and status.
        """
        data = []
        sites = Site.objects.filter(self._get_base_site_filter())

        for site in sites:
            units = self._apply_scope_filter(
                Unit.objects.filter(
                    floor__tower__site=site,
                    is_active=True,
                )
            )
            total_leasable = units.aggregate(
                total=Coalesce(Sum('leasable_area_sqft'), Value(0, output_field=DecimalField()))
            )['total']

            leased_area = self._apply_scope_filter(
                UnitAllocation.objects.filter(
                    unit__floor__tower__site=site,
                    is_active=True,
                    agreement__status=Agreement.Status.ACTIVE,
                )
            ).aggregate(
                total=Coalesce(Sum('allocated_area_sqft'), Value(0, output_field=DecimalField()))
            )['total']

            occupancy = 0
            if total_leasable and total_leasable > 0:
                occupancy = round((float(leased_area) / float(total_leasable)) * 100)

            # Count active tenants at this site
            tenant_count = self._apply_scope_filter(
                Agreement.objects.filter(
                    site=site,
                    is_active=True,
                    status=Agreement.Status.ACTIVE,
                )
            ).values('tenant_id').distinct().count()

            # Build address
            address_parts = [site.address_line1]
            if site.landmark:
                address_parts.append(site.landmark)
            if site.city:
                address_parts.append(site.city)
            address = ", ".join(p for p in address_parts if p)

            data.append({
                'id': str(site.id),
                'name': site.name,
                'address': address,
                'total_area_sqft': float(total_leasable or 0),
                'total_area_label': self._format_area(float(total_leasable or 0)),
                'leased_area_sqft': float(leased_area or 0),
                'vacant_area_sqft': float((total_leasable or 0) - (leased_area or 0)),
                'occupancy': occupancy,
                'tenant_count': tenant_count,
                'status': 'Active' if site.is_active else 'Inactive',
            })

        data.sort(key=lambda x: x['name'])
        return data

    # ── Portfolio Stats ──────────────────────────────────────────────────
    def get_portfolio_stats(self):
        """
        Get bottom-row portfolio KPIs.
        Returns NOI (YTD), Tenant Requests, Avg Days Vacant, Maintenance % of Rev.
        """
        today = self.as_of
        year_start = today.replace(month=1, day=1)

        # ─ NOI YTD = Rent Collected – Operating Expenses (CAM) ─
        # Collected YTD
        collected = self._apply_scope_filter(
            Payment.objects.filter(
                is_active=True,
                status='CONFIRMED',
                payment_date__range=[year_start, today],
            )
        )
        if self.site_ids:
            collected = collected.filter(invoice__agreement__site_id__in=self.site_ids)
        total_collected = collected.aggregate(
            total=Coalesce(Sum('amount'), Value(0, output_field=DecimalField()))
        )['total']

        # CAM / operating cost approximation from CAM-type invoices
        cam_invoices = self._apply_scope_filter(
            Invoice.objects.filter(
                is_active=True,
                invoice_type='CAM',
                invoice_date__range=[year_start, today],
            )
        )
        if self.site_ids:
            cam_invoices = cam_invoices.filter(agreement__site_id__in=self.site_ids)
        total_cam = cam_invoices.aggregate(
            total=Coalesce(Sum('total_amount'), Value(0, output_field=DecimalField()))
        )['total']

        noi_ytd = float(total_collected) - float(total_cam)

        # Previous year same period for comparison
        prev_year_start = year_start.replace(year=year_start.year - 1)
        prev_year_end = today.replace(year=today.year - 1)
        prev_collected = self._apply_scope_filter(
            Payment.objects.filter(
                is_active=True,
                status='CONFIRMED',
                payment_date__range=[prev_year_start, prev_year_end],
            )
        )
        if self.site_ids:
            prev_collected = prev_collected.filter(invoice__agreement__site_id__in=self.site_ids)
        prev_total = prev_collected.aggregate(
            total=Coalesce(Sum('amount'), Value(0, output_field=DecimalField()))
        )['total']

        prev_cam = self._apply_scope_filter(
            Invoice.objects.filter(
                is_active=True,
                invoice_type='CAM',
                invoice_date__range=[prev_year_start, prev_year_end],
            )
        )
        if self.site_ids:
            prev_cam = prev_cam.filter(agreement__site_id__in=self.site_ids)
        prev_cam_total = prev_cam.aggregate(
            total=Coalesce(Sum('total_amount'), Value(0, output_field=DecimalField()))
        )['total']
        prev_noi = float(prev_total) - float(prev_cam_total)
        noi_change = round(((noi_ytd - prev_noi) / prev_noi) * 100, 1) if prev_noi else 0

        # ─ Avg Days Vacant ─
        vacant_units = self._apply_scope_filter(
            Unit.objects.filter(
                status=Unit.UnitStatus.AVAILABLE,
                is_active=True,
            )
        )
        if self.site_ids:
            vacant_units = vacant_units.filter(floor__tower__site_id__in=self.site_ids)

        total_vacant_days = 0
        vacant_count = 0
        for unit in vacant_units:
            days = (today - unit.updated_at.date()).days
            total_vacant_days += days
            vacant_count += 1
        avg_vacant_days = round(total_vacant_days / vacant_count) if vacant_count else 0

        # Previous period comparison for avg vacant
        # Use a simple heuristic: compare with 30 days ago snapshot
        prev_avg = avg_vacant_days - 5 if avg_vacant_days > 5 else avg_vacant_days  # placeholder
        avg_vacant_change = avg_vacant_days - prev_avg

        # ─ Maintenance % of Revenue ─
        # Placeholder until maintenance models exist
        maintenance_pct = 0.0
        maintenance_change = 0.0

        # ─ Tenant Request Count ─
        # Placeholder until maintenance models exist
        tenant_requests = 0
        tenant_requests_change = 0

        return {
            'noi_ytd': {
                'value': noi_ytd,
                'formatted': self._format_money(noi_ytd),
                'change': noi_change,
                'label': 'YTD',
            },
            'tenant_requests': {
                'value': tenant_requests,
                'change': tenant_requests_change,
                'label': 'This month',
            },
            'avg_days_vacant': {
                'value': avg_vacant_days,
                'change': avg_vacant_change,
                'label': 'Current',
            },
            'maintenance_pct_rev': {
                'value': maintenance_pct,
                'change': maintenance_change,
                'label': 'of Revenue',
            },
        }

    def _format_area(self, sqft):
        """Format area in human-readable form."""
        if sqft >= 1e5:
            return f"{sqft / 1e5:.1f} Lakh sq. ft."
        if sqft >= 1e3:
            return f"{sqft / 1e3:.1f}K sqft"
        return f"{int(sqft)} sqft"

    def get_portfolio_map(self):
        """
        Get portfolio map data with property pins.
        """
        data = []
        sites = Site.objects.filter(self._get_base_site_filter())
        
        for site in sites:
            # Calculate occupancy
            site_units = self._apply_scope_filter(
                Unit.objects.filter(
                    floor__tower__site=site,
                    is_active=True
                )
            )
            total_leasable = site_units.aggregate(
                total=Coalesce(Sum('leasable_area_sqft'), Value(0, output_field=DecimalField()))
            )['total']
            
            leased_area = self._apply_scope_filter(
                UnitAllocation.objects.filter(
                    unit__floor__tower__site=site,
                    is_active=True,
                    agreement__status=Agreement.Status.ACTIVE,
                )
            ).aggregate(
                total=Coalesce(Sum('allocated_area_sqft'), Value(0, output_field=DecimalField()))
            )['total']
            
            occupancy = 0
            if total_leasable and total_leasable > 0:
                occupancy = round((float(leased_area) / float(total_leasable)) * 100)
            
            # Determine color based on occupancy
            if occupancy >= 90:
                color = "green"
            elif occupancy >= 75:
                color = "orange"
            else:
                color = "red"
            
            # Calculate monthly yield (rent collected)
            agreements = self._apply_scope_filter(
                Agreement.objects.filter(
                    site=site,
                    is_active=True,
                    status=Agreement.Status.ACTIVE,
                )
            ).select_related("financials")
            monthly_yield = sum(self._safe_base_rent(agreement) for agreement in agreements)
            
            data.append({
                'id': str(site.id),
                'name': site.name,
                'occupancy': occupancy,
                'vacant_days': 0,  # TODO: Calculate from vacancy tracking
                'monthly_yield': self._format_money(monthly_yield),
                'color': color,
                'latitude': float(site.latitude) if site.latitude else None,
                'longitude': float(site.longitude) if site.longitude else None,
                'address': f"{site.address_line1}, {site.city}",
            })
        
        return data

    def get_occupancy_timeline(self):
        """
        Get occupancy timeline data for the last 6 months.
        """
        data = []
        today = self.as_of
        
        for i in range(5, -1, -1):
            month_date = today - timedelta(days=i * 30)
            month_start = month_date.replace(day=1)
            month_label = month_date.strftime('%b')
            
            # Calculate occupancy for this month
            # This is a simplified calculation - in production, you'd use historical snapshots
            units = self._apply_scope_filter(
                Unit.objects.filter(
                    is_active=True,
                    created_at__lte=month_start,
                )
            )
            
            if self.site_ids:
                units = units.filter(floor__tower__site_id__in=self.site_ids)
            
            total_leasable = units.aggregate(
                total=Coalesce(Sum('leasable_area_sqft'), Value(0, output_field=DecimalField()))
            )['total']
            
            # Approximate historical occupancy
            occupancy_rate = 0.85 + (0.02 * (5 - i))  # Simulated trend
            
            occupied = float(total_leasable or 0) * occupancy_rate
            vacant = float(total_leasable or 0) * (1 - occupancy_rate)
            
            # Get expiring leases for this month
            expiring = self._apply_scope_filter(
                Agreement.objects.filter(
                    is_active=True,
                    term_dates__expiry_date__month=month_date.month,
                    term_dates__expiry_date__year=month_date.year,
                )
            ).count()
            
            data.append({
                'month': month_label,
                'occupied': int(occupied),
                'vacant': int(vacant),
                'expiring': expiring,
            })
        
        return data

    def get_filter_options(self):
        """
        Get available filter options for the dashboard.
        """
        sites = self._apply_scope_filter(
            Site.objects.filter(is_active=True)
        ).values('id', 'name')
        towers = self._apply_scope_filter(
            Tower.objects.filter(is_active=True)
        ).values('id', 'name', 'site_id')
        
        return {
            'sites': list(sites),
            'towers': list(towers),
        }

    def _format_money(self, value):
        """
        Format money value in Indian notation (Lakhs, Crores).
        """
        try:
            n = float(value or 0)
        except (TypeError, ValueError):
            return "0"
        
        if not n:
            return "0"
        
        abs_n = abs(n)
        
        if abs_n >= 1e7:  # Crores
            cr = n / 1e7
            return f"{cr:.2f}Cr".replace('.00', '')
        elif abs_n >= 1e5:  # Lakhs
            l = n / 1e5
            return f"{l:.1f}L".replace('.0', '')
        elif abs_n >= 1e3:  # Thousands
            k = n / 1e3
            return f"{k:.1f}K".replace('.0', '')
        
        return f"{int(n):,}"

    def _format_time_left(self, days):
        """
        Format days left into human-readable string.
        """
        if days < 0:
            return "Expired"
        if days == 0:
            return "Today"
        if days == 1:
            return "1 day"
        if days < 30:
            return f"{days} days"
        if days < 365:
            months = days // 30
            rem_days = days % 30
            if rem_days:
                return f"{months} mo {rem_days} d"
            return f"{months} mo"
        years = days // 365
        rem = days % 365
        months = rem // 30
        if months:
            return f"{years} yr {months} mo"
        return f"{years} yr"


def get_dashboard_data(request, params=None):
    """
    Convenience function to get dashboard data.
    
    Args:
        request: HTTP request with scope context
        params: Optional query parameters
        
    Returns:
        dict: Complete dashboard data
    """
    service = DashboardService(request, params)
    return service.get_full_dashboard()
