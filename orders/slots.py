from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from labs.models import Lab

from .models import Order

SLOT = timedelta(hours=1)
WEEKDAYS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
WEEKDAYS_LONG = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sept", "oct", "nov", "dic"]
MONTHS_LONG = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
               "noviembre", "diciembre"]


@dataclass
class Day:
    date: object
    slots: list

    @property
    def label(self):
        return day_label(self.date)


def day_label(day, today=None):
    today = today or timezone.localdate()
    if day == today:
        return f"Hoy {day.day} {MONTHS[day.month - 1]}"
    if day == today + timedelta(days=1):
        return f"Mañana {day.day} {MONTHS[day.month - 1]}"
    return f"{WEEKDAYS[day.weekday()]} {day.day} {MONTHS[day.month - 1]}"


def hour_label(start):
    start = timezone.localtime(start)
    return f"{start:%H:%M} a {start + SLOT:%H:%M}"


def slot_label(start):
    local = timezone.localtime(start)
    return (f"{WEEKDAYS_LONG[local.weekday()]} {local.day} de {MONTHS_LONG[local.month - 1]}, "
            f"entre {local:%H:%M} y {local + SLOT:%H:%M}")


def _candidates(lab, now):
    hours = {}
    for block in lab.opening_hours.all():
        hours.setdefault(block.weekday, []).append(block)
    earliest = now + timedelta(hours=lab.min_notice_hours)
    today = timezone.localdate(now)
    for offset in range(lab.booking_days_ahead + 1):
        day = today + timedelta(days=offset)
        for block in hours.get(day.weekday(), []):
            start = timezone.make_aware(datetime.combine(day, block.opens))
            end = timezone.make_aware(datetime.combine(day, block.closes))
            while start + SLOT <= end:
                if start >= earliest:
                    yield start
                start += SLOT


def _taken(lab, exclude_order=None):
    booked = Order.objects.filter(lab=lab, slot_start__isnull=False).exclude(visit_status=Order.Visit.CANCELLED)
    if exclude_order is not None:
        booked = booked.exclude(pk=exclude_order.pk)
    return {row["slot_start"]: row["n"] for row in booked.values("slot_start").annotate(n=Count("id"))}


def available_slots(lab, now=None, exclude_order=None):
    """Free one-hour slots grouped by day, within the lab's opening hours."""
    now = now or timezone.now()
    taken = _taken(lab, exclude_order)
    days = {}
    for start in _candidates(lab, now):
        if taken.get(start, 0) < lab.visits_per_slot:
            day = timezone.localdate(start)
            days.setdefault(day, []).append(start)
    return [Day(day, slots) for day, slots in days.items()]


def fasting_start(start, hours):
    """When the patient has to stop eating, as a readable phrase."""
    if not hours:
        return ""
    stop = timezone.localtime(start) - timedelta(hours=hours)
    day = timezone.localdate(start)
    when = "el día anterior" if stop.date() < day else "ese día"
    if stop.date() < day - timedelta(days=1):
        when = f"el {WEEKDAYS_LONG[stop.weekday()]} {stop.day}"
    return f"{stop:%H:%M} {when}"


def parse_slot(value):
    try:
        start = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return start if timezone.is_aware(start) else timezone.make_aware(start)


def book(order, start, now=None):
    """Books the slot if it's still free. Returns False when it was taken or isn't offered."""
    with transaction.atomic():
        lab = Lab.objects.select_for_update().get(pk=order.lab_id)
        free = {slot for day in available_slots(lab, now, exclude_order=order) for slot in day.slots}
        if start not in free:
            return False
        order.slot_start = start
        order.booked_at = timezone.now()
        order.visit_status = Order.Visit.REQUESTED
        order.save(update_fields=["slot_start", "booked_at", "visit_status"])
    return True
