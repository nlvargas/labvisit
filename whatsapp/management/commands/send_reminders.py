from django.core.management.base import BaseCommand

from whatsapp.reminders import due, send_reminders


class Command(BaseCommand):
    help = "Sends the inactivity reminder to WhatsApp conversations that are due."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, dry_run=False, **options):
        if dry_run:
            self.stdout.write(f"{len(list(due()))} due")
            return
        self.stdout.write(f"{send_reminders()} sent")
