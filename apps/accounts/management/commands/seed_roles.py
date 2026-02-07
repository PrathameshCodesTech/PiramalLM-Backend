from django.core.management.base import BaseCommand

from apps.accounts.models import TenantScope
from apps.accounts.role_utils import seed_roles_for_scope


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
            seed_roles_for_scope(scope)

        self.stdout.write(self.style.SUCCESS("Seeding complete."))
