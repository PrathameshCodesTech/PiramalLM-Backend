from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0011_remove_permission_rolepermission"),
    ]

    operations = [
        # Remove UserProfile.role (legacy flat enum, superseded by ScopeMembership → Role)
        migrations.RemoveField(
            model_name="userprofile",
            name="role",
        ),
        # Remove unimplemented data-scope fields from Role
        migrations.RemoveField(
            model_name="role",
            name="data_scope_type",
        ),
        migrations.RemoveField(
            model_name="role",
            name="data_scope_property_ids",
        ),
    ]
