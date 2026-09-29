"""Passwords the platform draws for a person it creates by command (DL-0284, DL-0343)."""

from __future__ import annotations

import secrets
import string

# Printable ASCII without the space: nothing a person must guess the spelling of.
ALPHABET = string.ascii_letters + string.digits + string.punctuation
CLASSES = (string.ascii_uppercase, string.ascii_lowercase, string.digits, string.punctuation)


def password(length: int = 20) -> str:
    """A password of `length` characters holding each of DL-0284's four classes, redrawn until
    it does."""
    while True:
        drawn = "".join(secrets.choice(ALPHABET) for _ in range(length))
        if all(any(c in chars for c in drawn) for chars in CLASSES):
            return drawn
