from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clauses", "0002_add_section_to_clause_usage"),
    ]

    operations = [
        migrations.AddField(
            model_name="clauseusage",
            name="sort_order",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Display order of this clause within its section",
            ),
        ),
        migrations.AlterModelOptions(
            name="clauseusage",
            options={"ordering": ["sort_order", "id"], "verbose_name": "Clause Usage", "verbose_name_plural": "Clause Usages"},
        ),
    ]
