"""
Reusable role seeding logic.
Used by seed_roles management command and TenantScope creation signal.
"""

from apps.accounts.models import Permission, Role, RolePermission, TenantScope


DEFAULT_PERMISSIONS = [
    "properties.site.read",
    "properties.site.write",
    "properties.tower.read",
    "properties.tower.write",
    "properties.floor.read",
    "properties.floor.write",
    "properties.unit.read",
    "properties.unit.write",
    "properties.amenity.read",
    "properties.amenity.write",
    "properties.asset.read",
    "properties.asset.write",
    "properties.form.read",
    "properties.form.write",
]

DEFAULT_ROLES = [
    ("admin", "Admin", DEFAULT_PERMISSIONS),
    ("manager", "Manager", [
        "properties.site.read",
        "properties.site.write",
        "properties.tower.read",
        "properties.tower.write",
        "properties.floor.read",
        "properties.floor.write",
        "properties.unit.read",
        "properties.unit.write",
        "properties.amenity.read",
        "properties.amenity.write",
        "properties.asset.read",
        "properties.asset.write",
        "properties.form.read",
        "properties.form.write",
    ]),
    ("staff", "Staff", [
        "properties.site.read",
        "properties.tower.read",
        "properties.floor.read",
        "properties.unit.read",
        "properties.amenity.read",
        "properties.asset.read",
        "properties.form.read",
    ]),
    ("viewer", "Viewer", [
        "properties.site.read",
        "properties.tower.read",
        "properties.floor.read",
        "properties.unit.read",
    ]),
]


def seed_roles_for_scope(scope):
    """
    Seed default roles and permissions for a TenantScope.
    Idempotent: safe to call multiple times (uses get_or_create).
    """
    perm_map = {}
    for code in DEFAULT_PERMISSIONS:
        perm, _ = Permission.objects.get_or_create(
            code=code,
            defaults={"name": code, "description": ""},
        )
        perm_map[code] = perm

    for role_code, role_name, perm_codes in DEFAULT_ROLES:
        role, _ = Role.objects.get_or_create(
            scope=scope,
            code=role_code,
            defaults={"name": role_name, "is_system": True},
        )
        for perm_code in perm_codes:
            RolePermission.objects.get_or_create(
                role=role,
                permission=perm_map[perm_code],
            )
