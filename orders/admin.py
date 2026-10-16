from django.contrib import admin

from .models import Order, OrderLine


class OrderLineInline(admin.TabularInline):
    model = OrderLine
    extra = 0
    fields = ["position", "raw_text", "legible", "exam", "confidence", "origin", "selected"]
    readonly_fields = ["raw_text", "legible", "confidence", "origin"]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["public_id", "lab", "status", "slot_start", "visit_status", "channel", "created_at"]
    list_filter = ["lab", "status", "visit_status", "channel"]
    readonly_fields = ["public_id", "patient_name", "patient_rut", "patient_rut_valid", "doctor_name", "doctor_rut", "order_date", "extraction", "error", "reader_provider", "reader_model", "prompt_version", "created_at"]
    inlines = [OrderLineInline]
