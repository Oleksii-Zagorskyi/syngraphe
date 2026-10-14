"""The quiet hold (ADR-0006, DL-0377): a hold idle past its organisation's timeout is prompted
through the editor's heartbeat and its holder told once per idle spell; still idle ten minutes later
it is released for inactivity, its draft kept; a reserved hold is left alone.

People, organisations and texts are synthetic examples; the texts are invented."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

import pytest
from django.test import Client

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

TEXT = "\nСинтетичне речення, вигадане для перевірки.\n"


def post(client: Any, document: Any, route: str, **body: Any) -> Any:
    return client.post(
        f"/document/{document.number}/edit/{route}/",
        data=json.dumps(body),
        content_type="application/json",
    )


def opened(member_of: Any, new_document: Any) -> tuple[Any, Any, Any, dict[str, Any]]:
    """A hold taken by its author with one editor open on its draft."""
    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
    loaded = client.post(f"/document/{document.number}/edit/load/").json()
    return client, author, document, loaded


def idle_for(tenant: Any, document: Any, minutes: int) -> Any:
    """The document's open hold, its last activity set `minutes` ago."""
    from django.utils import timezone

    from editing.models import Hold

    with schema_context(tenant.number):
        Hold.objects.filter(document=document, released_at__isnull=True).update(
            last_activity_at=timezone.now() - timedelta(minutes=minutes)
        )
        return Hold.objects.get(document=document, released_at__isnull=True)


def told(tenant: Any, event: str = "hold_expiring") -> list[Any]:
    from notifications.models import Notification

    with schema_context(tenant.number):
        return list(Notification.objects.filter(event=event).order_by("created_at"))


def test_prompt_before_release(migrated_tenant: Any, member_of: Any, new_document: Any) -> None:
    """Past the timeout and inside the grace period: prompted, told once, still held."""
    from django.utils import timezone

    from editing import tasks

    client, holder, document, loaded = opened(member_of, new_document)
    hold = idle_for(migrated_tenant, document, 31)

    beat = post(client, document, "heartbeat", editor=loaded["editor"])
    assert beat.status_code == 200
    assert beat.json()["prompt"] is True
    assert tasks.release_inactive_holds() == 0
    assert tasks.release_inactive_holds() == 0

    [notification] = told(migrated_tenant)
    assert notification.category == "document"
    assert notification.user_id == holder.pk
    assert notification.document_id == document.pk
    assert notification.facts["hold"] == str(hold.pk)
    with schema_context(migrated_tenant.number):
        hold.refresh_from_db()
    assert hold.released_at is None

    # *Still working*: the active heartbeat restarts the clock and ends the prompt.
    active = post(client, document, "heartbeat", editor=loaded["editor"], active=True)
    assert active.status_code == 200
    assert active.json()["prompt"] is False
    with schema_context(migrated_tenant.number):
        hold.refresh_from_db()
    assert timezone.now() - hold.last_activity_at < timedelta(seconds=10)


def test_one_notification_per_idle_spell(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    from django.utils import timezone

    from editing import tasks
    from editing.models import Hold

    _, _, document, _ = opened(member_of, new_document)
    idle_for(migrated_tenant, document, 31)
    tasks.release_inactive_holds()
    assert len(told(migrated_tenant)) == 1

    # Active again, as an active heartbeat leaves it; then idle again.
    with schema_context(migrated_tenant.number):
        Hold.objects.filter(document=document, released_at__isnull=True).update(
            last_activity_at=timezone.now()
        )
    tasks.release_inactive_holds()
    assert len(told(migrated_tenant)) == 1
    idle_for(migrated_tenant, document, 31)

    tasks.release_inactive_holds()

    assert len(told(migrated_tenant)) == 2


def test_release_after_the_grace_period(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    from audit.models import AuditEvent
    from documents import holds as document_holds
    from editing import tasks
    from editing.models import Draft

    client, _, document, loaded = opened(member_of, new_document)
    written = loaded["body"] + TEXT
    captured = post(
        client,
        document,
        "capture",
        editor=loaded["editor"],
        base_hash=loaded["base_hash"],
        body=written,
    )
    assert captured.status_code == 200
    hold = idle_for(migrated_tenant, document, 41)

    assert tasks.release_inactive_holds() == 1

    with schema_context(migrated_tenant.number):
        hold.refresh_from_db()
        assert Draft.objects.get(hold=hold).content["document.md"] == written
        assert not document_holds.is_held(document)
    assert hold.released_at is not None
    assert hold.release_kind == "inactivity"
    assert hold.released_by_id is None
    [event] = AuditEvent.objects.filter(action="document.hold_released")
    assert event.actor_kind == "system"
    assert event.after["release_kind"] == "inactivity"
    assert tasks.release_inactive_holds.name == "editing.release_inactive_holds"


def test_reserved_holds_are_left_alone(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    from django.utils import timezone

    from editing import tasks
    from editing.models import Hold

    client, _, document, loaded = opened(member_of, new_document)
    with schema_context(migrated_tenant.number):
        Hold.objects.filter(document=document, released_at__isnull=True).update(
            reserved_at=timezone.now(), last_activity_at=timezone.now() - timedelta(days=3)
        )

    beat = post(client, document, "heartbeat", editor=loaded["editor"])
    assert beat.status_code == 200
    assert beat.json()["prompt"] is False
    assert tasks.release_inactive_holds() == 0

    assert told(migrated_tenant) == []
    with schema_context(migrated_tenant.number):
        hold = Hold.objects.get(document=document)
    assert hold.released_at is None


def member_in(tenant: Any, email: str) -> tuple[Client, Any]:
    """A client signed in as a member of `tenant`, that organisation chosen in its session."""
    from identity.models import Membership, User

    user = User.objects.create_user(email, "test-only-not-a-password")
    Membership.objects.create(tenant=tenant, user=user, actor_kind="system")
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(user)
    session = client.session
    session["tenant_number"] = tenant.number
    session.save()
    return client, user


def document_in(tenant: Any, user: Any) -> Any:
    """A document created through the service in `tenant`'s root folder."""
    from documents import services
    from documents.models import DocumentType, Folder
    from identity.models import Language

    Language.objects.get_or_create(code="uk", defaults={"label": "uk", "actor_kind": "system"})
    with schema_context(tenant.number):
        return services.create_document(
            user,
            "Синтетичний порядок чергувань",
            "uk",
            DocumentType.objects.get(code="document"),
            Folder.objects.get(number=1),
        )


def test_timeout_per_organisation(make_tenant_schema: Any, repo_root: Any) -> None:
    from tenancy.models import Tenant

    prompts = {}
    for name, minutes, email in (
        ("Синтетична організація перша", 10, "first.author@example.test"),
        ("Синтетична організація друга", 30, "second.author@example.test"),
    ):
        tenant = make_tenant_schema(name)
        Tenant.objects.filter(pk=tenant.pk).update(hold_inactivity_minutes=minutes)
        client, user = member_in(tenant, email)
        document = document_in(tenant, user)
        assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
        loaded = client.post(f"/document/{document.number}/edit/load/").json()
        idle_for(tenant, document, 20)
        beat = post(client, document, "heartbeat", editor=loaded["editor"])
        assert beat.status_code == 200
        prompts[minutes] = beat.json()["prompt"]

    assert prompts == {10: True, 30: False}


def test_the_answer_counts_only_while_asked(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    """*I am still working* answers the prompt: an `active` heartbeat while the hold is not idle
    restarts nothing, so no client keeps an ordinary hold for good without the right to
    reserve (ADR-0009)."""
    client, _, document, loaded = opened(member_of, new_document)
    before = idle_for(migrated_tenant, document, 5).last_activity_at
    answered = post(client, document, "heartbeat", editor=loaded["editor"], active=True)
    assert answered.status_code == 200 and answered.json()["prompt"] is False
    from editing.models import Hold

    with schema_context(migrated_tenant.number):
        assert Hold.objects.get(document=document).last_activity_at == before
    idle_for(migrated_tenant, document, 31)
    answered = post(client, document, "heartbeat", editor=loaded["editor"], active=True)
    assert answered.json()["prompt"] is False
    with schema_context(migrated_tenant.number):
        assert Hold.objects.get(document=document).last_activity_at > before


def test_one_hold_that_fails_leaves_the_others_released(
    migrated_tenant: Any, member_of: Any, new_document: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A hold whose release raises is logged and left for the next visit; the other idle holds
    are released all the same."""
    from editing import services
    from editing.models import Hold
    from editing.tasks import release_inactive_holds

    _, _, first, _ = opened(member_of, new_document)
    other_client, other, _ = member_of("another.author@example.test")
    second = new_document(other)
    assert other_client.post(f"/document/{second.number}/edit/take/").status_code == 200
    failing = idle_for(migrated_tenant, first, 41)
    idle_for(migrated_tenant, second, 41)
    real = services.finish_stopped

    def finish_stopped(hold: Any, **given: Any) -> bool:
        if hold.pk == failing.pk:
            raise RuntimeError("a synthetic failure")
        return real(hold, **given)

    monkeypatch.setattr(services, "finish_stopped", finish_stopped)
    assert release_inactive_holds() == 1
    with schema_context(migrated_tenant.number):
        assert Hold.objects.get(pk=failing.pk).released_at is None
        assert Hold.objects.get(document=second).release_kind == "inactivity"


def test_one_organisation_that_fails_leaves_the_others_visited(
    migrated_tenant: Any, member_of: Any, new_document: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An organisation whose visit raises is logged; the next one's idle holds are released."""
    from editing import tasks
    from editing.models import Hold
    from tenancy.models import Tenant

    _, _, document, _ = opened(member_of, new_document)
    idle_for(migrated_tenant, document, 41)
    failing = Tenant.objects.create(name="Синтетична несправна організація", actor_kind="system")
    real = tasks._quiet_holds

    def quiet_holds(tenant: Any) -> int:
        if tenant.pk == failing.pk:
            raise ValueError("a synthetic failure")
        return real(tenant)

    monkeypatch.setattr(tasks, "_quiet_holds", quiet_holds)
    import tenancy.models

    monkeypatch.setattr(
        tenancy.models, "visited_by_background_work", lambda: [failing, migrated_tenant]
    )
    assert tasks.release_inactive_holds() == 1
    with schema_context(migrated_tenant.number):
        assert Hold.objects.get(document=document).release_kind == "inactivity"


def test_a_holder_active_again_is_not_told(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    """The notice is decided on the hold as it stands, read under its row's lock: a holder who
    became active since the visit listed the hold is not told their editing will end."""
    from django.utils import timezone

    from editing import tasks
    from editing.models import Hold

    _, _, document, _ = opened(member_of, new_document)
    listed = idle_for(migrated_tenant, document, 31)
    with schema_context(migrated_tenant.number):
        Hold.objects.filter(pk=listed.pk).update(last_activity_at=timezone.now())
        tasks._tell_once(listed)
    assert told(migrated_tenant) == []


def test_the_notice_takes_the_documents_lock_first(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    """The notice locks the document's row before the hold's, as every writer of a hold does: while
    a writer holds the document, the hold stays free for that writer, never deadlocked."""
    import threading

    from django.db import connection, transaction

    from documents.models import Document
    from editing import tasks
    from editing.models import Hold

    _, _, document, _ = opened(member_of, new_document)
    listed = idle_for(migrated_tenant, document, 31)
    holding, release = threading.Event(), threading.Event()

    def writer() -> None:
        try:
            with schema_context(migrated_tenant.number), transaction.atomic():
                Document.objects.select_for_update().get(pk=document.pk)
                holding.set()
                release.wait(timeout=30)
        finally:
            connection.close()

    def tell() -> None:
        try:
            with schema_context(migrated_tenant.number):
                tasks._tell_once(listed)
        finally:
            connection.close()

    first = threading.Thread(target=writer)
    first.start()
    assert holding.wait(timeout=30)
    second = threading.Thread(target=tell)
    second.start()
    second.join(timeout=1)
    try:
        with schema_context(migrated_tenant.number), transaction.atomic():
            # The hold is not taken while the notice waits for the document.
            Hold.objects.select_for_update(nowait=True).get(pk=listed.pk)
    finally:
        release.set()
        first.join(timeout=30)
        second.join(timeout=30)
    assert len(told(migrated_tenant)) == 1
