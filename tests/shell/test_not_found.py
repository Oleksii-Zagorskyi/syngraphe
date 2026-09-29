"""One answer for what does not exist and what may not be seen (ADR-0008)."""

from __future__ import annotations

import re
from typing import Any

import pytest
from django.test import Client

pytestmark = [pytest.mark.invariant, pytest.mark.django_db]

# Set per response and carrying nothing about the object: the clock, the request's own id, and
# the masked CSRF token in the shell's sign-out form.
PER_RESPONSE_HEADERS = {"Date", "X-Request-Id"}
CSRF_TOKEN = re.compile(rb'name="csrfmiddlewaretoken" value="[^"]+"')


def body_of(response: Any) -> bytes:
    return CSRF_TOKEN.sub(b'name="csrfmiddlewaretoken" value="-"', response.content)


def test_one_answer_for_missing_and_forbidden(signed_in: Any, tenant: Any) -> None:
    client, _ = signed_in("a.member@example.test", tenant=tenant)
    # The first response of a session sets the CSRF cookie; neither below may.
    client.get("/no-such-page/")

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


def test_bare_administration_paths_are_not_redirected(signed_in: Any, tenant: Any) -> None:
    """A path without its trailing slash answers as an unknown address, never with a redirect
    that would tell anyone the slashed page exists (ADR-0008)."""
    client, _ = signed_in("p.admin@example.test", tenant=tenant, is_platform_admin=True)
    anonymous = Client(headers={"host": "127.0.0.1"})

    bare = ("/administration", "/administration/platform/hosts", "/administration/tenant/groups")
    for path in bare:
        assert client.get(path).status_code == 404, path
        assert anonymous.get(path).status_code == 404, path
