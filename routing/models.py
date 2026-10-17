from django.db import models

from labs.models import Lab, Nurse
from orders.models import Order


class RoutePlan(models.Model):
    class Trigger(models.TextChoices):
        BOOKING = "booking", "Reserva"
        PANEL = "panel", "Cambio en el panel"
        MANUAL = "manual", "Recalculada"

    lab = models.ForeignKey(Lab, on_delete=models.CASCADE, related_name="route_plans")
    date = models.DateField()
    nurse = models.ForeignKey(Nurse, null=True, blank=True, on_delete=models.SET_NULL, related_name="route_plans")
    trigger = models.CharField(max_length=10, choices=Trigger.choices)
    feasible = models.BooleanField(default=True, help_text="False when no order keeps every promised hour.")
    method = models.CharField(max_length=20, blank=True, help_text="exact, insertion, slot order or no coordinates.")
    travel_min = models.FloatField(null=True, blank=True)
    depart_at = models.DateTimeField(null=True, blank=True)
    back_at = models.DateTimeField(null=True, blank=True)
    params = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["lab", "date"])]

    def __str__(self):
        return f"Route {self.lab} {self.date}"


class RouteStop(models.Model):
    class Kind(models.TextChoices):
        VISIT = "visit", "Visita"
        LAB = "lab", "Laboratorio"

    plan = models.ForeignKey(RoutePlan, on_delete=models.CASCADE, related_name="stops")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.VISIT)
    nurse = models.ForeignKey(Nurse, null=True, blank=True, on_delete=models.SET_NULL, related_name="route_stops")
    order = models.ForeignKey(Order, null=True, blank=True, on_delete=models.CASCADE, related_name="route_stops")
    sequence = models.PositiveSmallIntegerField()
    arrival = models.DateTimeField(null=True, blank=True)
    start = models.DateTimeField(null=True, blank=True)
    departure = models.DateTimeField(null=True, blank=True)
    travel_min = models.FloatField(default=0, help_text="From the previous stop or the lab.")
    wait_min = models.FloatField(default=0)
    late_min = models.FloatField(default=0)

    class Meta:
        ordering = ["nurse_id", "sequence"]


class SlotOffer(models.Model):
    """A slot shown to a patient, kept to learn later how discounts change choices."""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="slot_offers")
    channel = models.CharField(max_length=10, choices=Order.Channel.choices)
    slot_start = models.DateTimeField()
    discount_clp = models.PositiveIntegerField(default=0)
    extra_min = models.FloatField(null=True, blank=True, help_text="Marginal travel minutes of the slot.")
    standalone_min = models.FloatField(null=True, blank=True, help_text="Round trip from the lab.")
    shown_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["order", "shown_at"])]
