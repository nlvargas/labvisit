from django.core.management import call_command


def purge_old_data(event=None, context=None):
    """Daily schedule entry for Zappa."""
    import django

    django.setup()
    call_command("purge_old_data")
