from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0011_order_visit_times"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="details_prefilled",
            field=models.BooleanField(default=False, help_text="Coverage or address copied from the patient's last booking."),
        ),
    ]
