from datetime import timedelta
from statistics import median

from django.utils import timezone

from orders.models import Order
from routing import planner

# Rough front desk time per booking (transcribing the order, quoting, agreeing on a time).
DESK_MIN_PER_BOOKING = 10
OFFICE_HOURS = (9, 18)


def _avg(values):
    return sum(values) / len(values) if values else None


def _off_hours(moment):
    local = timezone.localtime(moment)
    return local.weekday() >= 5 or not OFFICE_HOURS[0] <= local.hour < OFFICE_HOURS[1]


def week_metrics(lab, days):
    first, last = days[0], days[-1]
    visits = list(Order.objects.filter(lab=lab, slot_start__date__gte=first, slot_start__date__lte=last)
                  .exclude(visit_status=Order.Visit.CANCELLED))

    travel, nurse_days, planned = 0.0, 0, 0
    for day in days:
        if not any(timezone.localdate(o.slot_start) == day for o in visits):
            continue
        plan = planner.current_plan(lab, day)
        if plan is None or plan.travel_min is None:
            continue
        stops = [s for s in plan.stops.all() if s.kind == "visit"]
        travel += plan.travel_min
        nurse_days += len({s.nurse_id for s in stops})
        planned += len(stops)

    timed = [o for o in visits if o.arrived_at and o.completed_at]
    real_service = [(o.completed_at - o.arrived_at).total_seconds() / 60 for o in timed]
    estimated_service = [o.service_minutes for o in timed if o.service_minutes]
    arrived = [o for o in visits if o.arrived_at]
    on_time = [o for o in arrived if o.arrived_at <= o.slot_start + timedelta(minutes=planner.SLOT_MIN)]

    booked = list(Order.objects.filter(lab=lab, booked_at__date__gte=first, booked_at__date__lte=last))
    quotes = list(Order.objects.filter(lab=lab, created_at__date__gte=first, created_at__date__lte=last,
                                       coverage__isnull=False, visit_fee_clp__isnull=False))
    quotes_booked = [o for o in quotes if o.booked_at]
    to_book = [(o.booked_at - o.created_at).total_seconds() / 60 for o in quotes_booked]
    discounted = [o for o in visits if o.visit_discount_clp]

    return {
        "visits": len(visits),
        "completed": sum(1 for o in visits if o.visit_status == Order.Visit.COMPLETED),
        "nurse_days": nurse_days,
        "visits_per_nurse_day": planned / nurse_days if nurse_days else None,
        "travel_per_nurse_day": travel / nurse_days if nurse_days else None,
        "travel_per_visit": travel / planned if planned else None,
        "travel_total": travel,
        "timed": len(timed),
        "real_service": _avg(real_service),
        "estimated_service": _avg(estimated_service),
        "arrived": len(arrived),
        "on_time_share": len(on_time) / len(arrived) if arrived else None,
        "bookings": len(booked),
        "bookings_whatsapp": sum(1 for o in booked if o.channel == Order.Channel.WHATSAPP),
        "bookings_off_hours": sum(1 for o in booked if _off_hours(o.booked_at)),
        "desk_hours": len(booked) * DESK_MIN_PER_BOOKING / 60,
        "desk_min_per_booking": DESK_MIN_PER_BOOKING,
        "quotes": len(quotes),
        "conversion": len(quotes_booked) / len(quotes) if quotes else None,
        "median_to_book": median(to_book) if to_book else None,
        "discounted": len(discounted),
        "discount_total": sum(o.visit_discount_clp for o in discounted),
    }
