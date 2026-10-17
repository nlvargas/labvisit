from django.db import models

from labs.models import Lab


class SampleContainer(models.Model):
    lab = models.ForeignKey(Lab, on_delete=models.CASCADE, related_name="containers")
    name = models.CharField(max_length=80, help_text="For example 'EDTA' or 'Suero'.")
    cap_color = models.CharField(max_length=40, blank=True)
    minutes = models.PositiveSmallIntegerField(null=True, blank=True,
                                               help_text="Blank uses the lab's minutes per tube.")

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["lab", "name"], name="unique_container_per_lab")]

    def __str__(self):
        return f"{self.name} ({self.cap_color})" if self.cap_color else self.name


class Exam(models.Model):
    class SampleType(models.TextChoices):
        BLOOD = "blood", "Sangre"
        URINE = "urine", "Orina"
        STOOL = "stool", "Deposiciones"
        OTHER = "other", "Otra"

    lab = models.ForeignKey(Lab, on_delete=models.CASCADE, related_name="exams")
    name = models.CharField(max_length=160)
    fonasa_code = models.CharField(max_length=20, blank=True)
    synonyms = models.TextField(blank=True, help_text="One synonym or abbreviation per line, for example HMG.")
    sample_type = models.CharField(max_length=10, choices=SampleType.choices, default=SampleType.BLOOD)
    container = models.ForeignKey(SampleContainer, null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="exams", help_text="Tube this exam is drawn into.")
    fasting_hours = models.PositiveSmallIntegerField(default=0)
    prep_text = models.TextField(blank=True, help_text="Patient instructions other than fasting.")
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["lab", "name"], name="unique_exam_name_per_lab")]

    def __str__(self):
        return self.name

    @property
    def synonym_list(self):
        return [s.strip() for s in self.synonyms.splitlines() if s.strip()]


class Coverage(models.Model):
    class Kind(models.TextChoices):
        FONASA = "fonasa", "Fonasa"
        ISAPRE = "isapre", "Isapre"
        PRIVATE = "private", "Private"

    lab = models.ForeignKey(Lab, on_delete=models.CASCADE, related_name="coverages")
    name = models.CharField(max_length=80)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    position = models.PositiveSmallIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["position", "name"]
        constraints = [models.UniqueConstraint(fields=["lab", "name"], name="unique_coverage_name_per_lab")]

    def __str__(self):
        return self.name


class Price(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="prices")
    coverage = models.ForeignKey(Coverage, on_delete=models.CASCADE, related_name="prices")
    amount_clp = models.PositiveIntegerField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["exam", "coverage"], name="unique_price_per_coverage")]

    def __str__(self):
        return f"{self.exam} / {self.coverage}: ${self.amount_clp}"
