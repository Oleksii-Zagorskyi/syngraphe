"""The password rule (DL-0284): ten US-keyboard characters, four kinds, two further checks."""

from __future__ import annotations

import pytest
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

pytestmark = pytest.mark.fast

EMAIL = "a.person@example.test"


def refusals(password: str) -> list[str]:
    from identity.models import User

    try:
        validate_password(password, user=User(email=EMAIL))
    except ValidationError as error:
        return [e.code or "" for e in error.error_list]
    return []


@pytest.mark.parametrize("password", ["Tr4vel-Plan-Ok", "Correct horse 9", "Aa1!aaaaaa"])
def test_accepted(password: str) -> None:
    assert refusals(password) == []


@pytest.mark.parametrize(
    ("password", "code"),
    [
        ("Aa1!aaaaa", "password_too_short"),
        ("tr4vel-plan-ok", "password_missing_kind"),
        ("TR4VEL-PLAN-OK", "password_missing_kind"),
        ("Travel-Plan-Ok", "password_missing_kind"),
        ("Tr4velPlanOk", "password_missing_kind"),
        ("Tr4vel-Plan-Окей", "password_not_us_keyboard"),
        ("Tr4vel-Plän-Ok", "password_not_us_keyboard"),
        ("Password1!", "password_too_common"),
        ("A.person@example.test1", "password_too_similar"),
    ],
)
def test_refused(password: str, code: str) -> None:
    assert code in refusals(password)
