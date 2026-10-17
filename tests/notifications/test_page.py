"""The notifications page and the count in the shell (DL-0204, DL-0236, DL-0367, DL-0385): two
tabs, newest first, opening marks read, *mark all as read* on the administrative tab alone, the
unread count across the schemas a person reads, and only the row's own person reaches it.

People, groups and titles are synthetic examples."""

from __future__ import annotations

import re
from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

ENTRY = re.compile(r'class="notification[^"]*" data-id="([0-9a-f-]+)"')
UNREAD = re.compile(r'class="notifications" href="/notifications/" data-unread="(\d+)"')


def without_tenant(client: Any) -> Any:
    """The same signed-in client with no organisation chosen in its session."""
    session = client.session
    session.pop("tenant_number", None)
    session.save()
    return client


def tokenless(body: bytes) -> bytes:
    """A page without its form's per-response token."""
    return re.sub(rb'name="csrfmiddlewaretoken" value="[^"]*"', b"", body)


def entries(body: str) -> list[str]:
    return ENTRY.findall(body)


def unread(body: str) -> int:
    found = UNREAD.search(body)
    assert found is not None, "the shell draws no notifications link"
    return int(found.group(1))


def test_tabs_count_and_opening_marks_read(
    member_of: Any, make_document: Any, written: Any
) -> None:
    client, person, _ = member_of("a.reader@example.test")
    document = make_document(title="Synthetic regulation", created_by=person)
    first = written(person, "version_committed", document=document, at=1)
    second = written(person, "version_committed", document=document, at=2)
    third = written(person, "version_committed", document=document, at=3)
    granted = written(person, "access_granted", at=4, facts={"group": "synthetic"})

    page = client.get("/notifications/").content.decode()
    assert unread(page) == 4
    assert entries(page) == [str(third.pk), str(second.pk), str(first.pk)]
    administrative = client.get("/notifications/?tab=administrative").content.decode()
    assert entries(administrative) == [str(granted.pk)]

    opened = client.get(f"/notifications/{second.pk}/")
    assert opened.status_code == 302
    assert opened["Location"] == f"/document/{document.number}/"
    assert unread(client.get("/notifications/").content.decode()) == 3


def test_read_all_marks_the_administrative_tab_alone(
    migrated_tenant: Any, member_of: Any, make_document: Any, written: Any
) -> None:
    from notifications.models import Notification

    client, person, _ = member_of("a.reader@example.test", is_tenant_admin=True)
    document = make_document(title="Synthetic regulation")
    one = written(person, "document_created", document=document, at=1)
    two = written(person, "access_granted", at=2, facts={"group": "synthetic"})
    kept = written(person, "version_committed", document=document, at=3)

    response = client.post("/notifications/read-all/")
    assert response.status_code == 302
    with schema_context(migrated_tenant.number):
        read = {row.pk: row.read_at for row in Notification.objects.all()}
    assert read[one.pk] is not None and read[two.pk] is not None
    assert read[kept.pk] is None


def test_only_its_person_and_a_member_only_in_a_tenant(
    member_of: Any, make_document: Any, written: Any
) -> None:
    owner_client, owner, _ = member_of("the.owner@example.test")
    other_client, _, _ = member_of("another.member@example.test")
    document = make_document(title="Synthetic regulation", created_by=owner)
    row = written(owner, "version_committed", document=document)

    refused = other_client.get(f"/notifications/{row.pk}/")
    missing = other_client.get("/notifications/00000000-0000-0000-0000-000000000000/")
    assert refused.status_code == missing.status_code == 404
    assert tokenless(refused.content) == tokenless(missing.content)

    alone = without_tenant(owner_client)
    refused = alone.get("/notifications/")
    assert refused.status_code == 404
    assert tokenless(refused.content) == tokenless(alone.get("/folder/999/").content)


def test_a_platform_administrator_reads_both_schemas_or_the_shared_alone(
    member_of: Any, make_document: Any, written: Any, written_platform: Any
) -> None:
    from tenancy.models import PlatformNotification

    client, admin, _ = member_of("p.admin@example.test", is_platform_admin=True)
    document = make_document(title="Synthetic regulation")
    tenant_row = written(admin, "document_created", document=document, at=1)
    shared_row = written_platform(admin, "backup_condition", at=2, facts={"change": "began"})

    page = client.get("/notifications/?tab=administrative").content.decode()
    assert unread(page) == 2
    assert entries(page) == [str(shared_row.pk), str(tenant_row.pk)]

    client = without_tenant(client)
    page = client.get("/notifications/?tab=administrative").content.decode()
    assert unread(page) == 1
    assert entries(page) == [str(shared_row.pk)]
    opened = client.get(f"/notifications/{shared_row.pk}/")
    assert opened.status_code == 302 and opened["Location"] == "/health/"
    with schema_context(None):
        assert PlatformNotification.objects.get().read_at is not None


def test_no_filters_for_events_a_person_never_receives(member_of: Any, written: Any) -> None:
    member_client, member, _ = member_of("a.member@example.test")
    admin_client, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    written(member, "access_granted", facts={"group": "synthetic"})

    member_page = member_client.get("/notifications/?tab=administrative").content.decode()
    assert 'class="filters"' not in member_page
    admin_page = admin_client.get("/notifications/?tab=administrative").content.decode()
    assert 'class="filters"' in admin_page


def test_administrators_read_that_no_sender_exists(member_of: Any) -> None:
    admin_client, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    member_client, _, _ = member_of("a.member@example.test")

    assert "data-no-sender" in admin_client.get("/notifications/").content.decode()
    assert "data-no-sender" not in member_client.get("/notifications/").content.decode()


def test_one_persons_count_and_read_all_leave_anothers_alone(
    migrated_tenant: Any, member_of: Any, make_document: Any, written: Any
) -> None:
    from notifications.models import Notification

    client, person, _ = member_of("a.reader@example.test", is_tenant_admin=True)
    _, other, _ = member_of("another.reader@example.test", is_tenant_admin=True)
    document = make_document(title="Synthetic regulation")
    written(person, "document_created", document=document, at=1)
    theirs = [
        written(other, "document_created", document=document, at=2),
        written(other, "version_committed", document=document, at=3),
    ]

    assert unread(client.get("/notifications/").content.decode()) == 1
    assert client.get("/notifications/read-all/").status_code == 404
    assert client.post("/notifications/read-all/").status_code == 302
    with schema_context(migrated_tenant.number):
        assert all(Notification.objects.get(pk=row.pk).read_at is None for row in theirs)


def test_read_all_marks_a_platform_administrators_shared_rows(
    member_of: Any, written_platform: Any
) -> None:
    from tenancy.models import PlatformNotification

    client, admin, _ = member_of("p.admin@example.test", is_platform_admin=True)
    _, other, _ = member_of("other.p.admin@example.test", is_platform_admin=True)
    written_platform(admin, "backup_condition", facts={"change": "began"})
    kept = written_platform(other, "backup_condition", facts={"change": "began"})

    assert client.post("/notifications/read-all/").status_code == 302
    with schema_context(None):
        assert PlatformNotification.objects.get(user=admin).read_at is not None
        assert PlatformNotification.objects.get(pk=kept.pk).read_at is None


def test_another_organisations_row_is_not_found_by_its_id(
    member_of: Any, make_tenant_schema: Any, written: Any
) -> None:
    from identity.models import Membership
    from notifications.models import Category, Event, Notification

    client, person, _ = member_of("both.places@example.test")
    elsewhere = make_tenant_schema("Another synthetic organisation")
    Membership.objects.create(tenant=elsewhere, user=person, actor_kind="system")
    with schema_context(elsewhere.number):
        row = Notification.objects.create(
            user=person,
            category=Category.ADMINISTRATIVE,
            event=Event.ACCESS_GRANTED,
            facts={},
        )

    assert client.get(f"/notifications/{row.pk}/").status_code == 404


@pytest.mark.parametrize("blocked", ["membership", "account"])
def test_a_blocked_person_reads_and_counts_nothing(
    migrated_tenant: Any, member_of: Any, written: Any, blocked: str
) -> None:
    from notifications.models import Notification

    client, person, membership = member_of("a.reader@example.test")
    _, admin, _ = member_of("the.admin@example.test", is_tenant_admin=True)
    row = written(person, "access_granted", facts={})
    if blocked == "membership":
        membership.change("state", "blocked", by=admin)
    else:
        person.self_blocked = True
        person.save(update_fields=["self_blocked"])

    assert client.get("/notifications/").status_code == 404
    assert client.get(f"/notifications/{row.pk}/").status_code == 404
    assert 'class="notifications"' not in client.get("/help/").content.decode()
    with schema_context(migrated_tenant.number):
        assert Notification.objects.get(pk=row.pk).read_at is None


def test_shared_rows_reach_only_their_platform_administrator(
    member_of: Any, written_platform: Any
) -> None:
    from tenancy.models import PlatformNotification

    client, _, _ = member_of("p.admin@example.test", is_platform_admin=True)
    member_client, member, _ = member_of("a.member@example.test")
    _, other, _ = member_of("other.p.admin@example.test", is_platform_admin=True)
    theirs = written_platform(other, "backup_condition", facts={"change": "began"})

    assert client.get(f"/notifications/{theirs.pk}/").status_code == 404
    assert member_client.get(f"/notifications/{theirs.pk}/").status_code == 404
    with schema_context(None):
        assert PlatformNotification.objects.get(pk=theirs.pk).read_at is None


def test_a_group_fact_never_leads_off_the_platform(member_of: Any, written: Any) -> None:
    client, person, _ = member_of("the.admin@example.test", is_tenant_admin=True)
    for fact in ("//elsewhere.example.test/", "https://elsewhere.example.test/", "../x"):
        row = written(person, "access_granted", facts={"group": fact})
        target = client.get(f"/notifications/{row.pk}/")["Location"]
        assert target == "/administration/tenant/groups/", fact


def test_a_member_is_led_to_the_list_and_an_administrator_to_the_group(
    migrated_tenant: Any, member_of: Any, written: Any
) -> None:
    from access.models import AccessGroup

    member_client, member, _ = member_of("a.member@example.test")
    admin_client, admin, _ = member_of("the.admin@example.test", is_tenant_admin=True)
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(
            name="Synthetic group", created_by=admin, actor_kind="user"
        )
    for client, person, target in (
        (member_client, member, "/folder/1/"),
        (admin_client, admin, f"/administration/tenant/groups/{group.pk}/members/"),
    ):
        row = written(person, "access_granted", facts={"group": str(group.pk)})
        assert client.get(f"/notifications/{row.pk}/")["Location"] == target


def test_a_platform_administrator_without_an_organisation_opens_on_the_administrative_tab(
    member_of: Any, written_platform: Any
) -> None:
    client, admin, _ = member_of("p.admin@example.test", is_platform_admin=True)
    shared = written_platform(admin, "backup_condition", facts={"change": "began"})

    page = without_tenant(client).get("/notifications/").content.decode()
    assert entries(page) == [str(shared.pk)]
    assert "?tab=document" not in page


def test_filters_drawn_are_the_events_each_person_can_receive(
    member_of: Any, written: Any, written_platform: Any
) -> None:
    filters = re.compile(r"event=([a-z_]+)")
    admin_client, admin, _ = member_of("the.admin@example.test", is_tenant_admin=True)
    platform_client, platform, _ = member_of("p.admin@example.test", is_platform_admin=True)
    written(admin, "access_granted", at=1, facts={})
    written(admin, "document_created", at=2, facts={})

    page = admin_client.get("/notifications/?tab=administrative").content.decode()
    assert filters.findall(page) == [
        "access_granted",
        "document_created",
        "document_copied",
        "email_failed",
        "reservation_started",
    ]
    chosen = admin_client.get("/notifications/?tab=administrative&event=access_granted")
    assert len(entries(chosen.content.decode())) == 1
    page = platform_client.get("/notifications/?tab=administrative").content.decode()
    assert filters.findall(page) == [
        "access_granted",
        "document_created",
        "document_copied",
        "backup_condition",
        "email_failed",
        "user_partially_blocked",
        "tenant_without_admin",
        "reservation_started",
    ]
    page = without_tenant(platform_client).get("/notifications/?tab=administrative")
    assert filters.findall(page.content.decode()) == [
        "backup_condition",
        "email_failed",
        "user_partially_blocked",
        "tenant_without_admin",
    ]
    assert "data-no-sender" in page.content.decode()


def test_document_events_name_their_document(migrated_tenant: Any, member_of: Any) -> None:
    from django.db import IntegrityError, transaction

    from notifications.models import Category, Event, Notification

    _, person, _ = member_of("a.reader@example.test")
    with schema_context(migrated_tenant.number):
        # The archived holder's notice names no document, which they may no longer
        # open (DL-0471); it alone is exempt.
        Notification.objects.create(
            user=person, category=Category.DOCUMENT, event=Event.DOCUMENT_ARCHIVED
        )
    with schema_context(migrated_tenant.number), pytest.raises(IntegrityError):
        with transaction.atomic():
            Notification.objects.create(user=person, category=Category.DOCUMENT, event=Event.FROZEN)


def test_an_entry_whose_document_its_reader_cannot_open_is_neither_drawn_nor_counted(
    migrated_tenant: Any, member_of: Any, make_document: Any, written: Any
) -> None:
    """DL-0386: a right revoked hides the entry and its count, as a missing document would; the
    right back brings both back."""
    from access.models import AccessGroup, DocumentGroup
    from access.rights import Right

    client, reader, membership = member_of("a.reader@example.test")
    _, admin, _ = member_of("the.admin@example.test", is_tenant_admin=True)
    document = make_document(title="Synthetic regulation", author_only=False)
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(
            name="Synthetic group", created_by=admin, actor_kind="user"
        )
        group.grant(Right.VIEW_ACCEPTED, by=admin)
        group.add_member(membership, by=admin)
        DocumentGroup.link(document, group, by=admin)
    row = written(reader, "frozen", document=document, at=1)

    page = client.get("/notifications/").content.decode()
    # Joining the group was itself an unread entry (*access granted*).
    assert entries(page) == [str(row.pk)] and unread(page) == 2
    with schema_context(migrated_tenant.number):
        DocumentGroup.unlink(document, group, by=admin)
    page = client.get("/notifications/").content.decode()
    assert entries(page) == [] and unread(page) == 1
    assert "Synthetic regulation" not in page
    # Opened by its address, it answers as a missing entry, and stays unread.
    assert client.get(f"/notifications/{row.pk}/").status_code == 404
    with schema_context(migrated_tenant.number):
        row.refresh_from_db()
    assert row.read_at is None
    with schema_context(migrated_tenant.number):
        DocumentGroup.link(document, group, by=admin)
    assert entries(client.get("/notifications/").content.decode()) == [str(row.pk)]


def test_the_platform_notices_lead_to_a_page_their_host_serves(
    migrated_tenant: Any, member_of: Any
) -> None:
    """The organisations page is a platform host's alone (DL-0290): on an organisation's domain a
    block's notices lead to the administration instead of a not-found."""
    from types import SimpleNamespace

    from notifications.views.detail import _target
    from tenancy.models import PlatformNotification

    _, admin, _ = member_of("p.admin@example.test", is_platform_admin=True)
    for event in ("user_partially_blocked", "tenant_without_admin"):
        row = PlatformNotification(
            user=admin, event=event, facts={"tenant": migrated_tenant.number}
        )
        on_platform = SimpleNamespace(tenant=None, tenant_from_domain=False, user=admin)
        on_domain = SimpleNamespace(tenant=migrated_tenant, tenant_from_domain=True, user=admin)
        assert _target(on_platform, row) == "/administration/platform/tenants/", event
        assert _target(on_domain, row) == "/administration/", event
