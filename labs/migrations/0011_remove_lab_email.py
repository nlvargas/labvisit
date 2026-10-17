from django.db import migrations, models


class Migration(migrations.Migration):
    """Lab.email was never used. Same approach as 0010: nullable column now, dropped later."""

    dependencies = [
        ("labs", "0010_remove_lab_visits_per_slot"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.AlterField(model_name="lab", name="email",
                                      field=models.EmailField(blank=True, max_length=254, null=True)),
            ],
            state_operations=[migrations.RemoveField(model_name="lab", name="email")],
        ),
    ]
