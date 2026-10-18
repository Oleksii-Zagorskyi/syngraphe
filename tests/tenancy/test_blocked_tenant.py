"""A blocked organisation is closed to its members on every page and open to platform
administrators (ST-0065, DL-0376): the membership step — an active membership needs an active
organisation — answers *Nothing to show here* on its domain and from the platform host, and the
platform administrator reaches each page, the organisation listed and marked in the selector.

People, organisations and texts are synthetic examples."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import Any

import pytest
from django.test import Client

_spec = importlib.util.spec_from_file_location(
    "blocked_editing_fixtures", Path(__file__).resolve().parents[1] / "editing" / "conftest.py"
)
assert _spec is not None and _spec.loader is not None
_editing = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _editing
_spec.loader.exec_module(_editing)

# The editing tests' fixture: a document with its repository.
new_document = _editing.new_document

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

DOMAIN = "blocked.example.test"


def _pages(number: int) -> list[str]:
    """The pages a platform administrator reaches in an active organisation too; the edit tab
    is not among them, an administrator holding no *edit* of their own."""
    return [
        "/folder/1/",
        f"/document/{number}/",
        f"/document/{number}/info/",
        f"/document/{number}/pending/",
        f"/document/{number}/export/",
        "/notifications/",
        "/administration/",
        "/administration/tenant/users/",
        "/administration/tenant/template/",
    ]


def _tokenless(body: bytes) -> bytes:
    """A page without its form's per-response token."""
    return re.sub(rb'name="csrfmiddlewaretoken" value="[^"]*"', b"", body)


def _signed_in(user: Any, host: str, tenant: Any = None) -> Client:
    client = Client(headers={"host": host})
    client.force_login(user)
    if tenant is not None:
        session = client.session
        session["tenant_number"] = tenant.number
        session.save()
    return client


def test_closed_to_members_open_to_platform_administrators(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    from identity.models import Membership, User
    from tenancy.middleware import invalidate_host_cache
    from tenancy.models import TenantDomain

    _, member, membership = member_of("m.synthetic@example.test", is_tenant_admin=True)
    document = new_document(member)
    TenantDomain.objects.create(
        tenant=migrated_tenant, host=DOMAIN, is_default=True, actor_kind="system"
    )
    platform = User.objects.create_user(
        "p.admin@example.test", "Tr4vel-Plan-Ok", is_platform_admin=True
    )
    migrated_tenant.state = "blocked"
    migrated_tenant.save(update_fields=["state"])
    invalidate_host_cache()

    for client in (_signed_in(member, DOMAIN), _signed_in(member, "127.0.0.1", migrated_tenant)):
        # The one answer for what may not be seen: the body an address that never existed gets.
        nothing = _tokenless(client.get("/no-such-address/").content)
        assert '<section class="content empty">' in nothing.decode()
        for page in ["/", *_pages(document.number), f"/document/{document.number}/edit/"]:
            answer = client.get(page)
            assert answer.status_code == 404, page
            assert _tokenless(answer.content) == nothing, page
            assert document.title not in answer.content.decode(), page
    assert Membership.objects.get(pk=membership.pk).state == "active"

    for client in (
        _signed_in(platform, DOMAIN),
        _signed_in(platform, "127.0.0.1", migrated_tenant),
    ):
        assert client.get("/").status_code == 302
        for page in _pages(document.number):
            assert client.get(page).status_code == 200, page
