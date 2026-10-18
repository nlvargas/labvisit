"""One reminder per silence: when the bot spoke last, the patient has been quiet for a while and the booking is
unfinished. Never at night and never outside Meta's 24 hour customer service window."""
import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .client import get_client
from .flow import Bot, _order_url
from .models import Conversation

logger = logging.getLogger(__name__)

State = Conversation.State
TEXTS = {
    State.AWAIT_ORDER: "¿Sigues ahí? Cuando tengas tu orden médica, mándame una foto o PDF y te digo los exámenes y "
                       "el precio.",
    State.REVIEW_EXAMS: "Te quedó pendiente confirmar tus exámenes. Respóndeme cuando quieras y seguimos.",
    State.AWAIT_COVERAGE: "Te quedó pendiente contarme tu previsión de salud. Respóndeme cuando quieras y seguimos.",
    State.AWAIT_ISAPRE: "Te quedó pendiente contarme tu isapre. Respóndeme cuando quieras y seguimos.",
    State.AWAIT_LOCATION: "Te quedó pendiente la dirección donde te tomamos la muestra. Respóndeme cuando quieras y "
                          "seguimos.",
    State.AWAIT_ADDRESS: "Te quedó pendiente la dirección donde te tomamos la muestra. Respóndeme cuando quieras y "
                         "seguimos.",
    State.CONFIRM_ADDRESS: "Te quedó pendiente confirmar la dirección. Respóndeme cuando quieras y seguimos.",
    State.AWAIT_DAY: "Te quedó pendiente elegir el día de la visita. Respóndeme cuando quieras y seguimos.",
    State.AWAIT_SLOT: "Te quedó pendiente elegir la hora de la visita. Respóndeme cuando quieras y seguimos.",
}


def reminder_text(conversation):
    text = TEXTS[conversation.state]
    if conversation.order_id and conversation.state != State.AWAIT_ORDER:
        text += f"\n\nTambién puedes terminar aquí: {_order_url(conversation.order)}"
    return text


def due(now=None):
    """Conversations that should get their reminder now."""
    now = now or timezone.now()
    start, end = settings.WHATSAPP_REMINDER_HOURS
    if not start <= timezone.localtime(now).hour < end:
        return Conversation.objects.none()
    quiet_since = now - timedelta(minutes=settings.WHATSAPP_REMINDER_AFTER_MINUTES)
    window = now - timedelta(hours=settings.WHATSAPP_REMINDER_WINDOW_HOURS)
    candidates = (Conversation.objects.exclude(state=State.DONE)
                  .filter(reminder_sent_at__isnull=True, last_inbound_at__gt=window,
                          last_outbound_at__lte=quiet_since)
                  .select_related("lab", "order"))
    return [c for c in candidates if c.last_outbound_at >= c.last_inbound_at]


def send_reminders(now=None, client=None):
    sent = 0
    for conversation in due(now):
        try:
            Bot(conversation, client or get_client(conversation.lab)).text(reminder_text(conversation))
        except Exception:
            logger.exception("WhatsApp ...%s: reminder failed", conversation.phone[-4:])
            continue
        Conversation.objects.filter(pk=conversation.pk).update(reminder_sent_at=now or timezone.now())
        logger.info("WhatsApp ...%s: reminder sent in state %s", conversation.phone[-4:], conversation.state)
        sent += 1
    return sent
