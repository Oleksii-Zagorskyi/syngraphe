"""The platform's own parts of the password rule (DL-0284); the length and the common-password
checks are the framework's validators, configured in the settings."""

from __future__ import annotations

from typing import Any

from django.contrib.auth.password_validation import UserAttributeSimilarityValidator
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

# Printable ASCII: every character a standard US keyboard types, the space included.
US_KEYBOARD = frozenset(chr(code) for code in range(0x20, 0x7F))


class KeyboardCompositionValidator:
    """Only US-keyboard characters, with an uppercase and a lowercase ASCII letter, a digit and a
    special character — any of those characters that is neither a letter nor a digit."""

    def validate(self, password: str, user: Any = None) -> None:
        if not set(password) <= US_KEYBOARD:
            raise ValidationError(
                _("A password may contain only characters of a standard US keyboard."),
                code="password_not_us_keyboard",
            )
        kinds = (
            any("A" <= c <= "Z" for c in password),
            any("a" <= c <= "z" for c in password),
            any("0" <= c <= "9" for c in password),
            any(not c.isalnum() for c in password),
        )
        if not all(kinds):
            raise ValidationError(
                _(
                    "This password must contain an uppercase letter, a lowercase letter, "
                    "a digit and a special character."
                ),
                code="password_missing_kind",
            )

    def get_help_text(self) -> str:
        return _(
            "An uppercase letter (A–Z), a lowercase letter (a–z), a digit (0–9) and a special "
            "character; only characters of a standard US keyboard."
        )


class AddressSimilarityValidator(UserAttributeSimilarityValidator):
    """The framework's similarity check against the person's email address, with a message of the
    platform's own: the framework's names the field in a form Ukrainian cannot inflect."""

    def __init__(self) -> None:
        super().__init__(user_attributes=("email",))

    def validate(self, password: str, user: Any = None) -> None:
        try:
            super().validate(password, user)
        except ValidationError as error:
            raise ValidationError(
                _("The password is too similar to the email address."),
                code="password_too_similar",
            ) from error
