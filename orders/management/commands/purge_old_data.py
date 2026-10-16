import logging
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from orders.models import Order
from whatsapp.models import Conversation, Message

logger = logging.getLogger("orders")


class Command(BaseCommand):
    help = "Deletes order files, WhatsApp messages and unbooked orders older than RETENTION_DAYS."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, dry_run=False, **options):
        cutoff = timezone.now() - timedelta(days=settings.RETENTION_DAYS)
        old_files = Order.objects.filter(created_at__lt=cutoff).exclude(file="")
        unbooked = Order.objects.filter(created_at__lt=cutoff, slot_start__isnull=True)
        messages = Message.objects.filter(created_at__lt=cutoff)
        idle = Conversation.objects.filter(updated_at__lt=cutoff)
        counts = {
            "files": old_files.count(),
            "unbooked_orders": unbooked.count(),
            "messages": messages.count(),
            "conversations": idle.count(),
        }
        if not dry_run:
            for order in old_files.iterator():
                order.file.delete(save=False)
                Order.objects.filter(pk=order.pk).update(file="")
            unbooked.delete()
            messages.delete()
            idle.delete()
        logger.info("Purge before %s%s: %s", cutoff.date(), " (dry run)" if dry_run else "", counts)
        self.stdout.write(str(counts))
