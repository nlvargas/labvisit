from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from catalog.models import Coverage, Exam
from labs.models import Lab, LabMember
from orders import services, slots
from orders.models import Order


class PanelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", stdout=open("/dev/null", "w"))
        cls.lab = Lab.objects.get(slug="biodata")
        cls.other_lab = Lab.objects.create(name="Otro", slug="otro")
        cls.staff = User.objects.create_user("secretaria", password="x")
        LabMember.objects.create(lab=cls.lab, user=cls.staff)
        cls.outsider = User.objects.create_user("otro", password="x")
        LabMember.objects.create(lab=cls.other_lab, user=cls.outsider)

    def booked_order(self):
        order = Order.objects.create(
            lab=self.lab, status=Order.Status.READY, patient_name="Ana Pérez", contact_phone="+56911112222",
            coverage=Coverage.objects.get(lab=self.lab, kind="fonasa"), address="Plaza de Armas 444",
            latitude=-33.4378, longitude=-70.6505, distance_km=2.3, visit_fee_clp=19500,
        )
        services.add_exam(order, Exam.objects.get(lab=self.lab, name="Hemograma"))
        start = slots.available_slots(self.lab)[0].slots[0]
        self.assertTrue(slots.book(order, start))
        return order

    def test_requires_lab_staff(self):
        self.assertRedirects(self.client.get(reverse("panel_agenda")),
                             reverse("login") + "?next=" + reverse("panel_agenda"))
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(reverse("panel_agenda")).status_code, 403)
        order = self.booked_order()
        self.assertEqual(self.client.get(reverse("panel_order", args=[order.public_id])).status_code, 403)

    def test_agenda_and_actions(self):
        order = self.booked_order()
        unbooked = Order.objects.create(lab=self.lab, coverage=order.coverage, address="Los Leones 10",
                                        visit_fee_clp=18000, contact_phone="+56933334444")
        self.client.force_login(self.staff)
        week = timezone.localdate(order.slot_start).isoformat()
        response = self.client.get(reverse("panel_agenda") + f"?semana={week}")
        self.assertContains(response, "Ana Pérez")
        self.assertContains(response, "Por confirmar")
        self.assertContains(response, "1 visita por confirmar")
        self.assertContains(response, "+56933334444")
        self.assertContains(response, reverse("panel_order", args=[unbooked.public_id]))

        detail = self.client.get(reverse("panel_order", args=[order.public_id]))
        self.assertContains(detail, "Hemograma")
        self.assertContains(detail, "https://wa.me/56911112222")
        self.assertContains(detail, "Confirmar visita")

        url = lambda action: reverse("panel_order_action", args=[order.public_id, action])
        self.client.post(url("confirm"))
        order.refresh_from_db()
        self.assertEqual(order.visit_status, Order.Visit.CONFIRMED)
        self.client.post(url("notes"), {"staff_notes": "Llamar antes"})
        order.refresh_from_db()
        self.assertEqual(order.staff_notes, "Llamar antes")

        self.client.post(url("cancel"))
        order.refresh_from_db()
        self.assertEqual(order.visit_status, Order.Visit.CANCELLED)
        free = {s for day in slots.available_slots(self.lab) for s in day.slots}
        self.assertIn(order.slot_start, free)
        self.assertEqual(self.client.post(url("explode")).status_code, 404)

    def test_week_navigation(self):
        self.client.force_login(self.staff)
        next_monday = timezone.localdate() + timedelta(days=7 - timezone.localdate().weekday())
        response = self.client.get(reverse("panel_agenda") + f"?semana={next_monday.isoformat()}")
        self.assertContains(response, "Hoy</a>")
