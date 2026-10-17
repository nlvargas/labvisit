from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models


FONTS = {
    "system": ("Sistema", ""),
    "montserrat": ("Montserrat", "Montserrat:wght@400;500;600;700"),
    "poppins": ("Poppins", "Poppins:wght@400;500;600;700"),
    "roboto": ("Roboto", "Roboto:wght@400;500;700"),
    "open-sans": ("Open Sans", "Open+Sans:wght@400;600;700"),
    "lato": ("Lato", "Lato:wght@400;700"),
    "nunito": ("Nunito", "Nunito:wght@400;600;700"),
}


class Lab(models.Model):
    class Corners(models.TextChoices):
        ROUNDED = "rounded", "Redondeadas"
        SQUARE = "square", "Rectas"
    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True, help_text="The lab's subdomain, for example 'biodata'.")
    phone = models.CharField(max_length=40, blank=True)
    whatsapp = models.CharField(max_length=40, blank=True)
    whatsapp_phone_number_id = models.CharField(
        max_length=40, blank=True, db_index=True, help_text="Phone number ID from the WhatsApp Cloud API."
    )
    is_active = models.BooleanField(default=True)
    latitude = models.FloatField(null=True, blank=True, help_text="Where home visits start from.")
    longitude = models.FloatField(null=True, blank=True)
    visit_base_fee_clp = models.PositiveIntegerField(default=18000)
    visit_fee_per_km_clp = models.PositiveIntegerField(default=500)
    max_visit_km = models.FloatField(default=25, help_text="Addresses farther than this are out of the coverage area.")
    booking_days_ahead = models.PositiveSmallIntegerField(default=7)
    min_notice_hours = models.PositiveSmallIntegerField(default=2, help_text="Earliest a visit can be booked from now.")

    service_base_min = models.PositiveSmallIntegerField(default=10, help_text="Minutes per visit before counting tubes.")
    service_per_tube_min = models.PositiveSmallIntegerField(default=1, help_text="Minutes per distinct blood tube.")
    service_container_min = models.PositiveSmallIntegerField(
        default=5, help_text="Minutes added once when the visit includes a urine or stool sample.")
    travel_speed_kmh = models.FloatField(default=22, help_text="Average driving speed used to estimate travel times.")
    detour_factor = models.FloatField(default=1.4, help_text="Road distance divided by straight-line distance.")
    max_sample_age_min = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Longest a sample can wait before reaching the lab. Blank means no limit.")
    drop_off_min = models.PositiveSmallIntegerField(default=5, help_text="Minutes to leave samples at the lab.")
    lab_return_ratio = models.FloatField(
        default=0, help_text="Extra driving minutes accepted per minute the nurse waits at the lab instead of the car. "
                             "0 never adds optional returns.")
    min_lab_minutes = models.PositiveSmallIntegerField(
        default=30, help_text="Shortest wait at the lab that justifies an optional return.")
    discount_share = models.FloatField(
        default=1.0, help_text="Share of the route savings given back as a visit discount. 0 turns discounts off.")
    discount_max_clp = models.PositiveIntegerField(default=5000)
    discount_min_clp = models.PositiveIntegerField(default=1000, help_text="Smaller discounts are not shown.")

    brand_color = models.CharField(max_length=7, default="#1f6f5c", help_text="Main color, for example #5dc1cf.",
                                   validators=[RegexValidator(r"^#[0-9a-fA-F]{6}$", "Use a color like #5dc1cf.")])
    font = models.CharField(max_length=20, default="system", choices=[(k, v[0]) for k, v in FONTS.items()])
    corners = models.CharField(max_length=10, default=Corners.ROUNDED, choices=Corners.choices)
    logo = models.ImageField(upload_to="labs/logos/", blank=True, help_text="Shown instead of the name. PNG or SVG with transparent background.")
    tagline = models.CharField(max_length=120, blank=True, help_text="Small line under the name, for example the legal name.")
    address_line = models.CharField(max_length=200, blank=True, help_text="Shown in the footer.")
    website_url = models.URLField(blank=True)
    results_url = models.URLField(blank=True, help_text="Link to the lab's results portal, shown at the top.")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def font_family(self):
        name = FONTS.get(self.font, FONTS["system"])[0]
        return "system-ui, -apple-system, 'Segoe UI', sans-serif" if self.font == "system" else f"'{name}', system-ui, sans-serif"

    @property
    def font_query(self):
        return FONTS.get(self.font, FONTS["system"])[1]

    @property
    def radius(self):
        return "3px" if self.corners == self.Corners.SQUARE else "12px"

    @property
    def radius_small(self):
        return "2px" if self.corners == self.Corners.SQUARE else "10px"

    @property
    def pill(self):
        return "3px" if self.corners == self.Corners.SQUARE else "999px"

    @property
    def whatsapp_url(self):
        digits = "".join(ch for ch in self.whatsapp if ch.isdigit())
        return f"https://wa.me/{digits}" if digits else ""

    @property
    def public_url(self):
        return settings.LAB_URL_TEMPLATE.format(slug=self.slug).rstrip("/")


class OpeningHours(models.Model):
    class Weekday(models.IntegerChoices):
        MONDAY = 0, "Lunes"
        TUESDAY = 1, "Martes"
        WEDNESDAY = 2, "Miércoles"
        THURSDAY = 3, "Jueves"
        FRIDAY = 4, "Viernes"
        SATURDAY = 5, "Sábado"
        SUNDAY = 6, "Domingo"

    lab = models.ForeignKey(Lab, on_delete=models.CASCADE, related_name="opening_hours")
    weekday = models.PositiveSmallIntegerField(choices=Weekday.choices)
    opens = models.TimeField()
    closes = models.TimeField(help_text="The last visit starts one hour before this.")

    class Meta:
        ordering = ["weekday", "opens"]
        verbose_name_plural = "opening hours"

    def __str__(self):
        return f"{self.get_weekday_display()} {self.opens:%H:%M}-{self.closes:%H:%M}"



class LabMember(models.Model):
    lab = models.ForeignKey(Lab, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lab_memberships")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["lab", "user"], name="unique_lab_member")]

    def __str__(self):
        return f"{self.user} @ {self.lab}"


def _minutes(value):
    return value.hour * 60 + value.minute


class Nurse(models.Model):
    lab = models.ForeignKey(Lab, on_delete=models.CASCADE, related_name="nurses")
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=40, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def shift_on(self, day):
        """Working minutes after midnight on that day, or None when she doesn't work."""
        blocks = [b for b in self.schedule.all() if b.weekday == day.weekday()]
        if not blocks:
            return None
        start, end = min(_minutes(b.starts) for b in blocks), max(_minutes(b.ends) for b in blocks)
        for off in self.time_off.filter(date=day):
            if off.starts is None or off.ends is None:
                return None
            off_start, off_end = _minutes(off.starts), _minutes(off.ends)
            if off_start <= start:
                start = max(start, off_end)
            else:
                end = min(end, off_start)
        return (start, end) if start < end else None


class NurseSchedule(models.Model):
    nurse = models.ForeignKey(Nurse, on_delete=models.CASCADE, related_name="schedule")
    weekday = models.PositiveSmallIntegerField(choices=OpeningHours.Weekday.choices)
    starts = models.TimeField()
    ends = models.TimeField()

    class Meta:
        ordering = ["weekday", "starts"]

    def __str__(self):
        return f"{self.nurse} {self.get_weekday_display()} {self.starts:%H:%M}-{self.ends:%H:%M}"


class NurseTimeOff(models.Model):
    nurse = models.ForeignKey(Nurse, on_delete=models.CASCADE, related_name="time_off")
    date = models.DateField()
    starts = models.TimeField(null=True, blank=True, help_text="Leave both times blank for the whole day.")
    ends = models.TimeField(null=True, blank=True)

    class Meta:
        ordering = ["date"]
        verbose_name_plural = "nurse time off"

    def __str__(self):
        return f"{self.nurse} {self.date}"
