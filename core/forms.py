from django import forms
from django.core.validators import RegexValidator
from django.forms import modelformset_factory
from django.utils import timezone

from .models import FoodItem, ListingPhoto, NGONeed
from .models import ReportReason
from .validators import validate_phone
from .validators import validate_photo_file as _validate_photo  # re-exported for clarity where imported

MAX_PHOTOS = 5


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """A FileField that accepts several files at once (Django's documented pattern)."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_clean = super().clean
        if isinstance(data, (list, tuple)):
            return [single_clean(item, initial) for item in data]
        return [single_clean(data, initial)] if data else []


class TimesForm(forms.Form):
    """The three moments that matter for a listing, with the checks they share."""

    pickup_window_start = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}), label="Pickup opens"
    )
    pickup_window_end = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}), label="Collection deadline"
    )
    safe_until = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}), label="Safe to eat until"
    )

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("pickup_window_start")
        end = cleaned.get("pickup_window_end")
        safe_until = cleaned.get("safe_until")
        now = timezone.now()
        if safe_until and safe_until <= now:
            self.add_error("safe_until", "This has to be in the future.")
        if start and end and end <= start:
            self.add_error("pickup_window_end", "The collection deadline must come after pickup opens.")
        if start and safe_until and start > safe_until:
            self.add_error("pickup_window_start", "Pickup can't open after the food is unsafe.")
        return cleaned


class _DetailsMixin(forms.Form):
    title = forms.CharField(
        max_length=120, required=False, label="Food name",
        widget=forms.TextInput(attrs={"placeholder": "e.g. Veg biryani and raita"}),
    )
    pickup_location = forms.CharField(
        required=False, label="Pickup address",
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Where to collect from. Starts as your hotel address; change it for events or a back entrance.",
    )
    contact_phone = forms.CharField(
        max_length=20, required=False, label="Contact number at pickup", validators=[validate_phone],
    )
    storage_notes = forms.CharField(
        max_length=500, required=False, label="Storage and handling notes",
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "e.g. Kept hot above 60 °C, packed in sealed steel containers"}),
    )


class ListingForm(_DetailsMixin, TimesForm):
    total_servings = forms.IntegerField(min_value=1, label="Total servings available")
    photos = MultipleFileField(required=False, label="Photos (up to 5)")
    field_order = [
        "title", "total_servings", "pickup_location", "contact_phone", "storage_notes",
        "pickup_window_start", "pickup_window_end", "safe_until", "photos",
    ]

    def clean_photos(self):
        photos = self.cleaned_data.get("photos") or []
        if len(photos) > MAX_PHOTOS:
            raise forms.ValidationError(f"Please choose at most {MAX_PHOTOS} photos.")
        for photo in photos:
            _validate_photo(photo)
        return photos


class ListingEditForm(_DetailsMixin, TimesForm):
    """Everything about a live listing that can change after posting (the food items cannot)."""

    field_order = [
        "title", "pickup_location", "contact_phone", "storage_notes",
        "pickup_window_start", "pickup_window_end", "safe_until",
    ]


class RepostForm(TimesForm):
    pass


class FoodItemForm(forms.ModelForm):
    class Meta:
        model = FoodItem
        fields = ["name", "category", "quantity", "unit", "cooking_time_note", "allergens_note"]
        widgets = {"allergens_note": forms.TextInput(attrs={"placeholder": "e.g. contains nuts, dairy (optional)"})}


FoodItemFormSet = modelformset_factory(
    FoodItem,
    form=FoodItemForm,
    extra=0,
    can_delete=True,
    min_num=1,
    validate_min=True,
)


class PickupRequestForm(forms.Form):
    amount = forms.IntegerField(min_value=1, label="Servings you want to collect")


class ReportForm(forms.Form):
    reason = forms.ChoiceField(choices=ReportReason.choices, widget=forms.RadioSelect, label="What is wrong?")
    details = forms.CharField(
        max_length=300, required=False, label="Anything an admin should know?",
        widget=forms.Textarea(attrs={"rows": 3}),
    )


class HandoverCodeForm(forms.Form):
    code = forms.CharField(
        label="Pickup code",
        max_length=6,
        min_length=6,
        validators=[RegexValidator(r"^\d{6}$", "The code is exactly 6 digits.")],
        widget=forms.TextInput(
            attrs={"inputmode": "numeric", "autocomplete": "off", "pattern": "[0-9]{6}", "class": "fb-code-input"}
        ),
    )

    def clean_code(self):
        return self.cleaned_data["code"].strip()


class OnTheWayForm(forms.Form):
    eta_minutes = forms.IntegerField(min_value=1, max_value=240, label="How many minutes away are you?")


class ReasonForm(forms.Form):
    reason = forms.CharField(label="Reason", widget=forms.Textarea(attrs={"rows": 2}))


class NGONeedForm(forms.ModelForm):
    class Meta:
        model = NGONeed
        fields = ["servings_needed", "needed_by", "notes"]
        widgets = {
            "needed_by": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def clean_needed_by(self):
        needed_by = self.cleaned_data["needed_by"]
        if needed_by <= timezone.now():
            raise forms.ValidationError("This has to be in the future.")
        return needed_by
