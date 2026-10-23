from django.core.management.base import BaseCommand, CommandError

from catalog.demo_catalog import FONASA_CODES
from catalog.models import Exam
from labs.models import Lab


class Command(BaseCommand):
    help = "Fills Fonasa codes for a lab's exams that share a name with the demo catalog, and sets its Fonasa level."

    def add_arguments(self, parser):
        parser.add_argument("slug")
        parser.add_argument("--level", type=int, choices=[1, 2, 3])

    def handle(self, *args, slug, level, **options):
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
        self.stdout.write(self.style.SUCCESS(f"{updated} exams got a Fonasa code; level {lab.fonasa_level or 'not set'}."))
