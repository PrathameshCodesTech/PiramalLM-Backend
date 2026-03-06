from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("leases", "0009_agreement_clause_mapping_draft"),
    ]

    operations = [
        migrations.AddField(
            model_name="leaseamendment",
            name="amendment_data",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    "Machine-readable changes to apply on execute. "
                    "RENT_REVISION: {base_rent_monthly}. "
                    "TERM_EXTENSION/RENEWAL: {expiry_date, initial_term_months}. "
                    "EARLY_TERMINATION: {termination_date}. "
                    "PARTY_CHANGE: {new_tenant_id}."
                ),
            ),
        ),
    ]
