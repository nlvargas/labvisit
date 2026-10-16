from datetime import timezone as dt_timezone

from django.utils import timezone

from .slots import SLOT


def _escape(text):
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def visit_ics(order, prep):
    """An iCalendar event for the visit, with an alarm when the fast starts."""
    start = order.slot_start.astimezone(dt_timezone.utc)
    end = start + SLOT
    fmt = "%Y%m%dT%H%M%SZ"
    lines_text = [f"Toma de muestras a domicilio de {order.lab.name}.", f"Dirección: {order.address}"]
    if prep.fasting_hours:
        lines_text.append(f"Ayuno de {prep.fasting_hours} horas. Puedes tomar agua.")
    lines_text += prep.instructions
    alarms = []
    if prep.fasting_hours:
        alarms.append((prep.fasting_hours * 60, f"Desde ahora no comas: ayuno de {prep.fasting_hours} horas para tus exámenes"))
    alarms.append((60, f"En una hora llega la enfermera de {order.lab.name}"))
    body = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//labvisit//ES", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{order.public_id}@labvisit",
        f"DTSTAMP:{timezone.now().astimezone(dt_timezone.utc).strftime(fmt)}",
        f"DTSTART:{start.strftime(fmt)}",
        f"DTEND:{end.strftime(fmt)}",
        f"SUMMARY:{_escape('Toma de muestras a domicilio · ' + order.lab.name)}",
        f"LOCATION:{_escape(order.address)}",
        f"DESCRIPTION:{_escape(chr(10).join(lines_text))}",
    ]
    for minutes, text in alarms:
        body += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_escape(text)}", f"TRIGGER:-PT{minutes}M", "END:VALARM"]
    body += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(body) + "\r\n"
