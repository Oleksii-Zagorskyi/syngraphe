"""Who sees that a document is held or reserved, and who sees by whom (ADR-0006, DL-0226,
DL-0262): *held* to every reader with the name to administrators alone; *reserved for editing,
since* to every reader with the name to holders of *edit* or *accept* and to administrators; the
reservation's band on the document page; the date in the display timezone.

Group names, people and titles are synthetic examples."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

HOLDER = "Synthetic Holder H"
ADDRESS = "the.holder@example.test"
# Late on the 13th in UTC, already the 14th east of it: the date shown is the display zone's.
RESERVED_AT = datetime(2026, 10, 13, 22, 30, tzinfo=UTC)
# Who may learn the holder's name on an ordinary hold, and on a reservation (DL-0226).
NAMED_ON_A_HOLD = {"administrator", "platform"}
NAMED_ON_A_RESERVATION = {"editor", "administrator", "platform", "holder"}


def _cast(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    make_tenant_schema: Any,
) -> dict[str, Any]:
    """A holder and, around their document: a reader of accepted text, a reader of pending text
    — the right just below *edit* — another editor, a tenant administrator, and a platform
    administrator who is a plain member here. The reader of accepted text administers another
    organisation, which names nobody here."""
    from access.rights import Right
    from identity.models import Membership

    holder, author, own = member_of(ADDRESS)
    author.display_name = HOLDER
    author.save(update_fields=["display_name"])
    reader, reader_user, reading = member_of("a.reader@example.test")
    pending, _, pending_reading = member_of("a.pending.reader@example.test")
    editor, _, editing = member_of("another.editor@example.test")
    administrator, _, _ = member_of("the.admin@example.test", is_tenant_admin=True)
    platform, _, _ = member_of("the.platform.admin@example.test", is_platform_admin=True)
    elsewhere = make_tenant_schema("Another synthetic organisation")
    Membership.objects.create(
        tenant=elsewhere, user=reader_user, is_tenant_admin=True, actor_kind="system"
    )
    document = new_document(author)
    link_group(document, [Right.EDIT], [own, editing], author)
    link_group(document, [Right.VIEW_ACCEPTED], [reading], author)
    link_group(document, [Right.VIEW_PENDING], [pending_reading], author)
    assert holder.post(f"/document/{document.number}/edit/take/").status_code == 200
    return {
        "document": document,
        "holder": holder,
        "reader": reader,
        "pending": pending,
        "editor": editor,
        "administrator": administrator,
        "platform": platform,
    }


def _pages(client: Any, document: Any) -> tuple[str, str]:
    listed = client.get("/folder/1/")
    page = client.get(f"/document/{document.number}/")
    assert listed.status_code == 200 and page.status_code == 200
    return listed.content.decode(), page.content.decode()


def test_held_by_rights(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    make_tenant_schema: Any,
    settings: Any,
) -> None:
    settings.LANGUAGE_CODE = "en"
    cast = _cast(migrated_tenant, member_of, new_document, link_group, make_tenant_schema)
    for who in ("reader", "pending", "editor", "administrator", "platform"):
        tag = (
            f'data-state="held">held by {HOLDER}<'
            if who in NAMED_ON_A_HOLD
            else 'data-state="held">held<'
        )
        for body in _pages(cast[who], cast["document"]):
            assert tag in body, who
            assert ADDRESS not in body, who
            assert 'class="band res"' not in body, who


def test_reserved_by_rights(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    make_tenant_schema: Any,
    settings: Any,
) -> None:
    from editing.models import Hold

    settings.LANGUAGE_CODE = "en"
    settings.DISPLAY_TIMEZONE = "Europe/Kyiv"
    cast = _cast(migrated_tenant, member_of, new_document, link_group, make_tenant_schema)
    with schema_context(migrated_tenant.number):
        Hold.objects.filter(document=cast["document"]).update(reserved_at=RESERVED_AT)

    for who in ("reader", "pending", "editor", "administrator", "platform", "holder"):
        named = who in NAMED_ON_A_RESERVATION
        tag = (
            f'data-state="reserved">reserved for editing by {HOLDER}, since Oct. 14, 2026<'
            if named
            else 'data-state="reserved">reserved for editing, since Oct. 14, 2026<'
        )
        listed, page = _pages(cast[who], cast["document"])
        for body in (listed, page):
            assert tag in body, who
            assert 'data-state="held"' not in body, who
            assert "Oct. 13, 2026" not in body, who
            if who != "holder":
                assert ADDRESS not in body, who
        assert 'class="band res"' in page, who
        if who == "holder":
            assert "Reserved for editing by you since Oct. 14, 2026." in page
        else:
            assert "review, freezing and changes to the document's groups wait" in page, who
            band = page.split('class="band res"', 1)[1].split("</p>", 1)[0]
            assert (HOLDER in band) is named, who


def test_frozen_comes_before_the_hold(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, settings: Any
) -> None:
    """A holder of *accept* may hold a frozen document (ADR-0016): *frozen* stands first after the
    title (DL-0351), then the hold."""
    from access.rights import Right
    from editions.models import Freeze

    settings.LANGUAGE_CODE = "en"
    client, author, own = member_of(ADDRESS)
    document = new_document(author)
    link_group(document, [Right.EDIT, Right.ACCEPT], [own], author)
    with schema_context(migrated_tenant.number):
        from django.utils import timezone

        Freeze.objects.create(
            document=document, frozen_by=author, frozen_at=timezone.now(), reason=""
        )
    assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
    for body in _pages(client, document):
        assert body.index('data-state="frozen"') < body.index('data-state="held"')
