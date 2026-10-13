"""The sending address's form (DL-0202, DL-0368, DL-0371, DL-0388, DL-0390): every value with its
rule. The password is write-only — never filled in — and an empty field keeps the stored one only
while the server it was entered for stays as stored. Names and addresses in any script are kept as
the mail needs them: a host and an address's domain in their ASCII form."""

from __future__ import annotations

import ipaddress
import re
from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _

from mail.models import Security

# A host name of labels in their ASCII form: never a scheme, a path or a port.
HOST = re.compile(
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*"
)
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
# What the stored password was entered for; a change to any of them asks for it again.
SERVER = ("host", "port", "security", "username")
HOST_RULE = _("A server's name or address, with no smtp://, path or port.")


def _ascii_domain(name: str) -> str | None:
    """`name` in its ASCII form, or `None` when it is not a name a mail server can carry."""
    try:
        return name.encode("idna").decode("ascii")
    except UnicodeError:
        return None


class SenderForm(forms.Form):
    host = forms.CharField(label=_("Server"), max_length=253)
    port = forms.IntegerField(label=_("Port"), min_value=1, max_value=65535)
    security = forms.ChoiceField(
        label=_("Connection"),
        choices=[
            (Security.STARTTLS, _("STARTTLS")),
            (Security.TLS, _("TLS")),
            (Security.NONE, _("Unencrypted")),
        ],
    )
    address = forms.EmailField(label=_("Sending address"), max_length=254)
    display_name = forms.CharField(label=_("Sender's name"), max_length=100, required=False)
    username = forms.CharField(label=_("User name"), max_length=254, required=False)
    password = forms.CharField(
        label=_("Password"),
        max_length=500,
        required=False,
        strip=False,
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
    )

    def __init__(self, *args: Any, stored: dict[str, Any] | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.stored = stored or {}
        if self.stored.get("password"):
            self.fields["password"].label = _("Replace the password")

    def clean_host(self) -> str:
        host = str(self.cleaned_data["host"]).strip().rstrip(".")
        if "%" in host or CONTROL.search(host) or " " in host:
            raise forms.ValidationError(HOST_RULE)
        try:
            return str(ipaddress.ip_address(host))
        except ValueError:
            pass
        name = _ascii_domain(host)
        if name is None or len(name) > 253 or not HOST.fullmatch(name):
            raise forms.ValidationError(HOST_RULE)
        return name

    def clean_address(self) -> str:
        local, _at, domain = str(self.cleaned_data["address"]).rpartition("@")
        name = _ascii_domain(domain)
        if not local.isascii() or name is None:
            raise forms.ValidationError(
                _("The part before @ may hold Latin letters, digits and symbols only.")
            )
        return f"{local}@{name}"

    def clean_display_name(self) -> str:
        name = str(self.cleaned_data["display_name"]).strip()
        if CONTROL.search(name):
            raise forms.ValidationError(_("The name may hold printable characters only."))
        return name

    def clean_username(self) -> str:
        username = str(self.cleaned_data["username"]).strip()
        # Python's mail library signs in with ASCII alone; refused here, not at the first send.
        if not username.isascii():
            raise forms.ValidationError(
                _("The user name may hold Latin letters, digits and symbols only.")
            )
        return username

    def clean_password(self) -> str:
        password = str(self.cleaned_data["password"])
        if not password.isascii():
            raise forms.ValidationError(
                _("The password may hold Latin letters, digits and symbols only.")
            )
        return password

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        username = cleaned.get("username")
        if username and not cleaned.get("password") and "password" not in self.errors:
            if not self.stored.get("password"):
                self.add_error("password", _("Signing in with a user name needs a password."))
            elif any(cleaned.get(field) != self.stored.get(field) for field in SERVER):
                # The stored password goes only to the server it was entered for (DL-0390).
                self.add_error(
                    "password", _("Type the password again: the server or user name has changed.")
                )
        host = cleaned.get("host")
        if username and host and cleaned.get("security") == Security.NONE and not _loopback(host):
            # The password would cross the network in the clear (DL-0388).
            self.add_error(
                "security",
                _(
                    "Signing in needs an encrypted connection, unless the server runs on this "
                    "machine."
                ),
            )
        return cleaned


def _loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False
