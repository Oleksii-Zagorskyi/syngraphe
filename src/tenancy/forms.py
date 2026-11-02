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


class PersonByAddressForm(forms.Form):
    """An address naming a person the form's rule accepts; `person` once valid."""

    email = forms.EmailField(
        label=_("Email address"),
        max_length=254,
        error_messages={"invalid": _("Enter a valid email address.")},
    )

    person: User
    missing = _("No registered person has this address.")

    def find(self, email: str) -> User | None:
        return User.objects.filter(email=email, is_tombstoned=False, self_blocked=False).first()

    def clean_email(self) -> str:
        email = fold_email(self.cleaned_data["email"])
        person = self.find(email)
        if person is None:
            raise forms.ValidationError(self.missing)
        self.person = person
        return email


class GrantForm(PersonByAddressForm):
    """*Grant to*: a registered person, neither erased nor blocked by themselves — a platform
    page, so naming a missing person tells only a platform administrator."""

    def clean_email(self) -> str:
        email = fold_email(self.cleaned_data["email"])
        if User.objects.filter(email=email, is_tombstoned=False, self_blocked=True).exists():
            raise forms.ValidationError(
                _("This person has blocked their own account; the role cannot be granted.")
            )
        return super().clean_email()


class AppointForm(PersonByAddressForm):
    """*Appoint an administrator…*: an active member of the organisation."""

    missing = _("No active member of this organisation has this address.")

    def __init__(self, *args: Any, tenant: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.tenant = tenant

    def find(self, email: str) -> User | None:
        from identity.models import Membership, member_in_good_standing_q

        membership = (
            Membership.objects.filter(member_in_good_standing_q(), tenant=self.tenant)
            .filter(user__email=email)
            .select_related("user")
            .first()
        )
        self.membership = membership
        return membership.user if membership is not None else None
