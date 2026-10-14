"""The outbox (DL-0202, DL-0203, DL-0205): each notification queues one email in the same schema as
the notification, from the schema's own sender or else the platform's, saying who did what to
which document and where to look — never a line of the document; with no sender anywhere nothing
is queued and an administrator is told so; links use the organisation's own address or the
platform's.

People, groups, addresses and texts are synthetic examples; every address ends in `@example.test`.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.utils import timezone

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

WRITTEN = (
    "# Синтетичні положення\n\n"
    "Заяву на синтетичне погодження подають письмово.\n"
    "Строк розгляду синтетичної заяви становить десять днів.\n"
)
AUTHOR = "Авторка Синтетична"


def committed(migrated_tenant: Any, cast: Any, commit_version: Any) -> tuple[Any, Any, str]:
    """A document by `a`, named, with one content version under review by `r1` and `r2`; the
    people, the version and the number it carries."""
    from editing import numbering

    people = cast(editors=("a",), reviewers=("r1", "r2"))
    people["a"].display_name = AUTHOR
    people["a"].save(update_fields=["display_name"])
    version = commit_version(people.document, people["a"], WRITTEN, "edit")
    with schema_context(migrated_tenant.number):
        number = numbering.latest(people.document)
    return people, version, number


def tell_reviewers(people: Any, version: Any, number: str) -> list[Any]:
    """`version_committed` to both reviewers, in the current schema."""
    from notifications.models import Category, Event
    from notifications.services import notify

    return notify(
        users=[people["r1"], people["r2"]],
        category=Category.DOCUMENT,
        event=Event.VERSION_COMMITTED,
        actor=people["a"],
        document=people.document,
        version=version,
        facts={"version": number},
    )


def test_each_notification_queues_one_email_with_facts_only(
    migrated_tenant: Any, cast: Any, commit_version: Any, sender: Any
) -> None:
    from mail import services as mail
    from mail.models import EmailOutbox, Status

    people, version, number = committed(migrated_tenant, cast, commit_version)
    sending = sender(migrated_tenant.number)
    document = people.document

    with schema_context(migrated_tenant.number):
        before = timezone.now()
        made = tell_reviewers(people, version, number)
        after = timezone.now()
        rows = list(EmailOutbox.objects.order_by("recipient"))
        links = {
            row.pk: mail.link(migrated_tenant, f"/notifications/{row.notification_id}/")
            for row in rows
        }
    with schema_context(None):
        assert not EmailOutbox.objects.exists()

    assert [row.recipient for row in rows] == [
        "r1.synthetic@example.test",
        "r2.synthetic@example.test",
    ]
    by_user = {notification.user.email: notification for notification in made}
    for row in rows:
        assert row.status == Status.QUEUED
        assert row.attempts == 0
        assert before <= row.next_attempt_at <= after
        assert row.sent_at is None
        assert row.sender == sending.address
        assert row.tenant_id == migrated_tenant.pk
        assert row.notification_id == by_user[row.recipient].pk
        assert by_user[row.recipient].emailed_at is None
        # Facts: the document's number and title, the version, the author, one link — to the
        # notification it carries, which marks it read and leads where the entry leads.
        assert links[row.pk] in row.body
        assert f"/document/{document.number}/" not in row.body
        assert document.title in row.body
        assert number in row.body
        assert AUTHOR in row.body
        # Never a line of the text.
        for line in WRITTEN.splitlines():
            if line.strip():
                assert line not in row.body
                assert line.lstrip("# ") not in row.body
                assert line not in row.subject


def test_nothing_queued_without_a_sender(
    migrated_tenant: Any, member_of: Any, cast: Any, commit_version: Any, sender: Any
) -> None:
    from mail.models import EmailOutbox, MailSender
    from notifications.models import Notification

    people, version, number = committed(migrated_tenant, cast, commit_version)
    admin_client, _, _ = member_of("t.synthetic@example.test", is_tenant_admin=True)
    with schema_context(None):
        assert not MailSender.objects.exists()

    with schema_context(migrated_tenant.number):
        assert not MailSender.objects.exists()
        made = tell_reviewers(people, version, number)
        assert not EmailOutbox.objects.exists()
        written = Notification.objects.filter(pk__in=[n.pk for n in made])
        assert written.count() == 2
        assert all(n.emailed_at is None for n in written)
    with schema_context(None):
        assert not EmailOutbox.objects.exists()

    # The administrator is told that no email leaves the platform.
    page = admin_client.get("/notifications/")
    assert page.status_code == 200
    assert "data-no-sender" in page.content.decode()

    # Either sender saved removes it.
    platform = sender(None)
    assert "data-no-sender" not in admin_client.get("/notifications/").content.decode()
    with schema_context(None):
        MailSender.objects.filter(pk=platform.pk).delete()
    assert "data-no-sender" in admin_client.get("/notifications/").content.decode()
    sender(migrated_tenant.number)
    assert "data-no-sender" not in admin_client.get("/notifications/").content.decode()


def test_platform_sender_is_the_fallback(
    migrated_tenant: Any, cast: Any, commit_version: Any, sender: Any
) -> None:
    from mail import services as mail
    from mail.models import EmailOutbox, Status

    people, version, number = committed(migrated_tenant, cast, commit_version)
    platform = sender(None)

    with schema_context(migrated_tenant.number):
        found = mail.sender_for_queue()
        assert found is not None and found.address == platform.address
        made = tell_reviewers(people, version, number)
        rows = list(EmailOutbox.objects.all())
    with schema_context(None):
        assert not EmailOutbox.objects.exists()

    assert len(rows) == 2
    assert {row.notification_id for row in rows} == {n.pk for n in made}
    for row in rows:
        assert row.sender == platform.address
        assert row.tenant_id == migrated_tenant.pk
        assert row.status == Status.QUEUED


def test_platform_mail_lives_in_the_shared_outbox(migrated_tenant: Any, sender: Any) -> None:
    from identity.models import User
    from mail.models import EmailOutbox, Status
    from notifications.models import Event
    from notifications.services import notify_platform
    from tenancy.models import PlatformNotification

    operator = User.objects.create_user(
        "o.synthetic@example.test", "test-only-not-a-password", is_platform_admin=True
    )
    # The tenant's own sender is there too: platform mail never leaves through it.
    sender(migrated_tenant.number)
    platform = sender(None)

    # Written from inside a tenant's schema, as a request on an organisation's address would.
    with schema_context(migrated_tenant.number):
        made = notify_platform(event=Event.BACKUP_CONDITION, users=[operator])
        assert not EmailOutbox.objects.exists()

    assert len(made) == 1
    with schema_context(None):
        assert PlatformNotification.objects.filter(pk=made[0].pk, user=operator).exists()
        rows = list(EmailOutbox.objects.all())
    assert len(rows) == 1
    row = rows[0]
    assert row.tenant_id is None
    assert row.recipient == "o.synthetic@example.test"
    assert row.sender == platform.address
    assert row.status == Status.QUEUED
    assert row.notification_id == made[0].pk


def test_links_use_the_default_host(settings: Any) -> None:
    from mail import services as mail
    from tenancy.models import PlatformHost, Tenant, TenantDomain

    with_domain = Tenant.objects.create(name="Перша синтетична організація", actor_kind="system")
    TenantDomain.objects.create(
        tenant=with_domain, host="other.example.test", is_default=False, actor_kind="system"
    )
    TenantDomain.objects.create(
        tenant=with_domain, host="docs.example.test", is_default=True, actor_kind="system"
    )
    without = Tenant.objects.create(name="Друга синтетична організація", actor_kind="system")
    platform = PlatformHost.objects.filter(is_default=True).first()
    if platform is None:
        platform = PlatformHost.objects.create(
            host="platform.example.test", is_default=True, actor_kind="system"
        )

    settings.SITE_HTTPS = True
    assert mail.link(with_domain, "/document/7/") == "https://docs.example.test/document/7/"
    assert mail.link(without, "/document/7/") == f"https://{platform.host}/document/7/"
    assert mail.link(None, "/document/7/") == f"https://{platform.host}/document/7/"

    settings.SITE_HTTPS = False
    assert mail.link(with_domain, "/document/7/") == "http://docs.example.test/document/7/"


def test_no_email_names_a_document_its_recipient_cannot_open(
    migrated_tenant: Any, member_of: Any, make_document: Any, sender: Any
) -> None:
    """DL-0386 by email as on the page: a notification about a document its person cannot open
    queues nothing."""
    from mail.models import EmailOutbox
    from notifications.models import Category, Event
    from notifications.services import notify

    sender(migrated_tenant.number)
    _, outsider, _ = member_of("outsider.synthetic@example.test")
    _, creator, _ = member_of("creator.synthetic@example.test")
    document = make_document(title="Синтетичне закрите положення", created_by=creator)
    with schema_context(migrated_tenant.number):
        notify(users=[outsider], category=Category.DOCUMENT, event=Event.FROZEN, document=document)
        notify(users=[creator], category=Category.DOCUMENT, event=Event.FROZEN, document=document)
        assert list(EmailOutbox.objects.values_list("recipient", flat=True)) == [
            "creator.synthetic@example.test"
        ]


def test_the_version_author_is_named_only_where_a_version_awaits_review(
    migrated_tenant: Any, cast: Any, commit_version: Any
) -> None:
    from mail import services as mail
    from notifications.models import Category, Event
    from notifications.services import notify

    people, version, number = committed(migrated_tenant, cast, commit_version)
    with schema_context(migrated_tenant.number):
        [frozen] = notify(
            users=[people["r1"]],
            category=Category.DOCUMENT,
            event=Event.MADE_CANONICAL,
            actor=people["a"],
            document=people.document,
            version=version,
            facts={"edition": "1.0"},
        )
        [waiting] = tell_reviewers(people, version, number)[:1]
        assert AUTHOR not in mail.compose(frozen)[1]
        assert AUTHOR in mail.compose(waiting)[1]


def test_an_email_without_a_notification_is_sent_as_queued(
    migrated_tenant: Any, sender: Any, sink: Any
) -> None:
    """An invitation's or a reset's email carries no notification; it is queued and sent as any
    other, never withheld for a notification it never had."""
    from mail import services as mail
    from mail.models import EmailOutbox, Status
    from mail.tasks import send_outbox

    sender(migrated_tenant.number)
    with schema_context(migrated_tenant.number):
        row = mail.queue(
            migrated_tenant, "i.synthetic@example.test", "Синтетична тема", "Синтетичний лист.\n"
        )
        assert row is not None and row.notification_id is None

    send_outbox(now=row.next_attempt_at)

    with schema_context(migrated_tenant.number):
        row = EmailOutbox.objects.get(pk=row.pk)
    assert row.status == Status.SENT
    assert [message.rcpt_tos for message in sink.messages] == [["i.synthetic@example.test"]]
