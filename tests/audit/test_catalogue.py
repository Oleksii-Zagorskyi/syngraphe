"""The audit log renders in Ukrainian from the one catalogue: the filters, the events at the bound
and a refused filter.

People, organisations and events are synthetic examples."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

_spec = importlib.util.spec_from_file_location(
    "audit_catalogue", Path(__file__).resolve().parents[1] / "review" / "test_catalogue.py"
)
assert _spec is not None and _spec.loader is not None
_review = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_review)

PAGE = "/administration/platform/audit/"


@pytest.mark.integration
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_catalogue_covers_the_audit_log(
    migrated_tenant: Any, member_of: Any, signed_in_without_tenant: Any, settings: Any
) -> None:
    from audit.models import AuditEvent

    settings.LANGUAGE_CODE = "uk"
    _, person, _ = member_of("p.synthetic@example.test")
    start = datetime(2026, 3, 1, tzinfo=UTC)
    for n in range(200):
        AuditEvent.objects.create(
            tenant=migrated_tenant if n % 2 else None,
            actor=person if n % 3 else None,
            actor_kind="user" if n % 3 else "system",
            action="synthetic.changed",
            object_type="document",
            # Payloads are codes and numbers, drawn as stored and never translated.
            before={"count": n},
            after={"count": n + 1, "number": n},
            at=start + timedelta(minutes=n),
        )
    client = signed_in_without_tenant("o.synthetic@example.test", is_platform_admin=True)
    ids = _review.message_ids(_review.CATALOGUE.read_text(encoding="utf-8"))
    bodies = {
        "the events": client.get(PAGE).content.decode(),
        "refused": client.get(
            PAGE, {"since": "2026-03-04", "until": "2026-03-03"}
        ).content.decode(),
        "the frame": client.get("/administration/").content.decode(),
    }
    # The format string, whose id never matches the page as drawn; the actors' kinds.
    own = ["The newest", "events matching", "person", "the platform"]
    for name, body in bodies.items():
        shown = _review.text_of(body)
        leaked = [message for message in [*ids, *own] if message in shown]
        assert leaked == [], (name, leaked)
