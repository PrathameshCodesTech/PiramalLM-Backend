from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clauses", "0003_clauseusage_sort_order"),
    ]

    operations = [
        # Add clause_type to Clause
        migrations.AddField(
            model_name="clause",
            name="clause_type",
            field=models.CharField(
                choices=[
                    ("TERMINATION", "Termination & Early Exit"),
                    ("RENEWAL", "Renewal Option"),
                    ("SUBLETTING", "Subletting & Signage"),
                    ("EXCLUSIVITY", "Exclusivity & Non-Compete"),
                    ("INSURANCE", "Insurance & Reinstatement"),
                    ("DISPUTE", "Dispute Resolution"),
                    ("GENERAL", "General"),
                ],
                default="GENERAL",
                help_text="Which Legal Config model this clause seeds when attached to an agreement",
                max_length=20,
            ),
        ),
        # Add active flag to ClauseUsage
        migrations.AddField(
            model_name="clauseusage",
            name="active",
            field=models.BooleanField(
                default=True,
                help_text="Whether this clause applies to this agreement",
            ),
        ),
    ]
