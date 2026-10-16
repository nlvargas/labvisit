from dataclasses import dataclass


@dataclass
class Incoming:
    phone_number_id: str
    phone: str
    wa_id: str
    kind: str
    text: str = ""
    reply_id: str = ""
    media_id: str = ""
    mime_type: str = ""
    filename: str = ""
    latitude: float | None = None
    longitude: float | None = None
    raw: dict | None = None


def parse_webhook(payload):
    """Turns a Cloud API webhook payload into incoming messages. Delivery statuses are ignored."""
    messages = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            phone_number_id = value.get("metadata", {}).get("phone_number_id", "")
            for msg in value.get("messages", []):
                messages.append(_parse_message(phone_number_id, msg))
    return messages


def _parse_message(phone_number_id, msg):
    kind = msg.get("type", "")
    incoming = Incoming(phone_number_id=phone_number_id, phone=msg.get("from", ""), wa_id=msg.get("id", ""),
                        kind=kind, raw=msg)
    if kind == "text":
        incoming.text = msg["text"].get("body", "")
    elif kind in ("image", "document"):
        media = msg[kind]
        incoming.media_id = media.get("id", "")
        incoming.mime_type = media.get("mime_type", "")
        incoming.filename = media.get("filename", "")
        incoming.text = media.get("caption", "")
    elif kind == "location":
        loc = msg["location"]
        incoming.latitude = loc.get("latitude")
        incoming.longitude = loc.get("longitude")
        incoming.text = loc.get("address") or loc.get("name") or ""
    elif kind == "interactive":
        data = msg["interactive"]
        reply = data.get("button_reply") or data.get("list_reply") or {}
        incoming.kind = "reply"
        incoming.reply_id = reply.get("id", "")
        incoming.text = reply.get("title", "")
    elif kind == "button":
        incoming.kind = "reply"
        incoming.reply_id = msg["button"].get("payload", "")
        incoming.text = msg["button"].get("text", "")
    return incoming
