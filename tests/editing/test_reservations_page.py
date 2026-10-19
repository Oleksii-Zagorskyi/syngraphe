"""Administration › reservations: every reservation of the organisation, its holder and date,
and the way to end each (ST-0070, DL-0226, DL-0415).

People, organisations, groups and texts are synthetic examples: every address ends in
`@example.test`, and every text is invented."""

from __future__ import annotations

import html
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import pytest

from access.rights import Right
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

URL = "/administration/tenant/reservations/"


def redirected_to(response: Any, path: str) -> bool:
    """Whether `response` is a 302 whose target is `path`."""
    return response.status_code == 302 and urlsplit(response["Location"]).path == path


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


def test_lists_each_with_its_end_link(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, settings: Any
) -> None:
    from editing.models import Hold

    settings.LANGUAGE_CODE = "en"
    _, author, _ = member_of("author.synthetic@example.test")
    admin_client, _, _ = member_of("admin.synthetic@example.test", is_tenant_admin=True)
    member_client, _, _ = member_of("member.synthetic@example.test")
    first_client, first, first_membership = member_of("first.holder.synthetic@example.test")
    first.display_name = "Synthetic First Owner"
    first.save(update_fields=["display_name"])
    second_client, second, second_membership = member_of("second.holder.synthetic@example.test")
    second.display_name = "Synthetic Second Owner"
    second.save(update_fields=["display_name"])
    reservations = [
        (
            new_document(author, "Synthetic archiving procedure"),
            first,
            first_client,
            first_membership,
            datetime(2026, 9, 3, 10, 0, tzinfo=UTC),
        ),
        (
            new_document(author, "Synthetic training procedure"),
            second,
            second_client,
            second_membership,
            datetime(2026, 9, 21, 10, 0, tzinfo=UTC),
        ),
    ]
    for document, _, client, membership, date in reservations:
        link_group(document, [Right.EDIT, Right.RESERVE_FOR_EDITING], [membership], author)
        number = document.number
        assert client.post(f"/document/{number}/edit/take/").status_code == 200
        made = client.post(f"/document/{number}/edit/reserve/")
        assert redirected_to(made, f"/document/{number}/edit/"), made.status_code
        with schema_context(migrated_tenant.number):
            Hold.objects.filter(document=document, released_at__isnull=True).update(
                reserved_at=date
            )

    page = admin_client.get(URL)

    assert page.status_code == 200
    body = page.content.decode()
    shown = text_of(body)
    for document, holder, _, _, date in reservations:
        number = document.number
        assert document.title in shown or f"#{number}" in shown or f"/document/{number}/" in body
        # An administration page names a person by address (DL-0434).
        assert holder.email in shown and holder.display_name not in shown
        assert date_shown(shown, date, settings.DISPLAY_TIMEZONE), number
        assert f'href="/document/{number}/edit/end-reservation/"' in body
    frame = admin_client.get("/administration/tenant/users/").content.decode()
    assert f'href="{URL}"' in frame

    assert member_client.get(URL).status_code == 404


def test_an_administrators_own_reservation_offers_no_end(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, settings: Any
) -> None:
    """An administrator who reserved a document cancels it; the links page and the reservations
    page offer them no *End the reservation…* on it, while another administrator sees one."""
    from access.rights import Right

    settings.LANGUAGE_CODE = "en"
    admin_client, admin, own = member_of("the.admin@example.test", is_tenant_admin=True)
    other_client, _, _ = member_of("another.admin@example.test", is_tenant_admin=True)
    document = new_document(admin)
    link_group(document, [Right.EDIT, Right.RESERVE_FOR_EDITING], [own], admin)
    assert admin_client.post(f"/document/{document.number}/edit/take/").status_code == 200
    admin_client.post(f"/document/{document.number}/edit/reserve/")
    end = f"/document/{document.number}/edit/end-reservation/"
    for path in ("/administration/tenant/document-links/", "/administration/tenant/reservations/"):
        assert end not in admin_client.get(path).content.decode(), path
        assert end in other_client.get(path).content.decode(), path


def test_the_links_page_forces_an_ordinary_hold(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, settings: Any
) -> None:
    """The links page offers *Force release* on another member's ordinary hold, naming the hold,
    and the form releases it; never on the administrator's own hold."""
    from access.rights import Right
    from editing.models import Hold

    settings.LANGUAGE_CODE = "en"
    admin_client, admin, own = member_of("the.admin@example.test", is_tenant_admin=True)
    holder_client, _, theirs = member_of("the.holder@example.test")
    document = new_document(admin)
    link_group(document, [Right.EDIT], [own, theirs], admin)
    assert holder_client.post(f"/document/{document.number}/edit/take/").status_code == 200
    with schema_context(migrated_tenant.number):
        hold = Hold.objects.get(document=document, released_at__isnull=True)
    page = admin_client.get("/administration/tenant/document-links/").content.decode()
    action = f'action="/document/{document.number}/edit/force-release/"'
    assert action in page and f'value="{hold.pk}"' in page
    forced = admin_client.post(
        f"/document/{document.number}/edit/force-release/", {"hold": str(hold.pk)}
    )
    assert forced.status_code == 302
    with schema_context(migrated_tenant.number):
        hold.refresh_from_db()
    assert hold.release_kind == "forced"
    # Their own hold: no force offered.
    assert admin_client.post(f"/document/{document.number}/edit/take/").status_code == 200
    page = admin_client.get("/administration/tenant/document-links/").content.decode()
    assert action not in page
