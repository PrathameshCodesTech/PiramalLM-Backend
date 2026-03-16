from django.db import migrations, models
import django.db.models.deletion


def migrate_pending_to_pending_approval(apps, schema_editor):
    """Convert legacy PENDING status to PENDING_APPROVAL."""
    Agreement = apps.get_model("leases", "Agreement")
    Agreement.objects.filter(status="PENDING").update(status="PENDING_APPROVAL")


class Migration(migrations.Migration):

    dependencies = [
        ("leases", "0011_remove_clause_mapping_draft"),
        ("approvals", "0001_initial"),
    ]

    operations = [
        # Add approval_rule FK
        migrations.AddField(
            model_name="agreement",
            name="approval_rule",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="agreements",
                to="approvals.approvalrule",
            ),
        ),
        # Widen status field to hold AWAITING_WORKFLOW (17 chars) — already 20, no-op in Postgres
        # but we need to update choices
        migrations.AlterField(
            model_name="agreement",
            name="status",
            field=models.CharField(
                choices=[
                    ("DRAFT", "Draft"),
                    ("AWAITING_WORKFLOW", "Awaiting Workflow"),
                    ("PENDING_APPROVAL", "Pending Approval"),
                    ("READY_TO_ACTIVATE", "Ready to Activate"),
                    ("ACTIVE", "Active"),
                    ("EXPIRED", "Expired"),
                    ("TERMINATED", "Terminated"),
                ],
                default="DRAFT",
                max_length=20,
            ),
        ),
        # Data migration: convert any legacy PENDING records
        migrations.RunPython(
            migrate_pending_to_pending_approval,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
