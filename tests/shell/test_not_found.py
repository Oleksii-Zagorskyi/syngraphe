"""One answer for what does not exist and what may not be seen (ADR-0008)."""

from __future__ import annotations

import re
from typing import Any

import pytest

pytestmark = [pytest.mark.invariant, pytest.mark.django_db]

# Set per response and carrying nothing about the object: the clock, the request's own id, and
# the masked CSRF token in the shell's sign-out form.
PER_RESPONSE_HEADERS = {"Date", "X-Request-Id"}
CSRF_TOKEN = re.compile(rb'name="csrfmiddlewaretoken" value="[^"]+"')


def body_of(response: Any) -> bytes:
    return CSRF_TOKEN.sub(b'name="csrfmiddlewaretoken" value="-"', response.content)


def test_one_answer_for_missing_and_forbidden(signed_in: Any, tenant: Any) -> None:
    client, _ = signed_in("a.member@example.test", tenant=tenant)
    client.get("/")  # the first response of a session sets the CSRF cookie; neither below may

    missing = client.get("/no-such-page/")
    forbidden = client.get("/administration/")

    assert missing.status_code == forbidden.status_code == 404
    assert body_of(missing) == body_of(forbidden)
    assert {k: v for k, v in missing.headers.items() if k not in PER_RESPONSE_HEADERS} == {
        k: v for k, v in forbidden.headers.items() if k not in PER_RESPONSE_HEADERS
    }
    assert set(missing.cookies) == set(forbidden.cookies)
    body = missing.content.decode()
    assert "Nothing to show here" in body or "нічого" in body
    assert "administration" not in body.lower().replace("/administration/", "")
