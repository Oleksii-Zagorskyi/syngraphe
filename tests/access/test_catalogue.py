"""The access history renders in Ukrainian from the one catalogue: the form, an answer with its
lines, groups and changes, *any document* at its bound, and the form's refusals.

People, groups, documents and their histories are synthetic examples."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

from tenancy.schemas import schema_context

_HERE = Path(__file__).resolve().parent


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_review = _load("access_catalogue_review", _HERE.parent / "review" / "test_catalogue.py")
_history = _load("access_catalogue_history", _HERE / "test_access_history.py")

PAGE = "/administration/tenant/access-history/"


@pytest.mark.integration
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_catalogue_covers_the_access_history(
    migrated_tenant: Any, member_of: Any, make_document: Any, settings: Any
) -> None:
    settings.LANGUAGE_CODE = "uk"
    settings.DISPLAY_TIMEZONE = "UTC"
    admin_client, admin, _ = member_of("t.synthetic@example.test", is_tenant_admin=True)
    _, _, membership = member_of("r.synthetic@example.test")
    _at = _history._at
    with schema_context(migrated_tenant.number):
        document = _history._dated(make_document(created_by=admin), _at(1, 0))
        readers = _history._group("Readers", admin)
        _history._right(readers, "view_canonical", admin, _at(1, 9))
        _history._right(readers, "accept", None, _at(1, 9, 30))
        _history._link(readers, document, admin, _at(1, 10))
        _history._member(readers, membership, admin, _at(1, 11))
        _history._state(membership, "active", "blocked", admin, _at(2, 9))
        _history._admin_flag(membership, False, True, admin, _at(2, 10))
        _history._link(readers, document, admin, _at(2, 11), "removed")
        _history._right(readers, "accept", admin, _at(2, 12), "removed")
        _history._member(readers, membership, admin, _at(2, 13), "removed")
        _history._state(membership, "blocked", "active", admin, _at(2, 14))
        _history._admin_flag(membership, True, False, admin, _at(2, 15))
        _history._organisation(migrated_tenant, "active", "blocked", admin, _at(3, 9))
        for n in range(200):
            _history._member(readers, membership, admin, _at(4, 0, 0, 0, n))
    from audit.models import AuditEvent

    for action, day in (("document.archived", 3), ("document.restored", 4)):
        AuditEvent.objects.create(
            tenant=migrated_tenant,
            actor=admin,
            actor_kind="user",
            action=action,
            object_type="document",
            object_id=document.pk,
            after={"number": document.number},
            at=_at(day, 10),
        )

    ids = _review.message_ids(_review.CATALOGUE.read_text(encoding="utf-8"))
    number = document.number
    bodies = {
        "the form": admin_client.get(PAGE).content.decode(),
        "before it existed": admin_client.get(
            PAGE, {"document": number, "on": "2026-02-28"}
        ).content.decode(),
        "a day": admin_client.get(PAGE, {"document": number, "on": "2026-03-01"}).content.decode(),
        "archived and blocked": admin_client.get(
            PAGE, {"document": number, "on": "2026-03-03"}
        ).content.decode(),
        "any document": admin_client.get(
            PAGE, {"document": "any", "on": "2026-03-04"}
        ).content.decode(),
        "refused": admin_client.get(
            PAGE, {"document": "any", "on": "2999-01-01", "edition": "1.0"}
        ).content.decode(),
    }
    # The format strings, whose ids never match the page as drawn.
    own = [
        "readable by",
        "people",
        "linked ",
        "granted ",
        "added to",
        "removed from",
        "membership",
        "administrator",
        "archived",
        "restored",
        "The newest",
        "did not exist",
    ]
    for name, body in bodies.items():
        shown = _review.text_of(body)
        leaked = [message for message in [*ids, *own] if message in shown]
        assert leaked == [], (name, leaked)
