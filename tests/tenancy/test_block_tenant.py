"""An organisation blocked and its block lifted (ST-0065, ST-0071, DL-0256, DL-0291): a platform
administrator blocks an active organisation from the organisations page — its state and history
row, every open hold in it ended with the drafts kept, audited — and lifts it, every membership,
group and link applying as it stood; an organisation being set up offers no act; the block and its
releases are one transaction.

People, organisations, groups and texts are synthetic examples."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest
from django.test import Client

from tenancy.schemas import schema_context

_spec = importlib.util.spec_from_file_location(
    "tenancy_editing_fixtures", Path(__file__).resolve().parents[1] / "editing" / "conftest.py"
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
]

PAGE = "/administration/platform/tenants/"


def _with_an_edit(tenant: int, document: Any) -> None:
    """The open hold's draft given an edit: a hold with no edits keeps nothing when it ends."""
    from editing.models import Draft

    with schema_context(tenant):
        draft = Draft.objects.get(hold__document=document, hold__released_at__isnull=True)
        body = draft.content["document.md"] + "\nAn invented sentence kept in the draft.\n"
        draft.content = {**draft.content, "document.md": body}
        draft.save()


def _held(tenant: Any, member_of: Any, new_document: Any, link_group: Any, email: str) -> Any:
    from access.rights import Right
    from editing import holds

    _, editor, membership = member_of(email)
    document = new_document(editor)
    link_group(document, [Right.EDIT], [membership], editor)
    with schema_context(tenant.number):
        hold = holds.take(document, editor)
    _with_an_edit(tenant.number, document)
    return hold


def _platform(email: str = "p.admin@example.test") -> tuple[Client, Any]:
    from identity.models import User

    user = User.objects.create_user(email, "Tr4vel-Plan-Ok", is_platform_admin=True)
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(user)
    return client, user


def test_block_ends_every_hold(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    from audit.models import AuditEvent
    from editing.models import Draft, Hold
    from tenancy.models import TenantStateHistory

    first = _held(migrated_tenant, member_of, new_document, link_group, "a.synthetic@example.test")
    second = _held(migrated_tenant, member_of, new_document, link_group, "b.synthetic@example.test")
    client, admin = _platform()

    page = client.get(f"{PAGE}{migrated_tenant.number}/block/")
    done = client.post(f"{PAGE}{migrated_tenant.number}/block/")

    assert page.status_code == 200
    assert done.status_code == 302 and done["Location"] == PAGE
    migrated_tenant.refresh_from_db()
    assert migrated_tenant.state == "blocked"
    [history] = TenantStateHistory.objects.filter(tenant=migrated_tenant, after="blocked")
    assert (history.before, history.by_id) == ("active", admin.pk)
    with schema_context(migrated_tenant.number):
        for hold in (first, second):
            hold = Hold.objects.get(pk=hold.pk)
            assert hold.released_at is not None and hold.release_kind == "blocked"
            assert hold.released_by_id == admin.pk
            assert Draft.objects.filter(hold=hold).exists()
    assert AuditEvent.objects.filter(action="tenant.blocked").count() == 1
    assert AuditEvent.objects.filter(action="document.hold_released").count() == 2


def test_lift_restores_as_it_stood(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    from access.rights import Right, rights_on
    from audit.models import AuditEvent
    from tenancy.models import TenantStateHistory

    _, member, membership = member_of("m.synthetic@example.test")
    document = new_document(member)
    link_group(document, [Right.EDIT], [membership], member)
    with schema_context(migrated_tenant.number):
        before = rights_on(member, document)
    client, _ = _platform()

    client.post(f"{PAGE}{migrated_tenant.number}/block/")
    with schema_context(migrated_tenant.number):
        blocked = rights_on(member, document)
    lifted = client.post(f"{PAGE}{migrated_tenant.number}/lift/")

    assert lifted.status_code == 302 and lifted["Location"] == PAGE
    migrated_tenant.refresh_from_db()
    assert migrated_tenant.state == "active"
    assert blocked == frozenset()
    with schema_context(migrated_tenant.number):
        assert rights_on(member, document) == before != frozenset()
    assert TenantStateHistory.objects.filter(
        tenant=migrated_tenant, before="blocked", after="active"
    ).exists()
    assert AuditEvent.objects.filter(action="tenant.block_lifted").count() == 1


def test_no_act_on_a_migrating_organisation(migrated_tenant: Any) -> None:
    from tenancy.models import Tenant

    setting_up = Tenant.objects.create(
        name="Synthetic, being set up", state="migrating", actor_kind="system"
    )
    client, _ = _platform()

    page = client.get(PAGE).content.decode()

    row = page.split(setting_up.name, 1)[1].split("</tr>", 1)[0]
    assert f"/{setting_up.number}/" not in row
    for act in ("block", "lift", "appoint"):
        assert client.post(f"{PAGE}{setting_up.number}/{act}/").status_code == 404
    setting_up.refresh_from_db()
    assert setting_up.state == "migrating"


@pytest.mark.crash
def test_block_is_one_transaction(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, monkeypatch: Any
) -> None:
    """Stopped after the holds' releases, at its own audit: the state, its history and every
    release roll back together."""
    from audit import record as audit_record
    from editing.models import Hold
    from tenancy import services
    from tenancy.models import TenantStateHistory

    hold = _held(migrated_tenant, member_of, new_document, link_group, "a.synthetic@example.test")
    _, admin = _platform()
    original = audit_record.record

    def stop_at_the_block(*args: Any, **kwargs: Any) -> Any:
        if kwargs.get("action") == "tenant.blocked":
            raise RuntimeError("a synthetic failure")
        return original(*args, **kwargs)

    monkeypatch.setattr("tenancy.services.record", stop_at_the_block)
    with pytest.raises(RuntimeError):
        services.block_tenant(migrated_tenant, by=admin)

    migrated_tenant.refresh_from_db()
    assert migrated_tenant.state == "active"
    assert not TenantStateHistory.objects.filter(tenant=migrated_tenant, after="blocked").exists()
    with schema_context(migrated_tenant.number):
        assert Hold.objects.get(pk=hold.pk).released_at is None


def test_a_busy_document_refuses_the_block(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    monkeypatch: Any,
    settings: Any,
) -> None:
    import threading

    from django.db import connection

    from documents.locks import document_lock
    from editing.models import Hold
    from tenancy.models import TenantStateHistory

    hold = _held(migrated_tenant, member_of, new_document, link_group, "a.synthetic@example.test")
    with schema_context(migrated_tenant.number):
        number = Hold.objects.get(pk=hold.pk).document.number
    settings.LANGUAGE_CODE = "en"
    client, _ = _platform()
    monkeypatch.setattr("editing.holds.LOCK_WAIT_SECONDS", 0.2)
    held, done = threading.Event(), threading.Event()

    def hold_the_lock() -> None:
        try:
            with document_lock(migrated_tenant.number, number):
                held.set()
                done.wait(timeout=30)
        finally:
            connection.close()

    other = threading.Thread(target=hold_the_lock)
    other.start()
    assert held.wait(timeout=30)
    try:
        answer = client.post(f"{PAGE}{migrated_tenant.number}/block/")
    finally:
        done.set()
        other.join(timeout=30)

    assert answer.status_code == 200
    assert "A document is being worked on. Try again in a moment." in answer.content.decode()
    migrated_tenant.refresh_from_db()
    assert migrated_tenant.state == "active"
    assert not TenantStateHistory.objects.filter(tenant=migrated_tenant, after="blocked").exists()
    with schema_context(migrated_tenant.number):
        assert Hold.objects.get(pk=hold.pk).released_at is None


def test_a_hold_cannot_be_taken_while_the_organisation_is_blocked(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, monkeypatch: Any
) -> None:
    """The block holds the organisation's row until it commits; a take waits for it, then sees
    the organisation blocked (DL-0256: no hold outlives a block)."""
    import threading

    from django.db import connection

    import identity.blocking
    from access.rights import Right
    from editing import holds
    from tenancy import services

    _, editor, membership = member_of("a.synthetic@example.test")
    document = new_document(editor)
    link_group(document, [Right.EDIT], [membership], editor)
    _, admin = _platform()
    in_block, release = threading.Event(), threading.Event()
    original = identity.blocking.end_holds

    def end_holds_slowly(*args: Any, **kwargs: Any) -> int:
        in_block.set()
        release.wait(timeout=30)
        return original(*args, **kwargs)

    monkeypatch.setattr("identity.blocking.end_holds", end_holds_slowly)

    def blocking_in_progress() -> None:
        try:
            services.block_tenant(migrated_tenant, by=admin)
        finally:
            connection.close()

    other = threading.Thread(target=blocking_in_progress)
    other.start()
    assert in_block.wait(timeout=30)
    outcome: list[Any] = []

    def take() -> None:
        try:
            with schema_context(migrated_tenant.number):
                outcome.append(holds.take(document, editor))
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

    assert still_waiting
    assert len(outcome) == 1 and isinstance(outcome[0], holds.NotEditable)


def test_the_acts_are_closed_to_everyone_else(
    migrated_tenant: Any, member_of: Any, make_tenant_schema: Any
) -> None:
    """Block, lift and appoint answer a tenant administrator, and a platform administrator on an
    organisation's own domain, as a missing page; nothing changes."""
    from identity.models import User
    from tenancy.middleware import invalidate_host_cache
    from tenancy.models import Tenant, TenantDomain

    blocked = make_tenant_schema("Synthetic blocked")
    Tenant.objects.filter(pk=blocked.pk).update(state="blocked")
    admin, _, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    platform = User.objects.create_user(
        "p.admin@example.test", "Tr4vel-Plan-Ok", is_platform_admin=True
    )
    TenantDomain.objects.create(
        tenant=migrated_tenant, host="docs.example.test", is_default=True, actor_kind="system"
    )
    invalidate_host_cache()
    on_domain = Client(headers={"host": "docs.example.test"})
    on_domain.force_login(platform)

    for client in (admin, on_domain):
        for act, number in (
            ("block", migrated_tenant.number),
            ("appoint", migrated_tenant.number),
            ("lift", blocked.number),
        ):
            assert client.get(f"{PAGE}{number}/{act}/").status_code == 404
            assert client.post(f"{PAGE}{number}/{act}/").status_code == 404
    states = dict(Tenant.objects.values_list("pk", "state"))
    assert states[migrated_tenant.pk] == "active" and states[blocked.pk] == "blocked"
