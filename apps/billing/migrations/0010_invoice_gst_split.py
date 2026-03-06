from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0009_remove_billingrule_rule_config_billingrule_amount_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoice",
            name="gst_type",
            field=models.CharField(
                blank=True,
                choices=[("IGST", "IGST"), ("CGST_SGST", "CGST+SGST")],
                default="",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="invoice",
            name="cgst_amount",
            field=models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14),
        ),
        migrations.AddField(
            model_name="invoice",
            name="sgst_amount",
            field=models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14),
        ),
        migrations.AddField(
            model_name="invoice",
            name="igst_amount",
            field=models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14),
        ),
    ]
