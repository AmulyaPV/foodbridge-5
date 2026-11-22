from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import HotelProfile, IndividualProfile, NGOProfile, Role, User


class EmailLoginForm(AuthenticationForm):
    username = forms.CharField(label="Email", widget=forms.EmailInput(attrs={"autofocus": True}))


class _BaseRegisterForm(UserCreationForm):
    """Shared account fields (email + password) for both hotel and NGO sign-up."""

    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ["email"]

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists. Try logging in instead.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data["email"]
        user.email = self.cleaned_data["email"]
        user.role = self.role
        if commit:
            user.save()
        return user


class HotelRegisterForm(_BaseRegisterForm):
    role = Role.HOTEL

    class Meta(_BaseRegisterForm.Meta):
        pass


class HotelProfileForm(forms.ModelForm):
    class Meta:
        model = HotelProfile
        fields = ["name", "contact_person", "phone", "address", "latitude", "longitude", "fssai_number", "photo"]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 2}),
            "latitude": forms.HiddenInput(),
            "longitude": forms.HiddenInput(),
        }
        labels = {"name": "Hotel / restaurant name", "fssai_number": "Licence / FSSAI number"}


class NGORegisterForm(_BaseRegisterForm):
    role = Role.NGO

    class Meta(_BaseRegisterForm.Meta):
        pass


class NGOProfileForm(forms.ModelForm):
    class Meta:
        model = NGOProfile
        fields = [
            "name", "contact_person", "phone", "address", "latitude", "longitude",
            "registration_number", "daily_capacity", "service_area", "certificate",
        ]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 2}),
            "latitude": forms.HiddenInput(),
            "longitude": forms.HiddenInput(),
        }
        labels = {"name": "NGO name", "daily_capacity": "Daily collection capacity (servings)"}


class IndividualRegisterForm(_BaseRegisterForm):
    role = Role.INDIVIDUAL

    class Meta(_BaseRegisterForm.Meta):
        pass


class IndividualProfileForm(forms.ModelForm):
    class Meta:
        model = IndividualProfile
        fields = ["name", "phone", "address", "latitude", "longitude", "household_size", "supporting_document"]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 2}),
            "latitude": forms.HiddenInput(),
            "longitude": forms.HiddenInput(),
        }
        labels = {"name": "Your full name"}


class VerificationDecisionForm(forms.Form):
    DECISIONS = [("approve", "Approve"), ("reject", "Reject"), ("suspend", "Suspend")]
    decision = forms.ChoiceField(choices=DECISIONS, widget=forms.RadioSelect)
    note = forms.CharField(
        label="Reason (shown to the user for reject or suspend)",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("decision") in {"reject", "suspend"} and not cleaned.get("note", "").strip():
            self.add_error("note", "Please give a short reason.")
        return cleaned
