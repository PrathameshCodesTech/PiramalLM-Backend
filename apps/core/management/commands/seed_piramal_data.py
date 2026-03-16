"""
Django Management Command: Seed Piramal Demo Data

Usage:
    python manage.py seed_piramal_data

Creates:
- Org: Piramal Group
- Company: Piramal Realty
- Entity: Mumbai Properties
- TenantScopes for each hierarchy level
- Sites: Piramal Tower (Lower Parel) + Piramal Agastya (Kurla West)
- Towers, Floors, Units for each site
- Tenant companies: Abc, Unity Bank, Teb Ltd, Infinity B Tech, Marvel, Kotak Bank, Sun Pharma
- Lease agreements matching dashboard mock data (LSE-2026-000001 to LSE-2026-000005)

Idempotent — safe to run multiple times.
"""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.accounts.models import (
    Company, Entity, Org, Role, ScopeMembership, TenantScope,
)
from apps.leases.models import Agreement, LeaseTermDates, UnitAllocation
from apps.properties.models import Floor, Site, Tower, Unit
from apps.tenants.models import TenantCompany


class Command(BaseCommand):
    help = "Seed Piramal demo data matching the static dashboard"

    def handle(self, *args, **options):
        User = get_user_model()

        self.stdout.write("=" * 60)
        self.stdout.write("Piramal Demo Data Seed")
        self.stdout.write("=" * 60)

        # ─────────────────────────────────────────────────────────────
        # 1. ORG / COMPANY / ENTITY
        # ─────────────────────────────────────────────────────────────
        self.stdout.write("\n[1/7] Org structure...")

        org, _ = Org.objects.get_or_create(
            code="piramal-group",
            defaults={"name": "Piramal Group"},
        )
        self._log("Org", org.name, _)

        company, _ = Company.objects.get_or_create(
            org=org,
            code="piramal-realty",
            defaults={"name": "Piramal Realty"},
        )
        self._log("Company", company.name, _)

        entity, _ = Entity.objects.get_or_create(
            company=company,
            code="mumbai-properties",
            defaults={"name": "Mumbai Properties"},
        )
        self._log("Entity", entity.name, _)

        # ─────────────────────────────────────────────────────────────
        # 2. TENANT SCOPES
        # ─────────────────────────────────────────────────────────────
        self.stdout.write("\n[2/7] TenantScopes...")

        org_scope, _ = TenantScope.objects.get_or_create(
            scope_type=TenantScope.ScopeType.ORG,
            org=org,
            defaults={"name": "Piramal Group Scope", "code": "scope-piramal-group"},
        )
        self._log("ORG scope", org_scope.name, _)

        company_scope, _ = TenantScope.objects.get_or_create(
            scope_type=TenantScope.ScopeType.COMPANY,
            company=company,
            defaults={"name": "Piramal Realty Scope", "code": "scope-piramal-realty"},
        )
        self._log("COMPANY scope", company_scope.name, _)

        entity_scope, _ = TenantScope.objects.get_or_create(
            scope_type=TenantScope.ScopeType.ENTITY,
            entity=entity,
            defaults={"name": "Mumbai Properties Scope", "code": "scope-mumbai-properties"},
        )
        self._log("ENTITY scope", entity_scope.name, _)

        # All properties/tenants/leases use the entity scope
        scope = entity_scope

        # ─────────────────────────────────────────────────────────────
        # 3. ADMIN USER
        # ─────────────────────────────────────────────────────────────
        self.stdout.write("\n[3/7] Admin user...")

        superuser = User.objects.filter(is_superuser=True).first()
        if superuser:
            self.stdout.write(f"  Using existing superuser: {superuser.username}")
        else:
            superuser = User.objects.create_superuser(
                username="admin",
                password="admin123",
                email="admin@piramallease.com",
            )
            self.stdout.write("  Created superuser: admin / admin123")

        # ─────────────────────────────────────────────────────────────
        # 4. SITES (Properties)
        # ─────────────────────────────────────────────────────────────
        self.stdout.write("\n[4/7] Sites...")

        tower_site, _ = Site.objects.get_or_create(
            scope=scope,
            code="piramal-tower",
            defaults={
                "name": "Piramal Tower",
                "site_type": Site.SiteType.COMMERCIAL,
                "address_line1": "Ganpatrao Kadam Marg",
                "city": "Mumbai",
                "state": "Maharashtra",
                "pincode": "400013",
                "landmark": "Lower Parel",
                "leasable_area_sqft": Decimal("52000"),
                "total_builtup_area_sqft": Decimal("60000"),
                "latitude": Decimal("18.998200"),
                "longitude": Decimal("72.831300"),
            },
        )
        self._log("Site", tower_site.name, _)

        agastya_site, _ = Site.objects.get_or_create(
            scope=scope,
            code="piramal-agastya",
            defaults={
                "name": "Piramal Agastya",
                "site_type": Site.SiteType.COMMERCIAL,
                "address_line1": "Opposite Fire Brigade, Kamani Junction",
                "city": "Mumbai",
                "state": "Maharashtra",
                "pincode": "400070",
                "landmark": "Kurla (West)",
                "leasable_area_sqft": Decimal("74200"),
                "total_builtup_area_sqft": Decimal("80000"),
                "latitude": Decimal("19.070700"),
                "longitude": Decimal("72.879200"),
            },
        )
        self._log("Site", agastya_site.name, _)

        # ─────────────────────────────────────────────────────────────
        # 5. TOWERS / FLOORS / UNITS
        # ─────────────────────────────────────────────────────────────
        self.stdout.write("\n[5/7] Towers / Floors / Units...")

        # Helper to create a tower + floors + units
        def make_tower_floors_units(site, tower_code, tower_name, floors_data):
            """floors_data: list of (floor_number, label, units_list)
               units_list: list of (unit_no, area_sqft)
            """
            tower, created = Tower.objects.get_or_create(
                site=site,
                code=tower_code,
                defaults={
                    "scope": scope,
                    "name": tower_name,
                    "building_type": Tower.BuildingType.COMMERCIAL,
                    "total_floors": len(floors_data),
                },
            )
            self._log("  Tower", tower.name, created)

            for floor_number, floor_label, units in floors_data:
                floor, f_created = Floor.objects.get_or_create(
                    tower=tower,
                    number=floor_number,
                    defaults={
                        "scope": scope,
                        "site": site,
                        "label": floor_label,
                        "status": Floor.FloorStatus.LEASED,
                        "leasable_area_sqft": sum(a for _, a in units),
                    },
                )
                self._log(f"    Floor {floor_number}", floor_label, f_created)

                for unit_no, area in units:
                    unit, u_created = Unit.objects.get_or_create(
                        floor=floor,
                        unit_no=unit_no,
                        defaults={
                            "scope": scope,
                            "unit_type": Unit.UnitType.COMMERCIAL,
                            "status": Unit.UnitStatus.LEASED,
                            "leasable_area_sqft": Decimal(str(area)),
                        },
                    )
                    self._log(f"      Unit", unit_no, u_created)

            return tower

        tower_a = make_tower_floors_units(
            tower_site, "pt-tower-a", "Tower A",
            [
                (5,  "5th Floor",  [("5A", 12000)]),
                (8,  "8th Floor",  [("8B", 18500), ("8C", 1200)]),
                (12, "12th Floor", [("12A", 17340), ("12B", 2960)]),
            ],
        )

        agastya_a = make_tower_floors_units(
            agastya_site, "pa-tower-a", "Tower A",
            [
                (3, "3rd Floor", [("3A", 22000), ("3B", 4000)]),
                (6, "6th Floor", [("6A", 37360), ("6B", 10840)]),
            ],
        )

        # ─────────────────────────────────────────────────────────────
        # 6. TENANT COMPANIES
        # ─────────────────────────────────────────────────────────────
        self.stdout.write("\n[6/7] Tenant companies...")

        tenants_data = [
            ("Abc",            "abc@example.com",         "+91 98765 43210"),
            ("Unity Bank",     "unity@example.com",       "+91 98765 11111"),
            ("Teb Ltd",        "tebltd@example.com",      "+91 98765 22222"),
            ("Infinity B Tech","infinitybtech@example.com","+91 98765 55555"),
            ("Marvel",         "marvel@example.com",      "+91 98765 33333"),
            ("Kotak Bank",     "kotak@example.com",       "+91 98765 66666"),
            ("Sun Pharma",     "sunpharma@example.com",   "+91 98765 44444"),
        ]

        tenant_map = {}  # name → TenantCompany
        for legal_name, email, phone in tenants_data:
            tc, created = TenantCompany.objects.get_or_create(
                scope=scope,
                legal_name=legal_name,
                defaults={
                    "email": email,
                    "phone": phone,
                    "status": TenantCompany.Status.ACTIVE,
                    "industry": "Commercial",
                },
            )
            tenant_map[legal_name] = tc
            self._log("  Tenant", legal_name, created)

        # ─────────────────────────────────────────────────────────────
        # 7. LEASE AGREEMENTS
        # ─────────────────────────────────────────────────────────────
        self.stdout.write("\n[7/7] Lease agreements...")

        leases = [
            {
                "lease_id":    "LSE-2026-000001",
                "tenant":      "Marvel",
                "site":        agastya_site,
                "start":       date(2024, 8, 1),
                "end":         date(2027, 11, 15),
                "monthly_rent": Decimal("2590000"),  # ₹25.9L
                "area_sqft":   Decimal("37360"),
            },
            {
                "lease_id":    "LSE-2026-000002",
                "tenant":      "Abc",
                "site":        tower_site,
                "start":       date(2024, 1, 15),
                "end":         date(2028, 2, 1),
                "monthly_rent": Decimal("4130000"),  # ₹41.3L
                "area_sqft":   Decimal("12000"),
            },
            {
                "lease_id":    "LSE-2026-000003",
                "tenant":      "Teb Ltd",
                "site":        tower_site,
                "start":       date(2023, 6, 1),
                "end":         date(2029, 3, 15),
                "monthly_rent": Decimal("2610000"),  # ₹26.1L
                "area_sqft":   Decimal("17340"),
            },
            {
                "lease_id":    "LSE-2026-000004",
                "tenant":      "Infinity B Tech",
                "site":        agastya_site,
                "start":       date(2022, 12, 1),
                "end":         date(2030, 4, 20),
                "monthly_rent": Decimal("1360000"),  # ₹13.6L
                "area_sqft":   Decimal("22000"),
            },
            {
                "lease_id":    "LSE-2026-000005",
                "tenant":      "Kotak Bank",
                "site":        tower_site,
                "start":       date(2022, 1, 1),
                "end":         date(2031, 1, 1),
                "monthly_rent": Decimal("1820000"),  # ₹18.2L
                "area_sqft":   Decimal("18500"),
            },
        ]

        for ld in leases:
            tenant_obj = tenant_map[ld["tenant"]]
            agreement, created = Agreement.objects.get_or_create(
                scope=scope,
                lease_id=ld["lease_id"],
                version_number=1,
                defaults={
                    "status": Agreement.Status.ACTIVE,
                    "agreement_type": Agreement.AgreementType.OFFICE,
                    "tenant": tenant_obj,
                    "site": ld["site"],
                },
            )
            self._log(f"  Agreement", ld["lease_id"], created)

            # LeaseTermDates
            LeaseTermDates.objects.get_or_create(
                agreement=agreement,
                defaults={
                    "scope": scope,
                    "commencement_date": ld["start"],
                    "expiry_date": ld["end"],
                },
            )

            # UnitAllocation at SITE level (simplest, always links to correct site)
            UnitAllocation.objects.get_or_create(
                agreement=agreement,
                allocation_level=UnitAllocation.AllocationLevel.SITE,
                site=ld["site"],
                defaults={
                    "scope": scope,
                    "allocation_mode": UnitAllocation.AllocationMode.FULL,
                    "allocated_area_sqft": ld["area_sqft"],
                    "monthly_rent": ld["monthly_rent"],
                },
            )

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("Piramal demo data seeded successfully!"))
        self.stdout.write("")
        self.stdout.write("  Org:      Piramal Group")
        self.stdout.write("  Company:  Piramal Realty")
        self.stdout.write("  Sites:    Piramal Tower · Piramal Agastya")
        self.stdout.write("  Tenants:  Abc, Unity Bank, Teb Ltd, Infinity B Tech,")
        self.stdout.write("            Marvel, Kotak Bank, Sun Pharma")
        self.stdout.write("  Leases:   LSE-2026-000001 … LSE-2026-000005")
        self.stdout.write("=" * 60)

    def _log(self, kind, name, created):
        status = "Created" if created else "Already exists"
        self.stdout.write(f"  {status}: {kind} — {name}")
