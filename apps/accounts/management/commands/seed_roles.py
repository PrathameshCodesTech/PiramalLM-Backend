from django.core.management.base import BaseCommand

from apps.accounts.models import Permission, Role, RolePermission, ScopeMembership, TenantScope


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


class Command(BaseCommand):
    help = "Seed default roles and permissions per tenant scope."

    def add_arguments(self, parser):
        parser.add_argument("--scope-id", type=int, required=False)
        parser.add_argument("--apply-to-all", action="store_true")

    def handle(self, *args, **options):
        scope_id = options.get("scope_id")
        apply_to_all = options.get("apply_to_all")

        if not scope_id and not apply_to_all:
            self.stderr.write("Provide --scope-id or --apply-to-all")
            return

        scopes = TenantScope.objects.all()
        if scope_id:
            scopes = scopes.filter(id=scope_id)

        for scope in scopes:
            self.stdout.write(f"Seeding scope {scope.id} ({scope.code})")
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

        self.stdout.write(self.style.SUCCESS("Seeding complete."))
