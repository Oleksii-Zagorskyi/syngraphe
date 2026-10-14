"""An administrator ending someone else's reservation with a reason (ST-0030, ST-0070, DL-0225,
DL-0369, DL-0378, DL-0415): the hold released `forced`, the draft kept, the holder told why — the
reason in the application, never in the email — and the document free.

People, organisations, groups and texts are synthetic examples: every address ends in
`@example.test`, and every text is invented."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

import pytest

from access.rights import Right
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

REASON = "Синтетична причина: потрібна термінова правка бюджету"
CHANGED = "# Синтетичні умови\n\nВласниця чернетки переписала перше речення.\n"
BIDI = "‮"
REFUSED = (
    "я" * 600,
    "",
    "   ",
    f"Синтетична причина {BIDI}з керуванням напрямком",
    "Синтетичний перший рядок\nСинтетичний другий рядок",
)


@dataclass
class Reserved:
    document: Any
    holder: Any
    holder_client: Any
    admin: Any
    admin_client: Any
    editor_client: Any
    hold: Any
    draft: Any


def redirected_to(response: Any, path: str) -> bool:
    """Whether `response` is a 302 whose target is `path`."""
    return response.status_code == 302 and urlsplit(response["Location"]).path == path


def text_of(body: str) -> str:
    """The page's text: tags removed, entities read, whitespace collapsed."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", body)))


def text_nodes(body: str) -> set[str]:
    """Every run of text between two tags, stripped, entities read."""
    return {html.unescape(node).strip() for node in re.findall(r">([^<]+)<", body) if node.strip()}


def form_posting_to(body: str, path: str) -> bool:
    """Whether the page draws a form posting to `path`: named in its action, or the page's own
    address when the action is left out."""
    for opening in re.findall(r"<form\b[^>]*>", body):
        if not re.search(r'\bmethod="post"', opening, re.I):
            continue
        action = re.search(r'\baction="([^"]*)"', opening)
        if action is None or action.group(1) in ("", path):
            return True
    return False


def has_reason_field(body: str) -> bool:
    return any(
        re.search(r'\bname="reason"', tag)
        for tag in re.findall(r"<(?:input|textarea)\b[^>]*>", body)
    )


def date_shown(text: str, moment: datetime, zone: str) -> bool:
    """Whether `text` carries the date of `moment` in the reader's time zone, in one of the forms
    a page writes a date in English."""
    from zoneinfo import ZoneInfo

    from django.utils import formats, translation

    local = moment.astimezone(ZoneInfo(zone))
    with translation.override("en"):
        forms = {
            formats.date_format(local, name)
            for name in ("DATE_FORMAT", "SHORT_DATE_FORMAT", "DATETIME_FORMAT")
        }
    forms |= {
        local.strftime("%Y-%m-%d"),
        local.strftime("%d.%m.%Y"),
        f"{local.day} {local:%B %Y}",
        f"{local:%B} {local.day}, {local.year}",
    }
    return any(form in text for form in forms)


def sending_address(number: int | None) -> Any:
    """A sending address in an organisation's schema, so its emails are queued."""
    from mail.models import MailSender

    with schema_context(number):
        return MailSender.objects.create(
            host="127.0.0.1",
            port=2525,
            address="mail@example.test",
            display_name="Synthetic",
            username="",
            password_encrypted=b"",
            security="none",
        )


@pytest.fixture
def reserved(migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any) -> Reserved:
    """A document reserved by its holder through the screens, its draft changed, and a tenant
    administrator and another editor of it."""
    from editing.models import Draft, Hold

    _, author, _ = member_of("author.synthetic@example.test")
    holder_client, holder, holder_membership = member_of("holder.synthetic@example.test")
    holder.display_name = "Синтетична Власниця"
    holder.save(update_fields=["display_name"])
    editor_client, _, editor_membership = member_of("editor.synthetic@example.test")
    admin_client, admin, _ = member_of("admin.synthetic@example.test", is_tenant_admin=True)
    admin.display_name = "Синтетичний Адміністратор"
    admin.save(update_fields=["display_name"])
    document = new_document(author)
    link_group(document, [Right.EDIT, Right.RESERVE_FOR_EDITING], [holder_membership], author)
    link_group(document, [Right.EDIT], [editor_membership], author)
    number = document.number
    assert holder_client.post(f"/document/{number}/edit/take/").status_code == 200
    with schema_context(migrated_tenant.number):
        draft = Draft.objects.get(hold__document=document, hold__released_at__isnull=True)
        draft.content = {**draft.content, "document.md": CHANGED}
        draft.save()
    made = holder_client.post(f"/document/{number}/edit/reserve/")
    assert redirected_to(made, f"/document/{number}/edit/"), made.status_code
    with schema_context(migrated_tenant.number):
        hold = Hold.objects.get(document=document, released_at__isnull=True)
        draft.refresh_from_db()
    assert hold.reserved_at is not None
    return Reserved(
        document, holder, holder_client, admin, admin_client, editor_client, hold, draft
    )


def test_end_with_a_reason(migrated_tenant: Any, reserved: Reserved, settings: Any) -> None:
    from audit.models import AuditEvent
    from documents import holds as document_holds
    from editing.models import Draft, Hold
    from mail.models import EmailOutbox
    from notifications.models import Notification

    settings.LANGUAGE_CODE = "en"
    sending_address(migrated_tenant.number)
    number = reserved.document.number
    url = f"/document/{number}/edit/end-reservation/"

    page = reserved.admin_client.get(url)

    assert page.status_code == 200
    body = page.content.decode()
    assert form_posting_to(body, url)
    assert has_reason_field(body)
    shown = text_of(body)
    assert reserved.holder.display_name in shown or reserved.holder.email in shown
    assert date_shown(shown, reserved.hold.reserved_at, settings.DISPLAY_TIMEZONE)

    ended = reserved.admin_client.post(url, {"reason": REASON, "hold": str(reserved.hold.pk)})

    assert redirected_to(ended, f"/document/{number}/"), ended.status_code
    with schema_context(migrated_tenant.number):
        hold = Hold.objects.get(pk=reserved.hold.pk)
        assert hold.released_at is not None
        assert hold.release_kind == "forced"
        assert hold.released_by_id == reserved.admin.pk
        assert hold.release_reason == REASON
        draft = Draft.objects.get(pk=reserved.draft.pk)
        assert draft.hold_id == hold.pk
        assert draft.content["document.md"] == CHANGED
    [event] = AuditEvent.objects.filter(
        action="document.hold_released", object_id=reserved.document.pk
    )
    assert event.after["release_kind"] == "forced"
    assert event.after["reason"] == REASON
    assert event.after["draft_base"] == reserved.draft.base_commit
    assert "draft_updated_at" in event.after
    assert isinstance(event.after["open_editors"], int)
    assert not isinstance(event.after["open_editors"], bool)
    with schema_context(migrated_tenant.number):
        [told] = Notification.objects.filter(
            user=reserved.holder, event="reservation_ended_by_admin"
        )
        assert told.facts["reason"] == REASON
        [email] = EmailOutbox.objects.filter(notification_id=told.pk)
        assert REASON not in email.subject
        assert REASON not in email.body
        assert not document_holds.is_held(reserved.document)
    # Free: another editor takes it.
    assert reserved.editor_client.post(f"/document/{number}/edit/take/").status_code == 200


def test_reason_rule(migrated_tenant: Any, reserved: Reserved, settings: Any) -> None:
    from audit.models import AuditEvent
    from editing.models import Hold
    from notifications.models import Notification

    settings.LANGUAGE_CODE = "en"
    url = f"/document/{reserved.document.number}/edit/end-reservation/"
    plain = reserved.admin_client.get(url)
    assert plain.status_code == 200
    before = text_nodes(plain.content.decode())
    events = AuditEvent.objects.count()
    with schema_context(migrated_tenant.number):
        notifications = Notification.objects.count()

    for reason in REFUSED:
        refused = reserved.admin_client.post(url, {"reason": reason, "hold": str(reserved.hold.pk)})

        assert refused.status_code == 200, repr(reason[:20])
        body = refused.content.decode()
        assert has_reason_field(body), repr(reason[:20])
        # A sentence the plain page did not have, other than the reason typed coming back.
        typed = [part.replace(BIDI, "").strip() for part in reason.split("\n")]
        added = [
            node
            for node in text_nodes(body) - before
            if not any(part and part in node.replace(BIDI, "") for part in typed)
            and re.search(r"[A-Za-z]{2}", node)
        ]
        assert added, repr(reason[:20])
        assert "one line of at most 500 characters" in body, repr(reason[:20])
        with schema_context(migrated_tenant.number):
            hold = Hold.objects.get(pk=reserved.hold.pk)
            assert hold.released_at is None and hold.reserved_at is not None
            assert Notification.objects.count() == notifications
        assert AuditEvent.objects.count() == events


def test_end_is_for_administrators_of_a_reservation(
    migrated_tenant: Any,
    reserved: Reserved,
    member_of: Any,
    new_document: Any,
    link_group: Any,
) -> None:
    from audit.models import AuditEvent
    from editing.models import Hold

    member_client, _, member_membership = member_of("member.synthetic@example.test")
    _, author, _ = member_of("second.author.synthetic@example.test")
    held = new_document(author, "Синтетичний порядок звітування")
    link_group(held, [Right.EDIT], [member_membership], author)
    assert member_client.post(f"/document/{held.number}/edit/take/").status_code == 200
    events = AuditEvent.objects.count()
    reserved_url = f"/document/{reserved.document.number}/edit/end-reservation/"
    held_url = f"/document/{held.number}/edit/end-reservation/"

    for client, url in (
        (member_client, reserved_url),
        (reserved.admin_client, held_url),
    ):
        assert client.get(url).status_code == 404, url
        assert client.post(url, {"reason": REASON}).status_code == 404, url

    with schema_context(migrated_tenant.number):
        hold = Hold.objects.get(pk=reserved.hold.pk)
        assert hold.released_at is None and hold.reserved_at is not None
        other = Hold.objects.get(document=held, released_at__isnull=True)
        assert other.reserved_at is None
    assert AuditEvent.objects.count() == events
    # The administrator reaches the page of the reserved one: the refusals were the rule's.
    assert reserved.admin_client.get(reserved_url).status_code == 200


def test_where_the_ending_is_offered_and_read(
    migrated_tenant: Any, reserved: Reserved, settings: Any
) -> None:
    """The administrator finds *end the reservation…* under the document page's *More ▾*; once it
    is ended the holder reads, on the document, that their editing ended and where their draft
    is, and, among their notifications, the reason; the other editor learns of neither."""
    settings.LANGUAGE_CODE = "en"
    number = reserved.document.number
    end = f"/document/{number}/edit/end-reservation/"
    assert f'href="{end}"' in reserved.admin_client.get(f"/document/{number}/").content.decode()
    assert end not in reserved.editor_client.get(f"/document/{number}/").content.decode()
    assert end not in reserved.holder_client.get(f"/document/{number}/").content.decode()

    assert redirected_to(
        reserved.admin_client.post(end, {"reason": REASON, "hold": str(reserved.hold.pk)}),
        f"/document/{number}/",
    )

    page = reserved.holder_client.get(f"/document/{number}/").content.decode()
    assert 'class="band end"' in page and f'href="/document/{number}/edit/"' in page
    assert (
        'class="band end"'
        not in reserved.editor_client.get(f"/document/{number}/").content.decode()
    )
    listed = reserved.holder_client.get("/notifications/?tab=document").content.decode()
    assert html.escape(REASON) in listed or REASON in listed


def test_the_end_names_its_people_as_every_page_does(
    migrated_tenant: Any, reserved: Reserved, settings: Any
) -> None:
    """A holder without a name is *anonymous editor* to administrators too, never an address
    (DL-0339); the holder is told who ended the reservation (DL-0225), in the entry and its
    email, the reason in neither email."""
    from mail.models import EmailOutbox
    from notifications.models import Notification

    settings.LANGUAGE_CODE = "en"
    sending_address(migrated_tenant.number)
    reserved.holder.display_name = ""
    reserved.holder.save(update_fields=["display_name"])
    number = reserved.document.number
    for page in (
        reserved.admin_client.get(f"/document/{number}/edit/end-reservation/"),
        reserved.admin_client.get("/administration/tenant/reservations/"),
    ):
        body = page.content.decode()
        assert "anonymous editor" in body
        assert reserved.holder.email not in body
    reserved.admin_client.post(
        f"/document/{number}/edit/end-reservation/",
        {"reason": REASON, "hold": str(reserved.hold.pk)},
    )
    with schema_context(migrated_tenant.number):
        told = Notification.objects.get(event="reservation_ended_by_admin")
        assert told.facts["by"] == str(reserved.admin.pk)
    listed = reserved.holder_client.get("/notifications/?tab=document").content.decode()
    assert "Синтетичний Адміністратор" in listed
    with schema_context(migrated_tenant.number):
        email = EmailOutbox.objects.get(notification_id=told.pk)
    assert "Синтетичний Адміністратор" in email.body and REASON not in email.body


def test_the_end_is_of_the_reservation_confirmed(
    migrated_tenant: Any, reserved: Reserved, settings: Any
) -> None:
    """The page names one reservation; a POST naming another — the first one finished and a new
    one taken meanwhile — ends nothing."""
    import uuid

    settings.LANGUAGE_CODE = "en"
    number = reserved.document.number
    response = reserved.admin_client.post(
        f"/document/{number}/edit/end-reservation/", {"reason": REASON, "hold": str(uuid.uuid4())}
    )
    assert response.status_code == 409
    with schema_context(migrated_tenant.number):
        reserved.hold.refresh_from_db()
    assert reserved.hold.released_at is None


def test_the_end_reads_the_administrator_inside_the_act(
    migrated_tenant: Any, reserved: Reserved
) -> None:
    """Who may end a reservation is read from the database under the locks, never from a request
    that may predate a demotion; and nobody ends their own reservation — they cancel it."""
    from editing import reservations

    with schema_context(migrated_tenant.number):
        with pytest.raises(reservations.ReservationRefused):
            reservations.end_reservation(reserved.hold, reserved.holder, REASON)
        reserved.hold.refresh_from_db()
        assert reserved.hold.released_at is None


def test_more_holds_the_act_the_hold_allows(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, settings: Any
) -> None:
    """*More ▾* holds *force release* on an ordinary hold and *end the reservation…* on a reserved
    one; the holder, administrator or not, is offered neither — they finish, discard or cancel."""
    settings.LANGUAGE_CODE = "en"
    admin_client, admin, admin_membership = member_of(
        "admin.synthetic@example.test", is_tenant_admin=True
    )
    other_client, _, other_membership = member_of(
        "other.synthetic@example.test", is_tenant_admin=True
    )
    document = new_document(admin)
    link_group(
        document,
        [Right.EDIT, Right.RESERVE_FOR_EDITING],
        [admin_membership, other_membership],
        admin,
    )
    number = document.number
    assert admin_client.post(f"/document/{number}/edit/take/").status_code == 200
    page = other_client.get(f"/document/{number}/").content.decode()
    assert f'action="/document/{number}/edit/force-release/"' in page
    assert "/edit/end-reservation/" not in page
    assert 'class="more"' not in admin_client.get(f"/document/{number}/").content.decode()
    admin_client.post(f"/document/{number}/edit/reserve/")
    assert 'class="more"' not in admin_client.get(f"/document/{number}/").content.decode()
    page = other_client.get(f"/document/{number}/").content.decode()
    assert f'href="/document/{number}/edit/end-reservation/"' in page
    assert "/edit/force-release/" not in page
