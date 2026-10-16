from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.demo_catalog import COVERAGES, EXAMS, LAB_LOCATION, LAB_STYLE, OPENING_HOURS, VISIT_FEE
from catalog.models import Coverage, Exam, Price
from labs.models import Lab, OpeningHours

class Command(BaseCommand):
    help = "Creates or updates a demo lab with a sample catalog and reference prices."

    def add_arguments(self, parser):
        parser.add_argument("--slug", default="biodata")
        parser.add_argument("--name", default="Biodata")

    @transaction.atomic
    def handle(self, *args, slug, name, **options):
        lab, _ = Lab.objects.update_or_create(slug=slug, defaults={
            "name": name, "latitude": LAB_LOCATION[0], "longitude": LAB_LOCATION[1], **VISIT_FEE, **LAB_STYLE,
        })
        if not lab.opening_hours.exists():
            OpeningHours.objects.bulk_create(
                OpeningHours(lab=lab, weekday=day, opens=opens, closes=closes) for day, opens, closes in OPENING_HOURS
            )
        coverages = []
        for position, (cov_name, kind, column) in enumerate(COVERAGES):
            cov, _ = Coverage.objects.update_or_create(
                lab=lab, kind=kind, defaults={"name": cov_name, "position": position, "active": True}
            )
            coverages.append((cov, column))
        Coverage.objects.filter(lab=lab).exclude(pk__in=[cov.pk for cov, _ in coverages]).update(active=False)
        for exam_name, synonyms, sample, fasting, prep, fonasa, private in EXAMS:
            exam, _ = Exam.objects.update_or_create(
                lab=lab, name=exam_name,
                defaults={
                    "synonyms": "\n".join(synonyms),
                    "sample_type": sample,
                    "fasting_hours": fasting,
                    "prep_text": prep,
                    "active": True,
                },
            )
            prices = {"fonasa": fonasa, "private": private}
            for cov, column in coverages:
                Price.objects.update_or_create(exam=exam, coverage=cov, defaults={"amount_clp": prices[column]})
        stale = Exam.objects.filter(lab=lab).exclude(name__in=[e[0] for e in EXAMS]).update(active=False)
        self.stdout.write(self.style.SUCCESS(f"Lab '{lab.slug}' ready with {len(EXAMS)} exams ({stale} old ones deactivated)."))
