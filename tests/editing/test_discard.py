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


# --- letting go with nothing edited --------------------------------------------------------------


def taken_and_reserved(tenant: Any, member_of: Any, new_document: Any, link_group: Any) -> Any:
    """A document its holder took and reserved, the draft as the take left it: no edits."""
    client, author, own = member_of("the.author@example.test")
    document = new_document(author)
    link_group(document, [Right.EDIT, Right.RESERVE_FOR_EDITING], [own], author)
    assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
    assert client.post(f"/document/{document.number}/edit/reserve/").status_code == 302
    return client, author, document


def assert_released_empty(tenant: Any, document: Any, author: Any, response: Any) -> None:
    """The route's answer and what it leaves: the hold `released`, nothing kept, no discard."""
    from audit.models import AuditEvent
    from documents import holds as document_holds
    from editing import holds
    from editing.models import Draft, DraftFile, Hold

    assert response.status_code == 302 and response["Location"] == f"/document/{document.number}/"
    with schema_context(tenant.number):
        hold = Hold.objects.get(document=document)
        assert hold.release_kind == "released" and hold.released_by is None
        assert hold.released_at is not None
        assert not Draft.objects.filter(hold=hold).exists()
        assert not DraftFile.objects.exists()
        assert not document_holds.is_held(document)
        assert holds.preserved_draft(document, author) is None
    event = AuditEvent.objects.get(action="document.hold_released")
    assert event.after["release_kind"] == "released"
    assert event.after["kept"] is False
    assert event.after["draft_base"], "the draft's state is read before it is deleted"
    assert not AuditEvent.objects.filter(action="document.draft_discarded").exists()


def test_a_hold_with_no_edits_is_released(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, settings: Any
) -> None:
    """Nothing edited: the draft decides, and the hold is let go `released` — nothing thrown
    away, nothing kept, the reservation ended with it — whatever the button said."""
    settings.LANGUAGE_CODE = "en"
    client, author, document = taken_and_reserved(
        migrated_tenant, member_of, new_document, link_group
    )
    number = document.number

    response = client.post(f"/document/{number}/edit/discard/", {"release": "1"})

    assert_released_empty(migrated_tenant, document, author, response)
    page = client.get(f"/document/{number}/").content.decode()
    assert "You released the document." in page
    assert 'class="band end"' not in page and 'data-go="kept"' not in page
    # Nothing is kept: the next visit opens the tab as usual.
    tab = client.get(f"/document/{number}/edit/").content.decode()
    assert 'id="editor"' in tab and "band end" not in tab


def test_no_edits_posted_without_release_is_released_too(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, settings: Any
) -> None:
    """The *Discard my edits* form on a draft with no edits: the same release, the same message
    — there was nothing to discard."""
    settings.LANGUAGE_CODE = "en"
    client, author, document = taken_and_reserved(
        migrated_tenant, member_of, new_document, link_group
    )

    response = client.post(f"/document/{document.number}/edit/discard/")

    assert_released_empty(migrated_tenant, document, author, response)
    page = client.get(f"/document/{document.number}/").content.decode()
    assert "You released the document." in page
    assert "Your edits were discarded." not in page


def test_a_stale_release_is_refused(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, settings: Any
) -> None:
    """*Release* sent for a draft that has edits since the page was drawn: refused, the edit page
    drawn again saying so; the hold open and the draft, its text and its file, untouched."""
    from audit.models import AuditEvent
    from editing.models import Draft, DraftFile, Hold

    settings.LANGUAGE_CODE = "en"
    client, document, draft = reserved_with_a_file(
        migrated_tenant, member_of, new_document, link_group
    )
    number = document.number

    refused = client.post(f"/document/{number}/edit/discard/", {"release": "1"})

    assert refused.status_code == 409
    body = refused.content.decode()
    assert "Your draft has edits" in body and "Discard my edits" in body
    assert 'id="editor"' in body
    with schema_context(migrated_tenant.number):
        hold = Hold.objects.get(document=document)
        assert hold.released_at is None and hold.release_kind == ""
        assert hold.reserved_at is not None
        kept = Draft.objects.get(pk=draft.pk)
        assert kept.content == draft.content
        assert DraftFile.objects.filter(draft=kept).count() == 1
    assert not AuditEvent.objects.filter(action="document.hold_released").exists()
    assert not AuditEvent.objects.filter(action="document.draft_discarded").exists()
    # The discard proper still stands, as built.
    discarded = client.post(f"/document/{number}/edit/discard/")
    assert discarded.status_code == 302 and discarded["Location"] == f"/document/{number}/"
    with schema_context(migrated_tenant.number):
        assert Hold.objects.get(document=document).release_kind == "discarded"


def test_a_stopped_finish_with_release_is_discarded_as_built(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, settings: Any
) -> None:
    """A finish stopped after its commit, then *Release*: the draft is behind a version the
    person already made — the stop's path as built, never `released`; the version stands and
    its reviewers are told."""
    from editing import services
    from editing.models import Draft, Hold
    from notifications.models import Notification

    settings.LANGUAGE_CODE = "en"
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
            services.commit_draft(hold, author, "Synthetic edit", fault_at=1)

    response = client.post(f"/document/{document.number}/edit/discard/", {"release": "1"})

    assert response.status_code == 302 and response["Location"] == f"/document/{document.number}/"
    page = client.get(f"/document/{document.number}/").content.decode()
    assert "the version you had already made stands and awaits review" in page
    assert "You released the document." not in page
    with schema_context(migrated_tenant.number):
        hold.refresh_from_db()
        assert hold.released_at is not None and hold.release_kind != "released"
        assert not Draft.objects.filter(hold__document=document).exists()
        assert Notification.objects.filter(user=reviewer, event="version_committed").count() == 1


# --- the windows ------------------------------------------------------------------------------


def test_a_reservation_asks_before_the_release(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, settings: Any
) -> None:
    """Reserved and nothing edited: *Release the document* opens its window, which says the
    reservation ends; the window's form releases it (DL-0510)."""
    settings.LANGUAGE_CODE = "en"
    client, author, document = taken_and_reserved(
        migrated_tenant, member_of, new_document, link_group
    )
    page = client.get(f"/document/{document.number}/edit/").content.decode()
    window = page.split('<dialog id="release"', 1)[1].split("</dialog>", 1)[0]

    assert 'data-command="release" data-window="release"' in page
    assert "Releasing the document ends your reservation." in window
    released = client.post(f"/document/{document.number}/edit/discard/", {"release": "1"})
    assert_released_empty(migrated_tenant, document, author, released)


def test_the_window_on_three_pages(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, settings: Any
) -> None:
    """*Discard my edits…*'s window stands in the frame of the draft's page and the finishing
    screen; *Discard this draft…*'s on the kept draft's page — each a form that posts."""
    from django.db import transaction

    from documents.locks import document_lock
    from editing import holds
    from editing.models import Hold, ReleaseKind

    settings.LANGUAGE_CODE = "en"
    client, document, _ = reserved_with_a_file(migrated_tenant, member_of, new_document, link_group)
    n = document.number
    for path in (f"/document/{n}/edit/", f"/document/{n}/edit/finish/"):
        page = client.get(path).content.decode()
        window = page.split('<dialog id="discard"', 1)[1].split("</dialog>", 1)[0]
        assert f'action="/document/{n}/edit/discard/"' in window, path
        assert 'data-command="discard-confirmed"' in window and "data-close" in window, path
    with schema_context(migrated_tenant.number):
        with document_lock(migrated_tenant.number, n), transaction.atomic():
            holds.release(Hold.objects.get(document=document), ReleaseKind.FORCED)
    kept = client.get(f"/document/{n}/edit/").content.decode()
    window = kept.split('<dialog id="discard-draft"', 1)[1].split("</dialog>", 1)[0]
    assert f'action="/document/{n}/edit/discard-draft/"' in window


def test_the_window_without_script(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, settings: Any
) -> None:
    """Without script the act asks for its page with `?confirm=discard`, which draws the window
    open; another value opens nothing and is never echoed (DL-0513)."""
    settings.LANGUAGE_CODE = "en"
    client, document, _ = reserved_with_a_file(migrated_tenant, member_of, new_document, link_group)
    url = f"/document/{document.number}/edit/"

    asked = client.get(f"{url}?confirm=discard").content.decode()
    other = client.get(f"{url}?confirm=%3Cscript%3E").content.decode()

    assert '<dialog id="discard" aria-label="Discard my edits" open>' in asked
    assert " open>" not in other.split('<dialog id="discard"', 1)[1].split(">", 1)[0] + ">"
    assert "<script>" not in other and "%3Cscript" not in other
    assert '<form class="inline" method="get" action="">' in asked


def test_the_page_served_for_the_take_offers_the_release(
    migrated_tenant: Any, member_of: Any, new_document: Any, settings: Any
) -> None:
    """Opened from the application, the draft's page is served before the editor takes the hold:
    it already carries *Release the document* and *Discard my edits…*'s window, for the hold the
    editor is about to take."""
    settings.LANGUAGE_CODE = "en"
    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)

    page = client.get(
        f"/document/{document.number}/edit/", headers={"Sec-Fetch-Site": "same-origin"}
    ).content.decode()

    assert 'data-command="release"' in page
    assert '<dialog id="discard"' in page
