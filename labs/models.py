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
    email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)
    latitude = models.FloatField(null=True, blank=True, help_text="Where home visits start from.")
    longitude = models.FloatField(null=True, blank=True)
    visit_base_fee_clp = models.PositiveIntegerField(default=18000)
    visit_fee_per_km_clp = models.PositiveIntegerField(default=500)
    max_visit_km = models.FloatField(default=25, help_text="Addresses farther than this are out of the coverage area.")
    visits_per_slot = models.PositiveSmallIntegerField(default=1, help_text="Home visits the lab can do in the same hour.")
    booking_days_ahead = models.PositiveSmallIntegerField(default=7)
    min_notice_hours = models.PositiveSmallIntegerField(default=2, help_text="Earliest a visit can be booked from now.")

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
