"""
Test Data Population Script for LM-MonoLithic

Run this script in Django shell:
    cd Backend
    .venv\Scripts\activate
    python manage.py shell < scripts\populate_test_data.py

Or copy-paste into interactive shell:
    python manage.py shell
    >>> exec(open('scripts/populate_test_data.py').read())

Creates:
- 1 Organization: "Acme Corporation"
- 2 Companies: "Acme Properties" and "Acme Commercial"
- 2 Entities: "Mumbai Region" (under Acme Properties) and "Delhi Region" (under Acme Commercial)
- TenantScopes for each hierarchy level
- Users with roles and scope memberships
"""

from django.contrib.auth import get_user_model
from apps.accounts.models import (
    Org, Company, Entity, TenantScope,
    Role, Permission, ScopeMembership, UserProfile
)

User = get_user_model()

print("=" * 60)
print("LM-MonoLithic Test Data Population")
print("=" * 60)

# =============================================================================
# 1. CREATE ORGANIZATION
# =============================================================================
print("\n[1/7] Creating Organization...")

org, org_created = Org.objects.get_or_create(
    code="acme-corp",
    defaults={"name": "Acme Corporation"}
)
print(f"  {'Created' if org_created else 'Found existing'}: {org.name} (ID: {org.id})")

# =============================================================================
# 2. CREATE COMPANIES
# =============================================================================
print("\n[2/7] Creating Companies...")

company1, c1_created = Company.objects.get_or_create(
    org=org,
    code="acme-properties",
    defaults={"name": "Acme Properties Ltd"}
)
print(f"  {'Created' if c1_created else 'Found existing'}: {company1.name} (ID: {company1.id})")

company2, c2_created = Company.objects.get_or_create(
    org=org,
    code="acme-commercial",
    defaults={"name": "Acme Commercial Realty"}
)
print(f"  {'Created' if c2_created else 'Found existing'}: {company2.name} (ID: {company2.id})")

# =============================================================================
# 3. CREATE ENTITIES
# =============================================================================
print("\n[3/7] Creating Entities...")

entity1, e1_created = Entity.objects.get_or_create(
    company=company1,
    code="mumbai-region",
    defaults={"name": "Mumbai Region"}
)
print(f"  {'Created' if e1_created else 'Found existing'}: {entity1.name} under {company1.name} (ID: {entity1.id})")

entity2, e2_created = Entity.objects.get_or_create(
    company=company2,
    code="delhi-region",
    defaults={"name": "Delhi Region"}
)
print(f"  {'Created' if e2_created else 'Found existing'}: {entity2.name} under {company2.name} (ID: {entity2.id})")

# =============================================================================
# 4. CREATE TENANT SCOPES
# =============================================================================
print("\n[4/7] Creating TenantScopes...")

# ORG scope
org_scope, os_created = TenantScope.objects.get_or_create(
    scope_type=TenantScope.ScopeType.ORG,
    org=org,
    defaults={
        "name": f"{org.name} Scope",
        "code": f"scope-{org.code}"
    }
)
print(f"  {'Created' if os_created else 'Found existing'}: ORG Scope - {org_scope.name} (ID: {org_scope.id})")

# COMPANY scopes
company1_scope, cs1_created = TenantScope.objects.get_or_create(
    scope_type=TenantScope.ScopeType.COMPANY,
    company=company1,
    defaults={
        "name": f"{company1.name} Scope",
        "code": f"scope-{company1.code}"
    }
)
print(f"  {'Created' if cs1_created else 'Found existing'}: COMPANY Scope - {company1_scope.name} (ID: {company1_scope.id})")

company2_scope, cs2_created = TenantScope.objects.get_or_create(
    scope_type=TenantScope.ScopeType.COMPANY,
    company=company2,
    defaults={
        "name": f"{company2.name} Scope",
        "code": f"scope-{company2.code}"
    }
)
print(f"  {'Created' if cs2_created else 'Found existing'}: COMPANY Scope - {company2_scope.name} (ID: {company2_scope.id})")

# ENTITY scopes
entity1_scope, es1_created = TenantScope.objects.get_or_create(
    scope_type=TenantScope.ScopeType.ENTITY,
    entity=entity1,
    defaults={
        "name": f"{entity1.name} Scope",
        "code": f"scope-{entity1.code}"
    }
)
print(f"  {'Created' if es1_created else 'Found existing'}: ENTITY Scope - {entity1_scope.name} (ID: {entity1_scope.id})")

entity2_scope, es2_created = TenantScope.objects.get_or_create(
    scope_type=TenantScope.ScopeType.ENTITY,
    entity=entity2,
    defaults={
        "name": f"{entity2.name} Scope",
        "code": f"scope-{entity2.code}"
    }
)
print(f"  {'Created' if es2_created else 'Found existing'}: ENTITY Scope - {entity2_scope.name} (ID: {entity2_scope.id})")

# =============================================================================
# 5. CREATE PERMISSIONS
# =============================================================================
print("\n[5/7] Creating Permissions...")

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
for code, name, desc in permissions_data:
    perm, created = Permission.objects.get_or_create(
        code=code,
        defaults={"name": name, "description": desc}
    )
    permissions[code] = perm
    if created:
        print(f"  Created: {code}")

print(f"  Total permissions: {len(permissions)}")

# =============================================================================
# 6. CREATE ROLES
# =============================================================================
print("\n[6/7] Creating Roles...")

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
print(f"  {'Created' if ar_created else 'Found existing'}: Admin Role at ORG scope (ID: {admin_role.id})")

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
print(f"  {'Created' if mr1_created else 'Found existing'}: Manager Role at Company 1 (ID: {manager_role1.id})")

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
print(f"  {'Created' if mr2_created else 'Found existing'}: Manager Role at Company 2 (ID: {manager_role2.id})")

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
print(f"  {'Created' if vr1_created else 'Found existing'}: Viewer Role at Entity 1 (ID: {viewer_role1.id})")

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
print(f"  {'Created' if vr2_created else 'Found existing'}: Viewer Role at Entity 2 (ID: {viewer_role2.id})")

# =============================================================================
# 7. CREATE USERS
# =============================================================================
print("\n[7/7] Creating Users...")

users_data = [
    # (username, email, password, first_name, last_name, is_superuser, scope, role, profile_role)
    ("admin", "admin@acme.com", "admin123", "System", "Admin", True, org_scope, admin_role, "ADMIN"),
    ("org_admin", "org.admin@acme.com", "orgadmin123", "Org", "Administrator", False, org_scope, admin_role, "ADMIN"),
    ("manager1", "manager1@acme.com", "manager123", "Rahul", "Sharma", False, company1_scope, manager_role1, "MANAGER"),
    ("manager2", "manager2@acme.com", "manager123", "Priya", "Patel", False, company2_scope, manager_role2, "MANAGER"),
    ("user1", "user1@acme.com", "user123", "Amit", "Kumar", False, entity1_scope, viewer_role1, "VIEWER"),
    ("user2", "user2@acme.com", "user123", "Sneha", "Reddy", False, entity2_scope, viewer_role2, "VIEWER"),
]

created_users = []
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

        # Create profile
        UserProfile.objects.get_or_create(
            user=user,
            defaults={"role": profile_role}
        )

        # Create scope membership
        ScopeMembership.objects.get_or_create(
            user=user,
            scope=scope,
            defaults={"role": role, "is_active": True}
        )

        print(f"  Created: {username} ({email}) - {scope.scope_type} scope")
        created_users.append((username, password, scope.id))
    else:
        print(f"  Found existing: {username}")

# =============================================================================
# SUMMARY
# =============================================================================
print("\n" + "=" * 60)
print("TEST DATA CREATION COMPLETE!")
print("=" * 60)

print("\n📊 HIERARCHY OVERVIEW:")
print(f"""
  {org.name} (ORG)
  └── Scope ID: {org_scope.id}
      │
      ├── {company1.name} (COMPANY)
      │   └── Scope ID: {company1_scope.id}
      │       │
      │       └── {entity1.name} (ENTITY)
      │           └── Scope ID: {entity1_scope.id}
      │
      └── {company2.name} (COMPANY)
          └── Scope ID: {company2_scope.id}
              │
              └── {entity2.name} (ENTITY)
                  └── Scope ID: {entity2_scope.id}
""")

print("\n👤 USER CREDENTIALS:")
print("-" * 50)
print(f"{'Username':<15} {'Password':<15} {'Scope Level':<15} {'Scope ID'}")
print("-" * 50)
print(f"{'admin':<15} {'admin123':<15} {'ORG (super)':<15} {org_scope.id}")
print(f"{'org_admin':<15} {'orgadmin123':<15} {'ORG':<15} {org_scope.id}")
print(f"{'manager1':<15} {'manager123':<15} {'COMPANY':<15} {company1_scope.id}")
print(f"{'manager2':<15} {'manager123':<15} {'COMPANY':<15} {company2_scope.id}")
print(f"{'user1':<15} {'user123':<15} {'ENTITY':<15} {entity1_scope.id}")
print(f"{'user2':<15} {'user123':<15} {'ENTITY':<15} {entity2_scope.id}")
print("-" * 50)

print("\n🔑 SCOPE IDs FOR API TESTING:")
print(f"  ORG Scope:        {org_scope.id}")
print(f"  Company 1 Scope:  {company1_scope.id}")
print(f"  Company 2 Scope:  {company2_scope.id}")
print(f"  Entity 1 Scope:   {entity1_scope.id}")
print(f"  Entity 2 Scope:   {entity2_scope.id}")

print("\n📝 EXAMPLE API CALLS:")
print(f"""
  # Get auth token:
  POST /api/v1/auth/token/
  {{"username": "admin", "password": "admin123"}}

  # Create billing rule at ORG level (visible to all):
  POST /api/v1/billing/billing-rules/
  Headers: Authorization: Bearer <token>, X-Scope-ID: {org_scope.id}

  # Create clause at COMPANY level (visible to company + entities):
  POST /api/v1/clauses/clauses/
  Headers: Authorization: Bearer <token>, X-Scope-ID: {company1_scope.id}

  # View inherited configs from ENTITY level:
  GET /api/v1/billing/billing-rules/
  Headers: Authorization: Bearer <token>, X-Scope-ID: {entity1_scope.id}
  (Returns: Entity + Company + ORG rules)
""")

print("\n✅ Ready for testing!")
