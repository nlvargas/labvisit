import uuid

from django.db import models

from catalog.models import Coverage, Exam
from labs.models import Lab


def order_upload_path(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"orders/{instance.lab.slug}/{instance.public_id}.{ext}"


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        READING = "reading", "Reading"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    class Visit(models.TextChoices):
        REQUESTED = "requested", "Por confirmar"
        CONFIRMED = "confirmed", "Confirmada"
        COMPLETED = "completed", "Realizada"
        CANCELLED = "cancelled", "Cancelada"

    class Channel(models.TextChoices):
        WEB = "web", "Web"
        WHATSAPP = "whatsapp", "WhatsApp"

    lab = models.ForeignKey(Lab, on_delete=models.CASCADE, related_name="orders")
    channel = models.CharField(max_length=10, choices=Channel.choices, default=Channel.WEB)
    contact_phone = models.CharField(max_length=30, blank=True)
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    file = models.FileField(upload_to=order_upload_path, blank=True)
    content_type = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    coverage = models.ForeignKey(Coverage, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders")
    isapre = models.CharField(max_length=60, blank=True)
    address = models.CharField(max_length=300, blank=True)
    address_place_id = models.CharField(max_length=300, blank=True)
    apartment = models.CharField(max_length=80, blank=True)
    address_notes = models.CharField(max_length=300, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    distance_km = models.FloatField(null=True, blank=True)
    visit_fee_clp = models.PositiveIntegerField(null=True, blank=True)
    visit_discount_clp = models.PositiveIntegerField(default=0, help_text="Discount for the booked slot.")
    service_minutes = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Estimated when booking.")
    patient_name = models.CharField(max_length=160, blank=True)
    patient_rut = models.CharField(max_length=20, blank=True)
    patient_rut_valid = models.BooleanField(default=False)
    doctor_name = models.CharField(max_length=160, blank=True)
    doctor_rut = models.CharField(max_length=20, blank=True)
    order_date = models.CharField(max_length=40, blank=True)
    extraction = models.JSONField(null=True, blank=True)
    error = models.TextField(blank=True)
    reader_provider = models.CharField(max_length=40, blank=True)
    reader_model = models.CharField(max_length=80, blank=True)
    prompt_version = models.CharField(max_length=20, blank=True)
    slot_start = models.DateTimeField(null=True, blank=True, db_index=True)
    booked_at = models.DateTimeField(null=True, blank=True)
    visit_status = models.CharField(max_length=10, choices=Visit.choices, default=Visit.REQUESTED)
    staff_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order {self.public_id} ({self.lab})"

    @property
    def is_reading(self):
        return self.status in (self.Status.PENDING, self.Status.READING)

    @property
    def has_details(self):
        return self.coverage_id is not None and bool(self.address) and self.visit_fee_clp is not None

    @property
    def out_of_range(self):
        return bool(self.address) and self.visit_fee_clp is None

    @property
    def coverage_label(self):
        if self.coverage and self.coverage.kind == "isapre" and self.isapre:
            return f"Isapre {self.isapre}"
        return str(self.coverage) if self.coverage else ""

    @property
    def is_manual(self):
        return not self.file and not self.is_reading

    @property
    def is_booked(self):
        return self.slot_start is not None

    def selected_exams(self):
        return Exam.objects.filter(order_lines__order=self, order_lines__selected=True).distinct()


class OrderLine(models.Model):
    class Origin(models.TextChoices):
        INFERRED = "inferred", "Read from the order"
        ADDED = "added", "Added by the patient"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="lines")
    position = models.PositiveSmallIntegerField(default=0)
    raw_text = models.CharField(max_length=300, blank=True)
    legible = models.BooleanField(default=True)
    exam = models.ForeignKey(Exam, null=True, blank=True, on_delete=models.SET_NULL, related_name="order_lines")
    confidence = models.FloatField(default=0)
    candidates = models.JSONField(default=list, blank=True)
    origin = models.CharField(max_length=10, choices=Origin.choices, default=Origin.INFERRED)
    selected = models.BooleanField(default=False)
    matcher_version = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return self.raw_text or str(self.exam)
