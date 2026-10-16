import logging
import time
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction

from catalog.models import Exam, Price

from .matching import MATCHER_VERSION, CatalogIndex, split_entry
from .models import Order, OrderLine
from .reader import get_reader
from .rut import format_rut

logger = logging.getLogger(__name__)


def process_order(order_id):
    order = Order.objects.select_related("lab").get(pk=order_id)
    order.status = Order.Status.READING
    order.save(update_fields=["status"])
    reader = get_reader()
    if reader.name == "fake":
        logger.warning("Order %s: READER_PROVIDER=fake, returning a fixed sample list without reading the file", order.public_id)
    started = time.monotonic()
    try:
        with order.file.open("rb") as fh:
            data = fh.read()
        logger.info("Order %s: reading %s (%d KB) with %s", order.public_id, order.content_type, len(data) // 1024,
                    getattr(reader, "model", reader.name))
        result = reader.read(data, order.content_type or "image/jpeg")
    except Exception as exc:
        logger.exception("Order %s: reading failed after %.1fs", order.public_id, time.monotonic() - started)
        order.status = Order.Status.FAILED
        order.error = str(exc)[:2000]
        order.save(update_fields=["status", "error"])
        return

    logger.info("Order %s: read %d entries in %.1fs (medical order: %s)", order.public_id, len(result.entries),
                time.monotonic() - started, result.is_medical_order)
    index = CatalogIndex(Exam.objects.filter(lab=order.lab, active=True))
    with transaction.atomic():
        order.lines.filter(origin=OrderLine.Origin.INFERRED).delete()
        position = 0
        for entry in result.entries:
            for part in split_entry(entry.text) or [entry.text]:
                line = OrderLine(order=order, position=position, raw_text=part[:300], legible=entry.legible)
                if entry.legible:
                    _apply_match(line, index.match(part, settings.MATCH_SUGGEST_THRESHOLD))
                line.save()
                _log_line(order, line)
                position += 1
        order.patient_name = result.patient_name.strip()[:160]
        order.patient_rut = format_rut(result.patient_rut) or result.patient_rut.strip()[:20]
        order.patient_rut_valid = bool(format_rut(result.patient_rut))
        order.doctor_name = result.doctor_name.strip()[:160]
        order.doctor_rut = format_rut(result.doctor_rut) or result.doctor_rut.strip()[:20]
        order.order_date = result.order_date.strip()[:40]
        order.extraction = result.raw
        order.reader_provider = result.provider
        order.reader_model = result.model
        order.prompt_version = result.prompt_version
        order.status = Order.Status.READY
        order.error = "" if result.is_medical_order else "not_medical_order"
        order.save(update_fields=[
            "patient_name", "patient_rut", "patient_rut_valid", "doctor_name", "doctor_rut", "order_date",
            "extraction", "reader_provider", "reader_model", "prompt_version", "status", "error",
        ])
    logger.info(
        "Order %s: patient name %s, RUT %s, doctor %s, doctor RUT %s, date %s", order.public_id,
        "found" if order.patient_name else "missing",
        "valid" if order.patient_rut_valid else ("invalid" if order.patient_rut else "missing"),
        "found" if order.doctor_name else "missing",
        "found" if order.doctor_rut else "missing",
        "found" if order.order_date else "missing",
    )


def _log_line(order, line):
    if not line.legible:
        verdict = "illegible"
    elif line.exam_id is None:
        verdict = "no match"
    else:
        verdict = f"{line.exam.name} ({line.confidence:.2f}, {'preselected' if line.selected else 'ask patient'})"
    logger.info("Order %s:   %r -> %s", order.public_id, line.raw_text, verdict)


def _apply_match(line, result):
    line.exam_id = result.exam_id
    line.confidence = result.confidence
    line.candidates = result.candidates
    line.matcher_version = MATCHER_VERSION
    line.selected = result.exam_id is not None and result.confidence >= settings.MATCH_PRESELECT_THRESHOLD


def add_exam(order, exam):
    line = order.lines.filter(exam=exam).first()
    if line:
        line.selected = True
        line.save(update_fields=["selected"])
        return line
    position = (order.lines.order_by("-position").values_list("position", flat=True).first() or 0) + 1
    return OrderLine.objects.create(
        order=order, position=position, exam=exam, confidence=1.0,
        origin=OrderLine.Origin.ADDED, selected=True,
    )


def choose_candidate(line, exam):
    line.exam = exam
    line.selected = True
    line.save(update_fields=["exam", "selected"])


@dataclass
class QuoteLine:
    exam: Exam
    amount_clp: int | None


@dataclass
class Quote:
    lines: list[QuoteLine]
    exams_clp: int
    visit_fee_clp: int
    total_clp: int
    missing_prices: bool


def build_quote(exams, coverage, visit_fee_clp=0):
    prices = dict(Price.objects.filter(exam__in=exams, coverage=coverage).values_list("exam_id", "amount_clp"))
    lines = [QuoteLine(exam, prices.get(exam.id)) for exam in exams]
    exams_clp = sum(l.amount_clp for l in lines if l.amount_clp is not None)
    visit_fee = visit_fee_clp or 0
    return Quote(
        lines=lines,
        exams_clp=exams_clp,
        visit_fee_clp=visit_fee,
        total_clp=exams_clp + visit_fee,
        missing_prices=any(l.amount_clp is None for l in lines),
    )


@dataclass
class Prep:
    fasting_hours: int
    instructions: list[str]


def merge_prep(exams):
    instructions = []
    for exam in exams:
        for text in exam.prep_text.splitlines():
            text = text.strip()
            if text and text not in instructions:
                instructions.append(text)
    return Prep(max((e.fasting_hours for e in exams), default=0), instructions)
