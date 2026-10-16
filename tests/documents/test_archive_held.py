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


commit_version = _review.commit_version


def _restore(migrated_tenant: Any, document: Any, by: Any) -> None:
    from documents import archive

    with schema_context(migrated_tenant.number):
        archive.restore(document, by)


def test_the_holder_takes_it_back_after_a_restore(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, settings: Any
) -> None:
    """The archived sentence on the restored document's edit tab; a hold forced with no archive
    keeps its own sentence; *take the document back* restores the holder's draft."""
    import html

    from access.rights import Right

    settings.LANGUAGE_CODE = "en"
    editor_client, editor, membership = member_of("the.editor@example.test")
    admin_client, admin, _ = member_of("the.admin@example.test", is_tenant_admin=True)
    admin.display_name = "Synthetic Administrator"
    admin.save()
    archived = new_document(editor, "Synthetic archived rules")
    forced = new_document(editor, "Synthetic forced rules")
    for document in (archived, forced):
        link_group(document, [Right.EDIT], [membership], editor)
    _held(migrated_tenant, editor_client, archived)
    forced_hold = _held(migrated_tenant, editor_client, forced)
    _archive(migrated_tenant, archived, admin)
    _restore(migrated_tenant, archived, admin)
    assert (
        admin_client.post(
            f"/document/{forced.number}/edit/force-release/", {"hold": str(forced_hold.pk)}
        ).status_code
        == 302
    )

    archived_tab = html.unescape(
        editor_client.get(f"/document/{archived.number}/edit/").content.decode()
    )
    forced_tab = html.unescape(
        editor_client.get(f"/document/{forced.number}/edit/").content.decode()
    )
    taken = editor_client.post(f"/document/{archived.number}/edit/take-back/")
    loaded = editor_client.post(f"/document/{archived.number}/edit/load/").json()

    assert "when Synthetic Administrator archived the document." in archived_tab
    assert f'action="/document/{archived.number}/edit/take-back/"' in archived_tab
    assert "archived the document" not in forced_tab
    assert ": Synthetic Administrator." in forced_tab
    assert taken.status_code in (200, 302)
    assert loaded["body"] == BODY


def test_no_take_back_once_someone_committed(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
) -> None:
    from access.rights import Right

    editor_client, editor, membership = member_of("the.editor@example.test")
    _, other, other_membership = member_of("another.editor@example.test")
    _, admin, _ = member_of("the.admin@example.test", is_tenant_admin=True)
    document = new_document(editor, "Synthetic archived rules")
    link_group(document, [Right.EDIT], [membership, other_membership], editor)
    _held(migrated_tenant, editor_client, document)
    _archive(migrated_tenant, document, admin)
    _restore(migrated_tenant, document, admin)
    commit_version(document, other, "# Other\n\nA synthetic sentence by another editor.\n", "edit")

    tab = editor_client.get(f"/document/{document.number}/edit/").content.decode()

    assert f'action="/document/{document.number}/edit/take-back/"' not in tab


def test_the_holder_is_told(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, settings: Any
) -> None:
    """A member's hold and a member's reservation: each holder told by `document_archived`, no
    document attached, the number and the archiver, never the title; nobody told for a finish
    completed instead, or for the archiver's own hold."""
    from django.utils import timezone

    from access.rights import Right
    from editing import services
    from editing.models import Hold
    from notifications.models import Notification

    settings.LANGUAGE_CODE = "en"
    held_client, held_user, held_membership = member_of("a.holder@example.test")
    reserved_client, reserved_user, reserved_membership = member_of("a.reserver@example.test")
    stopped_client, stopped_user, stopped_membership = member_of("a.stopped@example.test")
    admin_client, admin, _ = member_of("the.admin@example.test", is_tenant_admin=True)
    admin.display_name = "Synthetic Administrator"
    admin.save()
    titles = ("Synthetic held title", "Synthetic reserved title", "Synthetic stopped title")
    held_doc, reserved_doc, stopped_doc = (new_document(admin, t) for t in titles)
    own_doc = new_document(admin, "Synthetic own title")
    for document, membership in (
        (held_doc, held_membership),
        (reserved_doc, reserved_membership),
        (stopped_doc, stopped_membership),
    ):
        link_group(document, [Right.EDIT], [membership], admin)
    _held(migrated_tenant, held_client, held_doc)
    reserved = _held(migrated_tenant, reserved_client, reserved_doc)
    stopped = _held(migrated_tenant, stopped_client, stopped_doc)
    _held(migrated_tenant, admin_client, own_doc)
    with schema_context(migrated_tenant.number):
        Hold.objects.filter(pk=reserved.pk).update(reserved_at=timezone.now())
        with pytest.raises(services.InjectedFault):
            services.commit_draft(
                _reread(migrated_tenant, stopped), stopped_user, "Synthetic edit", fault_at=1
            )

    for document in (held_doc, reserved_doc, stopped_doc, own_doc):
        _archive(migrated_tenant, document, admin)

    with schema_context(migrated_tenant.number):
        told = list(Notification.objects.filter(event="document_archived").order_by("user__email"))
    assert [n.user_id for n in told] == [held_user.pk, reserved_user.pk]
    for row, document in zip(told, (held_doc, reserved_doc), strict=True):
        assert row.category == "document" and row.document_id is None
        assert row.facts == {"number": document.number, "by": str(admin.pk)}
    page = held_client.get("/notifications/?tab=document").content.decode()
    assert (
        f"Document #{held_doc.number}, which you were editing, was archived by Synthetic"
        " Administrator; your draft is kept." in page
    )
    opened = held_client.get(f"/notifications/{told[0].pk}/")
    assert opened.status_code == 302 and opened["Location"] == "/notifications/?tab=document"
    # The email each would be sent — no sending address is set here, so none is queued
    # (DL-0203): its subject and body name the number and the archiver, never a title.
    from mail.services import compose

    with schema_context(migrated_tenant.number):
        for row in told:
            subject, body = compose(row)
            assert f"#{row.facts['number']}" in subject
            assert all(title not in subject + body for title in titles)


def test_the_platforms_reason_is_not_typed(
    migrated_tenant: Any, member_of: Any, new_document: Any, settings: Any
) -> None:
    """*Archived* typed as a reservation's end refuses, the hold left open; the archiver's own
    kept draft says *… when you archived the document.*"""
    import html

    from django.utils import timezone

    from editing.models import Hold

    settings.LANGUAGE_CODE = "en"
    holder_client, author, _ = member_of("the.author@example.test")
    admin_client, admin, _ = member_of("the.admin@example.test", is_tenant_admin=True)
    document = new_document(author, "Synthetic reserved rules")
    hold = _held(migrated_tenant, holder_client, document)
    with schema_context(migrated_tenant.number):
        Hold.objects.filter(pk=hold.pk).update(reserved_at=timezone.now())

    refused = admin_client.post(
        f"/document/{document.number}/edit/end-reservation/",
        {"hold": str(hold.pk), "reason": "Archived"},
    )

    assert refused.status_code == 200  # the page again, with the reason's rule
    assert _reread(migrated_tenant, hold).released_at is None

    own = new_document(admin, "Synthetic own rules")
    _held(migrated_tenant, admin_client, own)
    _archive(migrated_tenant, own, admin)
    _restore(migrated_tenant, own, admin)
    tab = html.unescape(admin_client.get(f"/document/{own.number}/edit/").content.decode())
    assert "when you archived the document." in tab


def test_a_typed_reason_archived_from_before_is_not_read_as_an_archive(
    migrated_tenant: Any, member_of: Any, new_document: Any, settings: Any
) -> None:
    """A reservation an administrator ended with the typed reason *archived*, before that reason
    was refused, reads as the reservation's end with its reason; a reservation archiving ended
    reads as the archive. The audit trail, not the reason, tells them apart (DL-0433)."""
    import html

    from django.utils import timezone

    from editing.models import Hold

    settings.LANGUAGE_CODE = "en"
    typed_client, typed_author, _ = member_of("a.typed.holder@example.test")
    archived_client, archived_author, _ = member_of("an.archived.holder@example.test")
    _, admin, _ = member_of("the.admin@example.test", is_tenant_admin=True)
    admin.display_name = "Synthetic Administrator"
    admin.save()
    typed_doc = new_document(typed_author, "Synthetic typed rules")
    archived_doc = new_document(archived_author, "Synthetic archived rules")
    typed_hold = _held(migrated_tenant, typed_client, typed_doc)
    archived_hold = _held(migrated_tenant, archived_client, archived_doc)
    now = timezone.now()
    with schema_context(migrated_tenant.number):
        Hold.objects.filter(pk__in=[typed_hold.pk, archived_hold.pk]).update(reserved_at=now)
        # Written as an earlier end of the reservation stored it, the reason typed.
        Hold.objects.filter(pk=typed_hold.pk).update(
            released_at=now, release_kind="forced", released_by=admin, release_reason="archived"
        )
    _archive(migrated_tenant, archived_doc, admin)
    _restore(migrated_tenant, archived_doc, admin)

    typed_tab = html.unescape(
        typed_client.get(f"/document/{typed_doc.number}/edit/").content.decode()
    )
    archived_tab = html.unescape(
        archived_client.get(f"/document/{archived_doc.number}/edit/").content.decode()
    )

    assert "archived the document" not in typed_tab
    assert "Synthetic Administrator, “archived”." in typed_tab
    assert "when Synthetic Administrator archived the document." in archived_tab
