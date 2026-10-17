from django.contrib import admin

from .models import Coverage, Exam, Price, SampleContainer


class PriceInline(admin.TabularInline):
    model = Price
    extra = 0

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "coverage" and request.resolver_match.kwargs.get("object_id"):
            exam = Exam.objects.filter(pk=request.resolver_match.kwargs["object_id"]).first()
            if exam:
                kwargs["queryset"] = Coverage.objects.filter(lab=exam.lab)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ["name", "lab", "fonasa_code", "sample_type", "container", "fasting_hours", "active"]
    list_filter = ["lab", "sample_type", "container", "active"]
    list_editable = ["container"]
    search_fields = ["name", "synonyms", "fonasa_code"]
    inlines = [PriceInline]


@admin.register(Coverage)
class CoverageAdmin(admin.ModelAdmin):
    list_display = ["name", "lab", "kind", "position", "active"]
    list_filter = ["lab", "kind"]


@admin.register(SampleContainer)
class SampleContainerAdmin(admin.ModelAdmin):
    list_display = ["name", "lab", "cap_color", "minutes"]
    list_filter = ["lab"]
