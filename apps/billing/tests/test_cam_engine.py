from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.accounts.models import Org, TenantScope
from apps.billing.cam_engine import get_cam_line_items_for_schedule
from apps.billing.models import Invoice, InvoiceSchedule
from apps.leases.models import Agreement, LeaseCAM, UnitAllocation
from apps.properties.models import CAMComponent, CAMComponentGroup, Floor, Site, SiteCAMConfig, Tower, Unit
from apps.tenants.models import TenantCompany


class CAMEngineTests(TestCase):
    def setUp(self):
        self.scope = self._create_scope()
        self.site = self._create_site(self.scope, code="nb-techpark", common_area_percent=Decimal("10"))
        self.tenant = TenantCompany.objects.create(
            scope=self.scope,
            legal_name="Asterlane Retail Private Limited",
        )
        self.agreement = Agreement.objects.create(
            scope=self.scope,
            lease_id="LSE-NB-001",
            tenant=self.tenant,
            site=self.site,
        )
        self.schedule = InvoiceSchedule.objects.create(
            scope=self.scope,
            agreement=self.agreement,
            schedule_name="Monthly Rent",
            invoice_type=Invoice.InvoiceType.RENT,
            frequency=InvoiceSchedule.ScheduleFrequency.MONTHLY,
            amount=Decimal("100000.00"),
            tax_rate=Decimal("18.00"),
            start_date=date(2026, 1, 1),
            next_scheduled_date=date(2026, 1, 1),
        )

    def _create_scope(self):
        org = Org.objects.create(
            name="Northbridge Asset Group",
            code="northbridge-asset-group-test",
        )
        scope = TenantScope.objects.filter(org=org).first()
        if scope:
            return scope
        return TenantScope.objects.create(
            scope_type=TenantScope.ScopeType.ORG,
            org=org,
            name=org.name,
            code="org-northbridge-asset-group-test",
        )

    def _create_site(self, scope, code, common_area_percent):
        return Site.objects.create(
            scope=scope,
            name="Northbridge TechPark Bengaluru",
            code=code,
            site_type=Site.SiteType.COMMERCIAL,
            total_builtup_area_sqft=Decimal("500000"),
            leasable_area_sqft=Decimal("420000"),
            common_area_percent=common_area_percent,
        )

    def _create_floor(self, site, suffix):
        tower = Tower.objects.create(
            scope=site.scope,
            site=site,
            name=f"Tower {suffix}",
            code=f"tower-{suffix}",
            total_area_sqft=Decimal("200000"),
            leasable_area_sqft=Decimal("180000"),
        )
        return Floor.objects.create(
            scope=site.scope,
            site=site,
            tower=tower,
            number=1,
            label=f"Floor {suffix}",
            total_area_sqft=Decimal("10000"),
            leasable_area_sqft=Decimal("8000"),
            cam_area_sqft=Decimal("2000"),
        )

    def _create_cam_component(self, *, rate_logic, rate, area_basis=CAMComponent.AreaBasis.LEASABLE_AREA):
        group = CAMComponentGroup.objects.create(
            scope=self.scope,
            name=f"Core CAM {rate_logic}",
            code=f"core-cam-{rate_logic.lower()}",
        )
        return CAMComponent.objects.create(
            scope=self.scope,
            group=group,
            name=f"CAM Component {rate_logic}",
            code=f"cam-comp-{rate_logic.lower()}",
            rate_logic=rate_logic,
            default_rate=rate,
            area_basis=area_basis,
            gst_rate=Decimal("18.00"),
        )

    def test_site_cam_uses_floor_allocation_area_and_chargeable_basis(self):
        floor = self._create_floor(self.site, "A")
        UnitAllocation.objects.create(
            scope=self.scope,
            agreement=self.agreement,
            allocation_level=UnitAllocation.AllocationLevel.FLOOR,
            floor=floor,
            allocated_area_sqft=Decimal("1000.00"),
        )

        component = self._create_cam_component(
            rate_logic=CAMComponent.RateLogic.PER_SQFT_MONTHLY,
            rate=Decimal("10.00"),
            area_basis=CAMComponent.AreaBasis.CHARGEABLE_AREA,
        )
        SiteCAMConfig.objects.create(
            scope=self.scope,
            site=self.site,
            component=component,
            is_active=True,
        )

        items = get_cam_line_items_for_schedule(
            schedule=self.schedule,
            base_rent_amount=Decimal("100000.00"),
        )

        self.assertEqual(len(items), 1)
        # 1000 sqft * 1.10 chargeable multiplier * 10 = 11000
        self.assertEqual(items[0]["amount"], Decimal("11000.00"))
        self.assertEqual(items[0]["gst_amount"], Decimal("1980.00"))
        self.assertEqual(items[0]["source"], "SITE_CAM_CONFIG")

    def test_lease_cam_override_takes_precedence_over_site_cam(self):
        floor = self._create_floor(self.site, "B")
        UnitAllocation.objects.create(
            scope=self.scope,
            agreement=self.agreement,
            allocation_level=UnitAllocation.AllocationLevel.FLOOR,
            floor=floor,
            allocated_area_sqft=Decimal("1200.00"),
        )

        component = self._create_cam_component(
            rate_logic=CAMComponent.RateLogic.PER_SQFT_MONTHLY,
            rate=Decimal("25.00"),
        )
        SiteCAMConfig.objects.create(
            scope=self.scope,
            site=self.site,
            component=component,
            is_active=True,
        )

        LeaseCAM.objects.create(
            scope=self.scope,
            agreement=self.agreement,
            allocation_basis=LeaseCAM.CAMBasis.FIXED,
            monthly_total=Decimal("5000.00"),
        )

        items = get_cam_line_items_for_schedule(
            schedule=self.schedule,
            base_rent_amount=Decimal("100000.00"),
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["source"], "LEASE_CAM")
        self.assertEqual(items[0]["amount"], Decimal("5000.00"))
        self.assertEqual(items[0]["gst_amount"], Decimal("900.00"))

    def test_site_cam_per_unit_counts_unit_allocations(self):
        floor = self._create_floor(self.site, "C")
        unit1 = Unit.objects.create(
            scope=self.scope,
            floor=floor,
            unit_no="C-101",
            unit_type=Unit.UnitType.COMMERCIAL,
            builtup_area_sqft=Decimal("600.00"),
            leasable_area_sqft=Decimal("500.00"),
        )
        unit2 = Unit.objects.create(
            scope=self.scope,
            floor=floor,
            unit_no="C-102",
            unit_type=Unit.UnitType.COMMERCIAL,
            builtup_area_sqft=Decimal("700.00"),
            leasable_area_sqft=Decimal("550.00"),
        )

        UnitAllocation.objects.create(
            scope=self.scope,
            agreement=self.agreement,
            allocation_level=UnitAllocation.AllocationLevel.UNIT,
            unit=unit1,
            allocated_area_sqft=Decimal("500.00"),
        )
        UnitAllocation.objects.create(
            scope=self.scope,
            agreement=self.agreement,
            allocation_level=UnitAllocation.AllocationLevel.UNIT,
            unit=unit2,
            allocated_area_sqft=Decimal("550.00"),
        )

        component = self._create_cam_component(
            rate_logic=CAMComponent.RateLogic.PER_UNIT,
            rate=Decimal("1200.00"),
        )
        SiteCAMConfig.objects.create(
            scope=self.scope,
            site=self.site,
            component=component,
            is_active=True,
        )

        items = get_cam_line_items_for_schedule(
            schedule=self.schedule,
            base_rent_amount=Decimal("100000.00"),
        )

        self.assertEqual(len(items), 1)
        # 2 allocated units * 1200 = 2400
        self.assertEqual(items[0]["amount"], Decimal("2400.00"))
        self.assertEqual(items[0]["gst_amount"], Decimal("432.00"))
        self.assertEqual(items[0]["source"], "SITE_CAM_CONFIG")

    def test_lease_cam_pro_rata_uses_allocated_area_for_floor_allocation(self):
        floor = self._create_floor(self.site, "D")
        UnitAllocation.objects.create(
            scope=self.scope,
            agreement=self.agreement,
            allocation_level=UnitAllocation.AllocationLevel.FLOOR,
            floor=floor,
            allocated_area_sqft=Decimal("600.00"),
        )
        LeaseCAM.objects.create(
            scope=self.scope,
            agreement=self.agreement,
            allocation_basis=LeaseCAM.CAMBasis.PRO_RATA,
            per_sqft_monthly=Decimal("5.00"),
        )

        items = get_cam_line_items_for_schedule(
            schedule=self.schedule,
            base_rent_amount=Decimal("100000.00"),
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["source"], "LEASE_CAM")
        self.assertEqual(items[0]["amount"], Decimal("3000.00"))
        self.assertEqual(items[0]["gst_amount"], Decimal("540.00"))
