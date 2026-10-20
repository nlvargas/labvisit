import random
from datetime import datetime, time, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from catalog.models import Coverage, Exam
from labs.geo import distance_km, visit_fee
from labs.models import Lab
from orders import slots
from orders.models import Order, OrderLine

NOTE = "Visita de ejemplo del demo"
PLACES = [
    ("Av. Irarrázaval 3450, Ñuñoa", -33.4545, -70.5960),
    ("Los Leones 1200, Providencia", -33.4325, -70.6080),
    ("Av. Apoquindo 4500, Las Condes", -33.4135, -70.5830),
    ("Av. Grecia 2100, Ñuñoa", -33.4640, -70.6010),
    ("Av. Pedro de Valdivia 900, Providencia", -33.4300, -70.6050),
    ("Av. Italia 1200, Providencia", -33.4398, -70.6160),
    ("Av. Vitacura 3600, Vitacura", -33.4020, -70.5990),
    ("Santa Isabel 500, Santiago", -33.4480, -70.6420),
]
NAMES = ["Ana Rojas", "Pedro Díaz", "Marta Silva", "Luis Torres", "Sofía Vega", "Diego Fuentes", "Paula Reyes",
         "Tomás Araya", "Valentina Lagos", "Ignacio Peña", "Fernanda Castro", "Matías Herrera"]
EXAMS = [["Hemograma", "Glicemia"], ["Perfil lipídico", "TSH"], ["Orina completa"],
         ["Hemograma", "Perfil bioquímico"], ["TSH", "T4 libre"]]
WEEKDAY_HOURS = [8, 10, 12]
SATURDAY_HOURS = [8, 9]


class Command(BaseCommand):
    help = "Keeps a few made-up booked visits on the demo lab's upcoming days, so slot discounts show up."

    def add_arguments(self, parser):
        parser.add_argument("--lab", default="demo")

    def handle(self, *args, lab, **options):
        lab = Lab.objects.filter(slug=lab).first()
        if lab is None:
            self.stdout.write("No demo lab.")
            return
        today = timezone.localdate()
        old = Order.objects.filter(lab=lab, staff_notes=NOTE, slot_start__date__lt=today)
        removed = old.count()
        old.delete()
        coverages = list(Coverage.objects.filter(lab=lab, active=True))
        exams = {e.name: e for e in Exam.objects.filter(lab=lab, active=True)}
        booked = 0
        for offset in range(1, lab.booking_days_ahead + 1):
            day = today + timedelta(days=offset)
            hours = WEEKDAY_HOURS if day.weekday() < 5 else SATURDAY_HOURS if day.weekday() == 5 else []
            if not hours or Order.objects.filter(lab=lab, staff_notes=NOTE, slot_start__date=day).exists():
                continue
            rng = random.Random(day.toordinal())
            for hour, (address, lat, lng) in zip(hours, rng.sample(PLACES, len(hours))):
                km = distance_km(lab.latitude, lab.longitude, lat, lng)
                order = Order.objects.create(
                    lab=lab, status=Order.Status.READY, coverage=rng.choice(coverages), address=address,
                    latitude=lat, longitude=lng, distance_km=km, visit_fee_clp=visit_fee(lab, km),
                    patient_name=rng.choice(NAMES), staff_notes=NOTE,
                )
                names = [n for n in rng.choice(EXAMS) if n in exams]
                OrderLine.objects.bulk_create(
                    OrderLine(order=order, position=i, raw_text=n, exam=exams[n], confidence=1, selected=True)
                    for i, n in enumerate(names)
                )
                if slots.book(order, timezone.make_aware(datetime.combine(day, time(hour)))):
                    booked += 1
                else:
                    order.delete()
        self.stdout.write(f"Booked {booked} demo visits, removed {removed} past ones.")
