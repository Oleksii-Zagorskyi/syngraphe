"""Administration › document links: which groups reach which document, for administrators only.

Group names and people are synthetic examples."""

from __future__ import annotations

from typing import Any

import pytest

from documents import holds
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

URL = "/administration/tenant/document-links/"


def test_page_for_administrators_only(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    admin_client, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    member_client, creator, _ = member_of("the.creator@example.test")
    creator.display_name = "Авторка Приклад"
    creator.save()
    make_document(title="Синтетичний приклад", created_by=creator, author_only=True)

    as_admin = admin_client.get(URL)
    as_member = member_client.get(URL)

    body = as_admin.content.decode()
    assert as_admin.status_code == 200
    assert "Синтетичний приклад" in body
    assert "Авторка Приклад" in body
    assert 'class="tag author-only"' in body
    assert as_member.status_code == 404


def test_link_and_unlink_through_the_page(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    from access.models import AccessGroup, DocumentGroup

    admin_client, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    document = make_document(title="Синтетичний приклад", created_by=admin)
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(name="Readers", created_by=admin, actor_kind="user")

    linked = admin_client.post(
        f"{URL}{document.number}/", {"group": str(group.id), "action": "link"}
    )
    with schema_context(migrated_tenant.number):
        after_link = DocumentGroup.objects.filter(document=document, group=group).count()
    unlinked = admin_client.post(
        f"{URL}{document.number}/", {"group": str(group.id), "action": "unlink"}
    )
    with schema_context(migrated_tenant.number):
        after_unlink = DocumentGroup.objects.filter(document=document, group=group).count()

    assert linked.status_code == 302
    assert unlinked.status_code == 302
    assert (after_link, after_unlink) == (1, 0)


def test_members_cannot_link(migrated_tenant: Any, member_of: Any, make_document: Any) -> None:
    from access.models import AccessGroup, DocumentGroup

    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    member_client, _, _ = member_of("a.member@example.test")
    document = make_document(created_by=admin)
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(name="Readers", created_by=admin, actor_kind="user")

    response = member_client.post(
        f"{URL}{document.number}/", {"group": str(group.id), "action": "link"}
    )

    assert response.status_code == 404
    with schema_context(migrated_tenant.number):
        assert not DocumentGroup.objects.exists()


def test_the_groups_page_shows_the_platform_pane(migrated_tenant: Any, member_of: Any) -> None:
    client, _, _ = member_of("an.operator@example.test", is_platform_admin=True)

    body = client.get("/administration/tenant/groups/").content.decode()

    assert 'class="pane platform"' in body


def test_other_methods_answer_not_found(migrated_tenant: Any, member_of: Any) -> None:
    client, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)

    assert client.post(URL).status_code == 404
    assert client.get(f"{URL}1/").status_code == 404
    assert client.put("/administration/tenant/groups/").status_code == 404


def _hold(document: Any, user: Any, *, reserved: Any = None) -> Any:
    from django.utils import timezone

    from editing.models import Hold

    now = timezone.now()
    return Hold.objects.create(
        document=document, user=user, acquired_at=now, last_activity_at=now, reserved_at=reserved
    )


def test_locked_rows_name_the_holder(
    migrated_tenant: Any, member_of: Any, make_document: Any, settings: Any
) -> None:
    from datetime import UTC, datetime

    settings.LANGUAGE_CODE = "en"
    # Just before midnight in UTC is the next day east of it: the date is the reader's.
    settings.DISPLAY_TIMEZONE = "Asia/Tokyo"
    late = datetime(2026, 10, 4, 22, 30, tzinfo=UTC)
    admin_client, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    _, holder, _ = member_of("the.holder@example.test")
    holder.display_name = "Редакторка Приклад"
    holder.save()
    _, keeper, _ = member_of("the.keeper@example.test")
    keeper.display_name = "Рецензент Приклад"
    keeper.save()
    with schema_context(migrated_tenant.number):
        held = make_document(title="Синтетичний утримуваний", created_by=admin)
        reserved = make_document(title="Синтетичний зарезервований", created_by=admin)
        free = make_document(title="Синтетичний вільний", created_by=admin)
        _hold(held, holder)
        _hold(reserved, keeper, reserved=late)

    body = admin_client.get(URL).content.decode()

    rows = {
        document.number: body.split(f"<td>{document.number}</td>", 1)[1].split("</tr>", 1)[0]
        for document in (held, reserved, free)
    }
    assert "Held by Редакторка Приклад" in rows[held.number]
    assert "Reserved" not in rows[held.number] and "Held by" not in rows[reserved.number]
    with schema_context(migrated_tenant.number):
        assert holds.holder_of(held) == holder and holds.holder_of(free) is None
    assert "Рецензент Приклад" in rows[reserved.number]
    assert "Reserved for editing" in rows[reserved.number]
    assert "5 October 2026" in rows[reserved.number] or "Oct. 5, 2026" in rows[reserved.number]
    assert "Held by" not in rows[free.number] and "Reserved" not in rows[free.number]
    # A held document's chips stay locked.
    assert 'class="link-a-group"' not in rows[held.number]
    assert 'class="link-a-group"' not in rows[reserved.number]


def test_author_only_and_archived_rows(
    migrated_tenant: Any, member_of: Any, make_document: Any, settings: Any
) -> None:
    settings.LANGUAGE_CODE = "en"
    from access.models import AccessGroup

    admin_client, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    _, creator, _ = member_of("the.creator@example.test")
    creator.display_name = "Авторка Приклад"
    creator.save()
    with schema_context(migrated_tenant.number):
        AccessGroup.objects.create(name="Readers", created_by=admin, actor_kind="user")
        mine = make_document(title="Синтетичний авторський", created_by=creator, author_only=True)
        archived = make_document(
            title="Синтетичний архівний", created_by=admin, author_only=False, state="archived"
        )

    body = admin_client.get(URL).content.decode()

    mine_row = body.split(f"<td>{mine.number}</td>", 1)[1].split("</tr>", 1)[0]
    archived_row = body.split(f"<td>{archived.number}</td>", 1)[1].split("</tr>", 1)[0]
    assert "Авторка Приклад" in mine_row and 'class="tag author-only"' in mine_row
    # No group is linked, so no chip; linking one is how the row opens to others.
    assert 'class="chip"' not in mine_row and 'class="link-a-group"' in mine_row
    assert "Archived — its links take effect on restore." in archived_row
    assert 'class="link-a-group"' in archived_row


def test_a_holder_is_named_as_the_platform_names_a_person(
    migrated_tenant: Any, member_of: Any, make_document: Any, settings: Any
) -> None:
    settings.LANGUAGE_CODE = "en"
    admin_client, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    _, nameless, _ = member_of("no.name@example.test")
    with schema_context(migrated_tenant.number):
        document = make_document(title="Синтетичний утримуваний", created_by=admin)
        _hold(document, nameless)

    body = admin_client.get(URL).content.decode()

    row = body.split(f"<td>{document.number}</td>", 1)[1].split("</tr>", 1)[0]
    assert "Held by anonymous editor." in row
    assert "no.name@example.test" not in row


def test_the_page_reads_every_hold_at_once(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    admin_client, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    _, holder, _ = member_of("the.holder@example.test")

    def held(count: int) -> int:
        with schema_context(migrated_tenant.number):
            for index in range(count):
                # Another person's documents, so the shell's own menus read the same every time.
                document = make_document(
                    title=f"Синтетичний {index}", created_by=holder, author_only=False
                )
                _hold(document, holder)
        with CaptureQueriesContext(connection) as queries:
            assert admin_client.get(URL).status_code == 200
        return len(queries)

    # A first request fills the caches every later one reads.
    admin_client.get(URL)
    one = held(1)
    three = held(2)
    assert three == one
