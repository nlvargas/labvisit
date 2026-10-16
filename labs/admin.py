from django.contrib import admin

from .models import Lab, LabMember, OpeningHours


class OpeningHoursInline(admin.TabularInline):
    model = OpeningHours
    extra = 0


class LabMemberInline(admin.TabularInline):
    model = LabMember
    extra = 0
    verbose_name = "staff user"


@admin.register(Lab)
class LabAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "phone", "is_active"]
    prepopulated_fields = {"slug": ["name"]}
    inlines = [OpeningHoursInline, LabMemberInline]
    fieldsets = [
        (None, {"fields": ["name", "slug", "is_active", "phone", "whatsapp", "whatsapp_phone_number_id", "email"]}),
        ("Style", {"fields": ["brand_color", "font", "corners", "logo", "tagline", "address_line", "website_url",
                              "results_url"]}),
        ("Home visits", {"fields": ["latitude", "longitude", "visit_base_fee_clp", "visit_fee_per_km_clp",
                                    "max_visit_km", "visits_per_slot", "booking_days_ahead", "min_notice_hours"]}),
    ]
