"""Reserving a document from an editing session the holder already has, cancelling the
reservation, and the holder's own list of reservations (ST-0069, DL-0219, DL-0226, DL-0252).

People, organisations, groups and texts are synthetic examples: every address ends in
`@example.test`, and every text is invented."""

from __future__ import annotations

import html
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

import pytest

from access.rights import Right
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

FREEZE_REASON = "Synthetic reason: waiting for the board's conclusion"


def redirected_to(response: Any, path: str) -> bool:
    """Whether `response` is a 302 whose target is `path`."""
    return response.status_code == 302 and urlsplit(response["Location"]).path == path


def posts_to(body: str, path: str) -> bool:
    """Whether the page draws a form, or a submit control, posting to `path`."""
    return any(
        re.search(rf'\b(?:action|formaction)="{re.escape(path)}"', tag)
        for tag in re.findall(r"<(?:form|button|input)\b[^>]*>", body)
    )


def disabled_button(body: str) -> bool:
    """Whether the markup draws a button, or a submit input, with the `disabled` attribute."""
    controls = re.findall(r"<button\b[^>]*>|<input\b[^>]*\btype=\"(?:submit|button)\"[^>]*>", body)
    return any(re.search(r"\sdisabled\b", control) for control in controls)


def text_of(body: str) -> str:
    """The page's text: tags removed, entities read, whitespace collapsed."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", body)))


def date_shown(text: str, moment: datetime, zone: str) -> bool:
    """Whether `text` carries the date of `moment` in the reader's time zone, in one of the forms
    a page writes a date in English."""
    from zoneinfo import ZoneInfo

    from django.utils import formats, translation

    local = moment.astimezone(ZoneInfo(zone))
    with translation.override("en"):
        forms = {formats.date_format(local, name) for name in ("j E Y",)}
    forms |= {
        local.strftime("%Y-%m-%d"),
        local.strftime("%d.%m.%Y"),
        f"{local.day} {local:%B %Y}",
        f"{local:%B} {local.day}, {local.year}",
    }
    return any(form in text for form in forms)


def open_hold(tenant: Any, document: Any) -> Any:
    from editing.models import Hold

    with schema_context(tenant.number):
        return Hold.objects.filter(document=document, released_at__isnull=True).first()


@pytest.mark.parametrize(
    "holder_administers", [False, True], ids=["holder-not-administrator", "holder-administrator"]
)
def test_reserve_from_the_editing_session(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    settings: Any,
    holder_administers: bool,
) -> None:
    from audit.models import AuditEvent
    from notifications.models import Notification

    settings.LANGUAGE_CODE = "en"
    _, author, _ = member_of("author.synthetic@example.test")
    first_client, first_admin, first_membership = member_of(
        "first.admin.synthetic@example.test", is_tenant_admin=True
    )
    _, second_admin, _ = member_of("second.admin.synthetic@example.test", is_tenant_admin=True)
    if holder_administers:
        holder_client, holder, holder_membership = first_client, first_admin, first_membership
    else:
        holder_client, holder, holder_membership = member_of("holder.synthetic@example.test")
    document = new_document(author)
    link_group(document, [Right.EDIT, Right.RESERVE_FOR_EDITING], [holder_membership], author)
    number = document.number
    assert holder_client.post(f"/document/{number}/edit/take/").status_code == 200

    reserved = holder_client.post(f"/document/{number}/edit/reserve/")

    assert redirected_to(reserved, f"/document/{number}/edit/"), reserved.status_code
    hold = open_hold(migrated_tenant, document)
    assert hold is not None and hold.user_id == holder.pk
    assert hold.reserved_at is not None
    [event] = AuditEvent.objects.filter(action="document.reserved", object_id=document.pk)
    assert event.after["number"] == number
    administrators = [first_admin, second_admin]
    told = [admin for admin in administrators if admin.pk != holder.pk]
    with schema_context(migrated_tenant.number):
        for admin in told:
            [notification] = Notification.objects.filter(user=admin, event="reservation_started")
            assert notification.category == "administrative"
            assert notification.document_id == document.pk
        assert not Notification.objects.filter(user=holder, event="reservation_started").exists()

    tab = holder_client.get(f"/document/{number}/edit/").content.decode()
    assert posts_to(tab, f"/document/{number}/edit/cancel-reservation/")
    assert not posts_to(tab, f"/document/{number}/edit/reserve/")


def test_refusals(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, settings: Any
) -> None:
    from editions import services as editions

    settings.LANGUAGE_CODE = "en"
    _, author, _ = member_of("author.synthetic@example.test")
    editor_client, _, editor_membership = member_of("editor.synthetic@example.test")
    keeper_client, _, keeper_membership = member_of("keeper.synthetic@example.test")
    reviewer_client, _, reviewer_membership = member_of("reviewer.synthetic@example.test")
    _, freezer, freezer_membership = member_of("freezer.synthetic@example.test")

    # (a) a holder whose groups grant `edit` alone.
    plain = new_document(author, "Synthetic duty rota procedure")
    link_group(plain, [Right.EDIT], [editor_membership], author)
    link_group(plain, [Right.EDIT, Right.RESERVE_FOR_EDITING], [keeper_membership], author)
    assert editor_client.post(f"/document/{plain.number}/edit/take/").status_code == 200
    assert editor_client.post(f"/document/{plain.number}/edit/reserve/").status_code == 404
    tab = editor_client.get(f"/document/{plain.number}/edit/").content.decode()
    assert not posts_to(tab, f"/document/{plain.number}/edit/reserve/")

    # (b) a member holding the right on a document someone else holds, and on one nobody holds.
    assert keeper_client.post(f"/document/{plain.number}/edit/reserve/").status_code == 404
    free = new_document(author, "Synthetic leave procedure")
    link_group(free, [Right.EDIT, Right.RESERVE_FOR_EDITING], [keeper_membership], author)
    assert keeper_client.post(f"/document/{free.number}/edit/reserve/").status_code == 404
    assert open_hold(migrated_tenant, free) is None
    hold = open_hold(migrated_tenant, plain)
    assert hold is not None and hold.reserved_at is None
    # The same member, once holding it, reserves: the refusals above were the rule's, not a
    # missing route's.
    assert keeper_client.post(f"/document/{free.number}/edit/take/").status_code == 200
    assert redirected_to(
        keeper_client.post(f"/document/{free.number}/edit/reserve/"),
        f"/document/{free.number}/edit/",
    )

    # (c) a holder of the right on a frozen document, holding *accept* so they may edit it.
    frozen = new_document(author, "Synthetic purchasing procedure")
    link_group(
        frozen,
        [Right.ACCEPT, Right.EDIT, Right.RESERVE_FOR_EDITING],
        [reviewer_membership],
        author,
    )
    link_group(frozen, [Right.FREEZE], [freezer_membership], author)
    with schema_context(migrated_tenant.number):
        editions.freeze(frozen, freezer, FREEZE_REASON)
    assert reviewer_client.post(f"/document/{frozen.number}/edit/take/").status_code == 200

    refused = reviewer_client.post(f"/document/{frozen.number}/edit/reserve/")

    assert refused.status_code == 409
    hold = open_hold(migrated_tenant, frozen)
    assert hold is not None and hold.reserved_at is None
    tab = reviewer_client.get(f"/document/{frozen.number}/edit/").content.decode()
    # The band above the frame names the freeze already; the page itself draws the button,
    # disabled, and says why.
    in_tab = tab.split('<nav class="path"', 1)[1]
    assert disabled_button(in_tab)
    drawn = text_of(in_tab)
    assert "Frozen" in drawn
    assert FREEZE_REASON in drawn


def test_cancel_restarts_the_clock(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    from django.utils import timezone

    from audit.models import AuditEvent
    from editing.models import Hold

    _, author, _ = member_of("author.synthetic@example.test")
    holder_client, holder, holder_membership = member_of("holder.synthetic@example.test")
    other_client, _, other_membership = member_of("other.synthetic@example.test")
    document = new_document(author)
    link_group(
        document,
        [Right.EDIT, Right.RESERVE_FOR_EDITING],
        [holder_membership, other_membership],
        author,
    )
    number = document.number
    assert holder_client.post(f"/document/{number}/edit/take/").status_code == 200
    assert redirected_to(
        holder_client.post(f"/document/{number}/edit/reserve/"), f"/document/{number}/edit/"
    )
    with schema_context(migrated_tenant.number):
        # Weeks of quiet under the reservation.
        Hold.objects.filter(document=document, released_at__isnull=True).update(
            last_activity_at=timezone.now() - timedelta(days=20)
        )

    forged = other_client.post(f"/document/{number}/edit/cancel-reservation/")

    assert forged.status_code == 404
    hold = open_hold(migrated_tenant, document)
    assert hold is not None and hold.user_id == holder.pk and hold.reserved_at is not None
    assert not AuditEvent.objects.filter(action="document.reservation_cancelled").exists()

    cancelled = holder_client.post(f"/document/{number}/edit/cancel-reservation/")

    assert redirected_to(cancelled, f"/document/{number}/edit/"), cancelled.status_code
    hold = open_hold(migrated_tenant, document)
    assert hold is not None and hold.user_id == holder.pk
    assert hold.reserved_at is None
    assert abs((timezone.now() - hold.last_activity_at).total_seconds()) <= 1
    assert AuditEvent.objects.filter(
        action="document.reservation_cancelled", object_id=document.pk
    ).exists()


def test_my_reservations(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, settings: Any
) -> None:
    from editing.models import Hold

    settings.LANGUAGE_CODE = "en"
    _, author, _ = member_of("author.synthetic@example.test")
    holder_client, _, holder_membership = member_of("holder.synthetic@example.test")
    other_client, _, other_membership = member_of("other.synthetic@example.test")
    first = new_document(author, "Synthetic archiving procedure")
    second = new_document(author, "Synthetic training procedure")
    for document in (first, second):
        link_group(document, [Right.EDIT, Right.RESERVE_FOR_EDITING], [holder_membership], author)
    # The other member edits, and reserves nowhere.
    link_group(first, [Right.EDIT], [other_membership], author)
    dates = {
        first.pk: datetime(2026, 9, 3, 10, 0, tzinfo=UTC),
        second.pk: datetime(2026, 9, 21, 10, 0, tzinfo=UTC),
    }
    for document in (first, second):
        number = document.number
        assert holder_client.post(f"/document/{number}/edit/take/").status_code == 200
        assert redirected_to(
            holder_client.post(f"/document/{number}/edit/reserve/"), f"/document/{number}/edit/"
        )
        with schema_context(migrated_tenant.number):
            Hold.objects.filter(document=document, released_at__isnull=True).update(
                reserved_at=dates[document.pk]
            )

    listed = holder_client.get("/my-reservations/")

    assert listed.status_code == 200
    body = listed.content.decode()
    shown = text_of(body)
    for document in (first, second):
        assert f'href="/document/{document.number}/"' in body
        assert date_shown(shown, dates[document.pk], settings.DISPLAY_TIMEZONE), document.number
    menu = holder_client.get("/folder/1/").content.decode()
    assert 'href="/my-reservations/"' in menu

    assert other_client.get("/my-reservations/").status_code == 404
    assert "/my-reservations/" not in other_client.get("/folder/1/").content.decode()


def test_my_reservations_lists_only_what_its_holder_may_read(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    """A reservation outlives its holder's removal from the document's group, but the document is
    no longer theirs to read: the list leaves it out, its number and its title."""
    _, author, _ = member_of("author.synthetic@example.test")
    holder_client, _, holder_membership = member_of("holder.synthetic@example.test")
    revoked = new_document(author, "Synthetic procedure of revoked access")
    kept = new_document(author, "Synthetic procedure of current access")
    groups = {}
    for document in (revoked, kept):
        groups[document.pk] = link_group(
            document, [Right.EDIT, Right.RESERVE_FOR_EDITING], [holder_membership], author
        )
        number = document.number
        assert holder_client.post(f"/document/{number}/edit/take/").status_code == 200
        assert redirected_to(
            holder_client.post(f"/document/{number}/edit/reserve/"), f"/document/{number}/edit/"
        )
    with schema_context(migrated_tenant.number):
        groups[revoked.pk].remove_member(holder_membership, by=author)
    assert open_hold(migrated_tenant, revoked).reserved_at is not None

    body = holder_client.get("/my-reservations/").content.decode()

    assert f'href="/document/{kept.number}/"' in body
    assert f'href="/document/{revoked.number}/"' not in body
    assert "revoked access" not in body


def test_reserving_never_waits_for_the_person(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    """A self-block holds the person's row while it ends their holds; a reservation locks the
    document's row and the hold's alone, so it goes ahead rather than waiting out its lock."""
    import threading

    from django.contrib.auth import get_user_model
    from django.db import connection, transaction

    from editing.reservations import reserve

    _, author, _ = member_of("author.synthetic@example.test")
    holder_client, holder, holder_membership = member_of("holder.synthetic@example.test")
    document = new_document(author, "Synthetic reservation procedure")
    link_group(document, [Right.EDIT, Right.RESERVE_FOR_EDITING], [holder_membership], author)
    assert holder_client.post(f"/document/{document.number}/edit/take/").status_code == 200
    hold = open_hold(migrated_tenant, document)
    holding, release = threading.Event(), threading.Event()
    outcome: list[Any] = []

    def block() -> None:
        try:
            with transaction.atomic():
                get_user_model().objects.select_for_update(no_key=True).get(pk=holder.pk)
                holding.set()
                release.wait(timeout=30)
        finally:
            connection.close()

    def reserving() -> None:
        try:
            with schema_context(migrated_tenant.number):
                outcome.append(reserve(hold, holder))
        except Exception as error:  # noqa: BLE001 — reported by the assertion below
            outcome.append(error)
        finally:
            connection.close()

    blocker = threading.Thread(target=block)
    blocker.start()
    assert holding.wait(timeout=30)
    worker = threading.Thread(target=reserving)
    worker.start()
    worker.join(timeout=10)
    try:
        assert not worker.is_alive()
    finally:
        release.set()
        blocker.join(timeout=30)
        worker.join(timeout=30)
    assert outcome and not isinstance(outcome[0], Exception), outcome
    assert open_hold(migrated_tenant, document).reserved_at is not None
