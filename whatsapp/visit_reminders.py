"""The evening before a visit, a WhatsApp reminder with the time and the fasting instructions. Business days only:
on Friday it covers the visits through Monday. Sent as an approved template, because the patient may not have written
in the last 24 hours."""
import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from orders import slots
from orders.models import Order
from orders.services import merge_prep

from .client import get_client
from .flow import _order_url

logger = logging.getLogger(__name__)

# a visit booked this recently already has its confirmation on screen
RECENT_BOOKING = timedelta(hours=2)


def target_days(today):
    """Visit days covered by today's reminder: tomorrow, through the next business day."""
    days, day = [], today
    while True:
        day += timedelta(days=1)
        days.append(day)
        if day.weekday() in settings.WHATSAPP_REMINDER_WEEKDAYS:
            return days


def whatsapp_number(phone):
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) == 9 and digits.startswith("9"):
        digits = "56" + digits
    return digits if len(digits) >= 11 else ""


def due(now=None):
    """Booked visits whose reminder should go out now."""
    if not settings.WHATSAPP_VISIT_REMINDER_TEMPLATE:
        return Order.objects.none()
    now = now or timezone.now()
    local = timezone.localtime(now)
    start, end = settings.WHATSAPP_VISIT_REMINDER_HOURS
    if local.weekday() not in settings.WHATSAPP_REMINDER_WEEKDAYS or not start <= local.hour < end:
        return Order.objects.none()
    return (Order.objects
            .filter(slot_start__date__in=target_days(local.date()), visit_reminder_sent_at__isnull=True,
                    booked_at__lte=now - RECENT_BOOKING)
            .exclude(visit_status__in=[Order.Visit.CANCELLED, Order.Visit.COMPLETED])
            .exclude(lab__whatsapp_phone_number_id="")
            .exclude(contact_phone="")
            .select_related("lab"))


def parameters(order, today):
    """Template body: {{1}} lab, {{2}} day and hour, {{3}} fasting, {{4}} link to the booking."""
    local = timezone.localtime(order.slot_start)
    when = f"{slots.day_phrase(local.date(), today)}, entre {local:%H:%M} y {local + slots.SLOT:%H:%M}"
    prep = merge_prep(list(order.selected_exams()))
    fasting = slots.fasting_start(order.slot_start, prep.fasting_hours)
    prep_text = (f"Recuerda el ayuno de {prep.fasting_hours} horas: deja de comer a las {fasting}." if fasting
                 else "No necesitas ayuno.")
    return [order.lab.name, when, prep_text, _order_url(order)]


def send_visit_reminders(now=None, client=None):
    now = now or timezone.now()
    today = timezone.localdate(now)
    sent = 0
    for order in due(now):
        to = whatsapp_number(order.contact_phone)
        if not to:
            continue
        # claim the order first so two overlapping runs never send the same reminder twice
        if not Order.objects.filter(pk=order.pk, visit_reminder_sent_at__isnull=True).update(visit_reminder_sent_at=now):
            continue
        try:
            (client or get_client(order.lab)).send_template(
                to, settings.WHATSAPP_VISIT_REMINDER_TEMPLATE, settings.WHATSAPP_VISIT_REMINDER_LANGUAGE,
                parameters(order, today))
        except Exception:
            logger.exception("Order %s: visit reminder failed", order.public_id)
            Order.objects.filter(pk=order.pk).update(visit_reminder_sent_at=None)
            continue
        logger.info("Order %s: visit reminder sent", order.public_id)
        sent += 1
    return sent
