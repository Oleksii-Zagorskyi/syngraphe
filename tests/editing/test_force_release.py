"""Force release (ADR-0006, DL-0414): an administrator frees a document from an ordinary hold,
the draft kept and the holder's editor told at its next request; a reserved hold is ended
elsewhere, never forced; nobody else may force; and a finish stopped after its commit is completed,
not forced.

People, groups and texts are synthetic examples; the texts are invented."""

from __future__ import annotations

import json
import re
from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

TEXT = "\nA synthetic sentence nobody managed to send.\n"
BODY = "# Terms\n\nThe first synthetic sentence.\nThe second synthetic sentence.\n"


def post(client: Any, document: Any, route: str, **body: Any) -> Any:
    return client.post(
        f"/document/{document.number}/edit/{route}/",
        data=json.dumps(body),
        content_type="application/json",
    )


def force(client: Any, document: Any, hold: Any = None) -> Any:
    """The force release's POST, naming the hold the page showed — the document's open one when
    none is given."""
    from editing.models import Hold
    from tenancy.models import Tenant

    if hold is None:
        with schema_context(Tenant.objects.get().number):
            hold = Hold.objects.filter(document=document, released_at__isnull=True).first()
    return client.post(
        f"/document/{document.number}/edit/force-release/",
        {"hold": str(hold.pk) if hold is not None else ""},
    )


def forms_to_force(body: str, document: Any) -> list[str]:
    """Every `<form>` tag on the page whose action is the document's force release."""
    action = f'action="/document/{document.number}/edit/force-release/"'
    return [tag for tag in re.findall(r"<form\b[^>]*>", body) if action in tag]


def open_hold(tenant: Any, document: Any) -> Any:
    from editing.models import Hold

    with schema_context(tenant.number):
        return Hold.objects.filter(document=document, released_at__isnull=True).first()


def test_force_release(migrated_tenant: Any, member_of: Any, new_document: Any) -> None:
    from audit.models import AuditEvent
    from documents import holds as document_holds
    from editing.models import Draft, Hold

    holder, author, _ = member_of("the.author@example.test")
    admin_client, admin, _ = member_of("the.admin@example.test", is_tenant_admin=True)
    document = new_document(author)
    assert holder.post(f"/document/{document.number}/edit/take/").status_code == 200
    loaded = holder.post(f"/document/{document.number}/edit/load/").json()
    written = loaded["body"] + TEXT
    captured = post(
        holder,
        document,
        "capture",
        editor=loaded["editor"],
        base_hash=loaded["base_hash"],
        body=written,
    )
    assert captured.status_code == 200
    hold = open_hold(migrated_tenant, document)

    response = force(admin_client, document)

    assert response.status_code == 302
    assert response["Location"] == f"/document/{document.number}/"
    with schema_context(migrated_tenant.number):
        hold = Hold.objects.get(pk=hold.pk)
        assert Draft.objects.get(hold=hold).content["document.md"] == written
        assert not document_holds.is_held(document)
    assert hold.released_at is not None
    assert hold.release_kind == "forced"
    assert hold.released_by_id == admin.pk
    assert hold.release_reason == ""
    [event] = AuditEvent.objects.filter(action="document.hold_released")
    assert event.actor_id == admin.pk

    beat = post(holder, document, "heartbeat", editor=loaded["editor"])
    late = post(
        holder,
        document,
        "capture",
        editor=loaded["editor"],
        base_hash=captured.json()["base_hash"],
        body=written + "A late synthetic sentence.\n",
    )
    for answer in (beat, late):
        assert answer.status_code == 409
        assert answer.json()["closed"] is True
        assert answer.json()["released"] == "forced"
    with schema_context(migrated_tenant.number):
        assert Draft.objects.get(hold=hold).content["document.md"] == written


def test_reserved_holds_are_ended_not_forced(
    migrated_tenant: Any, member_of: Any, new_document: Any, settings: Any
) -> None:
    from django.utils import timezone

    from editing.models import Hold

    settings.LANGUAGE_CODE = "en"
    holder, author, _ = member_of("the.author@example.test")
    admin_client, _, _ = member_of("the.admin@example.test", is_tenant_admin=True)
    document = new_document(author)
    assert holder.post(f"/document/{document.number}/edit/take/").status_code == 200
    with schema_context(migrated_tenant.number):
        Hold.objects.filter(document=document).update(reserved_at=timezone.now())

    page = admin_client.get(f"/document/{document.number}/")
    body = page.content.decode()
    assert page.status_code == 200
    assert f'href="/document/{document.number}/edit/end-reservation/"' in body
    assert forms_to_force(body, document) == []

    assert force(admin_client, document).status_code == 404
    hold = open_hold(migrated_tenant, document)
    assert hold is not None and hold.reserved_at is not None


def test_force_is_for_administrators(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, settings: Any
) -> None:
    """A member who is not an administrator — another editor or the holder — sees no force and
    cannot post one; the administrator's same page shows it, so its absence means something."""
    from access.rights import Right

    settings.LANGUAGE_CODE = "en"
    holder, author, own = member_of("the.author@example.test")
    other, _, membership = member_of("another.editor@example.test")
    admin_client, _, _ = member_of("the.admin@example.test", is_tenant_admin=True)
    document = new_document(author)
    link_group(document, [Right.EDIT], [own, membership], author)
    assert holder.post(f"/document/{document.number}/edit/take/").status_code == 200

    page = other.get(f"/document/{document.number}/")
    assert page.status_code == 200
    assert forms_to_force(page.content.decode(), document) == []
    assert force(other, document).status_code == 404
    assert force(holder, document).status_code == 404
    assert admin_client.get(f"/document/{document.number}/edit/force-release/").status_code == 404
    assert open_hold(migrated_tenant, document) is not None

    shown = admin_client.get(f"/document/{document.number}/").content.decode()
    assert any(
        re.search(r'method="post"', tag, re.IGNORECASE) for tag in forms_to_force(shown, document)
    )


@pytest.mark.parametrize("step", [1, 2])
def test_a_stopped_finish_is_finished_not_forced(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, step: int
) -> None:
    """Stopped after its commit (step 1) or after its version row (step 2), the hold still open:
    the administrator's force completes the finish (DL-0414)."""
    from access.rights import Right
    from documents import holds as document_holds
    from editing import services
    from editing.models import Draft, Hold
    from notifications.models import Notification

    editor_client, editor, editor_membership = member_of("the.editor@example.test")
    _, reviewer, reviewer_membership = member_of("the.reviewer@example.test")
    admin_client, admin, _ = member_of("the.admin@example.test", is_tenant_admin=True)
    document = new_document(editor)
    link_group(document, [Right.EDIT], [editor_membership], editor)
    link_group(document, [Right.ACCEPT], [reviewer_membership], editor)
    assert editor_client.post(f"/document/{document.number}/edit/take/").status_code == 200
    with schema_context(migrated_tenant.number):
        hold = Hold.objects.get(document=document, released_at__isnull=True)
        draft = Draft.objects.get(hold=hold)
        draft.content = {**draft.content, "document.md": BODY}
        draft.save()
        with pytest.raises(services.InjectedFault):
            services.commit_draft(hold, editor, "Synthetic edit", fault_at=step)
        hold.refresh_from_db()
    assert hold.released_at is None

    response = force(admin_client, document)

    assert response.status_code == 302
    with schema_context(migrated_tenant.number):
        hold.refresh_from_db()
        assert not Draft.objects.filter(hold=hold).exists()
        assert not document_holds.is_held(document)
        [told] = Notification.objects.filter(user=reviewer, event="version_committed")
    assert hold.release_kind == "finished"
    assert told.document_id == document.pk
    assert told.facts == {"version": "0.0-1"}
    # The administrator's act, and what it did, stand in the audit trail.
    from audit.models import AuditEvent

    event = AuditEvent.objects.filter(action="document.hold_released").latest("at")
    assert event.actor_id == admin.pk
    assert event.after["release_kind"] == "finished" and event.after["finish_completed"] is True


@pytest.mark.parametrize("by", ["block", "inactivity"])
def test_every_release_that_keeps_a_draft_completes_a_stopped_finish(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, by: str
) -> None:
    """A block and the inactivity release meet a stopped finish as the force does (DL-0414): the
    finish completed, the reviewers told, nothing kept."""
    from datetime import timedelta

    from django.db import transaction
    from django.utils import timezone

    from access.rights import Right
    from editing import services
    from editing.models import Draft, Hold
    from editing.tasks import release_inactive_holds
    from identity import blocking
    from notifications.models import Notification

    editor_client, editor, editor_membership = member_of("the.editor@example.test")
    _, reviewer, reviewer_membership = member_of("the.reviewer@example.test")
    _, admin, _ = member_of("the.admin@example.test", is_tenant_admin=True)
    document = new_document(editor)
    link_group(document, [Right.EDIT], [editor_membership], editor)
    link_group(document, [Right.ACCEPT], [reviewer_membership], editor)
    assert editor_client.post(f"/document/{document.number}/edit/take/").status_code == 200
    with schema_context(migrated_tenant.number):
        hold = Hold.objects.get(document=document, released_at__isnull=True)
        draft = Draft.objects.get(hold=hold)
        draft.content = {**draft.content, "document.md": BODY}
        draft.save()
        with pytest.raises(services.InjectedFault):
            services.commit_draft(hold, editor, "Synthetic edit", fault_at=2)
    if by == "block":
        with transaction.atomic():
            blocking.end_holds([migrated_tenant], by=admin, cause="blocked", user=editor)
    else:
        with schema_context(migrated_tenant.number):
            Hold.objects.filter(pk=hold.pk).update(
                last_activity_at=timezone.now() - timedelta(minutes=41)
            )
        release_inactive_holds()
    with schema_context(migrated_tenant.number):
        hold.refresh_from_db()
        assert hold.release_kind == "finished"
        assert not Draft.objects.filter(hold=hold).exists()
        assert Notification.objects.filter(user=reviewer, event="version_committed").count() == 1


def test_a_force_is_of_the_hold_shown_and_by_an_administrator_of_it(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    """The force names the hold its page showed: a newer hold is never forced by a stale page.
    An administrator is read again inside the act, never forces their own hold, and the act is
    theirs in the audit trail even where it completed a stopped finish (DL-0414)."""
    import uuid

    from access.rights import Right
    from audit.models import AuditEvent
    from editing import reservations
    from editing.models import Hold
    from identity.models import Membership

    holder_client, holder, holder_membership = member_of("the.holder@example.test")
    admin_client, admin, admin_membership = member_of(
        "the.admin@example.test", is_tenant_admin=True
    )
    document = new_document(holder)
    link_group(document, [Right.EDIT], [holder_membership, admin_membership], holder)
    assert holder_client.post(f"/document/{document.number}/edit/take/").status_code == 200
    hold = open_hold(migrated_tenant, document)

    stale = admin_client.post(
        f"/document/{document.number}/edit/force-release/", {"hold": str(uuid.uuid4())}
    )
    assert stale.status_code == 409
    assert open_hold(migrated_tenant, document) is not None

    with schema_context(migrated_tenant.number):
        Membership.objects.filter(pk=admin_membership.pk).update(is_tenant_admin=False)
        with pytest.raises(reservations.ReservationRefused):
            reservations.force_release(Hold.objects.get(pk=hold.pk), admin)
        Membership.objects.filter(pk=admin_membership.pk).update(is_tenant_admin=True)
        assert open_hold(migrated_tenant, document) is not None

    assert force(admin_client, document).status_code == 302
    event = AuditEvent.objects.filter(action="document.hold_released").latest("at")
    assert event.actor_id == admin.pk

    # Their own hold, an administrator finishes or discards; a force of it is refused.
    assert admin_client.post(f"/document/{document.number}/edit/take/").status_code == 200
    own = open_hold(migrated_tenant, document)
    assert force(admin_client, document, own).status_code == 404
    assert open_hold(migrated_tenant, document) is not None


def _stopped_finish(
    tenant: Any, member_of: Any, new_document: Any, link_group: Any, *, reserve: bool = False
) -> tuple[Any, ...]:
    """An editor's finish stopped after its version row, the hold still open; a reviewer and a
    tenant administrator."""
    from access.rights import Right
    from editing import services
    from editing.models import Draft, Hold

    editor_client, editor, editor_membership = member_of("the.editor@example.test")
    _, reviewer, reviewer_membership = member_of("the.reviewer@example.test")
    admin_client, admin, _ = member_of("the.admin@example.test", is_tenant_admin=True)
    document = new_document(editor)
    link_group(document, [Right.EDIT, Right.RESERVE_FOR_EDITING], [editor_membership], editor)
    link_group(document, [Right.ACCEPT], [reviewer_membership], editor)
    assert editor_client.post(f"/document/{document.number}/edit/take/").status_code == 200
    if reserve:
        editor_client.post(f"/document/{document.number}/edit/reserve/")
    with schema_context(tenant.number):
        hold = Hold.objects.get(document=document, released_at__isnull=True)
        draft = Draft.objects.get(hold=hold)
        draft.content = {**draft.content, "document.md": BODY}
        draft.save()
        with pytest.raises(services.InjectedFault):
            services.commit_draft(hold, editor, "Synthetic edit", fault_at=2)
    return document, hold, draft, editor, reviewer, admin, admin_client


def test_text_typed_after_the_stop_is_kept(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    """A draft holding more than the stopped commit is work at risk: the force keeps it, as
    asked (DL-0414)."""
    from editing.models import Draft

    document, hold, draft, *_, admin_client = _stopped_finish(
        migrated_tenant, member_of, new_document, link_group
    )
    with schema_context(migrated_tenant.number):
        Draft.objects.filter(pk=draft.pk).update(
            content={**draft.content, "document.md": BODY + "\nWritten after the stop.\n"}
        )
    assert force(admin_client, document).status_code == 302
    with schema_context(migrated_tenant.number):
        hold.refresh_from_db()
        assert hold.release_kind == "forced"
        assert Draft.objects.filter(pk=draft.pk).exists()


def test_an_ended_reservation_whose_finish_had_stopped_tells_nobody(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    """Ending a reservation completes the stopped finish under it: nothing of the holder's was
    ended, so they are told nothing (DL-0414)."""
    from notifications.models import Notification

    document, hold, *_, admin_client = _stopped_finish(
        migrated_tenant, member_of, new_document, link_group, reserve=True
    )
    ended = admin_client.post(
        f"/document/{document.number}/edit/end-reservation/",
        {"reason": "Synthetic reason", "hold": str(hold.pk)},
    )
    assert ended.status_code == 302
    with schema_context(migrated_tenant.number):
        hold.refresh_from_db()
        assert hold.release_kind == "finished"
        assert not Notification.objects.filter(event="reservation_ended_by_admin").exists()


def test_a_stopped_acceptance_above_the_stopped_finish_is_settled_first(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    """An acceptance that stopped after its commit sits above the stopped finish: the release
    settles the record first, so nobody is told a version awaits review that is already
    accepted."""
    from editing.models import Draft
    from notifications.models import Notification
    from review import services as review

    document, hold, draft, _, reviewer, _, admin_client = _stopped_finish(
        migrated_tenant, member_of, new_document, link_group
    )
    with schema_context(migrated_tenant.number), pytest.raises(review.InjectedFault):
        review.accept(document, reviewer, fault_at=1)
    assert force(admin_client, document).status_code == 302
    with schema_context(migrated_tenant.number):
        hold.refresh_from_db()
        assert hold.release_kind == "finished"
        assert not Draft.objects.filter(pk=draft.pk).exists()
        assert not Notification.objects.filter(event="version_committed").exists()


def test_a_stopped_version_is_told_even_when_the_draft_is_kept(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    """Text typed after the stop keeps the draft; the version the stop made is committed all the
    same, and its reviewers are told it awaits them, once; the reconciler names the kept draft."""
    from documents import reconcile
    from editing.models import Draft
    from notifications.models import Notification

    document, hold, draft, _, reviewer, _, admin_client = _stopped_finish(
        migrated_tenant, member_of, new_document, link_group
    )
    with schema_context(migrated_tenant.number):
        Draft.objects.filter(pk=draft.pk).update(
            content={**draft.content, "document.md": BODY + "\nWritten after the stop.\n"}
        )
    assert force(admin_client, document).status_code == 302
    with schema_context(migrated_tenant.number):
        hold.refresh_from_db()
        assert hold.release_kind == "forced"
        assert Notification.objects.filter(user=reviewer, event="version_committed").count() == 1
    found = [
        f for f in reconcile.run(tenant=migrated_tenant.number) if f.kind == "finish_stopped_kept"
    ]
    assert [f.document for f in found] == [document.number]


def test_a_release_goes_ahead_over_an_unreadable_repository(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, settings: Any
) -> None:
    """A release must not depend on git: a block over a held document whose repository is gone
    still ends the hold, the draft kept (DL-0256)."""
    from pathlib import Path

    from django.db import transaction

    from access.rights import Right
    from documents import gitstore
    from editing.models import Hold
    from identity import blocking

    editor_client, editor, editor_membership = member_of("the.editor@example.test")
    _, admin, _ = member_of("the.admin@example.test", is_tenant_admin=True)
    document = new_document(editor)
    link_group(document, [Right.EDIT], [editor_membership], editor)
    assert editor_client.post(f"/document/{document.number}/edit/take/").status_code == 200
    path = Path(gitstore.repository_path(migrated_tenant.number, document.number))
    path.rename(path.with_name(path.name + "-gone"))
    try:
        with transaction.atomic():
            blocking.end_holds([migrated_tenant], by=admin, cause="blocked", user=editor)
    finally:
        path.with_name(path.name + "-gone").rename(path)
    with schema_context(migrated_tenant.number):
        assert Hold.objects.get(document=document).release_kind == "blocked"


def test_ending_a_reservation_over_a_stopped_finish_keeps_its_reason(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, settings: Any
) -> None:
    """The administrator's reason stays in the audit of the finish the end completed, and the
    administrator is told what happened."""
    from audit.models import AuditEvent

    settings.LANGUAGE_CODE = "en"
    document, hold, *_, admin_client = _stopped_finish(
        migrated_tenant, member_of, new_document, link_group, reserve=True
    )
    page = admin_client.post(
        f"/document/{document.number}/edit/end-reservation/",
        {"reason": "Synthetic reason", "hold": str(hold.pk)},
        follow=True,
    ).content.decode()
    event = AuditEvent.objects.filter(action="document.hold_released").latest("at")
    assert event.after["release_kind"] == "finished" and event.after["finish_completed"] is True
    assert event.after["reason"] == "Synthetic reason"
    assert "interrupted finish of this editing was completed" in page


@pytest.mark.parametrize("later", ["entity", "attachment", "appendix"])
def test_a_stop_with_later_files_keeps_the_draft(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, later: str
) -> None:
    """An entity declared, an attachment staged or an appendix written after the stop is later
    work, as typed text is: the force keeps the draft, and the hold is not released as
    finished."""
    import hashlib

    from django.utils import timezone

    from documents import entities
    from editing.models import Draft, DraftFile

    document, hold, draft, *_, admin_client = _stopped_finish(
        migrated_tenant, member_of, new_document, link_group
    )
    with schema_context(migrated_tenant.number):
        if later == "entity":
            declared = entities.dump([entities.Declared("role", "approver", "the approver")])
            content = {**draft.content, "entities.yaml": declared}
            Draft.objects.filter(pk=draft.pk).update(content=content)
        elif later == "appendix":
            created = [{"number": 1, "title": "Synthetic appendix"}]
            content = {
                **draft.content,
                "frontmatter": {**draft.content["frontmatter"], "appendices": created},
                "appendices/1.md": "# Synthetic appendix\n\nAn appendix sentence.\n",
            }
            Draft.objects.filter(pk=draft.pk).update(content=content)
        else:
            data = b"an attachment staged after the stop"
            DraftFile.objects.create(
                draft=draft,
                kind="attachment",
                path="attachments/1",
                operation="add",
                content=data,
                file_name="form.txt",
                sha256=hashlib.sha256(data).hexdigest(),
                at=timezone.now(),
            )
    assert force(admin_client, document).status_code == 302
    with schema_context(migrated_tenant.number):
        hold.refresh_from_db()
        assert hold.release_kind == "forced"
        assert Draft.objects.filter(pk=draft.pk).exists()
