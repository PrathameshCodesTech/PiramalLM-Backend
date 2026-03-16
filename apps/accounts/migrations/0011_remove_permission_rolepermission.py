from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0010_add_company_entity_details_fields"),
    ]

    operations = [
        # Remove the M2M accessor on Role first (it points to the through table)
        migrations.RemoveField(
            model_name="role",
            name="permissions",
        ),
        # Drop the through table
        migrations.DeleteModel(
            name="RolePermission",
        ),
        # Drop the permission table
        migrations.DeleteModel(
            name="Permission",
        ),
    ]
