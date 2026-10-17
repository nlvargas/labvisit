from django.db import migrations

COLUMNS = ["visits_per_slot", "email"]


def drop_columns(apps, schema_editor):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        existing = {c.name for c in connection.introspection.get_table_description(cursor, "labs_lab")}
    for column in COLUMNS:
        if column in existing:
            schema_editor.execute(f"ALTER TABLE labs_lab DROP COLUMN {column}")


class Migration(migrations.Migration):
    """Drops the columns 0010 and 0011 left behind once the code no longer used them. SQLite may have removed
    them already when it rebuilt the table, so only existing ones are dropped."""

    dependencies = [
        ("labs", "0011_remove_lab_email"),
    ]

    operations = [migrations.RunPython(drop_columns, migrations.RunPython.noop)]
