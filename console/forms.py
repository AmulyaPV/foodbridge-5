from django import forms


class ModerationDecisionForm(forms.Form):
    DECISIONS = [("remove", "Remove the listing"), ("dismiss", "Dismiss the report")]
    decision = forms.ChoiceField(choices=DECISIONS, widget=forms.RadioSelect, label="Decision")
    note = forms.CharField(
        label="Reason (the hotel sees this if you remove the listing)",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("decision") == "remove" and not cleaned.get("note", "").strip():
            self.add_error("note", "Please give a short reason. The hotel will see it.")
        return cleaned


class RemoveListingForm(forms.Form):
    reason = forms.CharField(label="Reason (the hotel sees this)", widget=forms.Textarea(attrs={"rows": 2}))
