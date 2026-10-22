import logging
import re
from datetime import timedelta

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import IntegrityError
from django.urls import reverse
from django.utils import timezone

from catalog.insurers import ISAPRES
from catalog.models import Coverage, Exam
from catalog.templatetags.money import clp
from labs.geo import distance_km, geocode, visit_fee
from labs.models import Lab
from orders import services, slots
from orders.matching import CatalogIndex, normalize, split_entry
from orders.models import Order, OrderLine
from routing import planner

from .client import get_client
from .inbound import Incoming
from .models import Conversation, Message

logger = logging.getLogger(__name__)

State = Conversation.State
RESTART_WORDS = {"reiniciar", "menu", "inicio", "empezar", "comenzar"}
GREETINGS = {"hola", "holi", "ola", "buenas", "buenos", "buen", "alo", "hi", "hello", "saludos"}
EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "application/pdf": "pdf"}


class Bot:
    def __init__(self, conversation, client):
        self.conversation = conversation
        self.client = client
        self.to = conversation.phone

    def _log(self, kind, **payload):
        Message.objects.create(conversation=self.conversation, direction=Message.Direction.OUT, kind=kind,
                               payload=payload)
        self.conversation.last_outbound_at = timezone.now()
        Conversation.objects.filter(pk=self.conversation.pk).update(last_outbound_at=self.conversation.last_outbound_at)

    def text(self, body):
        self.client.send_text(self.to, body)
        self._log("text", body=body)

    def buttons(self, body, buttons):
        self.client.send_buttons(self.to, body, buttons)
        self._log("buttons", body=body, buttons=buttons)

    def choices(self, body, label, rows):
        if len(rows) <= 3:
            self.buttons(body, rows)
        else:
            self.list(body, label, rows)

    def list(self, body, label, rows):
        self.client.send_list(self.to, body, label, rows)
        self._log("list", body=body, rows=rows)

    def location(self, body):
        self.client.request_location(self.to, body)
        self._log("location_request", body=body)


def handle_incoming_data(data):
    """Background entry point: jobs only carry JSON, so the message travels as a dict."""
    return handle_incoming(Incoming(**data))


def handle_incoming(incoming, client=None, lab=None):
    lab = lab or Lab.objects.filter(whatsapp_phone_number_id=incoming.phone_number_id, is_active=True).first()
    if lab is None:
        logger.warning("WhatsApp message for unknown phone number id %s", incoming.phone_number_id)
        return
    conversation, created = Conversation.objects.get_or_create(lab=lab, phone=incoming.phone)
    try:
        Message.objects.create(conversation=conversation, direction=Message.Direction.IN, wa_id=incoming.wa_id or None,
                               kind=incoming.kind, payload=incoming.raw or {"text": incoming.text})
    except IntegrityError:
        return
    sent_at = incoming.sent_at or timezone.now()
    if _stale(conversation, sent_at):
        logger.info("WhatsApp ...%s: ignoring a %s sent at %s (delivered late)", incoming.phone[-4:], incoming.kind,
                    sent_at.isoformat())
        return
    conversation.last_inbound_at = sent_at
    conversation.reminder_sent_at = None
    fresh = created or _expired(conversation) or conversation.state == State.DONE
    if fresh:
        _reset(conversation)
    bot = Bot(conversation, client or get_client(lab))
    logger.info("WhatsApp ...%s: %s in state %s", incoming.phone[-4:], incoming.kind, conversation.state)

    if incoming.kind == "text" and normalize(incoming.text) in RESTART_WORDS:
        _reset(conversation)
        return _greet(bot)

    handler = {
        State.AWAIT_ORDER: _await_order,
        State.REVIEW_EXAMS: _review_exams,
        State.AWAIT_COVERAGE: _await_coverage,
        State.AWAIT_ISAPRE: _await_isapre,
        State.AWAIT_LOCATION: _await_location,
        State.AWAIT_ADDRESS: _await_address,
        State.CONFIRM_ADDRESS: _confirm_address,
        State.AWAIT_DAY: _await_day,
        State.AWAIT_SLOT: _await_slot,
    }[conversation.state]
    handler(bot, conversation, incoming, fresh)
    conversation.save()


def _stale(conversation, sent_at):
    """Late deliveries: older than WHATSAPP_STALE_MINUTES, or older than a message already handled."""
    if sent_at < timezone.now() - timedelta(minutes=settings.WHATSAPP_STALE_MINUTES):
        return True
    return conversation.last_inbound_at is not None and sent_at < conversation.last_inbound_at


def _expired(conversation):
    ttl = timedelta(hours=settings.WHATSAPP_CONVERSATION_TTL_HOURS)
    return conversation.updated_at < timezone.now() - ttl


def _reset(conversation):
    conversation.state = State.AWAIT_ORDER
    conversation.order = None
    conversation.save()


def _greet(bot):
    lab = bot.conversation.lab
    bot.buttons(
        f"Hola, soy el asistente de reservas de toma de muestras a domicilio de {lab.name}. "
        "Envíame una foto o PDF de tu orden médica y te digo los exámenes y el precio.",
        [("no_order", "No tengo la orden")],
    )


def _await_order(bot, conversation, incoming, fresh):
    if incoming.kind in ("image", "document"):
        return _read_order(bot, conversation, incoming)
    if incoming.kind == "reply" and incoming.reply_id == "no_order":
        return bot.text("Escribe los exámenes que necesitas, separados por coma. Por ejemplo: hemograma, glicemia, TSH.")
    if fresh or incoming.kind != "text" or _is_greeting(incoming.text):
        return _greet(bot)
    _add_typed_exams(bot, conversation, incoming.text)


def _new_order(conversation, **fields):
    order = Order.objects.create(lab=conversation.lab, channel=Order.Channel.WHATSAPP,
                                 contact_phone=conversation.phone, **fields)
    conversation.order = order
    return order


def _read_order(bot, conversation, incoming):
    mime = incoming.mime_type.split(";")[0].strip()
    if mime not in EXTENSIONS and not mime.startswith("image/"):
        return bot.text("Envíame la orden como foto o PDF, por favor.")
    data, _ = bot.client.download_media(incoming.media_id)
    order = _new_order(conversation, content_type=mime)
    order.file.save(f"whatsapp.{EXTENSIONS.get(mime, 'jpg')}", ContentFile(data))
    bot.text("Recibí tu orden, la estoy leyendo. Esto toma unos segundos.")
    services.process_order(order.pk)
    order.refresh_from_db()
    if order.status == Order.Status.FAILED:
        return bot.text("No pude leer tu orden. Envíala de nuevo con buena luz, o escribe los exámenes separados por coma.")
    if order.error == "not_medical_order":
        return bot.text("Eso no parece una orden médica. Envíame una foto de la orden, o escribe los exámenes separados por coma.")
    _send_review(bot, conversation)


def _is_greeting(text):
    words = re.findall(r"[a-zñ]+", normalize(text))
    return bool(words) and len(words) <= 4 and words[0] in GREETINGS


def _add_typed_exams(bot, conversation, text):
    index = CatalogIndex(Exam.objects.filter(lab=conversation.lab, active=True))
    found, not_found = [], []
    for part in split_entry(text):
        result = index.match(part, settings.MATCH_SUGGEST_THRESHOLD)
        (found if result.exam_id else not_found).append(result.exam_id or part)
    if not found and conversation.order is None:
        return bot.buttons("No reconocí exámenes en tu mensaje. Envíame una foto o PDF de tu orden médica, "
                           "o escribe los exámenes separados por coma, por ejemplo: hemograma, glicemia.",
                           [("no_order", "No tengo la orden")])
    order = conversation.order or _new_order(conversation, status=Order.Status.READY)
    for exam_id in found:
        services.add_exam(order, Exam.objects.get(pk=exam_id))
    _send_review(bot, conversation, not_found)


def _selected_lines(order):
    return list(order.lines.filter(selected=True, exam__isnull=False).select_related("exam").order_by("position", "id"))


def _send_review(bot, conversation, not_found=()):
    order = conversation.order
    lines = _selected_lines(order)
    unclear = [
        f"«{line.raw_text}»" + (f" (¿{line.exam.name}?)" if line.exam_id else "")
        for line in order.lines.filter(selected=False, origin=OrderLine.Origin.INFERRED).select_related("exam")
        if line.raw_text and (line.exam_id is None or line.confidence < settings.MATCH_PRESELECT_THRESHOLD)
    ] + [f"«{text}»" for text in not_found]
    notes = ""
    if unclear:
        notes = "\n\nNo pude identificar: " + ", ".join(unclear) + ". Si los necesitas, escribe su nombre."
    if not lines:
        conversation.state = State.AWAIT_ORDER
        return bot.text("No encontré exámenes. Escríbelos separados por coma, por ejemplo: hemograma, glicemia." + notes)
    listing = "\n".join(f"{i}. {line.exam.name}" for i, line in enumerate(lines, 1))
    conversation.state = State.REVIEW_EXAMS
    bot.buttons(f"Estos son tus exámenes:\n{listing}{notes}\n\n¿Está bien?",
                [("exams_ok", "Sí, continuar"), ("exams_edit", "Quitar o agregar")])


def _review_exams(bot, conversation, incoming, fresh):
    if incoming.kind in ("image", "document"):
        return _read_order(bot, conversation, incoming)
    if incoming.kind == "reply" and incoming.reply_id == "exams_ok":
        return _ask_coverage(bot, conversation)
    if incoming.kind == "reply" and incoming.reply_id == "exams_edit":
        return bot.text("Para quitar un examen, escribe «quitar» y su número, por ejemplo: quitar 2. "
                        "Para agregar uno, escribe su nombre.")
    if incoming.kind != "text":
        return _send_review(bot, conversation)
    command = normalize(incoming.text)
    if command.startswith("quitar"):
        lines = _selected_lines(conversation.order)
        numbers = {int(n) for n in re.findall(r"\d+", command)}
        for i, line in enumerate(lines, 1):
            if i in numbers:
                line.selected = False
                line.save(update_fields=["selected"])
        return _send_review(bot, conversation)
    _add_typed_exams(bot, conversation, incoming.text)


def _ask_coverage(bot, conversation):
    conversation.state = State.AWAIT_COVERAGE
    rows = [(f"cov_{c.pk}", c.name) for c in Coverage.objects.filter(lab=conversation.lab, active=True)]
    bot.choices("¿Cuál es tu sistema previsional de salud?", "Elegir", rows)


def _match_isapre(text):
    typed = normalize(text).replace("isapre", "").strip()
    return next((name for name in ISAPRES if typed and (typed in normalize(name) or normalize(name) in typed)), None)


def _set_coverage(conversation, coverage, isapre=""):
    order = conversation.order
    order.coverage, order.isapre = coverage, isapre
    order.save(update_fields=["coverage", "isapre"])


def _await_coverage(bot, conversation, incoming, fresh):
    coverages = Coverage.objects.filter(lab=conversation.lab, active=True)
    coverage = None
    if incoming.kind == "reply" and incoming.reply_id.startswith("cov_"):
        coverage = coverages.filter(pk=incoming.reply_id.removeprefix("cov_")).first()
    elif incoming.kind == "text":
        isapre = _match_isapre(incoming.text)
        isapre_coverage = coverages.filter(kind="isapre").first()
        if isapre and isapre_coverage:
            _set_coverage(conversation, isapre_coverage, isapre)
            return _ask_location(bot, conversation)
        typed = normalize(incoming.text)
        coverage = next((c for c in coverages if typed and typed in normalize(c.name)), None)
    if coverage is None:
        return _ask_coverage(bot, conversation)
    if coverage.kind == "isapre":
        _set_coverage(conversation, coverage)
        return _ask_isapre(bot, conversation)
    _set_coverage(conversation, coverage)
    _ask_location(bot, conversation)


def _ask_isapre(bot, conversation):
    conversation.state = State.AWAIT_ISAPRE
    bot.list("¿Cuál es tu isapre?", "Elegir isapre", [(f"isapre_{i}", name) for i, name in enumerate(ISAPRES)])


def _await_isapre(bot, conversation, incoming, fresh):
    isapre = None
    if incoming.kind == "reply" and incoming.reply_id.startswith("isapre_"):
        index = incoming.reply_id.removeprefix("isapre_")
        isapre = ISAPRES[int(index)] if index.isdigit() and int(index) < len(ISAPRES) else None
    elif incoming.kind == "text":
        isapre = _match_isapre(incoming.text)
    if isapre is None:
        return _ask_isapre(bot, conversation)
    _set_coverage(conversation, conversation.order.coverage, isapre)
    _ask_location(bot, conversation)


def _ask_location(bot, conversation):
    conversation.state = State.AWAIT_LOCATION
    bot.location("¿Dónde te tomamos la muestra? Envíame la ubicación con el botón, o escribe la dirección "
                 "con número y comuna si no estás ahí ahora.")


def _set_point(order, lab, latitude, longitude):
    order.latitude, order.longitude = latitude, longitude
    order.distance_km = None
    if lab.latitude is not None:
        order.distance_km = round(distance_km(lab.latitude, lab.longitude, latitude, longitude), 1)
    order.visit_fee_clp = visit_fee(lab, order.distance_km)


def _out_of_range(bot, conversation):
    lab = conversation.lab
    conversation.state = State.DONE
    bot.text(f"Por ahora no llegamos a esa dirección: está a más de {lab.max_visit_km:g} km del laboratorio."
             + (f" Puedes llamarnos al {lab.phone}." if lab.phone else ""))


def _await_location(bot, conversation, incoming, fresh):
    order = conversation.order
    lab = conversation.lab
    if incoming.kind == "location" and incoming.latitude is not None:
        _set_point(order, lab, incoming.latitude, incoming.longitude)
        order.address_place_id = ""
        order.save(update_fields=["latitude", "longitude", "distance_km", "visit_fee_clp", "address_place_id"])
        if order.visit_fee_clp is None:
            return _out_of_range(bot, conversation)
        conversation.state = State.AWAIT_ADDRESS
        return bot.text("Gracias. Ahora escribe tu dirección exacta, con número y depto o casa si aplica, "
                        "para que la enfermera llegue sin problemas.")
    if incoming.kind == "text" and incoming.text.strip():
        return _typed_address(bot, conversation, incoming.text.strip()[:300])
    _ask_location(bot, conversation)


def _typed_address(bot, conversation, text):
    order = conversation.order
    lab = conversation.lab
    order.address = text
    if not settings.GOOGLE_MAPS_SERVER_KEY:
        order.latitude = order.longitude = order.distance_km = None
        order.visit_fee_clp = visit_fee(lab, None)
        order.save(update_fields=["address", "latitude", "longitude", "distance_km", "visit_fee_clp"])
        return _send_quote(bot, conversation)
    place = geocode(text, lab)
    if place is None:
        return bot.text("No encontré esa dirección. Escríbela con calle, número y comuna, "
                        "o envíame tu ubicación con el botón.")
    _set_point(order, lab, place.latitude, place.longitude)
    order.address_place_id = place.place_id
    order.save(update_fields=["address", "address_place_id", "latitude", "longitude", "distance_km",
                              "visit_fee_clp"])
    if order.visit_fee_clp is None:
        return _out_of_range(bot, conversation)
    conversation.state = State.CONFIRM_ADDRESS
    distance = f" ({order.distance_km:.1f} km del laboratorio)".replace(".", ",") if order.distance_km is not None else ""
    bot.buttons(f"Encontré esta dirección:\n{place.address}{distance}\n\n¿Es correcta?",
                [("address_ok", "Sí, es correcta"), ("address_retry", "No, corregir")])


def _confirm_address(bot, conversation, incoming, fresh):
    if incoming.kind == "reply" and incoming.reply_id == "address_ok":
        return _send_quote(bot, conversation)
    if incoming.kind == "reply" and incoming.reply_id == "address_retry":
        conversation.state = State.AWAIT_LOCATION
        return bot.text("Escribe la dirección de nuevo, con calle, número y comuna, o envíame tu ubicación con el botón.")
    if incoming.kind == "text" and incoming.text.strip():
        return _typed_address(bot, conversation, incoming.text.strip()[:300])
    if incoming.kind == "location" and incoming.latitude is not None:
        conversation.state = State.AWAIT_LOCATION
        return _await_location(bot, conversation, incoming, fresh)
    bot.buttons("¿La dirección es correcta?", [("address_ok", "Sí, es correcta"), ("address_retry", "No, corregir")])


def _await_address(bot, conversation, incoming, fresh):
    if incoming.kind != "text" or not incoming.text.strip():
        return bot.text("Escribe tu dirección exacta, con número y depto o casa si aplica.")
    order = conversation.order
    order.address = incoming.text.strip()[:300]
    order.save(update_fields=["address"])
    _send_quote(bot, conversation)


def _send_quote(bot, conversation):
    order = conversation.order
    exams = list(order.selected_exams())
    quote = services.build_quote(exams, order.coverage, order.visit_fee_clp)
    prep = services.merge_prep(exams)
    lines = [f"• {line.exam.name}: {clp(line.amount_clp) if line.amount_clp is not None else 'a confirmar'}"
             for line in quote.lines]
    distance = f" ({order.distance_km:.1f} km)".replace(".", ",") if order.distance_km is not None else ""
    lines.append(f"• Visita a domicilio{distance}: {clp(quote.visit_fee_clp)}")
    prep_lines = [f"• Ayuno de {prep.fasting_hours} horas. Puedes tomar agua." if prep.fasting_hours
                  else "• No necesitas ayuno."] + [f"• {text}" for text in prep.instructions]
    bot.text(f"Tu cotización con {order.coverage_label}:\n" + "\n".join(lines) + f"\n*Total: {clp(quote.total_clp)}*"
             + "\n\nCómo prepararte:\n" + "\n".join(prep_lines))
    logger.info("WhatsApp ...%s: quote sent for order %s, total %s", conversation.phone[-4:], order.public_id,
                quote.total_clp)
    _ask_day(bot, conversation)


def _order_url(order):
    return order.lab.public_url + reverse("schedule", args=[order.public_id])


def _ask_day(bot, conversation):
    days = slots.available_slots(conversation.lab, exclude_order=conversation.order, order=conversation.order)[:10]
    if not days:
        conversation.state = State.DONE
        return bot.text("No quedan horas disponibles en los próximos días. El laboratorio te escribirá para coordinar.\n\n"
                        f"Tu solicitud: {_order_url(conversation.order)}")
    conversation.state = State.AWAIT_DAY
    rows = [(f"day_{day.date.isoformat()}", day.label, _day_description(day)) for day in days]
    bot.list("¿Qué día quieres la visita?", "Elegir día", rows)


def _await_day(bot, conversation, incoming, fresh):
    if incoming.kind == "reply" and incoming.reply_id.startswith("day_"):
        chosen = incoming.reply_id.removeprefix("day_")
        day = next((d for d in slots.available_slots(conversation.lab, exclude_order=conversation.order,
                                                     order=conversation.order)
                    if d.date.isoformat() == chosen), None)
        if day:
            return _ask_slot(bot, conversation, day)
        bot.text("Ese día ya no tiene horas disponibles.")
    _ask_day(bot, conversation)


def _day_description(day):
    n = len(day.offers)
    text = f"{n} hora{'s' if n > 1 else ''} disponible{'s' if n > 1 else ''}"
    if day.best_discount:
        text += f", hasta {clp(day.best_discount)} menos"
    return text


def _ask_slot(bot, conversation, day):
    conversation.state = State.AWAIT_SLOT
    offers = day.offers[:9]
    planner.log_offers(conversation.order, offers, Order.Channel.WHATSAPP)
    rows = [(f"slot_{o.start.isoformat()}", slots.hour_label(o.start),
             f"{clp(o.discount_clp)} menos en la visita" if o.discount_clp else "") for o in offers]
    rows.append(("other_day", "Otro día"))
    body = f"¿A qué hora {slots.day_phrase(day.date)}? La enfermera llega dentro del rango que elijas."
    bot.list(body, "Elegir hora", rows)


def _await_slot(bot, conversation, incoming, fresh):
    order = conversation.order
    if incoming.kind == "reply" and incoming.reply_id.startswith("slot_"):
        start = slots.parse_slot(incoming.reply_id.removeprefix("slot_"))
        if start and slots.book(order, start):
            conversation.state = State.DONE
            logger.info("WhatsApp ...%s: booked %s for order %s", conversation.phone[-4:], start.isoformat(),
                        order.public_id)
            saving = (f" Tienes {clp(order.visit_discount_clp)} de descuento en la visita por elegir una hora en ruta."
                      if order.visit_discount_clp else "")
            return bot.text(f"Listo, tu visita quedó reservada para el {slots.slot_label(start)}.{saving}\n\n"
                            f"Puedes revisar o cambiar tu solicitud aquí: {_order_url(order)}")
        bot.text("Esa hora ya no está disponible. Elige otra.")
    _ask_day(bot, conversation)
