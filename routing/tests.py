import itertools
import random
from datetime import date, datetime, time

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from catalog.models import Exam, SampleContainer
from labs.models import Lab, LabMember, Nurse, NurseSchedule, NurseTimeOff, OpeningHours
from orders import slots
from orders.models import Order, OrderLine

from . import multi, planner, tsptw
from .models import RoutePlan, SlotOffer
from .service import estimate_minutes


def V(key, opens, closes, service, node):
    return tsptw.Visit(key, opens, closes, service, node)


def brute_force(visits, travel, start, end, max_age=None, origin=0, drop=0, oldest=None, allow_via=False):
    best = None
    n = len(visits)
    via_options = [frozenset()]
    if allow_via:
        via_options = [frozenset(p for p in range(n) if mask >> p & 1) for mask in range(1 << n)]
    for perm in itertools.permutations(range(n)):
        for via in via_options:
            route = tsptw.evaluate(visits, travel, list(perm), start, origin, via, drop, oldest)
            if tsptw.is_feasible(route, end, max_age) and (best is None or route.travel < best - 1e-9):
                best = route.travel
    return best


def random_day(rng, n):
    points = [(rng.uniform(0, 10), rng.uniform(0, 10)) for _ in range(n + 1)]
    travel = [[3 * ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** .5 for b in points] for a in points]
    visits = []
    for k in range(n):
        opens = 420 + 60 * rng.randint(0, 4)
        visits.append(V(k, opens, opens + 60, rng.choice([10, 15, 20]), k + 1))
    return visits, travel


class SolverTests(TestCase):
    def test_matches_brute_force_on_random_days(self):
        rng = random.Random(7)
        for _ in range(150):
            visits, travel = random_day(rng, rng.randint(1, 6))
            route = tsptw.solve(visits, travel, 420, 960)
            expected = brute_force(visits, travel, 420, 960)
            if expected is None:
                self.assertIsNone(route)
            else:
                self.assertAlmostEqual(route.travel, expected, places=6)

    def test_matches_brute_force_with_sample_age_and_lab_returns(self):
        rng = random.Random(11)
        for _ in range(120):
            visits, travel = random_day(rng, rng.randint(1, 5))
            max_age = rng.choice([45, 90, 150])
            route = tsptw.solve(visits, travel, 420, 960, max_age, drop=5)
            expected = brute_force(visits, travel, 420, 960, max_age, drop=5, allow_via=True)
            if expected is None:
                self.assertIsNone(route)
            else:
                self.assertAlmostEqual(route.travel, expected, places=6)
                self.assertTrue(tsptw.is_feasible(route, 960, max_age))

    def test_matches_brute_force_mid_day_from_a_patient(self):
        rng = random.Random(5)
        for _ in range(100):
            visits, travel = random_day(rng, rng.randint(2, 6))
            origin, rest = visits[0].node, visits[1:]
            start, oldest = 480 + rng.randint(0, 120), rng.choice([None, 470])
            max_age = 200 if oldest else None
            route = tsptw.solve(rest, travel, start, 960, max_age, origin, 5, oldest)
            expected = brute_force(rest, travel, start, 960, max_age, origin, 5, oldest, allow_via=bool(max_age))
            if expected is None:
                self.assertIsNone(route)
            else:
                self.assertAlmostEqual(route.travel, expected, places=6)

    def test_reorders_booked_visits_to_fit_a_new_one(self):
        points = [(0, 0), (-10, 0), (10, 0), (11, 0)]
        travel = [[abs(a[0] - b[0]) for b in points] for a in points]
        visits = [V("a", 540, 600, 5, 1), V("b", 540, 600, 5, 2), V("new", 540, 600, 5, 3)]
        route = tsptw.solve(visits, travel, 480, 960)
        self.assertEqual(route.keys[0], "a")
        self.assertEqual(route.travel, 10 + 20 + 1 + 11)

    def test_infeasible_when_windows_cannot_all_be_met(self):
        travel = [[0, 50, 50], [50, 0, 100], [50, 100, 0]]
        visits = [V(1, 540, 600, 10, 1), V(2, 540, 600, 10, 2)]
        self.assertIsNone(tsptw.solve(visits, travel, 480, 960))

    def test_sample_age_adds_a_lab_return_when_needed(self):
        travel = [[0, 5, 5], [5, 0, 1], [5, 1, 0]]
        visits = [V(1, 480, 540, 10, 1), V(2, 720, 780, 10, 2)]
        free = tsptw.solve(visits, travel, 420, 960)
        self.assertEqual([leg.kind for leg in free.legs], ["visit", "visit"])
        limited = tsptw.solve(visits, travel, 420, 960, max_age=120, drop=5)
        self.assertEqual([leg.kind for leg in limited.legs], ["visit", "lab", "visit"])
        self.assertEqual(limited.travel, free.travel + 5 + 5 - 1)

    def test_leaves_the_lab_as_late_as_possible(self):
        travel = [[0, 20], [20, 0]]
        route = tsptw.solve([V(1, 600, 660, 10, 1)], travel, 420, 960)
        self.assertEqual((route.depart, route.legs[0].arrival, route.back), (580, 600, 630))

    def test_optional_lab_return_follows_the_ratio(self):
        travel = [[0, 10, 12], [10, 0, 4], [12, 4, 0]]
        visits = [V(1, 480, 540, 10, 1), V(2, 660, 720, 10, 2)]
        route = tsptw.solve(visits, travel, 420, 960)
        self.assertEqual(route.travel, 26)
        same = tsptw.add_lab_breaks(route, visits, travel, 420, ratio=0.1, min_lab_minutes=30, drop=5)
        self.assertEqual([leg.kind for leg in same.legs], ["visit", "visit"])
        detour = tsptw.add_lab_breaks(route, visits, travel, 420, ratio=0.25, min_lab_minutes=30, drop=5)
        self.assertEqual([leg.kind for leg in detour.legs], ["visit", "lab", "visit"])
        self.assertEqual(detour.travel, 26 + 18)
        self.assertEqual([l.start for l in detour.visit_legs], [l.start for l in route.visit_legs])
        lab = detour.legs[1]
        self.assertEqual((lab.arrival, lab.departure), (500, 648))

    def test_insertion_fallback_for_big_days(self):
        n = tsptw.MAX_EXACT + 2
        travel = [[1 if i != j else 0 for j in range(n + 1)] for i in range(n + 1)]
        visits = [V(k, 420 + 30 * k, 480 + 30 * k, 5, k + 1) for k in range(n)]
        route = tsptw.solve(visits, travel, 420, 1400)
        self.assertEqual(route.method, "insertion")
        self.assertEqual(len(route.legs), n)


def brute_force_split(visits, travel, shifts, max_age=None):
    best = None
    n = len(visits)
    for assignment in itertools.product(range(len(shifts)), repeat=n):
        total = 0.0
        for index, shift in enumerate(shifts):
            subset = [visits[i] for i in range(n) if assignment[i] == index]
            route = tsptw.solve(subset, travel, shift.start, shift.end, max_age, shift.origin, oldest=shift.oldest)
            if route is None:
                total = None
                break
            total += route.travel
        if total is not None and (best is None or total < best - 1e-9):
            best = total
    return best


def plan_cost(visits, travel, shifts, routes, max_age=None):
    total = 0.0
    for shift, route in zip(shifts, routes):
        evaluated = tsptw.evaluate(visits, travel, route, shift.start, shift.origin, oldest=shift.oldest)
        assert tsptw.is_feasible(evaluated, shift.end, max_age)
        total += evaluated.travel
    return total


class MultiTests(TestCase):
    def test_split_matches_brute_force(self):
        rng = random.Random(3)
        for _ in range(60):
            n = rng.randint(1, 7)
            visits, travel = random_day(rng, n)
            shifts = [multi.Shift("a", 420, 960), multi.Shift("b", rng.choice([420, 540]), rng.choice([780, 960]))]
            routes = multi.plan(visits, travel, shifts)
            expected = brute_force_split(visits, travel, shifts)
            if expected is None:
                self.assertIsNone(routes)
            else:
                self.assertEqual(sorted(i for r in routes for i in r), list(range(n)))
                self.assertAlmostEqual(plan_cost(visits, travel, shifts, routes), expected, places=6)

    def test_three_nurses_mid_day_with_sample_age(self):
        rng = random.Random(8)
        for _ in range(25):
            visits, travel = random_day(rng, rng.randint(2, 6))
            shifts = [multi.Shift("a", 480, 960, origin=visits[0].node, oldest=470), multi.Shift("b", 480, 960),
                      multi.Shift("c", 600, 900)]
            rest = visits[1:]
            routes = multi.plan(rest, travel, shifts, max_age=240)
            expected = brute_force_split(rest, travel, shifts, max_age=240)
            if expected is None:
                self.assertIsNone(routes)
            else:
                self.assertAlmostEqual(plan_cost(rest, travel, shifts, routes, 240), expected, places=6)

    def test_two_nurses_take_simultaneous_far_visits(self):
        points = [(0, 0), (-40, 0), (40, 0)]
        travel = [[abs(a[0] - b[0]) for b in points] for a in points]
        visits = [V("west", 540, 600, 10, 1), V("east", 540, 600, 10, 2)]
        self.assertIsNone(tsptw.solve(visits, travel, 480, 960))
        routes = multi.plan(visits, travel, [multi.Shift("a", 480, 960), multi.Shift("b", 480, 960)])
        self.assertEqual(sorted(map(len, routes)), [1, 1])

    def test_greedy_for_big_days(self):
        n = multi.MAX_EXACT + 2
        travel = [[1 if i != j else 0 for j in range(n + 1)] for i in range(n + 1)]
        visits = [V(k, 420 + 25 * k, 480 + 25 * k, 10, k + 1) for k in range(n)]
        routes = multi.plan(visits, travel, [multi.Shift("a", 420, 1400), multi.Shift("b", 420, 1400)])
        self.assertEqual(sorted(i for r in routes for i in r), list(range(n)))


LAB = (-33.43519, -70.62627)


def point(east_km, north_km=0.0):
    return LAB[0] + north_km / 111.0, LAB[1] + east_km / 93.0


class PlannerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.lab = Lab.objects.create(name="Lab", slug="lab", latitude=LAB[0], longitude=LAB[1],
                                     booking_days_ahead=1, min_notice_hours=0)
        OpeningHours.objects.create(lab=cls.lab, weekday=1, opens=time(8), closes=time(13))

    def now(self):
        return timezone.make_aware(datetime(2026, 10, 19, 20))  # Monday night, offers for Tuesday

    def order(self, east_km, hour=None, **extra):
        lat, lng = point(east_km)
        order = Order.objects.create(lab=self.lab, latitude=lat, longitude=lng, distance_km=abs(east_km),
                                     address="x", visit_fee_clp=20000, **extra)
        if hour is not None:
            self.assertTrue(slots.book(order, timezone.make_aware(datetime(2026, 10, 20, hour)), now=self.now()))
        return order

    def offers(self, order):
        days = slots.available_slots(self.lab, now=self.now(), exclude_order=order, order=order)
        return {o.start.hour: o for day in days for o in day.offers}

    def test_empty_day_has_no_discounts(self):
        offers = self.offers(self.order(8))
        self.assertEqual(sorted(offers), [8, 9, 10, 11, 12])
        self.assertTrue(all(o.discount_clp == 0 for o in offers.values()))
        self.assertAlmostEqual(offers[9].extra_min, offers[9].standalone_min)

    def test_slots_next_to_a_booked_neighbour_get_a_discount(self):
        self.order(8, hour=9)
        offers = self.offers(self.order(8.5))
        self.assertGreater(offers[10].discount_clp, 0)
        self.assertEqual(offers[12].discount_clp, offers[12].discount_clp // 500 * 500)
        self.assertLess(offers[10].extra_min, offers[10].standalone_min / 2)

    def test_slots_that_break_a_promise_are_hidden(self):
        self.order(-15, hour=9)
        offers = self.offers(self.order(15))
        self.assertNotIn(9, offers)
        self.assertIn(11, offers)

    def test_booking_stores_discount_service_and_route(self):
        Order.objects.all().delete()
        first = self.order(8, hour=9)
        second = self.order(8.5)
        expected = self.offers(second)[10].discount_clp
        self.assertTrue(slots.book(second, timezone.make_aware(datetime(2026, 10, 20, 10)), now=self.now()))
        second.refresh_from_db()
        self.assertEqual(second.visit_discount_clp, expected)
        self.assertEqual(second.service_minutes, self.lab.service_base_min)
        plan = planner.current_plan(self.lab, date(2026, 10, 20))
        self.assertTrue(plan.feasible)
        self.assertEqual([s.order_id for s in plan.stops.all()], [first.pk, second.pk])
        self.assertEqual(SlotOffer.objects.count(), 0)

    def test_nurse_shift_and_time_off(self):
        nurse = Nurse.objects.create(lab=self.lab, name="Ana")
        NurseSchedule.objects.create(nurse=nurse, weekday=1, starts=time(9), ends=time(12))
        NurseTimeOff.objects.create(nurse=nurse, date=date(2026, 10, 20), starts=time(9), ends=time(10))
        offers = self.offers(self.order(2))
        self.assertEqual(sorted(offers), [10, 11])
        NurseTimeOff.objects.create(nurse=nurse, date=date(2026, 10, 20))
        self.assertEqual(self.offers(self.order(2)), {})

    def test_same_day_offers_start_after_the_last_visit(self):
        b = self.order(8.5, hour=9)
        self.order(8, hour=8)
        w = self.order(-3, hour=11)
        midday = timezone.make_aware(datetime(2026, 10, 20, 9, 40))
        new = self.order(9)
        days = slots.available_slots(self.lab, now=midday, exclude_order=new, order=new)
        offers = {o.start.hour: o for day in days for o in day.offers if o.start.date() == date(2026, 10, 20)}
        self.assertEqual(sorted(offers), [10, 11, 12])
        at = lambda o: (o.latitude, o.longitude)
        t = lambda x, y: planner.travel_minutes(self.lab, x, y)
        self.assertAlmostEqual(offers[10].extra_min, t(at(b), at(new)) + t(at(new), at(w)) - t(at(b), at(w)), places=6)

    def test_same_day_replan_keeps_done_visits_in_place(self):
        first = self.order(8, hour=8)
        second = self.order(-6, hour=9)
        third = self.order(7, hour=12)
        midday = timezone.make_aware(datetime(2026, 10, 20, 9, 30))
        late = self.order(7.5)
        self.assertTrue(slots.book(late, timezone.make_aware(datetime(2026, 10, 20, 11)), now=midday))
        plan = planner.current_plan(self.lab, date(2026, 10, 20))
        visits = [s.order_id for s in plan.stops.all() if s.kind == "visit"]
        self.assertEqual(visits[:2], [first.pk, second.pk])
        self.assertEqual(set(visits[2:]), {third.pk, late.pk})

    def test_optional_lab_return_in_the_stored_route(self):
        self.lab.lab_return_ratio = 0.5
        self.lab.min_lab_minutes = 30
        self.lab.save()
        self.order(2, hour=8)
        self.order(2.5, hour=12)
        plan = planner.current_plan(self.lab, date(2026, 10, 20))
        self.assertEqual([s.kind for s in plan.stops.all()], ["visit", "lab", "visit"])
        self.assertIsNone(plan.stops.all()[1].order)

    def test_orders_without_coordinates_fall_back_to_capacity(self):
        order = Order.objects.create(lab=self.lab, address="x")
        offers = self.offers(order)
        self.assertEqual(len(offers), 5)
        self.assertIsNone(offers[9].extra_min)


class TwoNursePlannerTests(PlannerTests):
    def setUp(self):
        for name in ("Ana", "Bea"):
            nurse = Nurse.objects.create(lab=self.lab, name=name)
            NurseSchedule.objects.create(nurse=nurse, weekday=1, starts=time(8), ends=time(13))

    def test_empty_day_has_no_discounts(self):
        offers = self.offers(self.order(8))
        self.assertEqual(sorted(offers), [8, 9, 10, 11, 12])
        self.assertTrue(all(o.discount_clp == 0 for o in offers.values()))

    def test_nurse_shift_and_time_off(self):
        pass

    def test_slots_that_break_a_promise_are_hidden(self):
        self.order(-15, hour=9)
        offers = self.offers(self.order(15))
        self.assertIn(9, offers)

    def test_same_day_replan_keeps_done_visits_in_place(self):
        first = self.order(8, hour=8)
        second = self.order(-6, hour=9)
        midday = timezone.make_aware(datetime(2026, 10, 20, 9, 30))
        late = self.order(7.5)
        self.assertTrue(slots.book(late, timezone.make_aware(datetime(2026, 10, 20, 11)), now=midday))
        plan = planner.current_plan(self.lab, date(2026, 10, 20))
        self.assertTrue(plan.feasible)
        self.assertEqual({s.order_id for s in plan.stops.all()}, {first.pk, second.pk, late.pk})

    def test_simultaneous_far_visits_go_to_different_nurses(self):
        west = self.order(-14, hour=9)
        east = self.order(14)
        offers = self.offers(east)
        self.assertIn(9, offers)
        self.assertTrue(slots.book(east, timezone.make_aware(datetime(2026, 10, 20, 9)), now=self.now()))
        plan = planner.current_plan(self.lab, date(2026, 10, 20))
        self.assertTrue(plan.feasible)
        owners = {s.order_id: s.nurse_id for s in plan.stops.all()}
        self.assertNotEqual(owners[west.pk], owners[east.pk])

    def test_offer_needs_moving_a_visit_to_the_other_nurse(self):
        a = self.order(-12, hour=9)
        b = self.order(-11, hour=10)
        far = self.order(12)
        offers = self.offers(far)
        self.assertIn(9, offers)
        self.assertIn(10, offers)

    def test_route_page_lists_each_nurse(self):
        self.order(-14, hour=9)
        self.order(14, hour=9)
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create_user("staff2", password="pw")
        LabMember.objects.create(lab=self.lab, user=user)
        self.client.force_login(user)
        with self.settings(DEFAULT_LAB_SLUG="lab"):
            page = self.client.get(reverse("panel_route", args=["2026-10-20"]))
        self.assertContains(page, "2 enfermeras")
        self.assertContains(page, "Ana")
        self.assertContains(page, "Bea")


class ServiceTests(TestCase):
    def test_counts_distinct_tubes_and_one_container(self):
        lab = Lab.objects.create(name="Lab", slug="lab")
        edta = SampleContainer.objects.create(lab=lab, name="EDTA")
        serum = SampleContainer.objects.create(lab=lab, name="Suero", minutes=3)
        exams = [
            Exam.objects.create(lab=lab, name="Hemograma", container=edta),
            Exam.objects.create(lab=lab, name="VHS", container=edta),
            Exam.objects.create(lab=lab, name="Perfil", container=serum),
            Exam.objects.create(lab=lab, name="TSH", container=serum),
            Exam.objects.create(lab=lab, name="Orina", sample_type=Exam.SampleType.URINE),
            Exam.objects.create(lab=lab, name="Urocultivo", sample_type=Exam.SampleType.URINE),
            Exam.objects.create(lab=lab, name="Sin tubo"),
        ]
        order = Order.objects.create(lab=lab)
        for i, exam in enumerate(exams):
            OrderLine.objects.create(order=order, exam=exam, position=i, selected=True)
        self.assertEqual(estimate_minutes(order), 10 + 1 + 3 + 1 + 5)


@override_settings(DEFAULT_LAB_SLUG="lab")
class RoutePanelTests(TestCase):
    def test_route_page_and_recalculate(self):
        lab = Lab.objects.create(name="Lab", slug="lab", latitude=LAB[0], longitude=LAB[1])
        user = get_user_model().objects.create_user("staff", password="pw")
        LabMember.objects.create(lab=lab, user=user)
        lat, lng = point(5)
        Order.objects.create(lab=lab, latitude=lat, longitude=lng, address="Calle 1", patient_name="Ana",
                             slot_start=timezone.make_aware(datetime(2026, 10, 20, 9)))
        self.client.force_login(user)
        url = reverse("panel_route", args=["2026-10-20"])
        response = self.client.get(url)
        self.assertContains(response, "Ruta para")
        self.assertContains(response, "Ana")
        self.assertContains(response, "google.com/maps/dir")
        with self.settings(GOOGLE_MAPS_API_KEY="k"):
            response = self.client.get(url)
        self.assertContains(response, "data-panel-map")
        self.assertContains(response, '"route": true')
        self.client.post(url)
        self.assertEqual(RoutePlan.objects.filter(lab=lab).count(), 2)


class DiscountTests(TestCase):
    def test_rounds_up_to_500_with_cap_and_minimum(self):
        lab = Lab(visit_fee_per_km_clp=500, discount_max_clp=5000, discount_min_clp=1000)
        order = Order(distance_km=8)
        self.assertEqual(planner.discount_for(lab, order, 6, 44), 3500)
        lab.discount_share = 0.5
        self.assertEqual(planner.discount_for(lab, order, 6, 44), 2000)
        lab.discount_share = 1.0
        self.assertEqual(planner.discount_for(lab, order, 44, 44), 0)
        self.assertEqual(planner.discount_for(lab, Order(distance_km=30), 0, 60), 5000)
        self.assertEqual(planner.discount_for(lab, Order(distance_km=1), 0, 10), 0)
