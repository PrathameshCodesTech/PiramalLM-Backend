"""
Drop deprecated fields that have been superseded by proper models:

  LeaseBilling:       grace_days, late_fee_flat, late_fee_percent,
                      interest_annual_percent
      → overdue-charge ownership moved to attached BillingRule records

  LeaseTermination:   governing_law, jurisdiction
      → replaced by the full LeaseDisputeResolution model (governing_law_country,
        governing_law_state, jurisdiction_court, exclusive_jurisdiction)
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("leases", "0012_agreement_approval_workflow"),
    ]

    operations = [
        # LeaseBilling — deprecated overdue-charge fields
        migrations.RemoveField(model_name="leasebilling", name="grace_days"),
        migrations.RemoveField(model_name="leasebilling", name="late_fee_flat"),
        migrations.RemoveField(model_name="leasebilling", name="late_fee_percent"),
        migrations.RemoveField(model_name="leasebilling", name="interest_annual_percent"),

        # LeaseTermination — deprecated law/jurisdiction stubs
        migrations.RemoveField(model_name="leasetermination", name="governing_law"),
        migrations.RemoveField(model_name="leasetermination", name="jurisdiction"),
    ]
