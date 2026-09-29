"""The operator's two commands: releasing a hold that will not release, and reading a draft as
stored.

People and titles are synthetic examples."""

from __future__ import annotations

import json
from io import StringIO
from typing import Any

import pytest
from django.core.management import call_command

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]


def test_release_hold(migrated_tenant: Any, member_of: Any, new_document: Any) -> None:
    from audit.models import AuditEvent
    from editing.models import Draft, Hold

    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    client.post(f"/document/{document.number}/edit/take/")

    call_command(
        "release_hold",
        f"--tenant={migrated_tenant.number}",
        f"--document={document.number}",
        "--reason=the holder left",
        stdout=StringIO(),
    )

    with schema_context(migrated_tenant.number):
        hold = Hold.objects.get(document=document)
        assert hold.release_kind == "forced"
        assert hold.released_at is not None and hold.released_by is None
        assert Draft.objects.filter(hold=hold).exists()
    events = AuditEvent.objects.filter(action="document.hold_released")
    assert events.count() == 1
    event = events.get()
    assert event.actor_kind == "system"
    assert event.after == {
        "number": document.number,
        "release_kind": "forced",
        "reason": "the holder left",
    }


def test_inspect_draft(migrated_tenant: Any, member_of: Any, new_document: Any) -> None:
    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    client.post(f"/document/{document.number}/edit/take/")
    out = StringIO()

    call_command(
        "inspect_draft",
        f"--tenant={migrated_tenant.number}",
        f"--document={document.number}",
        stdout=out,
    )

    printed = json.loads(out.getvalue())
    assert printed["document"] == document.number
    assert printed["hold"]["released_at"] is None
    assert len(printed["base_commit"]) == 40
    assert set(printed["content"]) == {"document.md", "frontmatter"}
