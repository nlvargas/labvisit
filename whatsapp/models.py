from django.db import models

from labs.models import Lab
from orders.models import Order


class Conversation(models.Model):
    class State(models.TextChoices):
        AWAIT_ORDER = "await_order", "Waiting for the order"
        REVIEW_EXAMS = "review_exams", "Reviewing exams"
        AWAIT_COVERAGE = "await_coverage", "Waiting for coverage"
        AWAIT_ISAPRE = "await_isapre", "Waiting for the isapre"
        AWAIT_LOCATION = "await_location", "Waiting for location"
        AWAIT_ADDRESS = "await_address", "Waiting for address"
        CONFIRM_ADDRESS = "confirm_address", "Confirming typed address"
        AWAIT_DAY = "await_day", "Choosing the visit day"
        AWAIT_SLOT = "await_slot", "Choosing the visit hour"
        DONE = "done", "Done"

    lab = models.ForeignKey(Lab, on_delete=models.CASCADE, related_name="conversations")
    phone = models.CharField(max_length=30)
    state = models.CharField(max_length=20, choices=State.choices, default=State.AWAIT_ORDER)
    order = models.ForeignKey(Order, null=True, blank=True, on_delete=models.SET_NULL, related_name="conversations")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["lab", "phone"], name="unique_conversation_per_phone")]

    def __str__(self):
        return f"{self.phone} ({self.lab})"


class Message(models.Model):
    class Direction(models.TextChoices):
        IN = "in", "Incoming"
        OUT = "out", "Outgoing"

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    direction = models.CharField(max_length=3, choices=Direction.choices)
    wa_id = models.CharField(max_length=128, blank=True, null=True, unique=True)
    kind = models.CharField(max_length=30)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
