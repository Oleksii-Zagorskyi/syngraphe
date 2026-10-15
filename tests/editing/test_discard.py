"""*Discard my edits* (ST-0022, DL-0180, DL-0237): the whole draft — its text and its staged files
— thrown away once confirmed, the hold released `discarded`, a reservation ended with it; refused
while an editor is open. People, titles and texts are synthetic examples."""

from __future__ import annotations

import json
from typing import Any

import pytest

from access.rights import Right
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]


def reserved_with_a_file(tenant: Any, member_of: Any, new_document: Any, link_group: Any) -> Any:
    """A document its holder reserved, its draft changed and holding a staged file."""
    from django.utils import timezone

    from editing.models import Draft, DraftFile

    client, author, own = member_of("the.author@example.test")
    document = new_document(author)
    link_group(document, [Right.EDIT, Right.RESERVE_FOR_EDITING], [own], author)
    assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
    assert client.post(f"/document/{document.number}/edit/reserve/").status_code == 302
    with schema_context(tenant.number):
        draft = Draft.objects.get(hold__document=document)
        draft.content = {**draft.content, "document.md": "# Synthetic section\n\nNew.\n"}
        draft.save()
        DraftFile.objects.create(
            draft=draft,
            kind="attachment",
            path="attachments/1",
            operation="add",
            content=b"synthetic",
            file_name="synthetic.txt",
            at=timezone.now(),
        )
    return client, document, draft


def test_discard_throws_the_draft_away(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    from audit.models import AuditEvent
    from documents import holds as document_holds
    from editing.models import Draft, DraftFile, Hold

    client, document, draft = reserved_with_a_file(
        migrated_tenant, member_of, new_document, link_group
    )
    response = client.post(f"/document/{document.number}/edit/discard/")
    assert response.status_code == 302 and response["Location"] == f"/document/{document.number}/"
    with schema_context(migrated_tenant.number):
        hold = Hold.objects.get(document=document)
        assert hold.release_kind == "discarded" and hold.released_by is None
        assert hold.reserved_at is not None
        assert not Draft.objects.filter(pk=draft.pk).exists()
        assert not DraftFile.objects.exists()
        assert not document_holds.is_held(document)
    event = AuditEvent.objects.get(action="document.hold_released")
    assert event.after["release_kind"] == "discarded" and event.after["draft_base"]
    # What was thrown away, as a kept draft's discard records it: the reservation, the files.
    thrown = AuditEvent.objects.get(action="document.draft_discarded")
    assert thrown.after["reserved"] is True and thrown.after["files"] == 1
    # Nothing is kept: the next visit opens the tab as usual.
    page = client.get(f"/document/{document.number}/edit/").content.decode()
    assert 'id="editor"' in page and "band end" not in page


def test_discard_waits_for_editors(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    """An open editor may still hold text not captured: the discard is refused, nothing deleted;
    the page closes its editors before it asks."""
    from editing.models import Draft, Hold

    client, document, draft = reserved_with_a_file(
        migrated_tenant, member_of, new_document, link_group
    )
    client.post(
        f"/document/{document.number}/edit/load/",
        data=json.dumps({"range": "whole"}),
        content_type="application/json",
    )
    refused = client.post(f"/document/{document.number}/edit/discard/")
    assert refused.status_code == 409
    with schema_context(migrated_tenant.number):
        assert Draft.objects.filter(pk=draft.pk).exists()
        assert Hold.objects.get(document=document).released_at is None


def test_discard_is_the_holders_alone(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    """Another editor of the document reaches the route and is refused by the holder's check."""
    from editing.models import Draft

    client, author, own = member_of("the.author@example.test")
    other, _, theirs = member_of("another.editor@example.test")
    document = new_document(author)
    link_group(document, [Right.EDIT], [own, theirs], author)
    assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
    assert other.post(f"/document/{document.number}/edit/discard/").status_code == 404
    assert client.get(f"/document/{document.number}/edit/discard/").status_code == 404
    with schema_context(migrated_tenant.number):
        assert Draft.objects.filter(hold__document=document).exists()


def test_a_discard_after_the_hold_ended_goes_back_to_the_tab(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    """A second click, or a hold released meanwhile: back to the edit tab, which says what stands,
    never a bare 404."""
    client, document, _ = reserved_with_a_file(migrated_tenant, member_of, new_document, link_group)
    assert client.post(f"/document/{document.number}/edit/discard/").status_code == 302
    again = client.post(f"/document/{document.number}/edit/discard/")
    assert again.status_code == 302 and again["Location"] == f"/document/{document.number}/edit/"


@pytest.mark.parametrize("step", [1, 2])
def test_a_discard_after_a_stopped_finish_leaves_the_version_told(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, step: int
) -> None:
    """A finish that stopped after its commit made a version a discard cannot take back: the
    reviewers are told it awaits them, and the person is told it stands."""
    from editing import services
    from editing.models import Draft, Hold
    from notifications.models import Notification

    client, author, own = member_of("the.author@example.test")
    _, reviewer, reviewing = member_of("the.reviewer@example.test")
    document = new_document(author)
    link_group(document, [Right.EDIT], [own], author)
    link_group(document, [Right.ACCEPT], [reviewing], author)
    assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
    with schema_context(migrated_tenant.number):
        hold = Hold.objects.get(document=document)
        draft = Draft.objects.get(hold=hold)
        draft.content = {**draft.content, "document.md": "# Synthetic section\n\nNew.\n"}
        draft.save()
        with pytest.raises(services.InjectedFault):
            services.commit_draft(hold, author, "Synthetic edit", fault_at=step)
    response = client.post(f"/document/{document.number}/edit/discard/", follow=True)
    assert response.status_code == 200
    with schema_context(migrated_tenant.number):
        assert Notification.objects.filter(user=reviewer, event="version_committed").count() == 1
        assert not Draft.objects.filter(hold__document=document).exists()


def test_the_controls_say_what_is_thrown_away(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, settings: Any
) -> None:
    """The edit tab and the finishing screen offer *discard my edits*, confirmed in a box saying
    the whole draft is thrown away and, where reserved, that the reservation ends."""
    settings.LANGUAGE_CODE = "en"
    client, document, _ = reserved_with_a_file(migrated_tenant, member_of, new_document, link_group)
    action = f'action="/document/{document.number}/edit/discard/"'
    for path in (f"/document/{document.number}/edit/", f"/document/{document.number}/edit/finish/"):
        page = client.get(path).content.decode()
        assert action in page, path
        assert "Discard my edits" in page, path
        assert "reservation ends" in page, path
