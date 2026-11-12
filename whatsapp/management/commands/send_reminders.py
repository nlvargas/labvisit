from django.core.management.base import BaseCommand

from whatsapp import visit_reminders
from whatsapp.reminders import due, send_reminders


class Command(BaseCommand):
    help = "Sends the inactivity reminders and the visit reminders that are due."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, dry_run=False, **options):
        if dry_run:
            self.stdout.write(f"{len(list(due()))} inactivity, {len(list(visit_reminders.due()))} visit reminders due")
            return
        self.stdout.write(f"{send_reminders()} inactivity, {visit_reminders.send_visit_reminders()} visit reminders sent")
