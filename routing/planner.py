import math
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from django.utils import timezone

from labs.geo import distance_km
from orders.models import Order

from . import multi, tsptw
from .models import RoutePlan, RouteStop, SlotOffer
from .service import service_minutes

SLOT_MIN = 60


@dataclass
class Offer:
    start: datetime
    discount_clp: int = 0
    extra_min: float | None = None
    standalone_min: float | None = None


def minutes_of(moment):
    local = timezone.localtime(moment)
    return local.hour * 60 + local.minute


def moment_at(day, minutes):
    return timezone.make_aware(datetime.combine(day, time(0))) + timedelta(minutes=minutes)


def shifts_for(lab, day):
    """[(nurse, start, end)] for everyone working that day. Without nurses on file, the lab's opening hours are a
    single shift."""
    nurses = [nurse for nurse in lab.nurses.all() if nurse.is_active]
    if not nurses:
        blocks = [b for b in lab.opening_hours.all() if b.weekday == day.weekday()]
        if not blocks:
            return []
        return [(None, min(b.opens.hour * 60 + b.opens.minute for b in blocks),
                 max(b.closes.hour * 60 + b.closes.minute for b in blocks))]
    return [(nurse, *shift) for nurse in nurses if (shift := nurse.shift_on(day))]


def travel_minutes(lab, a, b):
    if a == b:
        return 0.0
    return distance_km(*a, *b) * lab.detour_factor / lab.travel_speed_kmh * 60


def day_orders(lab, day, exclude=None):
    orders = (Order.objects.filter(lab=lab, slot_start__date=day).exclude(visit_status=Order.Visit.CANCELLED)
              .order_by("slot_start", "id"))
    if exclude is not None and exclude.pk:
        orders = orders.exclude(pk=exclude.pk)
    return list(orders)


def routable(lab, orders):
    return lab.latitude is not None and lab.longitude is not None and all(
        o.latitude is not None and o.longitude is not None for o in orders)


class Problem:
    """The day's visits and travel matrix. Node 0 is the lab, node i + 1 is orders[i]."""

    def __init__(self, lab, orders, extra_point=None):
        self.lab = lab
        points = [(lab.latitude, lab.longitude)] + [(o.latitude, o.longitude) for o in orders]
        if extra_point is not None:
            points.append(extra_point)
        self.extra_node = len(points) - 1 if extra_point is not None else None
        self.travel = [[travel_minutes(lab, a, b) for b in points] for a in points]
        self.visits = [self.visit(o.pk, o.slot_start, service_minutes(o), i + 1) for i, o in enumerate(orders)]

    @staticmethod
    def visit(key, slot_start, service, node):
        opens = minutes_of(slot_start)
        return tsptw.Visit(key, opens, opens + SLOT_MIN, service, node)


@dataclass
class Frame:
    """Where the day's route can still change from: visits already done stay as they are."""
    done: list
    pending: list
    origin: int = tsptw.LAB
    time: float = 0
    oldest: float | None = None


def frame_for(lab, day, orders, problem, shift, now=None):
    """Splits the day into visits that are done or under way and visits still to plan.

    Only today has a past: a visit counts as done when it was completed, its planned start in the current plan has
    passed, or its whole slot is over. The rest is planned from the last done visit, no earlier than now.
    """
    done_by, pending, starts = multi_frames(lab, day, orders, problem, [shift or (None, 0, 24 * 60)], now)
    start = starts[0]
    return Frame(done_by[0], pending, start.origin, start.start, start.oldest)


def _solve(lab, problem, visits, frame, shift):
    return tsptw.solve(visits, problem.travel, frame.time, shift[2], lab.max_sample_age_min, frame.origin,
                       lab.drop_off_min, frame.oldest)


def discount_for(lab, order, extra, standalone):
    if not lab.discount_share or not order.distance_km or standalone <= 0:
        return 0
    value = lab.discount_share * lab.visit_fee_per_km_clp * order.distance_km * max(0.0, 1 - extra / standalone)
    value = min(math.ceil(value / 500) * 500, lab.discount_max_clp)
    return value if value >= lab.discount_min_clp else 0


def offers_for_day(lab, day, starts, order=None, exclude_order=None, now=None, taken=None):
    """Which of the candidate starts can take the order, with the discount each one earns.

    A slot is shown when TSPTW(V + c) is feasible. Its marginal cost is TSPTW(V + c) - TSPTW(V). On the same day
    both are solved from where the nurse is: after her last visit, not from the lab. When the route can't be
    computed (no coordinates), each hour takes as many visits as there are nurses working; taken counts the
    visits already booked per start.
    """
    shifts = shifts_for(lab, day)
    if len(shifts) > 1:
        return _offers_multi(lab, day, starts, shifts, order, exclude_order, now, taken)
    shift = shifts[0] if shifts else None
    if shift is None:
        return []
    starts = [s for s in starts if shift[1] <= minutes_of(s) < shift[2]]
    capacity = max(1, len(shifts))
    plain = [Offer(s) for s in starts if (taken or {}).get(s, 0) < capacity]
    if order is None or not starts or not routable(lab, [order]):
        return plain
    booked = day_orders(lab, day, exclude=exclude_order or order)
    if not routable(lab, booked):
        return plain
    problem = Problem(lab, booked, extra_point=(order.latitude, order.longitude))
    frame = frame_for(lab, day, booked, problem, shift, now)
    pending = [problem.visits[i] for i in frame.pending]
    base = _solve(lab, problem, pending, frame, shift)
    if base is None:
        return plain
    c = problem.extra_node
    standalone = problem.travel[0][c] + problem.travel[c][0]
    service = service_minutes(order)
    offers = []
    for start in starts:
        candidate = Problem.visit("new", start, service, c)
        if candidate.closes < frame.time:
            continue
        route = _solve(lab, problem, pending + [candidate], frame, shift)
        if route is None:
            continue
        extra = max(0.0, route.travel - base.travel)
        offers.append(Offer(start, discount_for(lab, order, extra, standalone), extra, standalone))
    return offers


def log_offers(order, offers, channel):
    SlotOffer.objects.bulk_create([
        SlotOffer(order=order, channel=channel, slot_start=o.start, discount_clp=o.discount_clp,
                  extra_min=o.extra_min, standalone_min=o.standalone_min)
        for o in offers
    ])


def _stops(plan, day, route, by_pk, start_sequence=0):
    return [
        RouteStop(plan=plan, nurse=plan.nurse, order=by_pk.get(leg.key), kind=leg.kind, sequence=start_sequence + i,
                  arrival=moment_at(day, leg.arrival), start=moment_at(day, leg.start),
                  departure=moment_at(day, leg.departure), travel_min=leg.travel, wait_min=leg.wait,
                  late_min=leg.late)
        for i, leg in enumerate(route.legs)
    ]


def replan(lab, day, trigger, now=None):
    """Solves the day again and stores it as the current plan. Visits already done keep their place."""
    shifts = shifts_for(lab, day)
    if len(shifts) > 1:
        return _replan_multi(lab, day, trigger, shifts, now)
    orders = day_orders(lab, day)
    shift = shifts[0] if shifts else None
    nurse = shift[0] if shift else None
    params = {"speed_kmh": lab.travel_speed_kmh, "detour": lab.detour_factor,
              "max_sample_age_min": lab.max_sample_age_min, "shift": list(shift[1:]) if shift else None,
              "lab_return_ratio": lab.lab_return_ratio, "min_lab_minutes": lab.min_lab_minutes}
    plan = RoutePlan(lab=lab, date=day, nurse=nurse, trigger=trigger, params=params)
    if not orders:
        plan.method, plan.travel_min = "empty", 0
        plan.save()
        return plan
    if not routable(lab, orders):
        plan.method, plan.feasible = "no coordinates", False
        plan.save()
        RouteStop.objects.bulk_create([RouteStop(plan=plan, order=o, sequence=i) for i, o in enumerate(orders)])
        return plan
    shift = shift or (None, 0, 24 * 60)
    problem = Problem(lab, orders)
    frame = frame_for(lab, day, orders, problem, shift, now)
    pending = [problem.visits[i] for i in frame.pending]
    route = _solve(lab, problem, pending, frame, shift)
    if route is None:
        order_by_slot = sorted(range(len(pending)), key=lambda i: pending[i].opens)
        route = tsptw.evaluate(pending, problem.travel, order_by_slot, frame.time, frame.origin,
                               oldest=frame.oldest, method="slot order")
        plan.feasible = False
    route = tsptw.add_lab_breaks(route, pending, problem.travel, frame.time, frame.origin, lab.drop_off_min,
                                 lab.lab_return_ratio, lab.min_lab_minutes, frame.oldest)
    done_route = None
    if frame.done:
        done_visits = [problem.visits[i] for i in frame.done]
        done_route = tsptw.evaluate(done_visits, problem.travel, list(range(len(done_visits))), shift[1])
    by_pk = {o.pk: o for o in orders}
    plan.method = route.method
    plan.travel_min = route.travel + (sum(leg.travel for leg in done_route.legs) if done_route else 0)
    plan.depart_at = moment_at(day, done_route.depart if done_route else route.depart)
    plan.back_at = moment_at(day, route.back)
    plan.save()
    stops = _stops(plan, day, done_route, by_pk) if done_route else []
    stops += _stops(plan, day, route, by_pk, len(stops))
    RouteStop.objects.bulk_create(stops)
    return plan


def _done_visits(lab, day, orders, now):
    """Indices of today's visits that are completed, started in the current plan, or past their slot, with the
    plan's stops by order id."""
    previous = current_plan(lab, day)
    planned = {stop.order_id: stop for stop in previous.stops.all() if stop.order_id} if previous else {}
    clock = minutes_of(now)
    done = []
    for index, order in enumerate(orders):
        stop = planned.get(order.pk)
        started = stop is not None and stop.start is not None and stop.start <= now
        over = minutes_of(order.slot_start) + SLOT_MIN <= clock
        if order.visit_status == Order.Visit.COMPLETED or started or over:
            done.append(index)
    done.sort(key=lambda i: planned[orders[i].pk].start if orders[i].pk in planned and planned[orders[i].pk].start
              else orders[i].slot_start)
    return done, planned


def multi_frames(lab, day, orders, problem, shifts, now=None):
    """Per nurse: the visits she already did today and where she continues from. Returns (done per nurse,
    pending indices, multi.Shift per nurse)."""
    starts = [multi.Shift(nurse.pk if nurse else None, start, end) for nurse, start, end in shifts]
    now = now or timezone.now()
    if day != timezone.localdate(now):
        return [[] for _ in starts], list(range(len(orders))), starts
    clock = minutes_of(now)
    done, planned = _done_visits(lab, day, orders, now)
    keys = [shift.key for shift in starts]
    done_by = [[] for _ in starts]
    for index in done:
        stop = planned.get(orders[index].pk)
        owner = keys.index(stop.nurse_id) if stop and stop.nurse_id in keys else 0
        done_by[owner].append(index)
    for shift, mine in zip(starts, done_by):
        if not mine:
            shift.start = max(shift.start, clock)
            continue
        last, first = orders[mine[-1]], orders[mine[0]]
        last_stop, first_stop = planned.get(last.pk), planned.get(first.pk)
        visit_last, visit_first = problem.visits[mine[-1]], problem.visits[mine[0]]
        leaves = minutes_of(last_stop.departure) if last_stop and last_stop.departure else \
            visit_last.opens + visit_last.service
        shift.origin, shift.start = visit_last.node, max(leaves, clock)
        shift.oldest = minutes_of(first_stop.departure) if first_stop and first_stop.departure else \
            visit_first.opens + visit_first.service
    pending = [i for i in range(len(orders)) if i not in done]
    return done_by, pending, starts


def _route_cost(visits, travel, sequence, shift):
    return tsptw.evaluate(visits, travel, sequence, shift.start, shift.origin, oldest=shift.oldest).travel


def _offers_multi(lab, day, starts, shifts, order, exclude_order, now, taken=None):
    """Several nurses. A slot is first tried with each nurse keeping her own visits (fast); when nobody can take
    it alone, the full split is solved again in case moving visits between nurses makes room."""
    first_start, last_end = min(s[1] for s in shifts), max(s[2] for s in shifts)
    starts = [s for s in starts if first_start <= minutes_of(s) < last_end]
    capacity = max(1, len(shifts))
    plain = [Offer(s) for s in starts if (taken or {}).get(s, 0) < capacity]
    if order is None or not starts or not routable(lab, [order]):
        return plain
    booked = day_orders(lab, day, exclude=exclude_order or order)
    if not routable(lab, booked):
        return plain
    problem = Problem(lab, booked, extra_point=(order.latitude, order.longitude))
    _, pending_index, nurse_shifts = multi_frames(lab, day, booked, problem, shifts, now)
    pending = [problem.visits[i] for i in pending_index]
    age = lab.max_sample_age_min
    base = multi.plan(pending, problem.travel, nurse_shifts, age)
    if base is None:
        return plain
    costs = [_route_cost(pending, problem.travel, route, shift) for route, shift in zip(base, nurse_shifts)]
    c = problem.extra_node
    standalone = problem.travel[0][c] + problem.travel[c][0]
    service = service_minutes(order)
    offers = []
    for start in starts:
        candidate = Problem.visit("new", start, service, c)
        if candidate.closes < min(shift.start for shift in nurse_shifts):
            continue
        extra = math.inf
        for route, shift, cost in zip(base, nurse_shifts, costs):
            mine = [pending[i] for i in route] + [candidate]
            solved = tsptw.solve(mine, problem.travel, shift.start, shift.end, age, shift.origin, lab.drop_off_min,
                                 shift.oldest)
            if solved is not None:
                extra = min(extra, solved.travel - cost)
        if extra == math.inf:
            routes = multi.plan(pending + [candidate], problem.travel, nurse_shifts, age)
            if routes is None:
                continue
            total = sum(_route_cost(pending + [candidate], problem.travel, r, s) for r, s in zip(routes, nurse_shifts))
            extra = total - sum(costs)
        extra = max(0.0, extra)
        offers.append(Offer(start, discount_for(lab, order, extra, standalone), extra, standalone))
    return offers


def _fallback_routes(visits, travel, shifts):
    """When no split keeps every promise: visits by slot, each to the nurse who is least late."""
    routes = [[] for _ in shifts]
    for k in sorted(range(len(visits)), key=lambda i: visits[i].opens):
        scored = []
        for index, shift in enumerate(shifts):
            trial = routes[index] + [k]
            route = tsptw.evaluate(visits, travel, trial, shift.start, shift.origin, oldest=shift.oldest)
            scored.append((route.late, route.travel, index))
        routes[min(scored)[2]].append(k)
    return routes


def _replan_multi(lab, day, trigger, shifts, now):
    orders = day_orders(lab, day)
    params = {"speed_kmh": lab.travel_speed_kmh, "detour": lab.detour_factor,
              "max_sample_age_min": lab.max_sample_age_min, "lab_return_ratio": lab.lab_return_ratio,
              "min_lab_minutes": lab.min_lab_minutes,
              "shifts": [[nurse.pk if nurse else None, start, end] for nurse, start, end in shifts]}
    plan = RoutePlan(lab=lab, date=day, trigger=trigger, params=params)
    if not orders:
        plan.method, plan.travel_min = "empty", 0
        plan.save()
        return plan
    if not routable(lab, orders):
        plan.method, plan.feasible = "no coordinates", False
        plan.save()
        RouteStop.objects.bulk_create([RouteStop(plan=plan, order=o, sequence=i) for i, o in enumerate(orders)])
        return plan
    problem = Problem(lab, orders)
    done_by, pending_index, nurse_shifts = multi_frames(lab, day, orders, problem, shifts, now)
    pending = [problem.visits[i] for i in pending_index]
    routes = multi.plan(pending, problem.travel, nurse_shifts, lab.max_sample_age_min)
    if routes is None:
        routes = _fallback_routes(pending, problem.travel, nurse_shifts)
        plan.feasible = False
    plan.method = "exact" if len(pending) <= multi.MAX_EXACT else "greedy"
    by_pk = {o.pk: o for o in orders}
    stops, total, departs, backs = [], 0.0, [], []
    for (nurse, shift_start, _), shift, route, done in zip(shifts, nurse_shifts, routes, done_by):
        legs = []
        if done:
            done_visits = [problem.visits[i] for i in done]
            done_route = tsptw.evaluate(done_visits, problem.travel, list(range(len(done))), shift_start)
            legs += done_route.legs
            total += sum(leg.travel for leg in done_route.legs)
            departs.append(done_route.depart)
        if not route and not done:
            continue
        rest = tsptw.evaluate(pending, problem.travel, route, shift.start, shift.origin, oldest=shift.oldest)
        rest = tsptw.add_lab_breaks(rest, pending, problem.travel, shift.start, shift.origin, lab.drop_off_min,
                                    lab.lab_return_ratio, lab.min_lab_minutes, shift.oldest)
        if rest.late > tsptw.EPS:
            plan.feasible = False
        legs += rest.legs
        total += rest.travel
        if not done:
            departs.append(rest.depart)
        backs.append(rest.back)
        stops += [(nurse, leg) for leg in legs]
    plan.travel_min = total
    plan.depart_at = moment_at(day, min(departs)) if departs else None
    plan.back_at = moment_at(day, max(backs)) if backs else None
    plan.save()
    sequence = {}
    rows = []
    for nurse, leg in stops:
        key = nurse.pk if nurse else None
        sequence[key] = sequence.get(key, -1) + 1
        rows.append(RouteStop(plan=plan, nurse=nurse, order=by_pk.get(leg.key), kind=leg.kind,
                              sequence=sequence[key], arrival=moment_at(day, leg.arrival),
                              start=moment_at(day, leg.start), departure=moment_at(day, leg.departure),
                              travel_min=leg.travel, wait_min=leg.wait, late_min=leg.late))
    RouteStop.objects.bulk_create(rows)
    return plan


def current_plan(lab, day):
    return RoutePlan.objects.filter(lab=lab, date=day).first()
