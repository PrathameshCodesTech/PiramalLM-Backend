"""
Django Management Command: Populate Test Data

Usage:
    python manage.py populate_test_data

Creates:
- 1 Organization: "Acme Corporation"
- 2 Companies: "Acme Properties" and "Acme Commercial"
- 2 Entities: "Mumbai Region" and "Delhi Region"
- TenantScopes for each hierarchy level
- Users with roles and scope memberships
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from apps.accounts.models import (
    Org, Company, Entity, TenantScope,
    Role, Permission, ScopeMembership, UserProfile
)


class Command(BaseCommand):
    help = "Populate database with test data for development/testing"

    def handle(self, *args, **options):
        User = get_user_model()

        self.stdout.write("=" * 60)
        self.stdout.write("LM-MonoLithic Test Data Population")
        self.stdout.write("=" * 60)

        # =================================================================
        # 1. CREATE ORGANIZATION
        # =================================================================
        self.stdout.write("\n[1/7] Creating Organization...")

        org, org_created = Org.objects.get_or_create(
            code="acme-corp",
            defaults={"name": "Acme Corporation"}
        )
        status = "Created" if org_created else "Found existing"
        self.stdout.write(f"  {status}: {org.name} (ID: {org.id})")

        # =================================================================
        # 2. CREATE COMPANIES
        # =================================================================
        self.stdout.write("\n[2/7] Creating Companies...")

        company1, c1_created = Company.objects.get_or_create(
            org=org,
            code="acme-properties",
            defaults={"name": "Acme Properties Ltd"}
        )
        status = "Created" if c1_created else "Found existing"
        self.stdout.write(f"  {status}: {company1.name} (ID: {company1.id})")

        company2, c2_created = Company.objects.get_or_create(
            org=org,
            code="acme-commercial",
            defaults={"name": "Acme Commercial Realty"}
        )
        status = "Created" if c2_created else "Found existing"
        self.stdout.write(f"  {status}: {company2.name} (ID: {company2.id})")

        # =================================================================
        # 3. CREATE ENTITIES
        # =================================================================
        self.stdout.write("\n[3/7] Creating Entities...")

        entity1, e1_created = Entity.objects.get_or_create(
            company=company1,
            code="mumbai-region",
            defaults={"name": "Mumbai Region"}
        )
        status = "Created" if e1_created else "Found existing"
        self.stdout.write(f"  {status}: {entity1.name} under {company1.name} (ID: {entity1.id})")

        entity2, e2_created = Entity.objects.get_or_create(
            company=company2,
            code="delhi-region",
            defaults={"name": "Delhi Region"}
        )
        status = "Created" if e2_created else "Found existing"
        self.stdout.write(f"  {status}: {entity2.name} under {company2.name} (ID: {entity2.id})")

        # =================================================================
        # 4. CREATE TENANT SCOPES
        # =================================================================
        self.stdout.write("\n[4/7] Creating TenantScopes...")

        # ORG scope
        org_scope, os_created = TenantScope.objects.get_or_create(
            scope_type=TenantScope.ScopeType.ORG,
            org=org,
            defaults={
                "name": f"{org.name} Scope",
                "code": f"scope-{org.code}"
            }
        )
        status = "Created" if os_created else "Found existing"
        self.stdout.write(f"  {status}: ORG Scope - {org_scope.name} (ID: {org_scope.id})")

        # COMPANY scopes
        company1_scope, cs1_created = TenantScope.objects.get_or_create(
            scope_type=TenantScope.ScopeType.COMPANY,
            company=company1,
            defaults={
                "name": f"{company1.name} Scope",
                "code": f"scope-{company1.code}"
            }
        )
        status = "Created" if cs1_created else "Found existing"
        self.stdout.write(f"  {status}: COMPANY Scope - {company1_scope.name} (ID: {company1_scope.id})")

        company2_scope, cs2_created = TenantScope.objects.get_or_create(
            scope_type=TenantScope.ScopeType.COMPANY,
            company=company2,
            defaults={
                "name": f"{company2.name} Scope",
                "code": f"scope-{company2.code}"
            }
        )
        status = "Created" if cs2_created else "Found existing"
        self.stdout.write(f"  {status}: COMPANY Scope - {company2_scope.name} (ID: {company2_scope.id})")

        # ENTITY scopes
        entity1_scope, es1_created = TenantScope.objects.get_or_create(
            scope_type=TenantScope.ScopeType.ENTITY,
            entity=entity1,
            defaults={
                "name": f"{entity1.name} Scope",
                "code": f"scope-{entity1.code}"
            }
        )
        status = "Created" if es1_created else "Found existing"
        self.stdout.write(f"  {status}: ENTITY Scope - {entity1_scope.name} (ID: {entity1_scope.id})")

        entity2_scope, es2_created = TenantScope.objects.get_or_create(
            scope_type=TenantScope.ScopeType.ENTITY,
            entity=entity2,
            defaults={
                "name": f"{entity2.name} Scope",
                "code": f"scope-{entity2.code}"
            }
        )
        status = "Created" if es2_created else "Found existing"
        self.stdout.write(f"  {status}: ENTITY Scope - {entity2_scope.name} (ID: {entity2_scope.id})")

        # =================================================================
        # 5. CREATE PERMISSIONS
        # =================================================================
        self.stdout.write("\n[5/7] Creating Permissions...")

        permissions_data = [
            ("view-all", "View All", "Can view all resources"),
            ("create-all", "Create All", "Can create resources"),
            ("edit-all", "Edit All", "Can edit resources"),
            ("delete-all", "Delete All", "Can delete resources"),
            ("manage-users", "Manage Users", "Can manage users and roles"),
            ("manage-billing", "Manage Billing", "Can manage billing rules"),
            ("manage-leases", "Manage Leases", "Can manage lease agreements"),
            ("manage-clauses", "Manage Clauses", "Can manage clause library"),
        ]

        permissions = {}
        created_count = 0
        for code, name, desc in permissions_data:
            perm, created = Permission.objects.get_or_create(
                code=code,
                defaults={"name": name, "description": desc}
            )
            permissions[code] = perm
            if created:
                created_count += 1

        self.stdout.write(f"  Created {created_count} new permissions (total: {len(permissions)})")

        # =================================================================
        # 6. CREATE ROLES
        # =================================================================
        self.stdout.write("\n[6/7] Creating Roles...")

        # Admin role at ORG level
        admin_role, ar_created = Role.objects.get_or_create(
            scope=org_scope,
            code="admin",
            defaults={
                "name": "Administrator",
                "is_system": True
            }
        )
        if ar_created:
            admin_role.permissions.set(permissions.values())
        status = "Created" if ar_created else "Found existing"
        self.stdout.write(f"  {status}: Admin Role at ORG scope (ID: {admin_role.id})")

        # Manager role at Company 1
        manager_role1, mr1_created = Role.objects.get_or_create(
            scope=company1_scope,
            code="manager",
            defaults={
                "name": "Property Manager",
                "is_system": False
            }
        )
        if mr1_created:
            manager_role1.permissions.set([
                permissions["view-all"],
                permissions["create-all"],
                permissions["edit-all"],
                permissions["manage-leases"],
                permissions["manage-billing"],
            ])
        status = "Created" if mr1_created else "Found existing"
        self.stdout.write(f"  {status}: Manager Role at Company 1 (ID: {manager_role1.id})")

        # Manager role at Company 2
        manager_role2, mr2_created = Role.objects.get_or_create(
            scope=company2_scope,
            code="manager",
            defaults={
                "name": "Commercial Manager",
                "is_system": False
            }
        )
        if mr2_created:
            manager_role2.permissions.set([
                permissions["view-all"],
                permissions["create-all"],
                permissions["edit-all"],
                permissions["manage-leases"],
                permissions["manage-billing"],
            ])
        status = "Created" if mr2_created else "Found existing"
        self.stdout.write(f"  {status}: Manager Role at Company 2 (ID: {manager_role2.id})")

        # Viewer role at Entity 1
        viewer_role1, vr1_created = Role.objects.get_or_create(
            scope=entity1_scope,
            code="viewer",
            defaults={
                "name": "Viewer",
                "is_system": False
            }
        )
        if vr1_created:
            viewer_role1.permissions.set([permissions["view-all"]])
        status = "Created" if vr1_created else "Found existing"
        self.stdout.write(f"  {status}: Viewer Role at Entity 1 (ID: {viewer_role1.id})")

        # Viewer role at Entity 2
        viewer_role2, vr2_created = Role.objects.get_or_create(
            scope=entity2_scope,
            code="viewer",
            defaults={
                "name": "Viewer",
                "is_system": False
            }
        )
        if vr2_created:
            viewer_role2.permissions.set([permissions["view-all"]])
        status = "Created" if vr2_created else "Found existing"
        self.stdout.write(f"  {status}: Viewer Role at Entity 2 (ID: {viewer_role2.id})")

        # =================================================================
        # 7. CREATE USERS
        # =================================================================
        self.stdout.write("\n[7/7] Creating Users...")

        users_data = [
            ("admin", "admin@acme.com", "admin123", "System", "Admin", True, org_scope, admin_role, "ADMIN"),
            ("org_admin", "org.admin@acme.com", "orgadmin123", "Org", "Administrator", False, org_scope, admin_role, "ADMIN"),
            ("manager1", "manager1@acme.com", "manager123", "Rahul", "Sharma", False, company1_scope, manager_role1, "MANAGER"),
            ("manager2", "manager2@acme.com", "manager123", "Priya", "Patel", False, company2_scope, manager_role2, "MANAGER"),
            ("user1", "user1@acme.com", "user123", "Amit", "Kumar", False, entity1_scope, viewer_role1, "VIEWER"),
            ("user2", "user2@acme.com", "user123", "Sneha", "Reddy", False, entity2_scope, viewer_role2, "VIEWER"),
        ]

        for username, email, password, first_name, last_name, is_superuser, scope, role, profile_role in users_data:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": email,
                    "first_name": first_name,
                    "last_name": last_name,
                    "is_superuser": is_superuser,
                    "is_staff": is_superuser,
                    "is_active": True,
                }
            )

            if created:
                user.set_password(password)
                user.save()

                UserProfile.objects.get_or_create(
                    user=user,
                    defaults={"role": profile_role}
                )

                ScopeMembership.objects.get_or_create(
                    user=user,
                    scope=scope,
                    defaults={"role": role, "is_active": True}
                )

                self.stdout.write(f"  Created: {username} ({email}) - {scope.scope_type} scope")
            else:
                self.stdout.write(f"  Found existing: {username}")

        # =================================================================
        # SUMMARY
        # =================================================================
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("TEST DATA CREATION COMPLETE!"))
        self.stdout.write("=" * 60)

        self.stdout.write("\nHIERARCHY OVERVIEW:")
        self.stdout.write(f"  {org.name} (ORG) - Scope ID: {org_scope.id}")
        self.stdout.write(f"    |-- {company1.name} (COMPANY) - Scope ID: {company1_scope.id}")
        self.stdout.write(f"    |     |-- {entity1.name} (ENTITY) - Scope ID: {entity1_scope.id}")
        self.stdout.write(f"    |")
        self.stdout.write(f"    |-- {company2.name} (COMPANY) - Scope ID: {company2_scope.id}")
        self.stdout.write(f"          |-- {entity2.name} (ENTITY) - Scope ID: {entity2_scope.id}")

        self.stdout.write("\nUSER CREDENTIALS:")
        self.stdout.write("-" * 60)
        self.stdout.write(f"{'Username':<12} {'Password':<12} {'Scope Level':<12} {'Scope ID'}")
        self.stdout.write("-" * 60)
        self.stdout.write(f"{'admin':<12} {'admin123':<12} {'ORG (super)':<12} {org_scope.id}")
        self.stdout.write(f"{'org_admin':<12} {'orgadmin123':<12} {'ORG':<12} {org_scope.id}")
        self.stdout.write(f"{'manager1':<12} {'manager123':<12} {'COMPANY':<12} {company1_scope.id}")
        self.stdout.write(f"{'manager2':<12} {'manager123':<12} {'COMPANY':<12} {company2_scope.id}")
        self.stdout.write(f"{'user1':<12} {'user123':<12} {'ENTITY':<12} {entity1_scope.id}")
        self.stdout.write(f"{'user2':<12} {'user123':<12} {'ENTITY':<12} {entity2_scope.id}")
        self.stdout.write("-" * 60)

        self.stdout.write("\nSCOPE IDs FOR API TESTING (X-Scope-ID header):")
        self.stdout.write(f"  ORG Scope:        {org_scope.id}")
        self.stdout.write(f"  Company 1 Scope:  {company1_scope.id}")
        self.stdout.write(f"  Company 2 Scope:  {company2_scope.id}")
        self.stdout.write(f"  Entity 1 Scope:   {entity1_scope.id}")
        self.stdout.write(f"  Entity 2 Scope:   {entity2_scope.id}")

        self.stdout.write(self.style.SUCCESS("\nReady for testing!"))
