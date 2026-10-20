from django.contrib import admin

from .models import Lab, LabMember, Nurse, NurseSchedule, NurseTimeOff, OpeningHours


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
        (None, {"fields": ["name", "slug", "is_active", "phone", "whatsapp", "whatsapp_phone_number_id"]}),
        ("Style", {"fields": ["brand_color", "font", "corners", "logo", "tagline", "address_line", "website_url",
                              "results_url"]}),
        ("Demo", {"fields": ["show_online_payment"]}),
        ("Home visits", {"fields": ["latitude", "longitude", "visit_base_fee_clp", "visit_fee_per_km_clp",
                                    "max_visit_km", "booking_days_ahead", "min_notice_hours"]}),
        ("Routing", {"fields": ["service_base_min", "service_per_tube_min", "service_container_min",
                                "travel_speed_kmh", "detour_factor", "max_sample_age_min", "drop_off_min",
                                "lab_return_ratio", "min_lab_minutes", "discount_share",
                                "discount_max_clp", "discount_min_clp"]}),
    ]


class NurseScheduleInline(admin.TabularInline):
    model = NurseSchedule
    extra = 0


class NurseTimeOffInline(admin.TabularInline):
    model = NurseTimeOff
    extra = 0


@admin.register(Nurse)
class NurseAdmin(admin.ModelAdmin):
    list_display = ["name", "lab", "phone", "is_active"]
    list_filter = ["lab", "is_active"]
    readonly_fields = ["access_token"]
    inlines = [NurseScheduleInline, NurseTimeOffInline]
