"""The interface language a person sees (DL-0498, DL-0501): their own `language` preference
when it is one the catalogue serves, otherwise the installation's default."""

from __future__ import annotations

from typing import Any

from django.conf import settings

PREFERENCE = "language"


def language_of(user: Any) -> str:
    """`user`'s interface language; the installation's default for a person without a choice,
    for a stray stored value and for anyone signed out."""
    from identity.models import UserPreference

    if user is None or not getattr(user, "is_authenticated", False):
        return settings.LANGUAGE_CODE
    chosen = (
        UserPreference.objects.filter(user_id=user.pk, key=PREFERENCE)
        .values_list("value", flat=True)
        .first()
    )
    if chosen in {code for code, _ in settings.LANGUAGES}:
        return str(chosen)
    return settings.LANGUAGE_CODE
