"""A person's own block (ST-0066, DL-0254, DL-0256, DL-0308, DL-0315): from the user menu,
confirmed, it closes every organisation and ends every hold the person has, drafts kept and no
releaser named; the person still signs in and reaches nothing, the platform role included; the
last platform administrator's own block is refused; the act is one transaction.

People, organisations and texts are synthetic examples; every address ends in `@example.test`."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest
from django.test import Client

from tenancy.schemas import schema_context

_spec = importlib.util.spec_from_file_location(
    "self_block_editing_fixtures", Path(__file__).resolve().parents[1] / "editing" / "conftest.py"
)
assert _spec is not None and _spec.loader is not None
_editing = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _editing
_spec.loader.exec_module(_editing)

# The editing tests' fixtures: a document with its repository, and a group linked to it.
new_document = _editing.new_document
link_group = _editing.link_group

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
    pytest.mark.usefixtures("in_english"),
]

BLOCK = "/account/block/"
LAST = "The last platform administrator cannot block their own account."
PASSWORD = "test-only-not-a-password"


def _with_an_edit(tenant: int, document: Any) -> None:
    """The open hold's draft given an edit: a hold with no edits keeps nothing when it ends."""
    from editing.models import Draft

    with schema_context(tenant):
        draft = Draft.objects.get(hold__document=document, hold__released_at__isnull=True)
        body = draft.content["document.md"] + "\nAn invented sentence kept in the draft.\n"
        draft.content = {**draft.content, "document.md": body}
        draft.save()


def _document_held(tenant: Any, author: Any, user: Any, membership: Any, title: str) -> Any:
    """A document in `tenant` whose group gives `user` *edit*, and the hold `user` took on it."""
    from access.models import AccessGroup, DocumentGroup
    from access.rights import Right
    from documents import services
    from documents.models import DocumentType, Folder
    from editing import holds
    from identity.models import Language

    Language.objects.get_or_create(code="uk", defaults={"label": "uk", "actor_kind": "system"})
    with schema_context(tenant.number):
        document = services.create_document(
            author,
            title,
            "uk",
            DocumentType.objects.get(code="document"),
            Folder.objects.get(number=1),
        )
        group = AccessGroup.objects.create(
            name=f"Editors {title}", created_by=author, actor_kind="user"
        )
        group.grant(Right.EDIT, by=author)
        group.add_member(membership, by=author)
        DocumentGroup.link(document, group, by=author)
        hold = holds.take(document, user)
    _with_an_edit(tenant.number, document)
    return hold


def test_self_block_closes_every_organisation(
    migrated_tenant: Any, make_tenant_schema: Any, repo_root: Any
) -> None:
    from audit.models import AuditEvent
    from editing.models import Draft, Hold
    from identity.models import AccountBlockHistory, Membership, User

    other = make_tenant_schema("Another synthetic organisation")
    person = User.objects.create_user("the.person@example.test", PASSWORD)
    author = User.objects.create_user("the.author@example.test", PASSWORD)
    holds = []
    for tenant in (migrated_tenant, other):
        mine = Membership.objects.create(tenant=tenant, user=person, actor_kind="system")
        Membership.objects.create(tenant=tenant, user=author, actor_kind="system")
        holds.append(
            (tenant, _document_held(tenant, author, person, mine, f"Synthetic {tenant.number}"))
        )
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(person)

    page = client.get(BLOCK)
    done = client.post(BLOCK)

    assert page.status_code == 200
    assert done.status_code == 302
    person.refresh_from_db()
    assert person.self_blocked
    [history] = AccountBlockHistory.objects.filter(user=person)
    assert (history.action, history.by_id) == ("self_blocked", person.pk)
    for tenant, hold in holds:
        with schema_context(tenant.number):
            hold = Hold.objects.get(pk=hold.pk)
            assert hold.released_at is not None and hold.release_kind == "blocked"
            assert hold.released_by_id is None
            assert Draft.objects.filter(hold=hold).exists()
    released = AuditEvent.objects.filter(action="document.hold_released")
    assert {event.actor_id for event in released} == {person.pk} and released.count() == 2
    assert AuditEvent.objects.filter(action="user.self_blocked", actor=person).count() == 1
    # Signed out; signing in still works, and every page answers as to a non-member.
    assert "_auth_user_id" not in client.session
    signed_in = client.post("/signin/", {"email": person.email, "password": PASSWORD})
    assert signed_in.status_code == 302
    for tenant, hold in holds:
        session = client.session
        session["tenant_number"] = tenant.number
        session.save()
        with schema_context(tenant.number):
            number = Hold.objects.get(pk=hold.pk).document.number
        for page in (
            "/",
            "/folder/1/",
            f"/document/{number}/",
            "/notifications/",
            "/administration/",
        ):
            assert client.get(page).status_code == 404, page
    # Nothing to offer the person again.
    assert client.get(BLOCK).status_code == 404


def test_last_platform_administrator_is_refused(migrated_tenant: Any) -> None:
    from identity.models import AccountBlockHistory, User

    admin = User.objects.create_user("p.admin@example.test", PASSWORD, is_platform_admin=True)
    # A self-blocked one does not count (DL-0315).
    User.objects.create_user(
        "p.blocked@example.test", PASSWORD, is_platform_admin=True, self_blocked=True
    )
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(admin)

    page = client.get(BLOCK).content.decode()
    refused = client.post(BLOCK)

    assert LAST in page and 'aria-disabled="true"' in page
    assert refused.status_code == 200 and LAST in refused.content.decode()
    admin.refresh_from_db()
    assert not admin.self_blocked
    assert not AccountBlockHistory.objects.exists()


def test_platform_role_closes_too(migrated_tenant: Any) -> None:
    from identity.models import User

    User.objects.create_user("p.other@example.test", PASSWORD, is_platform_admin=True)
    admin = User.objects.create_user("p.admin@example.test", PASSWORD, is_platform_admin=True)
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(admin)

    assert client.post(BLOCK).status_code == 302
    client.force_login(admin)

    assert client.get("/administration/").status_code == 404
    assert client.get("/administration/platform/tenants/").status_code == 404


@pytest.mark.crash
def test_self_block_is_one_transaction(
    migrated_tenant: Any, repo_root: Any, monkeypatch: Any
) -> None:
    from editing.models import Hold
    from identity import blocking
    from identity.models import AccountBlockHistory, Membership, User

    person = User.objects.create_user("the.person@example.test", PASSWORD)
    author = User.objects.create_user("the.author@example.test", PASSWORD)
    mine = Membership.objects.create(tenant=migrated_tenant, user=person, actor_kind="system")
    Membership.objects.create(tenant=migrated_tenant, user=author, actor_kind="system")
    hold = _document_held(migrated_tenant, author, person, mine, "Synthetic")

    def refuse(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("a synthetic failure")

    monkeypatch.setattr("identity.blocking.end_holds", refuse)
    with pytest.raises(RuntimeError):
        blocking.self_block(person)

    person.refresh_from_db()
    assert not person.self_blocked
    assert not AccountBlockHistory.objects.exists()
    with schema_context(migrated_tenant.number):
        assert Hold.objects.get(pk=hold.pk).released_at is None


def test_the_menu_opens_the_account_page(migrated_tenant: Any, member_of: Any) -> None:
    """The menu row's own name opens the account page, where the block now stands apart (DL-0499,
    DL-0500, DL-0525)."""
    client, _, _ = member_of("a.member@example.test")

    page = client.get("/folder/1/").content.decode()

    assert '<a class="account-link" href="/account/">a.member@example.test</a>' in page
    assert f'href="{BLOCK}"' not in page
    assert f'href="{BLOCK}"' in client.get("/account/").content.decode()
    assert 'href="/account/"' not in (
        Client(headers={"host": "127.0.0.1"}).get("/signin/").content.decode()
    )


def test_a_busy_document_keeps_the_form(migrated_tenant: Any, monkeypatch: Any) -> None:
    from identity import blocking
    from identity.models import User

    User.objects.create_user("p.admin@example.test", PASSWORD, is_platform_admin=True)
    person = User.objects.create_user("the.person@example.test", PASSWORD)
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(person)

    def busy(*args: Any, **kwargs: Any) -> None:
        raise blocking.BlockRefused("busy")

    monkeypatch.setattr("identity.blocking.end_holds", busy)
    answer = client.post(BLOCK).content.decode()

    assert "A document is being worked on. Try again in a moment." in answer
    assert LAST not in answer and "<form" in answer.split('class="dlg"', 1)[1]


@pytest.mark.parametrize("another_administrator", [False, True])
def test_the_platform_is_told_of_an_organisation_left_without_one(
    migrated_tenant: Any, another_administrator: bool
) -> None:
    from identity import blocking
    from identity.models import Membership, User
    from tenancy.models import PlatformNotification

    watcher = User.objects.create_user("p.admin@example.test", PASSWORD, is_platform_admin=True)
    person = User.objects.create_user("the.admin@example.test", PASSWORD)
    Membership.objects.create(
        tenant=migrated_tenant, user=person, is_tenant_admin=True, actor_kind="system"
    )
    if another_administrator:
        other = User.objects.create_user("other.admin@example.test", PASSWORD)
        Membership.objects.create(
            tenant=migrated_tenant, user=other, is_tenant_admin=True, actor_kind="system"
        )

    blocking.self_block(person)

    with schema_context(None):
        told = list(PlatformNotification.objects.filter(user=watcher).values_list("event", "facts"))
    expected = (
        []
        if another_administrator
        else [("tenant_without_admin", {"tenant": migrated_tenant.number})]
    )
    assert told == expected


def test_a_hold_cannot_be_taken_while_the_self_block_is_written(
    migrated_tenant: Any, repo_root: Any, monkeypatch: Any
) -> None:
    """The self-block holds the person's memberships until it commits; a take waits, then sees
    the block (DL-0256: no hold outlives a block)."""
    import threading

    from django.db import connection, transaction

    from editing import holds
    from editing.models import Hold
    from identity.models import Membership, User

    person = User.objects.create_user("the.person@example.test", PASSWORD)
    author = User.objects.create_user("the.author@example.test", PASSWORD)
    mine = Membership.objects.create(tenant=migrated_tenant, user=person, actor_kind="system")
    Membership.objects.create(tenant=migrated_tenant, user=author, actor_kind="system")
    held = _document_held(migrated_tenant, author, person, mine, "Synthetic first")
    with schema_context(migrated_tenant.number):
        Hold.objects.filter(pk=held.pk).update(
            released_at=held.acquired_at, release_kind="discarded"
        )
        document = Hold.objects.get(pk=held.pk).document
    in_block = threading.Event()
    release = threading.Event()

    def end_holds_slowly(*args: Any, **kwargs: Any) -> int:
        in_block.set()
        release.wait(timeout=30)
        return 0

    import identity.blocking

    monkeypatch.setattr("identity.blocking.end_holds", end_holds_slowly)

    def blocking_in_progress() -> None:
        try:
            identity.blocking.self_block(person)
        finally:
            connection.close()

    other = threading.Thread(target=blocking_in_progress)
    other.start()
    try:
        assert in_block.wait(timeout=30)
        outcome: list[Any] = []

        def take() -> None:
            try:
                with schema_context(migrated_tenant.number):
                    outcome.append(holds.take(document, person))
            except holds.NotEditable as refused:
                outcome.append(refused)
            finally:
                connection.close()

        taker = threading.Thread(target=take)
        taker.start()
        taker.join(timeout=1)
        still_waiting = taker.is_alive()
        release.set()
        other.join(timeout=30)
        taker.join(timeout=30)
    finally:
        release.set()

    assert still_waiting
    assert len(outcome) == 1 and isinstance(outcome[0], holds.NotEditable)
    with transaction.atomic():
        assert User.objects.get(pk=person.pk).self_blocked
