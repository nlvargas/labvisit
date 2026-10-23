from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("labs", "0013_nurse_link_and_payment_button"),
    ]

    operations = [
        migrations.AddField(
            model_name="lab",
            name="fonasa_level",
            field=models.PositiveSmallIntegerField(
                blank=True, choices=[(1, "Nivel 1"), (2, "Nivel 2"), (3, "Nivel 3")], null=True,
                help_text="Fonasa MLE agreement level. Fonasa prices then come from the public tariff for each exam's "
                          "code. Blank uses the lab's own Fonasa prices."),
        ),
    ]
