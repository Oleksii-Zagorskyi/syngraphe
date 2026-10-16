"""The held work on archiving (DL-0449, DL-0456, DL-0414): archiving is always allowed; an open
hold is released as a force release releases it, the draft kept; a reservation is ended with the
platform's reason *archived*; a finish that stopped after its commit is completed instead.

People, groups and texts are synthetic examples; the texts are invented."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

from tenancy.schemas import schema_context

_spec = importlib.util.spec_from_file_location(
    "archive_held_review_fixtures", Path(__file__).resolve().parents[1] / "review" / "conftest.py"
)
assert _spec is not None and _spec.loader is not None
_review = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _review
_spec.loader.exec_module(_review)
new_document = _review.new_document
link_group = _review.link_group

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

BODY = "# Terms\n\nThe first synthetic sentence.\nThe second synthetic sentence.\n"


def _held(migrated_tenant: Any, client: Any, document: Any) -> Any:
    """The holder takes the document; the open hold, its draft holding `BODY`."""
    from editing.models import Draft, Hold

    assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
    with schema_context(migrated_tenant.number):
        hold = Hold.objects.get(document=document, released_at__isnull=True)
        draft = Draft.objects.get(hold=hold)
        draft.content = {**draft.content, "document.md": BODY}
        draft.save()
        return hold


def _archive(migrated_tenant: Any, document: Any, by: Any) -> bool:
    from documents import archive

    with schema_context(migrated_tenant.number):
        return archive.archive(document, by)


def _reread(migrated_tenant: Any, hold: Any) -> Any:
    from editing.models import Hold

    with schema_context(migrated_tenant.number):
        return Hold.objects.get(pk=hold.pk)


def test_a_hold_is_released_as_a_force_release(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    from access.rights import Right
    from audit.models import AuditEvent
    from editing.models import Draft

    editor_client, editor, membership = member_of("the.editor@example.test")
    _, admin, _ = member_of("the.admin@example.test", is_tenant_admin=True)
    document = new_document(editor)
    link_group(document, [Right.EDIT], [membership], editor)
    hold = _held(migrated_tenant, editor_client, document)

    assert _archive(migrated_tenant, document, admin) is True

    released = _reread(migrated_tenant, hold)
    assert released.released_at is not None
    assert (released.release_kind, released.released_by_id, released.release_reason) == (
        "forced",
        admin.pk,
        "archived",
    )
    with schema_context(migrated_tenant.number):
        assert Draft.objects.filter(hold=hold).exists()
    event = AuditEvent.objects.filter(action="document.hold_released").latest("at")
    assert event.actor_id == admin.pk and event.after["reason"] == "archived"
    # The release lands before the state: the archive's own event comes after.
    archived = AuditEvent.objects.get(action="document.archived")
    assert archived.at >= event.at


def test_a_reservation_is_ended_with_the_platforms_reason(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    from django.utils import timezone

    from editing.models import Hold

    holder_client, author, _ = member_of("the.author@example.test")
    _, admin, _ = member_of("the.admin@example.test", is_tenant_admin=True)
    document = new_document(author)
    hold = _held(migrated_tenant, holder_client, document)
    with schema_context(migrated_tenant.number):
        Hold.objects.filter(pk=hold.pk).update(reserved_at=timezone.now())

    _archive(migrated_tenant, document, admin)

    released = _reread(migrated_tenant, hold)
    assert (released.release_kind, released.release_reason) == ("forced", "archived")
    assert released.reserved_at is not None


def test_a_stopped_finish_is_completed_not_forced(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    """A finish stopped after its commit: archiving completes it, the hold `finished`; the
    reviewer's notice exists, neither drawn nor counted while archived, drawn after the restore."""
    from access.rights import Right
    from documents import archive
    from editing import services
    from notifications.models import Notification
    from notifications.services import openable

    editor_client, editor, editor_membership = member_of("the.editor@example.test")
    _, reviewer, reviewer_membership = member_of("the.reviewer@example.test")
    _, admin, _ = member_of("the.admin@example.test", is_tenant_admin=True)
    document = new_document(editor)
    link_group(document, [Right.EDIT], [editor_membership], editor)
    link_group(document, [Right.ACCEPT], [reviewer_membership], editor)
    hold = _held(migrated_tenant, editor_client, document)
    with schema_context(migrated_tenant.number):
        with pytest.raises(services.InjectedFault):
            services.commit_draft(
                _reread(migrated_tenant, hold), editor, "Synthetic edit", fault_at=1
            )

    _archive(migrated_tenant, document, admin)

    assert _reread(migrated_tenant, hold).release_kind == "finished"
    with schema_context(migrated_tenant.number):
        told = list(Notification.objects.filter(user=reviewer, event="version_committed"))
        assert len(told) == 1
        assert openable(reviewer, told) == []
        archive.restore(document, admin)
        assert openable(reviewer, told) == told


def test_the_archivers_own_hold_is_released(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    from editing.models import Draft

    admin_client, admin, _ = member_of("the.admin@example.test", is_tenant_admin=True)
    document = new_document(admin)
    hold = _held(migrated_tenant, admin_client, document)

    assert _archive(migrated_tenant, document, admin) is True

    released = _reread(migrated_tenant, hold)
    assert (released.release_kind, released.released_by_id, released.release_reason) == (
        "forced",
        admin.pk,
        "archived",
    )
    with schema_context(migrated_tenant.number):
        assert Draft.objects.filter(hold=hold).exists()
