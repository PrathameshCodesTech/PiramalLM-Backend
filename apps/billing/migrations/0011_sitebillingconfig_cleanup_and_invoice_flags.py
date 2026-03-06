from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0010_invoice_gst_split"),
    ]

    operations = [
        # ── Remove duplicate-of-BillingRule fields from SiteBillingConfig ──
        migrations.RemoveField(model_name="sitebillingconfig", name="early_payment_discount_percent"),
        migrations.RemoveField(model_name="sitebillingconfig", name="early_payment_discount_days"),
        migrations.RemoveField(model_name="sitebillingconfig", name="late_fee_percent"),
        migrations.RemoveField(model_name="sitebillingconfig", name="late_fee_flat_amount"),
        migrations.RemoveField(model_name="sitebillingconfig", name="interest_rate_annual"),

        # ── Add counter_last_reset to support counter_reset_frequency ──
        migrations.AddField(
            model_name="sitebillingconfig",
            name="counter_last_reset",
            field=models.DateField(
                blank=True,
                null=True,
                help_text="Date the invoice counter was last reset",
            ),
        ),

        # ── Add is_gst_invoice + billing_address to Invoice ──
        migrations.AddField(
            model_name="invoice",
            name="is_gst_invoice",
            field=models.BooleanField(
                default=True,
                help_text="Whether this is a GST invoice (seeded from SiteBillingConfig)",
            ),
        ),
        migrations.AddField(
            model_name="invoice",
            name="billing_address",
            field=models.TextField(
                blank=True,
                help_text="Overridden billing address for this invoice",
            ),
        ),
    ]
