import logging

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

GRAPH_URL = "https://graph.facebook.com"



def _row(rid, title, description=""):
    row = {"id": rid, "title": title[:24]}
    if description:
        row["description"] = description[:72]
    return row

class MetaClient:
    """WhatsApp Cloud API. Button titles are capped at 20 characters and list rows at 24 by Meta."""

    def __init__(self, phone_number_id):
        self.phone_number_id = phone_number_id
        self.http = httpx.Client(
            base_url=f"{GRAPH_URL}/{settings.WHATSAPP_API_VERSION}",
            headers={"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"},
            timeout=30,
        )

    def _send(self, to, payload):
        body = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": to, **payload}
        response = self.http.post(f"/{self.phone_number_id}/messages", json=body)
        if response.is_error:
            logger.error("WhatsApp send failed (%s): %s", response.status_code, response.text[:500])
        response.raise_for_status()
        return response.json()

    def send_text(self, to, body):
        return self._send(to, {"type": "text", "text": {"body": body, "preview_url": True}})

    def send_buttons(self, to, body, buttons):
        return self._send(to, {"type": "interactive", "interactive": {
            "type": "button",
            "body": {"text": body},
            "action": {"buttons": [
                {"type": "reply", "reply": {"id": bid, "title": title[:20]}} for bid, title in buttons
            ]},
        }})

    def send_list(self, to, body, button_label, rows):
        return self._send(to, {"type": "interactive", "interactive": {
            "type": "list",
            "body": {"text": body},
            "action": {"button": button_label[:20], "sections": [{"rows": [_row(*row) for row in rows[:10]]}]},
        }})

    def request_location(self, to, body):
        return self._send(to, {"type": "interactive", "interactive": {
            "type": "location_request_message",
            "body": {"text": body},
            "action": {"name": "send_location"},
        }})

    def download_media(self, media_id):
        meta = self.http.get(f"/{media_id}")
        meta.raise_for_status()
        info = meta.json()
        file = self.http.get(info["url"])
        file.raise_for_status()
        return file.content, info.get("mime_type", "")


class ConsoleClient:
    """Prints outgoing messages; used for local development and the terminal simulator."""

    def __init__(self, phone_number_id="", media=None, output=None):
        self.media = media or {}
        self.output = output or print
        self.sent = []

    def _record(self, to, kind, **data):
        self.sent.append({"to": to, "kind": kind, **data})

    def send_text(self, to, body):
        self._record(to, "text", body=body)
        self.output(f"\n[bot] {body}")

    def send_buttons(self, to, body, buttons):
        self._record(to, "buttons", body=body, buttons=buttons)
        options = "  ".join(f"[{bid}] {title}" for bid, title in buttons)
        self.output(f"\n[bot] {body}\n      buttons: {options}")

    def send_list(self, to, body, button_label, rows):
        self._record(to, "list", body=body, rows=rows)
        options = "\n".join(f"      [{row[0]}] {' '.join(row[1:])}" for row in rows)
        self.output(f"\n[bot] {body}\n      list ({button_label}):\n{options}")

    def request_location(self, to, body):
        self._record(to, "location_request", body=body)
        self.output(f"\n[bot] {body}\n      (location requested: reply /location lat,lng)")

    def download_media(self, media_id):
        return self.media[media_id]


def get_client(lab):
    if settings.WHATSAPP_BACKEND == "meta":
        return MetaClient(lab.whatsapp_phone_number_id)
    return ConsoleClient()
