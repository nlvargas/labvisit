from django.core.management.base import BaseCommand, CommandError

from catalog.demo_catalog import FONASA_CODES
from catalog.models import Exam
from labs.models import Lab


class Command(BaseCommand):
    help = ("Fills Fonasa codes for a lab's exams that share a name with the demo catalog, and sets its Fonasa level "
            "or turns on the Fonasa bono discount from its published prices.")

    def add_arguments(self, parser):
        parser.add_argument("slug")
        parser.add_argument("--level", type=int, choices=[1, 2, 3])
        parser.add_argument("--bonus-from-price", action="store_true")

    def handle(self, *args, slug, level, bonus_from_price=False, **options):
        lab = Lab.objects.filter(slug=slug).first()
        if lab is None:
            raise CommandError(f"No lab '{slug}'.")
        updated = 0
        for exam in Exam.objects.filter(lab=lab, fonasa_code=""):
            code = FONASA_CODES.get(exam.name)
            if code:
                exam.fonasa_code = code
                exam.save(update_fields=["fonasa_code"])
                updated += 1
        if level:
            lab.fonasa_level = level
            lab.save(update_fields=["fonasa_level"])
        if bonus_from_price:
            lab.fonasa_bonus_from_price = True
            lab.save(update_fields=["fonasa_bonus_from_price"])
        coded = Exam.objects.filter(lab=lab).exclude(fonasa_code="").count()
        mode = "bono from published prices" if lab.fonasa_bonus_from_price else f"level {lab.fonasa_level or 'not set'}"
        self.stdout.write(self.style.SUCCESS(f"{updated} exams got a Fonasa code ({coded} in total); {mode}."))
