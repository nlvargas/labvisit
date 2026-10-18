import logging

from django.conf import settings
from django.contrib import messages
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from catalog.models import Exam
from routing import planner

from . import jobs, services, slots
from .calendar import visit_ics
from .forms import BookingForm, OrderDetailsForm, OrderUploadForm
from .matching import CatalogIndex, normalize
from .models import Order
from .search import suggest_exams

logger = logging.getLogger(__name__)


def _lab(request):
    if request.lab is None:
        raise Http404("Lab not found")
    return request.lab


def _order(request, public_id):
    return get_object_or_404(Order, public_id=public_id, lab=_lab(request))


def _lines_context(order):
    lines = list(order.lines.select_related("exam"))
    ids = {c["exam_id"] for line in lines for c in line.candidates}
    exams = Exam.objects.in_bulk(ids)
    for line in lines:
        line.suggestions = [exams[c["exam_id"]] for c in line.candidates if c["exam_id"] in exams]
        line.show_source = bool(line.raw_text) and line.exam_id is not None and (
            normalize(line.raw_text) != normalize(line.exam.name)
        )
        line.needs_confirmation = (
            not line.selected and line.exam_id is not None
            and line.confidence < settings.MATCH_PRESELECT_THRESHOLD
        )
    with_exam = [line for line in lines if line.exam_id]
    selected = [line.exam for line in with_exam if line.selected]
    return {
        "order": order,
        "lines": lines,
        "exam_count": len(with_exam),
        "selected_count": len(selected),
        "quote": services.build_quote(selected, order.coverage, order.visit_fee_clp,
                                       order.visit_discount_clp) if order.coverage else None,
    }


def start(request):
    lab = _lab(request)
    form = OrderUploadForm(request.POST or None, request.FILES or None)
    wants_json = "application/json" in request.headers.get("Accept", "")
    if request.method == "POST" and form.is_valid():
        upload = form.cleaned_data["file"]
        order = Order.objects.create(lab=lab, file=upload, content_type=upload.content_type)
        logger.info("Order %s: uploaded %r (%s, %d KB) for lab %s", order.public_id, upload.name,
                    upload.content_type, upload.size // 1024, lab.slug)
        jobs.enqueue(services.process_order, order.pk)
        if wants_json:
            return JsonResponse({"url": reverse("order", args=[order.public_id])})
        return redirect("order", public_id=order.public_id)
    if request.method == "POST":
        logger.info("Upload rejected: %s", form.errors.as_text().replace("\n", " "))
        if wants_json:
            return JsonResponse({"error": form.errors["file"][0]}, status=400)
    return render(request, "orders/start.html", {"form": form})


@require_POST
def start_manual(request):
    order = Order.objects.create(lab=_lab(request), status=Order.Status.READY)
    logger.info("Order %s: started without a file", order.public_id)
    return redirect("order", public_id=order.public_id)


def order_detail(request, public_id):
    """Step 2: coverage and address, filled in while the order is being read."""
    order = _order(request, public_id)
    context = {"order": order, "details_form": OrderDetailsForm(instance=order, lab=order.lab)}
    if order.is_manual:
        context.update(_lines_context(order))
    context.update(_maps_context(order))
    return render(request, "orders/details.html", context)


def _maps_context(order):
    lab = order.lab
    return {
        "maps_key": settings.GOOGLE_MAPS_API_KEY,
        "maps_map_id": settings.GOOGLE_MAPS_MAP_ID,
        "lab_lat": lab.latitude,
        "lab_lng": lab.longitude,
    }


@require_POST
def order_details(request, public_id):
    order = _order(request, public_id)
    partial = request.headers.get("HX-Request") == "true"
    form = OrderDetailsForm(request.POST, instance=order, lab=order.lab, require_all=not partial)
    if form.is_valid():
        form.save()
        logger.info("Order %s: details set (coverage %s, address %s, %s km, visit $%s)", order.public_id,
                    order.coverage, "set" if order.address else "missing", order.distance_km, order.visit_fee_clp)
        if partial:
            return render(request, "orders/partials/details_saved.html", {"order": order})
        return redirect("exams", public_id=order.public_id)
    if partial:
        return render(request, "orders/partials/details_saved.html", {"order": order, "form": form})
    context = {"order": order, "details_form": form}
    if order.is_manual:
        context.update(_lines_context(order))
    context.update(_maps_context(order))
    return render(request, "orders/details.html", context)


def exams(request, public_id):
    """Step 3: the exams read from the order and the final price."""
    order = _order(request, public_id)
    if not order.has_details:
        messages.info(request, "Cuéntanos cómo vas a pagar y dónde te tomamos la muestra.")
        return redirect("order", public_id=order.public_id)
    return render(request, "orders/exams.html", _lines_context(order))


@require_POST
def retry_order(request, public_id):
    order = _order(request, public_id)
    if order.file and order.status == Order.Status.FAILED:
        order.status = Order.Status.PENDING
        order.error = ""
        order.save(update_fields=["status", "error"])
        logger.info("Order %s: patient retried reading", order.public_id)
        jobs.enqueue(services.process_order, order.pk)
    return redirect("order", public_id=order.public_id)


@require_GET
def order_status(request, public_id):
    order = _order(request, public_id)
    if order.is_reading:
        return HttpResponse(status=204)
    return render(request, "orders/partials/reading_status.html", {"order": order})


@require_POST
def toggle_line(request, public_id, line_id):
    order = _order(request, public_id)
    line = get_object_or_404(order.lines, pk=line_id, exam__isnull=False)
    line.selected = not line.selected
    line.save(update_fields=["selected"])
    logger.info("Order %s: patient %s %s", order.public_id, "selected" if line.selected else "removed", line.exam.name)
    return render(request, "orders/partials/lines.html", _lines_context(order))


@require_POST
def choose_line(request, public_id, line_id, exam_id):
    order = _order(request, public_id)
    line = get_object_or_404(order.lines, pk=line_id)
    exam = get_object_or_404(Exam, pk=exam_id, lab=order.lab, active=True)
    services.choose_candidate(line, exam)
    logger.info("Order %s: patient chose %s for %r", order.public_id, exam.name, line.raw_text)
    return render(request, "orders/partials/lines.html", _lines_context(order))


@require_GET
def search_exams(request, public_id):
    order = _order(request, public_id)
    q = request.GET.get("q", "").strip()
    suggestions = []
    if q:
        suggestions = suggest_exams(Exam.objects.filter(lab=order.lab, active=True), q)
        selected_ids = set(order.lines.filter(selected=True).values_list("exam_id", flat=True))
        for suggestion in suggestions:
            suggestion.selected = suggestion.exam.id in selected_ids
    return render(request, "orders/partials/search_results.html", {"order": order, "suggestions": suggestions, "q": q})


@require_POST
def add_exam(request, public_id, exam_id):
    order = _order(request, public_id)
    exam = get_object_or_404(Exam, pk=exam_id, lab=order.lab, active=True)
    services.add_exam(order, exam)
    logger.info("Order %s: patient added %s", order.public_id, exam.name)
    context = _lines_context(order)
    context["clear_search"] = True
    return render(request, "orders/partials/lines.html", context)


def _quote_context(order, exams, booking_form=None):
    prep = services.merge_prep(exams)
    days = slots.available_slots(order.lab, exclude_order=order, order=order)
    if not order.is_booked:
        planner.log_offers(order, [offer for day in days for offer in day.offers], Order.Channel.WEB)
    return {
        "fasting_from": slots.fasting_start(order.slot_start, prep.fasting_hours) if order.slot_start else "",
        "order": order,
        "coverage": order.coverage,
        "quote": services.build_quote(exams, order.coverage, order.visit_fee_clp, order.visit_discount_clp),
        "prep": prep,
        "days": days,
        "has_deals": any(day.best_discount for day in days),
        "slot_label": slots.slot_label(order.slot_start) if order.slot_start else "",
        "booking_form": booking_form or BookingForm(initial={"contact_phone": order.contact_phone}),
    }


def _quote_ready(request, order):
    if not order.has_details:
        messages.info(request, "Cuéntanos cómo vas a pagar y dónde te tomamos la muestra.")
        return None
    exams = list(order.selected_exams())
    if not exams:
        messages.info(request, "Marca al menos un examen para continuar.")
        return None
    return exams


def _not_ready_redirect(order):
    target = "exams" if order.has_details else "order"
    return redirect(target, public_id=order.public_id)


@require_GET
def schedule(request, public_id):
    """Step 4: pick the visit hour."""
    order = _order(request, public_id)
    exams = _quote_ready(request, order)
    if exams is None:
        return _not_ready_redirect(order)
    context = _quote_context(order, exams)
    logger.info("Order %s: quote with %s for %d exams, total $%s", order.public_id, order.coverage, len(exams),
                context["quote"].total_clp)
    return render(request, "orders/schedule.html", context)


@require_POST
def book(request, public_id):
    order = _order(request, public_id)
    exams = _quote_ready(request, order)
    if exams is None:
        return _not_ready_redirect(order)
    form = BookingForm(request.POST)
    if form.is_valid():
        start = slots.parse_slot(form.cleaned_data["slot"])
        order.contact_phone = form.cleaned_data["contact_phone"]
        order.save(update_fields=["contact_phone"])
        if start and slots.book(order, start):
            logger.info("Order %s: booked %s", order.public_id, start.isoformat())
            return redirect(reverse("schedule", args=[order.public_id]) + "#booking")
        form.add_error("slot", "Esa hora ya no está disponible. Elige otra.")
    return render(request, "orders/schedule.html", _quote_context(order, exams, form), status=422)


@require_GET
def calendar_event(request, public_id):
    order = _order(request, public_id)
    if not order.is_booked:
        raise Http404
    ics = visit_ics(order, services.merge_prep(list(order.selected_exams())))
    response = HttpResponse(ics, content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="toma-de-muestras.ics"'
    return response
