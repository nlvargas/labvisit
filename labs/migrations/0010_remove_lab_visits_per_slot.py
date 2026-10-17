from django.db import migrations, models


class Migration(migrations.Migration):
    """The app stops using visits_per_slot. The column stays (nullable) so the code still running during a deploy
    keeps working; a later migration can drop it."""

    dependencies = [
        ("labs", "0009_lab_drop_off_min_lab_lab_return_ratio_and_more"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.AlterField(
                    model_name="lab",
                    name="visits_per_slot",
                    field=models.PositiveSmallIntegerField(default=1, null=True),
                ),
            ],
            state_operations=[
                migrations.RemoveField(model_name="lab", name="visits_per_slot"),
            ],
        ),
    ]
