from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Retired. Roles are now created manually via the admin UI."

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("seed_roles is retired. Create roles via the UI."))
