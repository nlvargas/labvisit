import logging
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from orders import services, slots
from orders.models import Order
from routing import planner

from .access import lab_staff_required

logger = logging.getLogger(__name__)

ACTIONS = {
    "confirm": (Order.Visit.CONFIRMED, "Visita confirmada."),
    "complete": (Order.Visit.COMPLETED, "Visita marcada como realizada."),
    "cancel": (Order.Visit.CANCELLED, "Visita cancelada. La hora quedó libre."),
    "reopen": (Order.Visit.REQUESTED, "Visita vuelta a por confirmar."),
}


def _with_totals(orders):
    for order in orders:
        exams = list(order.selected_exams())
        order.exam_names = [exam.name for exam in exams]
        order.total_clp = (services.build_quote(exams, order.coverage, order.visit_fee_clp, order.visit_discount_clp)
                           .total_clp if order.coverage else None)
    return orders


@lab_staff_required
def agenda(request):
    lab = request.lab
    today = timezone.localdate()
    start = parse_date(request.GET.get("week", "")) or today
    start -= timedelta(days=start.weekday())
    days = [start + timedelta(days=i) for i in range(7)]
    booked = _with_totals(list(
        Order.objects.filter(lab=lab, slot_start__date__gte=days[0], slot_start__date__lte=days[-1])
        .select_related("coverage").order_by("slot_start")
    ))
    by_day = {day: [] for day in days}
    for order in booked:
        by_day[timezone.localdate(order.slot_start)].append(order)
    unbooked = _with_totals(list(
        Order.objects.filter(lab=lab, slot_start__isnull=True, coverage__isnull=False, visit_fee_clp__isnull=False,
                             created_at__gte=timezone.now() - timedelta(days=14))
        .exclude(address="").select_related("coverage")[:50]
    ))
    return render(request, "panel/agenda.html", {
        "lab": lab,
        "days": [{"date": day, "label": slots.day_label(day, today), "orders": by_day[day], "is_today": day == today,
                  "has_visits": any(o.visit_status != Order.Visit.CANCELLED for o in by_day[day])}
                 for day in days],
        "week_label": f"{days[0].day} {slots.MONTHS[days[0].month - 1]} al {days[-1].day} {slots.MONTHS[days[-1].month - 1]}",
        "prev_week": (days[0] - timedelta(days=7)).isoformat(),
        "next_week": (days[0] + timedelta(days=7)).isoformat(),
        "this_week": start <= today <= days[-1],
        "unbooked": unbooked,
        "pending_count": sum(1 for o in booked if o.visit_status == Order.Visit.REQUESTED),
    })


ROUTE_COLORS = ["#2a9db0", "#d9822b", "#7a5cc7", "#3c9a5f"]


def _minutes_home(lab, stop):
    if stop.kind == "lab" or not stop.order or stop.order.latitude is None or lab.latitude is None:
        return 0
    return planner.travel_minutes(lab, (stop.order.latitude, stop.order.longitude), (lab.latitude, lab.longitude))


def _map_context(lab, orders, route=False, paths=None):
    stops = [{"lat": o.latitude, "lng": o.longitude, "title": o.patient_name or o.address}
             for o in orders if o.latitude is not None]
    lab_point = {"lat": lab.latitude, "lng": lab.longitude} if lab.latitude is not None else None
    return {"maps_key": settings.GOOGLE_MAPS_API_KEY, "maps_map_id": settings.GOOGLE_MAPS_MAP_ID,
            "map_points": {"lab": lab_point, "stops": stops, "route": route, "paths": paths}}


def _route_path(lab, stops):
    if lab.latitude is None:
        return None
    home = {"lat": lab.latitude, "lng": lab.longitude}
    points = [home]
    for stop in stops:
        if stop.kind == "lab":
            points.append(home)
        elif stop.order and stop.order.latitude is not None:
            points.append({"lat": stop.order.latitude, "lng": stop.order.longitude})
    return points + [home]


def _order(request, public_id):
    return get_object_or_404(Order.objects.select_related("coverage", "lab"), public_id=public_id, lab=request.lab)


@lab_staff_required
def order_detail(request, public_id):
    order = _order(request, public_id)
    exams = list(order.selected_exams())
    phone = "".join(ch for ch in order.contact_phone if ch.isdigit())
    return render(request, "panel/order.html", {
        "order": order,
        "quote": (services.build_quote(exams, order.coverage, order.visit_fee_clp, order.visit_discount_clp)
                  if order.coverage else None),
        "prep": services.merge_prep(exams),
        "slot_label": slots.slot_label(order.slot_start) if order.slot_start else "",
        "whatsapp_url": f"https://wa.me/{phone}" if phone else "",
        "maps_url": (f"https://www.google.com/maps/search/?api=1&query={order.latitude},{order.longitude}"
                     if order.latitude is not None else ""),
        "week": timezone.localdate(order.slot_start).isoformat() if order.slot_start else "",
        **_map_context(order.lab, [order]),
    })


@require_POST
@lab_staff_required
def order_action(request, public_id, action):
    order = _order(request, public_id)
    if action == "notes":
        order.staff_notes = request.POST.get("staff_notes", "")[:2000]
        order.save(update_fields=["staff_notes"])
        messages.success(request, "Notas guardadas.")
        return redirect("panel_order", public_id=order.public_id)
    if action not in ACTIONS or not order.is_booked:
        raise Http404
    status, message = ACTIONS[action]
    order.visit_status = status
    order.save(update_fields=["visit_status"])
    if action in ("cancel", "reopen"):
        planner.replan(order.lab, timezone.localdate(order.slot_start), planner.RoutePlan.Trigger.PANEL)
    logger.info("Panel: %s set order %s to %s", request.user.pk, order.public_id, status)
    messages.success(request, message)
    return redirect("panel_order", public_id=order.public_id)


@lab_staff_required
def order_file(request, public_id):
    order = _order(request, public_id)
    if not order.file:
        raise Http404
    return FileResponse(order.file.open("rb"), content_type=order.content_type or None)


def _maps_directions(lab, stops):
    if lab.latitude is None:
        return ""
    home = f"{lab.latitude},{lab.longitude}"
    points = [home if s.kind == "lab" else f"{s.order.latitude},{s.order.longitude}"
              for s in stops if s.kind == "lab" or (s.order and s.order.latitude is not None)]
    if not points:
        return ""
    url = f"https://www.google.com/maps/dir/?api=1&origin={home}&destination={home}&travelmode=driving"
    return url + "&waypoints=" + "|".join(points[:9])


@lab_staff_required
def route(request, day):
    lab = request.lab
    day = parse_date(day)
    if day is None:
        raise Http404
    if request.method == "POST":
        planner.replan(lab, day, planner.RoutePlan.Trigger.MANUAL)
        messages.success(request, "Ruta recalculada.")
        return redirect("panel_route", day=day.isoformat())
    plan = planner.current_plan(lab, day) or planner.replan(lab, day, planner.RoutePlan.Trigger.MANUAL)
    stops = list(plan.stops.select_related("order", "nurse"))
    for stop in stops:
        stop.service_min = (stop.departure - stop.start).total_seconds() / 60 if stop.departure else None
    groups = []
    for stop in stops:
        if not groups or groups[-1]["nurse"] != stop.nurse:
            groups.append({"nurse": stop.nurse, "stops": [], "color": ROUTE_COLORS[len(groups) % len(ROUTE_COLORS)]})
        groups[-1]["stops"].append(stop)
    for group in groups:
        timed = [s for s in group["stops"] if s.departure]
        group["back"] = (timed[-1].departure + timedelta(minutes=_minutes_home(lab, timed[-1]))) if timed else None
        group["maps_url"] = _maps_directions(lab, group["stops"])
    return render(request, "panel/route.html", {
        "lab": lab,
        "plan": plan,
        "stops": stops,
        "day_label": slots.day_label(day),
        "week": day.isoformat(),
        "late": [s for s in stops if s.late_min >= 1],
        "visit_count": sum(1 for s in stops if s.kind == "visit"),
        "groups": groups,
        "several": len(groups) > 1,
        "maps_url": _maps_directions(lab, stops) if len(groups) <= 1 else "",
        **_map_context(lab, [s.order for s in stops if s.order], route=plan.method not in ("no coordinates", "empty"),
                       paths=[{"color": g["color"], "points": _route_path(lab, g["stops"]),
                               "count": sum(1 for s in g["stops"] if s.kind == "visit")} for g in groups]),
    })
