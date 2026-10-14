"""Forms of the identity pages."""

from __future__ import annotations

from typing import Any

from django import forms
from django.contrib.auth.password_validation import validate_password
from django.utils.translation import gettext_lazy as _

from identity.models import User, fold_email


class SetupTokenForm(forms.Form):
    token = forms.CharField(
        label=_("Setup token"),
        max_length=128,
        strip=True,
        widget=forms.TextInput(
            attrs={"class": "mono", "autocomplete": "off", "spellcheck": "false"}
        ),
    )


class FirstAdministratorForm(forms.Form):
    email = forms.EmailField(
        label=_("Email address"),
        max_length=254,
        error_messages={"invalid": _("Enter a valid email address.")},
        widget=forms.EmailInput(attrs={"autocomplete": "username"}),
    )
    password = forms.CharField(
        label=_("Password"),
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password_again = forms.CharField(
        label=_("Password again"),
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def clean_email(self) -> str:
        email = fold_email(self.cleaned_data["email"])
        # Only the installer reaches this form, before any administrator exists; naming the
        # clash tells them nothing they could not read from the database they just installed.
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError(_("This address already belongs to an account."))
        return email

    def clean(self) -> dict[str, Any]:
        """Every refusal at once: the rule is checked against the address as typed, whether or not
        the address itself was accepted, and the two entries are compared either way."""
        cleaned = super().clean() or {}
        password = cleaned.get("password")
        if password is None:
            return cleaned
        typed = cleaned.get("email") or self.data.get("email", "")
        try:
            validate_password(password, user=User(email=typed))
        except forms.ValidationError as error:
            self.add_error("password", error)
        if password != cleaned.get("password_again"):
            self.add_error("password_again", _("The two passwords differ."))
        return cleaned


class SignInForm(forms.Form):
    email = forms.EmailField(
        label=_("Email address"),
        max_length=254,
        widget=forms.EmailInput(attrs={"autocomplete": "username"}),
    )
    password = forms.CharField(
        label=_("Password"),
        strip=False,
        max_length=1024,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )

    def clean_email(self) -> str:
        """The stored form of the address; one that folds past the column's length is refused,
        so it counts against the client address alone."""
        email = fold_email(self.cleaned_data["email"])
        if len(email) > 254:
            raise forms.ValidationError(_("Enter a valid email address."))
        return email


class InviteForm(forms.Form):
    """*Invite by email*: an address, and the organisation's groups to join."""

    email = forms.EmailField(
        label=_("Email address"),
        max_length=254,
        error_messages={"invalid": _("Enter a valid email address.")},
    )
    groups = forms.MultipleChoiceField(
        label=_("Groups to join"), required=False, widget=forms.CheckboxSelectMultiple
    )

    def __init__(self, *args: Any, groups: list[Any], **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        field = self.fields["groups"]
        assert isinstance(field, forms.MultipleChoiceField)
        field.choices = [(str(group.pk), group.name) for group in groups]

    def clean_email(self) -> str:
        email = fold_email(self.cleaned_data["email"])
        if len(email) > 254:
            raise forms.ValidationError(_("Enter a valid email address."))
        return email


class SetPasswordForm(forms.Form):
    """The password an invitation or a reset sets, under the platform's rule (DL-0284)."""

    password = forms.CharField(
        label=_("Password"),
        strip=False,
        max_length=1024,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password_again = forms.CharField(
        label=_("Password again"),
        strip=False,
        max_length=1024,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def __init__(self, *args: Any, user: User, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.user = user

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        password = cleaned.get("password")
        if password is None:
            return cleaned
        try:
            validate_password(password, user=self.user)
        except forms.ValidationError as error:
            self.add_error("password", error)
        if password != cleaned.get("password_again"):
            self.add_error("password_again", _("The two passwords differ."))
        return cleaned


class ResetRequestForm(forms.Form):
    """The address a reset is asked for; never checked against the accounts here (ASR-17)."""

    email = forms.EmailField(
        label=_("Email address"),
        max_length=254,
        error_messages={"invalid": _("Enter a valid email address.")},
        widget=forms.EmailInput(attrs={"autocomplete": "username"}),
    )
