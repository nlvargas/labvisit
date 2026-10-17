import mimetypes
import uuid
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from labs.models import Lab
from whatsapp.client import ConsoleClient
from whatsapp.flow import handle_incoming
from whatsapp.inbound import Incoming

HELP = """Type as the patient. Commands:
  /photo <path>        sends a photo or PDF of the medical order
  /button <id>         taps a button or list option (the id is shown in brackets)
  /location <lat,lng>  shares a location, for example /location -33.4569,-70.5970
  /quit"""


class Command(BaseCommand):
    help = "Chat with the WhatsApp booking flow from the terminal, without Meta."

    def add_arguments(self, parser):
        parser.add_argument("--lab", default="biodata")
        parser.add_argument("--phone", default="56900000000")

    def handle(self, *args, lab, phone, **options):
        lab_obj = Lab.objects.filter(slug=lab).first()
        if lab_obj is None:
            raise CommandError(f"No lab with slug '{lab}'. Run seed_demo first.")
        client = ConsoleClient(output=self.stdout.write)
        self.stdout.write(HELP)
        while True:
            try:
                line = input("\n[patient] ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not line:
                continue
            if line == "/quit":
                break
            incoming = self._to_incoming(line, phone, client)
            if incoming:
                handle_incoming(incoming, client=client, lab=lab_obj)

    def _to_incoming(self, line, phone, client):
        base = {"phone_number_id": "", "phone": phone, "wa_id": f"console-{uuid.uuid4()}"}
        command, _, arg = line.partition(" ")
        if command == "/photo":
            path = Path(arg.strip()).expanduser()
            if not path.exists():
                self.stdout.write(f"{path} does not exist")
                return None
            mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
            media_id = str(uuid.uuid4())
            client.media[media_id] = (path.read_bytes(), mime)
            kind = "document" if mime == "application/pdf" else "image"
            return Incoming(**base, kind=kind, media_id=media_id, mime_type=mime, filename=path.name)
        if command == "/button":
            return Incoming(**base, kind="reply", reply_id=arg.strip())
        if command == "/location":
            lat, lng = (float(v) for v in arg.split(","))
            return Incoming(**base, kind="location", latitude=lat, longitude=lng)
        return Incoming(**base, kind="text", text=line)
