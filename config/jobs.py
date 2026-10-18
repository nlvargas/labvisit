from django.core.management import call_command


def purge_old_data(event=None, context=None):
    """Daily schedule entry for Zappa."""
    import django

    django.setup()
    call_command("purge_old_data")


def send_whatsapp_reminders(event=None, context=None):
    """Every 10 minutes from Zappa."""
    import django

    django.setup()
    call_command("send_reminders")
