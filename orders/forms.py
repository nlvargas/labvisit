from django import forms

from catalog.insurers import ISAPRES
from catalog.models import Coverage
from labs.geo import distance_km, visit_fee

from .models import Order

ALLOWED_TYPES = {
    "image/jpeg", "image/png", "image/webp", "image/heic", "image/heif", "application/pdf",
}
MAX_BYTES = 10 * 1024 * 1024


class OrderUploadForm(forms.Form):
    file = forms.FileField(label="Foto o PDF de tu orden médica")

    def clean_file(self):
        upload = self.cleaned_data["file"]
        if upload.content_type not in ALLOWED_TYPES:
            raise forms.ValidationError("Sube una foto (JPG, PNG, HEIC) o un PDF.")
        if upload.size > MAX_BYTES:
            raise forms.ValidationError("El archivo es muy grande. El máximo es 10 MB.")
        return upload


class OrderDetailsForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ["coverage", "isapre", "address", "address_place_id", "latitude", "longitude", "apartment",
                  "address_notes"]
        labels = {
            "coverage": "¿Cuál es tu sistema previsional de salud?",
            "isapre": "¿Cuál es tu isapre?",
            "address": "¿Dónde te tomamos la muestra?",
            "apartment": "Depto, casa u oficina",
            "address_notes": "Indicaciones para llegar",
        }
        widgets = {
            "coverage": forms.RadioSelect,
            "isapre": forms.Select(choices=[("", "Elige tu isapre")] + [(name, name) for name in ISAPRES]),
            "address_place_id": forms.HiddenInput,
            "latitude": forms.HiddenInput,
            "longitude": forms.HiddenInput,
            "address": forms.TextInput(attrs={"placeholder": "Calle, número y comuna", "autocomplete": "street-address"}),
            "apartment": forms.TextInput(attrs={"placeholder": "Ej: depto 504, torre B"}),
            "address_notes": forms.TextInput(attrs={"placeholder": "Ej: tocar el timbre 504, conserje"}),
        }

    def __init__(self, *args, lab, require_all=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.lab = lab
        self.fields["coverage"].queryset = Coverage.objects.filter(lab=lab, active=True)
        self.fields["coverage"].empty_label = None
        self.isapre_ids = [str(c.pk) for c in self.fields["coverage"].queryset if c.kind == "isapre"]
        self.require_all = require_all
        for name in ("coverage", "address"):
            self.fields[name].required = require_all

    def clean(self):
        data = super().clean()
        coverage = data.get("coverage")
        if coverage is None or coverage.kind != "isapre":
            data["isapre"] = ""
        elif self.require_all and not data.get("isapre"):
            self.add_error("isapre", "Elige tu isapre.")
        lat, lng = data.get("latitude"), data.get("longitude")
        if lat is None or lng is None:
            data["latitude"] = data["longitude"] = None
        lab = self.lab
        self.distance_km = None
        if data["latitude"] is not None and lab.latitude is not None:
            self.distance_km = round(distance_km(lab.latitude, lab.longitude, data["latitude"], data["longitude"]), 1)
        self.visit_fee_clp = visit_fee(lab, self.distance_km) if data.get("address") else None
        if data.get("address") and self.visit_fee_clp is None and self.fields["address"].required:
            self.add_error("address", f"Por ahora no llegamos a esa dirección: está a más de {lab.max_visit_km:g} km.")
        return data

    def save(self, commit=True):
        order = super().save(commit=False)
        order.distance_km = self.distance_km
        order.visit_fee_clp = self.visit_fee_clp
        if commit:
            order.save()
        return order


class BookingForm(forms.Form):
    slot = forms.CharField(error_messages={"required": "Elige una hora."})
    contact_phone = forms.CharField(
        label="Tu teléfono", max_length=30,
        error_messages={"required": "Déjanos un teléfono para confirmar la visita."},
        widget=forms.TextInput(attrs={"type": "tel", "autocomplete": "tel", "placeholder": "+56 9 1234 5678"}),
    )

    def clean_contact_phone(self):
        phone = "".join(ch for ch in self.cleaned_data["contact_phone"] if ch.isdigit() or ch == "+")
        if len(phone.lstrip("+")) < 8:
            raise forms.ValidationError("Revisa el teléfono.")
        return phone
