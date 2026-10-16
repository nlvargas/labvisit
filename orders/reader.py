import io
import logging
import time
from dataclasses import dataclass, field

import httpx
from django.conf import settings
from google import genai
from google.genai import errors, types
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v2"

PROMPT = """You are reading a Chilean medical order (orden médica) requesting laboratory exams.

Return every requested exam exactly as written, one entry per exam, in the order it appears.
- Do not correct spelling, expand abbreviations, or translate. "HMG", "PBQ" or "T4L" stay as written.
- If one line lists several exams ("ELP + BUN", "TSH, T4L"), return them as separate entries.
- Never add an exam that isn't written on the document.
- If you can't read an entry with confidence, set legible to false and put your best partial reading in text.
- Ignore diagnoses, medications, and anything that isn't a requested exam.
- If the document is not a medical order for exams, set is_medical_order to false and return no entries.

Also return, when they appear, the patient's full name and RUT, the doctor's full name and RUT, and the order date. Use empty strings for anything that doesn't appear.
- Orders often show both the patient's RUT and the doctor's RUT. Assign each by its label or position: the doctor's RUT usually sits next to the doctor's name, signature or stamp.
- If the order shows only one RUT, it is the patient's RUT.
- Copy RUTs exactly as written."""


MAX_IMAGE_SIDE = 2000


def shrink_image(data, mime_type):
    if not mime_type.startswith("image/"):
        return data, mime_type
    try:
        image = Image.open(io.BytesIO(data))
        image = ImageOps.exif_transpose(image)
    except (UnidentifiedImageError, OSError):
        return data, mime_type
    if max(image.size) <= MAX_IMAGE_SIDE and len(data) <= 1_500_000:
        return data, mime_type
    image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
    out = io.BytesIO()
    image.convert("RGB").save(out, "JPEG", quality=85)
    logger.info("Image resized from %d KB to %d KB", len(data) // 1024, out.tell() // 1024)
    return out.getvalue(), "image/jpeg"


class _Entry(BaseModel):
    text: str
    legible: bool


class _Extraction(BaseModel):
    is_medical_order: bool
    patient_name: str
    patient_rut: str
    doctor_name: str
    doctor_rut: str
    order_date: str
    entries: list[_Entry]


@dataclass
class ReadEntry:
    text: str
    legible: bool = True


@dataclass
class ReadResult:
    entries: list[ReadEntry]
    is_medical_order: bool = True
    patient_name: str = ""
    patient_rut: str = ""
    doctor_name: str = ""
    doctor_rut: str = ""
    order_date: str = ""
    provider: str = ""
    model: str = ""
    prompt_version: str = PROMPT_VERSION
    raw: dict = field(default_factory=dict)


class FakeReader:
    name = "fake"

    def read(self, data, mime_type):
        time.sleep(settings.FAKE_READER_DELAY)
        texts = ["HMG", "PBQ", "Perfil lipídico", "TSH", "T4L", "Orina completa", "Vit D", "Ac. úrico"]
        entries = [ReadEntry(t) for t in texts] + [ReadEntry("Gl...ina", legible=False)]
        return ReadResult(
            entries=entries,
            patient_name="Juan Pérez Soto",
            patient_rut="11.111.111-1",
            doctor_name="Dra. María González",
            doctor_rut="12.345.678-5",
            order_date="10/10/2026",
            provider=self.name,
            model="fake",
            raw={"entries": texts},
        )


# billing, quota, model not available and overload errors: try the next model instead of failing
RETRYABLE = {402, 403, 404, 429, 500, 502, 503, 504, "timeout"}


class GeminiReader:
    name = "gemini"

    def __init__(self, api_key, model, fallback_models=()):
        self.client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=45_000))
        self.model = model
        self.fallback_models = [m for m in fallback_models if m and m != model]
        self.rounds = 4
        self.backoff_seconds = 3
        self.deadline_seconds = 90

    def _generate(self, contents, config):
        """Tries each model, and when all are busy waits and goes around again until the deadline."""
        models = [self.model, *self.fallback_models]
        deadline = time.monotonic() + self.deadline_seconds
        for round_ in range(self.rounds):
            for model in models:
                try:
                    return self.client.models.generate_content(model=model, contents=contents, config=config), model
                except (errors.APIError, httpx.TimeoutException) as exc:
                    reason = getattr(exc, "code", None) or "timeout"
                    if reason not in RETRYABLE:
                        raise
                    last = exc
                    logger.warning("%s unavailable (%s), round %d", model, reason, round_ + 1)
                    if time.monotonic() > deadline:
                        raise
            wait = self.backoff_seconds * (2 ** round_)
            if time.monotonic() + wait > deadline:
                break
            time.sleep(wait)
        raise last

    def read(self, data, mime_type):
        data, mime_type = shrink_image(data, mime_type)
        contents = [types.Part.from_bytes(data=data, mime_type=mime_type), PROMPT]
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_Extraction,
            temperature=0,
        )
        response, model = self._generate(contents, config)
        parsed = response.parsed or _Extraction.model_validate_json(response.text)
        return ReadResult(
            entries=[ReadEntry(e.text.strip(), e.legible) for e in parsed.entries if e.text.strip()],
            is_medical_order=parsed.is_medical_order,
            patient_name=parsed.patient_name,
            patient_rut=parsed.patient_rut,
            doctor_name=parsed.doctor_name,
            doctor_rut=parsed.doctor_rut,
            order_date=parsed.order_date,
            provider=self.name,
            model=model,
            raw=parsed.model_dump(),
        )


def get_reader():
    if settings.READER_PROVIDER == "gemini":
        return GeminiReader(settings.GEMINI_API_KEY, settings.GEMINI_MODEL, settings.GEMINI_FALLBACK_MODELS)
    return FakeReader()
