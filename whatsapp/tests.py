import hashlib
import hmac
import json
import shutil
import tempfile
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from catalog.models import Coverage
from labs.geo import Place
from labs.models import Lab
from orders import slots
from orders.models import Order

from .client import ConsoleClient
from .flow import handle_incoming
from .inbound import Incoming, parse_webhook
from .models import Conversation

MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA, READER_PROVIDER="fake", JOBS_BACKEND="sync", LAB_URL_TEMPLATE="https://{slug}.lab.test")
class FlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", stdout=open("/dev/null", "w"))
        cls.lab = Lab.objects.get(slug="biodata")

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.client_wa = ConsoleClient(output=lambda *_: None)
        self.count = 0

    def send(self, kind, **fields):
        self.count += 1
        incoming = Incoming(phone_number_id="", phone="56911112222", wa_id=f"m{self.count}", kind=kind, **fields)
        before = len(self.client_wa.sent)
        handle_incoming(incoming, client=self.client_wa, lab=self.lab)
        return self.client_wa.sent[before:]

    def conversation(self):
        return Conversation.objects.get(lab=self.lab, phone="56911112222")

    def test_full_booking_with_order_photo(self):
        greeting = self.send("text", text="hola")
        self.assertIn("foto o PDF", greeting[0]["body"])

        self.client_wa.media["img1"] = (b"fake-image", "image/jpeg")
        replies = self.send("image", media_id="img1", mime_type="image/jpeg")
        review = replies[-1]
        self.assertEqual(review["kind"], "buttons")
        self.assertIn("1. Hemograma", review["body"])
        self.assertIn("«Gl...ina»", review["body"])

        replies = self.send("text", text="quitar 1")
        self.assertNotIn("Hemograma", replies[-1]["body"])
        replies = self.send("text", text="vitamina b12")
        self.assertIn("Vitamina B12", replies[-1]["body"])

        replies = self.send("reply", reply_id="exams_ok")
        self.assertEqual(replies[-1]["kind"], "buttons")
        fonasa = Coverage.objects.get(lab=self.lab, kind="fonasa")
        replies = self.send("reply", reply_id=f"cov_{fonasa.pk}")
        self.assertEqual(replies[-1]["kind"], "location_request")

        self.send("location", latitude=-33.4378, longitude=-70.6505)
        replies = self.send("text", text="Plaza de Armas 444, depto 1203")
        quote, days = replies[-2]["body"], replies[-1]
        self.assertIn("Vitamina B12", quote)
        self.assertNotIn("Hemograma", quote)
        self.assertIn("Visita a domicilio (2,3 km): $19.500", quote)
        self.assertIn("Ayuno de 12 horas", quote)
        self.assertEqual(days["kind"], "list")
        self.assertEqual(self.conversation().state, Conversation.State.AWAIT_DAY)

        replies = self.send("reply", reply_id=days["rows"][0][0])
        hours = replies[-1]
        self.assertEqual(hours["kind"], "list")
        self.assertEqual(hours["rows"][-1][0], "other_day")
        replies = self.send("reply", reply_id=hours["rows"][0][0])
        done = replies[-1]["body"]
        self.assertIn("tu visita quedó reservada", done)
        self.assertIn("https://biodata.lab.test/order/", done)

        order = self.conversation().order
        self.assertEqual(order.channel, Order.Channel.WHATSAPP)
        self.assertEqual(order.contact_phone, "56911112222")
        self.assertEqual(order.address, "Plaza de Armas 444, depto 1203")
        self.assertTrue(order.has_details)
        self.assertTrue(order.is_booked)
        self.assertEqual(self.conversation().state, Conversation.State.DONE)

    def test_greeting_in_progress_conversation_greets_again(self):
        self.send("text", text="hola")
        replies = self.send("text", text="Hola!")
        self.assertIn("foto o PDF", replies[-1]["body"])
        replies = self.send("text", text="buenas tardes")
        self.assertIn("foto o PDF", replies[-1]["body"])
        replies = self.send("text", text="quiero agendar algo raro")
        self.assertIn("No reconocí exámenes", replies[-1]["body"])
        self.assertIsNone(self.conversation().order)

    def test_typed_exams_without_order(self):
        self.send("text", text="hola")
        self.send("reply", reply_id="no_order")
        replies = self.send("text", text="hemograma, glicemia, cariotipo")
        body = replies[-1]["body"]
        self.assertIn("1. Hemograma\n2. Glicemia", body)
        self.assertIn("«cariotipo»", body)

    def test_out_of_range_location(self):
        self.send("text", text="hola")
        self.send("text", text="hemograma")
        self.send("reply", reply_id="exams_ok")
        coverage = Coverage.objects.get(lab=self.lab, kind="fonasa")
        self.send("reply", reply_id=f"cov_{coverage.pk}")
        replies = self.send("location", latitude=-34.17, longitude=-70.74)
        self.assertIn("no llegamos", replies[-1]["body"])

    def to_location_step(self):
        self.send("text", text="hola")
        self.send("text", text="hemograma")
        self.send("reply", reply_id="exams_ok")
        coverage = Coverage.objects.get(lab=self.lab, kind="fonasa")
        self.send("reply", reply_id=f"cov_{coverage.pk}")

    @override_settings(GOOGLE_MAPS_SERVER_KEY="test")
    def test_typed_address_is_found_and_confirmed(self):
        self.to_location_step()
        place = Place(-33.4378, -70.6505, "Plaza de Armas 444, Santiago, Chile", "pid1")
        with mock.patch("whatsapp.flow.geocode", return_value=place) as geocode:
            replies = self.send("text", text="Plaza de Armas 444 depto 1203, Santiago")
        geocode.assert_called_once()
        self.assertEqual(replies[-1]["kind"], "buttons")
        self.assertIn("Plaza de Armas 444, Santiago, Chile (2,3 km", replies[-1]["body"])
        self.assertEqual(self.conversation().state, Conversation.State.CONFIRM_ADDRESS)

        replies = self.send("reply", reply_id="address_ok")
        self.assertIn("Visita a domicilio (2,3 km): $19.500", replies[-2]["body"])
        self.assertEqual(replies[-1]["kind"], "list")
        order = self.conversation().order
        self.assertEqual(order.address, "Plaza de Armas 444 depto 1203, Santiago")
        self.assertEqual(order.address_place_id, "pid1")
        self.assertTrue(order.has_details)

    @override_settings(GOOGLE_MAPS_SERVER_KEY="test")
    def test_typed_address_retry_and_not_found(self):
        self.to_location_step()
        place = Place(-33.4378, -70.6505, "Otra calle 1, Santiago", "pid2")
        with mock.patch("whatsapp.flow.geocode", return_value=place):
            self.send("text", text="otra calle 1")
        replies = self.send("reply", reply_id="address_retry")
        self.assertIn("Escribe la dirección de nuevo", replies[-1]["body"])
        with mock.patch("whatsapp.flow.geocode", return_value=None):
            replies = self.send("text", text="asdf")
        self.assertIn("No encontré esa dirección", replies[-1]["body"])
        self.assertEqual(self.conversation().state, Conversation.State.AWAIT_LOCATION)

    @override_settings(GOOGLE_MAPS_SERVER_KEY="test")
    def test_typed_address_out_of_range(self):
        self.to_location_step()
        with mock.patch("whatsapp.flow.geocode", return_value=Place(-34.17, -70.74, "Rancagua", "pid3")):
            replies = self.send("text", text="Rancagua centro")
        self.assertIn("no llegamos", replies[-1]["body"])

    @override_settings(GOOGLE_MAPS_SERVER_KEY="")
    def test_typed_address_without_geocoding_uses_base_fee(self):
        self.to_location_step()
        replies = self.send("text", text="Los Leones 100, Providencia")
        self.assertIn("Visita a domicilio: $18.000", replies[-2]["body"])

    def test_taken_slot_is_offered_again(self):
        self.to_location_step()
        self.send("location", latitude=-33.4378, longitude=-70.6505)
        replies = self.send("text", text="Plaza de Armas 444")
        replies = self.send("reply", reply_id=replies[-1]["rows"][0][0])
        slot_id = replies[-1]["rows"][0][0]
        other = Order.objects.create(lab=self.lab)
        self.assertTrue(slots.book(other, slots.parse_slot(slot_id.removeprefix("slot_"))))
        replies = self.send("reply", reply_id=slot_id)
        self.assertIn("ya no está disponible", replies[-2]["body"])
        self.assertEqual(replies[-1]["kind"], "list")
        self.assertEqual(self.conversation().state, Conversation.State.AWAIT_DAY)

    def test_restart_and_duplicates(self):
        self.send("text", text="hola")
        self.send("text", text="hemograma")
        self.assertEqual(self.conversation().state, Conversation.State.REVIEW_EXAMS)
        self.send("text", text="Reiniciar")
        self.assertEqual(self.conversation().state, Conversation.State.AWAIT_ORDER)
        incoming = Incoming(phone_number_id="", phone="56911112222", wa_id="dup", kind="text", text="glicemia")
        handle_incoming(incoming, client=self.client_wa, lab=self.lab)
        sent = len(self.client_wa.sent)
        handle_incoming(incoming, client=self.client_wa, lab=self.lab)
        self.assertEqual(len(self.client_wa.sent), sent)


WEBHOOK = {
    "object": "whatsapp_business_account",
    "entry": [{"changes": [{"field": "messages", "value": {
        "metadata": {"phone_number_id": "PNID1"},
        "messages": [
            {"from": "56911112222", "id": "wamid.1", "type": "text", "text": {"body": "hola"}},
            {"from": "56911112222", "id": "wamid.2", "type": "location",
             "location": {"latitude": -33.4, "longitude": -70.6}},
            {"from": "56911112222", "id": "wamid.3", "type": "interactive",
             "interactive": {"type": "button_reply", "button_reply": {"id": "exams_ok", "title": "Sí"}}},
        ],
    }}]}],
}


@override_settings(WHATSAPP_APP_SECRET="secret", WHATSAPP_VERIFY_TOKEN="verify", JOBS_BACKEND="sync",
                   WHATSAPP_BACKEND="console")
class WebhookTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", stdout=open("/dev/null", "w"))
        Lab.objects.filter(slug="biodata").update(whatsapp_phone_number_id="PNID1")

    def test_parse(self):
        text, location, reply = parse_webhook(WEBHOOK)
        self.assertEqual((text.kind, text.text, text.phone_number_id), ("text", "hola", "PNID1"))
        self.assertEqual((location.latitude, location.longitude), (-33.4, -70.6))
        self.assertEqual((reply.kind, reply.reply_id), ("reply", "exams_ok"))

    def test_verify_challenge(self):
        url = reverse("whatsapp_webhook")
        ok = self.client.get(url, {"hub.mode": "subscribe", "hub.verify_token": "verify", "hub.challenge": "42"})
        self.assertEqual(ok.content, b"42")
        self.assertEqual(self.client.get(url, {"hub.mode": "subscribe", "hub.verify_token": "x"}).status_code, 403)

    def test_post_requires_signature(self):
        url = reverse("whatsapp_webhook")
        body = json.dumps(WEBHOOK).encode()
        self.assertEqual(self.client.post(url, body, content_type="application/json").status_code, 403)
        signature = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()
        response = self.client.post(url, body, content_type="application/json", HTTP_X_HUB_SIGNATURE_256=signature)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Conversation.objects.filter(phone="56911112222", lab__slug="biodata").exists())

    def test_zappa_backend_gets_json_arguments(self):
        import sys
        import types

        calls = []

        def run(func, args=()):
            payload = json.loads(json.dumps(args))
            calls.append(func.__name__)
            func(*payload)

        fake = types.ModuleType("zappa.asynchronous")
        fake.run = run
        url = reverse("whatsapp_webhook")
        body = json.dumps(WEBHOOK).encode()
        signature = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()
        with mock.patch.dict(sys.modules, {"zappa": types.ModuleType("zappa"), "zappa.asynchronous": fake}), \
                self.settings(JOBS_BACKEND="zappa"):
            response = self.client.post(url, body, content_type="application/json", HTTP_X_HUB_SIGNATURE_256=signature)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls, ["handle_incoming_data"] * 3)
        self.assertTrue(Conversation.objects.filter(phone="56911112222", lab__slug="biodata").exists())


class IsapreFlowTests(FlowTests):
    def test_isapre_asks_which_one(self):
        self.send("text", text="hola")
        self.send("text", text="hemograma")
        self.send("reply", reply_id="exams_ok")
        isapre = Coverage.objects.get(lab=self.lab, kind="isapre")
        replies = self.send("reply", reply_id=f"cov_{isapre.pk}")
        self.assertEqual(replies[-1]["kind"], "list")
        self.assertIn("Banmédica", [row[1] for row in replies[-1]["rows"]])
        replies = self.send("text", text="colmena")
        self.assertEqual(replies[-1]["kind"], "location_request")
        self.assertEqual(self.conversation().order.coverage_label, "Isapre Colmena")

    def test_typing_the_isapre_name_skips_the_list(self):
        self.send("text", text="hola")
        self.send("text", text="hemograma")
        self.send("reply", reply_id="exams_ok")
        replies = self.send("text", text="Isapre Consalud")
        self.assertEqual(replies[-1]["kind"], "location_request")
        self.assertEqual(self.conversation().order.isapre, "Consalud")


@override_settings(MEDIA_ROOT=MEDIA, READER_PROVIDER="fake", JOBS_BACKEND="sync", LAB_URL_TEMPLATE="https://{slug}.lab.test")
class LateDeliveryAndReminderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", stdout=open("/dev/null", "w"))
        cls.lab = Lab.objects.get(slug="biodata")

    def setUp(self):
        self.client_wa = ConsoleClient(output=lambda *_: None)
        self.count = 0

    def send(self, text="hola", sent_at=None):
        from django.utils import timezone
        self.count += 1
        stamp = int((sent_at or timezone.now()).timestamp())
        incoming = Incoming(phone_number_id="", phone="56911112222", wa_id=f"r{self.count}", kind="text", text=text,
                            raw={"timestamp": str(stamp), "type": "text", "text": {"body": text}})
        before = len(self.client_wa.sent)
        handle_incoming(incoming, client=self.client_wa, lab=self.lab)
        return self.client_wa.sent[before:]

    def at(self, hour, minute=0, day=19):
        from datetime import datetime
        from django.utils import timezone
        return timezone.make_aware(datetime(2026, 10, day, hour, minute))

    def quiet_conversation(self, inbound, outbound, state=Conversation.State.AWAIT_ORDER):
        from whatsapp.models import Conversation as C
        conversation = C.objects.create(lab=self.lab, phone="56933334444", state=state)
        C.objects.filter(pk=conversation.pk).update(last_inbound_at=inbound, last_outbound_at=outbound)
        return conversation

    def test_late_delivery_is_stored_but_not_answered(self):
        from datetime import timedelta
        from django.utils import timezone
        from whatsapp.models import Message
        self.assertEqual(self.send(sent_at=timezone.now() - timedelta(hours=2)), [])
        self.assertEqual(Message.objects.filter(direction="in").count(), 1)

    def test_older_message_than_one_already_handled_is_ignored(self):
        from datetime import timedelta
        from django.utils import timezone
        now = timezone.now()
        self.assertTrue(self.send(sent_at=now))
        self.assertEqual(self.send(sent_at=now - timedelta(minutes=3)), [])

    def test_one_reminder_after_an_hour_then_silence(self):
        from whatsapp.reminders import send_reminders
        conversation = self.quiet_conversation(self.at(10), self.at(10, 1))
        self.assertEqual(send_reminders(self.at(10, 30), client=self.client_wa), 0)
        self.assertEqual(send_reminders(self.at(11, 5), client=self.client_wa), 1)
        self.assertIn("¿Sigues ahí?", self.client_wa.sent[-1]["body"])
        self.assertEqual(send_reminders(self.at(12, 30), client=self.client_wa), 0)
        conversation.refresh_from_db()
        self.assertIsNotNone(conversation.reminder_sent_at)

    def test_reply_clears_the_reminder(self):
        from whatsapp.models import Conversation as C
        self.send()
        conversation = C.objects.get(phone="56911112222")
        C.objects.filter(pk=conversation.pk).update(reminder_sent_at=self.at(9))
        self.send("hola de nuevo")
        conversation.refresh_from_db()
        self.assertIsNone(conversation.reminder_sent_at)
        self.assertIsNotNone(conversation.last_outbound_at)
        self.assertGreaterEqual(conversation.last_outbound_at, conversation.last_inbound_at)

    def test_no_reminder_at_night_outside_the_window_or_when_done(self):
        from whatsapp.reminders import send_reminders
        self.quiet_conversation(self.at(20, 30), self.at(20, 31))
        self.assertEqual(send_reminders(self.at(22, 0), client=self.client_wa), 0)
        self.assertEqual(send_reminders(self.at(9, 0, day=20), client=self.client_wa), 1)
        Conversation.objects.all().delete()
        self.quiet_conversation(self.at(8, 0), self.at(8, 1))
        self.assertEqual(send_reminders(self.at(9, 0, day=20), client=self.client_wa), 0)
        Conversation.objects.all().delete()
        self.quiet_conversation(self.at(10), self.at(10, 1), state=Conversation.State.DONE)
        self.assertEqual(send_reminders(self.at(12), client=self.client_wa), 0)

    def test_no_reminder_when_the_patient_spoke_last(self):
        from whatsapp.reminders import send_reminders
        self.quiet_conversation(self.at(10, 5), self.at(10))
        self.assertEqual(send_reminders(self.at(12), client=self.client_wa), 0)

    def test_reminder_links_to_the_order_once_there_is_one(self):
        from whatsapp.reminders import reminder_text
        conversation = self.quiet_conversation(self.at(10), self.at(10, 1), state=Conversation.State.AWAIT_SLOT)
        conversation.order = Order.objects.create(lab=self.lab)
        self.assertIn("https://biodata.lab.test/order/", reminder_text(conversation))
