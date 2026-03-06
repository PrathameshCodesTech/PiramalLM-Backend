from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.leases.models import Agreement


class Command(BaseCommand):
    help = "Mark ACTIVE leases whose expiry_date has passed as EXPIRED."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print how many leases would be expired without making changes.",
        )

    def handle(self, *args, **options):
        today = timezone.now().date()
        dry_run = options["dry_run"]

        qs = Agreement.objects.filter(
            status=Agreement.AgreementStatus.ACTIVE,
            expiry_date__lt=today,
        )

        count = qs.count()

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"[DRY RUN] {count} lease(s) would be marked EXPIRED."
                )
            )
            return

        updated = qs.update(status=Agreement.AgreementStatus.EXPIRED)
        self.stdout.write(
            self.style.SUCCESS(f"Expired {updated} lease(s) as of {today}.")
        )
