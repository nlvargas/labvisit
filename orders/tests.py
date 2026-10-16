import io
import shutil
import tempfile
from datetime import date, datetime, time, timedelta
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from catalog.models import Coverage, Exam
from labs.geo import distance_km, visit_fee
from labs.models import Lab, OpeningHours

from .matching import CatalogIndex, normalize, split_entry
from .models import Order, OrderLine
from .reader import FakeReader, shrink_image
from .rut import format_rut
from . import slots
from .search import suggest_exams
from . import services
from .services import build_quote, merge_prep, process_order

MEDIA = tempfile.mkdtemp()


class NormalizeTests(TestCase):
    def test_accents_case_punctuation(self):
        self.assertEqual(normalize("  Perfil Lipídico. "), "perfil lipidico")
        self.assertEqual(normalize("Ac. úrico"), "ac urico")
        self.assertEqual(normalize("V.D.R.L."), "vdrl")

    def test_split(self):
        self.assertEqual(split_entry("ELP + BUN"), ["ELP", "BUN"])
        self.assertEqual(split_entry("TSH, T4L; Glicemia"), ["TSH", "T4L", "Glicemia"])
        self.assertEqual(split_entry("Hemograma"), ["Hemograma"])


class MatchingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", stdout=open("/dev/null", "w"))
        cls.lab = Lab.objects.get(slug="biodata")
        cls.index = CatalogIndex(Exam.objects.filter(lab=cls.lab))

    def name(self, result):
        return Exam.objects.get(pk=result.exam_id).name if result.exam_id else None

    def test_exact_synonyms(self):
        for raw, expected in [("HMG", "Hemograma"), ("PBQ", "Perfil bioquímico"), ("T4L", "T4 libre"),
                              ("perfil lipídico", "Perfil lipídico"), ("Vit D", "Vitamina D")]:
            result = self.index.match(raw)
            self.assertEqual(self.name(result), expected, raw)
            self.assertEqual(result.confidence, 1.0)

    def test_fuzzy_misspelling(self):
        result = self.index.match("hemogrma completo")
        self.assertEqual(self.name(result), "Hemograma")
        self.assertGreater(result.confidence, 0.85)

    def test_unknown_exam_is_not_forced(self):
        result = self.index.match("Cariotipo")
        self.assertTrue(result.exam_id is None or result.confidence < 0.92)

    def test_digits_must_agree(self):
        self.assertEqual(self.name(self.index.match("Vitamina B12")), "Vitamina B12")
        self.assertEqual(self.name(self.index.match("Vitamina B-12")), "Vitamina B12")
        self.assertEqual(self.name(self.index.match("CA 19-9")), "CA 19-9")
        b12 = Exam.objects.get(lab=self.lab, name="Vitamina B12")
        index_without_b12 = CatalogIndex(Exam.objects.filter(lab=self.lab).exclude(pk=b12.pk))
        self.assertIsNone(index_without_b12.match("Vitamina B12").exam_id)

    def test_new_examples(self):
        for raw, expected in [("VIH", "VIH"), ("VDRL", "VDRL"), ("V.D.R.L.", "VDRL"), ("Ac. úrico", "Ácido úrico"), ("HbA1c", "Hemoglobina glicosilada")]:
            self.assertEqual(self.name(self.index.match(raw)), expected, raw)

    def test_short_abbreviation_does_not_match_loosely(self):
        result = self.index.match("XYZ")
        self.assertIsNone(result.exam_id)


@override_settings(MEDIA_ROOT=MEDIA, DEFAULT_LAB_SLUG="biodata", READER_PROVIDER="fake", JOBS_BACKEND="sync")
class FlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", stdout=open("/dev/null", "w"))
        cls.lab = Lab.objects.get(slug="biodata")
        cls.other_lab = Lab.objects.create(name="Otro", slug="otro")

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def upload(self):
        file = SimpleUploadedFile("orden.jpg", b"fake-image", content_type="image/jpeg")
        response = self.client.post(reverse("start"), {"file": file})
        order = Order.objects.get()
        self.assertRedirects(response, reverse("order", args=[order.public_id]))
        return order

    def test_upload_reads_and_preselects(self):
        order = self.upload()
        self.assertEqual(order.status, Order.Status.READY)
        selected = set(order.selected_exams().values_list("name", flat=True))
        self.assertTrue({"Hemograma", "Perfil bioquímico", "TSH", "T4 libre", "Orina completa"} <= selected)
        self.assertTrue(order.lines.filter(legible=False, selected=False).exists())
        order.coverage = Coverage.objects.get(lab=self.lab, kind="fonasa")
        order.address, order.visit_fee_clp = "Los Leones 10", 18000
        order.save()
        response = self.client.get(reverse("exams", args=[order.public_id]))
        self.assertContains(response, "leído como «HMG»")
        self.assertEqual(order.patient_rut, "11.111.111-1")
        self.assertTrue(order.patient_rut_valid)
        self.assertContains(response, "Dra. María González")
        self.assertEqual(order.doctor_rut, "12.345.678-5")

    def test_background_upload_returns_json(self):
        file = SimpleUploadedFile("orden.jpg", b"fake-image", content_type="image/jpeg")
        response = self.client.post(reverse("start"), {"file": file}, HTTP_ACCEPT="application/json")
        order = Order.objects.get()
        self.assertEqual(response.json(), {"url": reverse("order", args=[order.public_id])})
        bad = SimpleUploadedFile("orden.txt", b"hola", content_type="text/plain")
        response = self.client.post(reverse("start"), {"file": bad}, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    def test_rejects_unsupported_file(self):
        file = SimpleUploadedFile("orden.txt", b"hola", content_type="text/plain")
        response = self.client.post(reverse("start"), {"file": file})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Order.objects.exists())

    def test_toggle_add_and_quote(self):
        order = self.upload()
        line = order.lines.get(exam__name="TSH")
        self.client.post(reverse("toggle_line", args=[order.public_id, line.pk]))
        line.refresh_from_db()
        self.assertFalse(line.selected)

        insulin = Exam.objects.get(lab=self.lab, name="Insulina basal")
        self.client.post(reverse("add_exam", args=[order.public_id, insulin.pk]))
        self.assertTrue(order.lines.filter(exam=insulin, origin=OrderLine.Origin.ADDED, selected=True).exists())

        coverage = Coverage.objects.get(lab=self.lab, kind="fonasa")
        self.assertRedirects(self.client.get(reverse("schedule", args=[order.public_id])),
                             reverse("order", args=[order.public_id]))
        self.assertRedirects(self.client.get(reverse("exams", args=[order.public_id])),
                             reverse("order", args=[order.public_id]))
        response = self.client.post(reverse("order_details", args=[order.public_id]), {
            "coverage": coverage.pk, "address": "Plaza de Armas, Santiago", "apartment": "Depto 504",
            "latitude": "-33.4378", "longitude": "-70.6505",
        })
        self.assertRedirects(response, reverse("exams", args=[order.public_id]))
        order.refresh_from_db()
        self.assertAlmostEqual(order.distance_km, 2.3, delta=0.2)
        self.assertEqual(order.visit_fee_clp, 19500)
        response = self.client.get(reverse("exams", args=[order.public_id]))
        self.assertContains(response, "Revisa tus exámenes")
        self.assertContains(response, "Visita a domicilio")
        self.assertContains(response, "$19.500")
        self.assertContains(response, "Depto 504")
        self.assertContains(response, "Insulina basal")
        line = order.lines.get(exam__name="Hemograma")
        partial = self.client.post(reverse("toggle_line", args=[order.public_id, line.pk]), HTTP_HX_REQUEST="true")
        self.assertContains(partial, 'id="price" hx-swap-oob="true"')
        self.client.post(reverse("toggle_line", args=[order.public_id, line.pk]))

        response = self.client.get(reverse("schedule", args=[order.public_id]))
        self.assertContains(response, "Ayuno de 12 horas")
        self.assertContains(response, "Elige el horario")

        start = slots.available_slots(self.lab)[0].slots[0]
        response = self.client.post(reverse("book", args=[order.public_id]),
                                    {"slot": start.isoformat(), "contact_phone": "+56 9 1234 5678"})
        self.assertRedirects(response, reverse("schedule", args=[order.public_id]) + "#booking")
        order.refresh_from_db()
        self.assertEqual(order.slot_start, start)
        self.assertEqual(order.contact_phone, "+56912345678")
        self.assertContains(self.client.get(reverse("schedule", args=[order.public_id])), "Visita reservada")

        other = Order.objects.create(lab=self.lab)
        response = self.client.post(reverse("book", args=[other.public_id]),
                                    {"slot": start.isoformat(), "contact_phone": "+56 9 1234 5678"})
        self.assertEqual(response.status_code, 302)

    def test_schedule_explains_why_it_cannot_show(self):
        order = Order.objects.create(lab=self.lab, status=Order.Status.READY)
        response = self.client.get(reverse("schedule", args=[order.public_id]), follow=True)
        self.assertContains(response, "cómo vas a pagar y dónde")
        order.coverage = Coverage.objects.get(lab=self.lab, kind="fonasa")
        order.address, order.visit_fee_clp = "Los Leones 10", 18000
        order.save()
        response = self.client.get(reverse("schedule", args=[order.public_id]), follow=True)
        self.assertContains(response, "Marca al menos un examen")
        self.assertContains(response, "Revisa tus exámenes")

    def test_details_step_shows_reading_status(self):
        file = SimpleUploadedFile("orden.jpg", b"fake-image", content_type="image/jpeg")
        order = Order.objects.create(lab=self.lab, file=file, content_type="image/jpeg")
        page = self.client.get(reverse("order", args=[order.public_id]))
        self.assertContains(page, "¿Cuál es tu sistema previsional de salud?")
        self.assertContains(page, "Leyendo tu orden")
        self.assertNotContains(page, "Hemograma")
        self.assertEqual(self.client.get(reverse("order_status", args=[order.public_id])).status_code, 204)
        order.status = Order.Status.READY
        order.save()
        self.assertContains(self.client.get(reverse("order_status", args=[order.public_id])), "Leímos tu orden")

    def test_out_of_range_address_is_rejected(self):
        order = Order.objects.create(lab=self.lab, status=Order.Status.READY)
        coverage = Coverage.objects.get(lab=self.lab, kind="fonasa")
        response = self.client.post(reverse("order_details", args=[order.public_id]), {
            "coverage": coverage.pk, "address": "Rancagua", "latitude": "-34.17", "longitude": "-70.74",
        })
        self.assertContains(response, "Por ahora no llegamos a esa dirección")
        response = self.client.post(reverse("order_details", args=[order.public_id]), {
            "coverage": coverage.pk, "address": "Rancagua", "latitude": "-34.17", "longitude": "-70.74",
        }, HTTP_HX_REQUEST="true")
        self.assertContains(response, "Por ahora no llegamos")
        order.refresh_from_db()
        self.assertTrue(order.out_of_range)
        self.assertFalse(order.has_details)

    def test_search_marks_selected(self):
        order = self.upload()
        response = self.client.get(reverse("search_exams", args=[order.public_id]), {"q": "glic"})
        self.assertContains(response, "Glicemia")
        self.assertContains(response, "data-add-exam")
        response = self.client.get(reverse("search_exams", args=[order.public_id]), {"q": "hemograma"})
        self.assertContains(response, "Ya está en tu lista")

    def test_details_saved_while_reading(self):
        order = Order.objects.create(lab=self.lab, status=Order.Status.READING, content_type="image/jpeg")
        page = self.client.get(reverse("order", args=[order.public_id]))
        self.assertContains(page, "Mientras tanto")
        coverage = Coverage.objects.get(lab=self.lab, kind="isapre")
        response = self.client.post(reverse("order_details", args=[order.public_id]), {"coverage": coverage.pk},
                                    HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.coverage, coverage)
        self.assertEqual(order.address, "")

    def test_reading_keeps_details_saved_meanwhile(self):
        coverage = Coverage.objects.get(lab=self.lab, kind="fonasa")

        def read_while_patient_answers(reader_self, data, mime_type):
            Order.objects.filter(pk=order.pk).update(coverage=coverage, address="Av. Italia 1000", visit_fee_clp=19000)
            return original_read(reader_self, data, mime_type)

        original_read = FakeReader.read
        order = Order.objects.create(lab=self.lab, file=SimpleUploadedFile("o.jpg", b"x"), content_type="image/jpeg")
        with mock.patch.object(FakeReader, "read", read_while_patient_answers):
            process_order(order.pk)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.READY)
        self.assertEqual((order.coverage, order.address, order.visit_fee_clp), (coverage, "Av. Italia 1000", 19000))

    def test_order_from_other_lab_is_hidden(self):
        order = Order.objects.create(lab=self.other_lab, status=Order.Status.READY)
        response = self.client.get(reverse("order", args=[order.public_id]))
        self.assertEqual(response.status_code, 404)


class QuoteAndPrepTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", stdout=open("/dev/null", "w"))
        cls.lab = Lab.objects.get(slug="biodata")

    def test_quote_sums_and_flags_missing(self):
        coverage = Coverage.objects.get(lab=self.lab, kind="isapre")
        new = Exam.objects.create(lab=self.lab, name="Examen sin precio")
        exams = [Exam.objects.get(lab=self.lab, name="Hemograma"), Exam.objects.get(lab=self.lab, name="TSH"), new]
        quote = build_quote(exams, coverage)
        self.assertEqual(quote.total_clp, 7605 + 11130)
        self.assertEqual(build_quote(exams, coverage, 25000).total_clp, 7605 + 11130 + 25000)
        self.assertTrue(quote.missing_prices)

    def test_prep_takes_longest_fasting_and_dedupes(self):
        exams = list(Exam.objects.filter(lab=self.lab, name__in=["Glicemia", "Perfil lipídico", "Orina completa", "Urocultivo"]))
        prep = merge_prep(exams)
        self.assertEqual(prep.fasting_hours, 12)
        self.assertEqual(len(prep.instructions), 1)


class ShrinkImageTests(TestCase):
    def test_large_image_is_resized(self):
        buf = io.BytesIO()
        Image.new("RGB", (4000, 3000), "white").save(buf, "PNG")
        data, mime = shrink_image(buf.getvalue(), "image/png")
        self.assertEqual(mime, "image/jpeg")
        self.assertEqual(max(Image.open(io.BytesIO(data)).size), 2000)

    def test_pdf_untouched(self):
        self.assertEqual(shrink_image(b"%PDF", "application/pdf"), (b"%PDF", "application/pdf"))


@override_settings(MEDIA_ROOT=MEDIA, DEFAULT_LAB_SLUG="biodata", READER_PROVIDER="fake", JOBS_BACKEND="sync")
class FailureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", stdout=open("/dev/null", "w"))

    def test_failed_reading_can_be_retried(self):
        file = SimpleUploadedFile("orden.jpg", b"x", content_type="image/jpeg")
        with mock.patch("orders.reader.FakeReader.read", side_effect=TimeoutError("slow")):
            self.client.post(reverse("start"), {"file": file})
        order = Order.objects.get()
        self.assertEqual(order.status, Order.Status.FAILED)
        self.assertContains(self.client.get(reverse("order", args=[order.public_id])), "Intentar leerla de nuevo")
        self.client.post(reverse("retry_order", args=[order.public_id]))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.READY)


class RutTests(TestCase):
    def test_valid_ruts_are_formatted(self):
        self.assertEqual(format_rut("11111111-1"), "11.111.111-1")
        self.assertEqual(format_rut("12.345.678-5"), "12.345.678-5")
        self.assertEqual(format_rut("10.000.013-k"), "10.000.013-K")

    def test_invalid_or_missing(self):
        self.assertEqual(format_rut("12.345.678-9"), "")
        self.assertEqual(format_rut(""), "")
        self.assertEqual(format_rut("abc"), "")


class SuggestTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", stdout=open("/dev/null", "w"))
        cls.exams = list(Exam.objects.filter(lab__slug="biodata", active=True))

    def names(self, q):
        return [s.exam.name for s in suggest_exams(self.exams, q)]

    def test_prefix_first(self):
        self.assertEqual(self.names("glic")[0], "Glicemia")

    def test_accent_insensitive(self):
        self.assertIn("Ácido úrico", self.names("acido"))

    def test_synonym_shows_alias(self):
        suggestion = suggest_exams(self.exams, "hmg")[0]
        self.assertEqual(suggestion.exam.name, "Hemograma")
        self.assertEqual(suggestion.alias, "hmg")

    def test_exact_synonym_wins(self):
        self.assertEqual(self.names("pcr")[0], "Proteína C reactiva")

    def test_typo(self):
        self.assertIn("Hemograma", self.names("hemogrma"))

    def test_digits(self):
        self.assertEqual(self.names("b12")[0], "Vitamina B12")
        self.assertNotIn("Vitamina D", self.names("vitamina b12"))


class GeoTests(TestCase):
    def test_distance(self):
        self.assertAlmostEqual(distance_km(-33.4489, -70.6693, -33.0472, -71.6127), 98, delta=3)

    def test_visit_fee(self):
        lab = Lab(visit_base_fee_clp=18000, visit_fee_per_km_clp=500, max_visit_km=25)
        self.assertEqual(visit_fee(lab, 0.0), 18000)
        self.assertEqual(visit_fee(lab, 2.6), 19500)
        self.assertEqual(visit_fee(lab, 20.0), 28000)
        self.assertIsNone(visit_fee(lab, 30.0))
        self.assertEqual(visit_fee(lab, None), 18000)


class SlotTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.lab = Lab.objects.create(name="Lab", slug="lab", visits_per_slot=2, booking_days_ahead=2, min_notice_hours=1)
        OpeningHours.objects.create(lab=cls.lab, weekday=0, opens=time(8), closes=time(12))
        OpeningHours.objects.create(lab=cls.lab, weekday=1, opens=time(9), closes=time(11, 30))

    def now(self):
        # Monday 2026-10-19 at 09:30 in Santiago
        return timezone.make_aware(datetime(2026, 10, 19, 9, 30))

    def test_hourly_slots_within_opening_hours_and_notice(self):
        days = slots.available_slots(self.lab, now=self.now())
        self.assertEqual([d.date for d in days], [date(2026, 10, 19), date(2026, 10, 20)])
        self.assertEqual([s.hour for s in days[0].slots], [11])
        self.assertEqual([s.hour for s in days[1].slots], [9, 10])

    def test_capacity(self):
        start = timezone.make_aware(datetime(2026, 10, 20, 9))
        first, second, third = (Order.objects.create(lab=self.lab) for _ in range(3))
        self.assertTrue(slots.book(first, start, now=self.now()))
        self.assertTrue(slots.book(second, start, now=self.now()))
        self.assertFalse(slots.book(third, start, now=self.now()))
        self.assertTrue(slots.book(first, start, now=self.now()))
        self.assertFalse(slots.book(third, timezone.make_aware(datetime(2026, 10, 20, 7)), now=self.now()))

    def test_labels(self):
        start = timezone.make_aware(datetime(2026, 10, 20, 9))
        self.assertEqual(slots.hour_label(start), "09:00 a 10:00")
        self.assertEqual(slots.slot_label(start), "martes 20 de octubre, entre 09:00 y 10:00")
        self.assertEqual(slots.day_label(date(2026, 10, 22), today=date(2026, 10, 20)), "Jue 22 oct")

    @override_settings(LAB_URL_TEMPLATE="https://{slug}.lab.compile.cl")
    def test_public_url(self):
        self.assertEqual(self.lab.public_url, "https://lab.lab.compile.cl")


@override_settings(MEDIA_ROOT=MEDIA, RETENTION_DAYS=90)
class PurgeTests(TestCase):
    def test_purges_old_files_messages_and_unbooked_orders(self):
        from whatsapp.models import Conversation, Message

        lab = Lab.objects.create(name="Lab", slug="lab")
        old = timezone.now() - timedelta(days=91)
        booked = Order.objects.create(lab=lab, slot_start=timezone.now())
        booked.file.save("o.jpg", io.BytesIO(b"x"))
        unbooked = Order.objects.create(lab=lab)
        recent = Order.objects.create(lab=lab)
        Order.objects.filter(pk__in=[booked.pk, unbooked.pk]).update(created_at=old)
        conversation = Conversation.objects.create(lab=lab, phone="569")
        Message.objects.create(conversation=conversation, direction="in", kind="text")
        Message.objects.filter(conversation=conversation).update(created_at=old)
        Conversation.objects.filter(pk=conversation.pk).update(updated_at=old)

        call_command("purge_old_data", stdout=io.StringIO())

        booked.refresh_from_db()
        self.assertEqual(booked.file.name, "")
        self.assertFalse(Order.objects.filter(pk=unbooked.pk).exists())
        self.assertTrue(Order.objects.filter(pk=recent.pk).exists())
        self.assertFalse(Message.objects.exists())
        self.assertFalse(Conversation.objects.exists())


class GeminiRetryTests(TestCase):
    def make_reader(self, outcomes):
        from google.genai import errors

        from .reader import GeminiReader

        reader = GeminiReader.__new__(GeminiReader)
        reader.model, reader.fallback_models = "main", ["backup"]
        reader.rounds, reader.backoff_seconds, reader.deadline_seconds = 3, 1, 90
        calls = []

        def generate_content(model, contents, config):
            calls.append(model)
            outcome = outcomes.pop(0)
            if outcome == "busy":
                raise errors.APIError(503, {"error": {"code": 503, "message": "high demand", "status": "UNAVAILABLE"}})
            return outcome

        reader.client = mock.Mock()
        reader.client.models.generate_content.side_effect = generate_content
        return reader, calls

    def test_waits_and_retries_when_all_models_are_busy(self):
        reader, calls = self.make_reader(["busy", "busy", "busy", "ok"])
        with mock.patch("orders.reader.time.sleep") as sleep:
            response, model = reader._generate([], None)
        self.assertEqual((response, model), ("ok", "backup"))
        self.assertEqual(calls, ["main", "backup", "main", "backup"])
        sleep.assert_called_once_with(1)

    def test_gives_up_after_the_last_round(self):
        from google.genai import errors

        reader, calls = self.make_reader(["busy"] * 6)
        with mock.patch("orders.reader.time.sleep"), self.assertRaises(errors.APIError):
            reader._generate([], None)
        self.assertEqual(len(calls), 6)


class IsapreFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", stdout=open("/dev/null", "w"))
        cls.lab = Lab.objects.get(slug="biodata")

    def test_isapre_is_required_for_isapre_coverage(self):
        from .forms import OrderDetailsForm

        order = Order.objects.create(lab=self.lab, status=Order.Status.READY)
        isapre = Coverage.objects.get(lab=self.lab, kind="isapre")
        fonasa = Coverage.objects.get(lab=self.lab, kind="fonasa")
        data = {"coverage": isapre.pk, "address": "Plaza de Armas", "latitude": "-33.4378", "longitude": "-70.6505"}
        form = OrderDetailsForm(data, instance=order, lab=self.lab)
        self.assertIn("isapre", form.errors)
        form = OrderDetailsForm({**data, "isapre": "Banmédica"}, instance=order, lab=self.lab)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.save().coverage_label, "Isapre Banmédica")
        form = OrderDetailsForm({**data, "coverage": fonasa.pk, "isapre": "Banmédica"}, instance=order, lab=self.lab)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.save().isapre, "")
        self.assertFalse(Coverage.objects.filter(lab=self.lab, kind="private", active=True).exists())


class FastingAndCalendarTests(TestCase):
    def test_fasting_start(self):
        start = timezone.make_aware(datetime(2026, 10, 20, 9))
        self.assertEqual(slots.fasting_start(start, 12), "21:00 el día anterior")
        self.assertEqual(slots.fasting_start(start, 8), "01:00 ese día")
        self.assertEqual(slots.fasting_start(start, 0), "")

    def test_calendar_event(self):
        from .calendar import visit_ics
        from .services import Prep

        lab = Lab.objects.create(name="Lab", slug="lab")
        order = Order.objects.create(lab=lab, address="Plaza de Armas 444, Santiago",
                                     slot_start=timezone.make_aware(datetime(2026, 10, 20, 9)))
        ics = visit_ics(order, Prep(12, ["Llevar la orden"]))
        self.assertIn("DTSTART:20261020T120000Z", ics)
        self.assertIn("TRIGGER:-PT720M", ics)
        self.assertIn("LOCATION:Plaza de Armas 444\\, Santiago", ics)
        response = self.client.get(reverse("calendar_event", args=[order.public_id]), HTTP_HOST="lab.localhost")
        self.assertEqual(response["Content-Type"], "text/calendar; charset=utf-8")
