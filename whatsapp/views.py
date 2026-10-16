import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt

from orders import jobs

from .flow import handle_incoming
from .inbound import parse_webhook

logger = logging.getLogger(__name__)


def _valid_signature(request):
    secret = settings.WHATSAPP_APP_SECRET.encode()
    header = request.headers.get("X-Hub-Signature-256", "")
    if not secret or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret, request.body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


@csrf_exempt
def webhook(request):
    if request.method == "GET":
        if (request.GET.get("hub.mode") == "subscribe" and settings.WHATSAPP_VERIFY_TOKEN
                and request.GET.get("hub.verify_token") == settings.WHATSAPP_VERIFY_TOKEN):
            return HttpResponse(request.GET.get("hub.challenge", ""))
        return HttpResponseForbidden()
    if request.method != "POST":
        return HttpResponseBadRequest()
    if not _valid_signature(request):
        logger.warning("WhatsApp webhook with an invalid signature")
        return HttpResponseForbidden()
    try:
        payload = json.loads(request.body)
    except ValueError:
        return HttpResponseBadRequest()
    for incoming in parse_webhook(payload):
        jobs.enqueue(handle_incoming, incoming)
    return HttpResponse("ok")
