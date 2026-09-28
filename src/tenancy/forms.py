"""Forms of the platform's administration pages."""

from __future__ import annotations

from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _

from identity.models import User, fold_email


class TenantForm(forms.Form):
    name = forms.CharField(label=_("Name"), max_length=200)
    first_administrator = forms.EmailField(
        label=_("First administrator — email address"),
        max_length=254,
        error_messages={
            "required": _("An organisation is never created without an administrator."),
            "invalid": _("Enter a valid email address."),
        },
    )

    person: User

    def clean_first_administrator(self) -> str:
        email = fold_email(self.cleaned_data["first_administrator"])
        # Someone who can act as its administrator: not erased, and not blocked by themselves.
        person = User.objects.filter(email=email, is_tombstoned=False, self_blocked=False).first()
        if person is None:
            raise forms.ValidationError(_("No registered person has this address."))
        self.person = person
        return email


class HostForm(forms.Form):
    host = forms.CharField(label=_("Host"), max_length=260)
    belongs_to = forms.CharField(max_length=20)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["host"].widget.attrs.update(
            {"placeholder": "docs.example-org.example", "spellcheck": "false"}
        )
