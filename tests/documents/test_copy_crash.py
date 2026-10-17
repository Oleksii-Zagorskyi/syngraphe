"""A copy that stopped (DL-0455): its source was recorded before any repository, so the reconciler
recognises it, reports it `copy_stopped` and never finishes it from the template; it stays
invisible, and an operator removes it by `remove_stopped_copy`.

Titles and people are synthetic examples."""

from __future__ import annotations

from datetime import timedelta
from io import StringIO
from typing import Any

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]


@pytest.fixture
def source(migrated_tenant: Any, member_of: Any, repo_root: Any) -> Any:
    """An active document its creator, who holds *create and edit*, may read: `(user, document)`."""
    from access.models import AccessGroup
    from access.rights import Right
    from documents import services
    from documents.models import DocumentType, Folder
    from identity.models import Language

    Language.objects.get_or_create(code="uk", defaults={"label": "uk", "actor_kind": "system"})
    _, user, membership = member_of("the.copier@example.test")
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(name="Creators", created_by=user, actor_kind="user")
        group.grant(Right.CREATE_AND_EDIT, by=user)
        group.add_member(membership, by=user)
        document = services.create_document(
            user,
            "Synthetic source",
            "uk",
            DocumentType.objects.get(code="document"),
            Folder.objects.get(number=1),
        )
    return user, document


def _stopped(migrated_tenant: Any, source: Any, step: int) -> Any:
    """A copy stopped after `step`, its row made an hour old: the grace is past."""
    from documents import copying
    from documents.models import Document, DocumentType, Folder

    user, document = source
    with schema_context(migrated_tenant.number):
        with pytest.raises(copying.CopyStopped):
            copying.copy_document(
                user,
                document,
                title="Synthetic copy",
                document_type=DocumentType.objects.get(code="document"),
                folder=Folder.objects.get(number=1),
                view="accepted",
                number="0.0",
                appendices=[],
                fault_at=step,
            )
        copy = Document.objects.exclude(pk=document.pk).get()
        Document.objects.filter(pk=copy.pk).update(created_at=timezone.now() - timedelta(hours=1))
        return copy


@pytest.mark.parametrize("step", [1, 2, 3, 4])
def test_a_stopped_copy_is_never_finished(
    migrated_tenant: Any, member_of: Any, source: Any, step: int
) -> None:
    from documents import reconcile
    from documents.models import Document

    copy = _stopped(migrated_tenant, source, step)
    user, _ = source

    report = reconcile.run(tenant=migrated_tenant.number)
    repaired = reconcile.run(tenant=migrated_tenant.number, repair=True)

    stopped = [(f.kind, f.document) for f in report if f.document == copy.number]
    assert stopped == [("copy_stopped", copy.number)]
    assert [f.kind for f in repaired if f.document == copy.number] == ["copy_stopped"]
    assert not any(f.repaired for f in repaired if f.document == copy.number)
    with schema_context(migrated_tenant.number):
        assert Document.objects.get(pk=copy.pk).state == "creating"
    # Invisible in every list, to an administrator too, and its address is nothing to show.
    admin, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    for path in ("/folder/1/", "/search/?q=Synthetic", "/in-edit/", "/in-review/"):
        assert f'href="/document/{copy.number}/"' not in admin.get(path).content.decode(), path
    assert admin.get(f"/document/{copy.number}/").status_code == 404


@pytest.mark.parametrize("step", [1, 4])
def test_the_operator_removes_a_stopped_copy(
    migrated_tenant: Any, member_of: Any, source: Any, step: int
) -> None:
    from audit.models import AuditEvent
    from documents import gitstore
    from documents.models import Document, HeadingIndex, PartIndex, Version

    copy = _stopped(migrated_tenant, source, step)

    out = StringIO()
    call_command(
        "remove_stopped_copy", tenant=migrated_tenant.number, document=copy.number, stdout=out
    )
    again = StringIO()
    call_command(
        "remove_stopped_copy", tenant=migrated_tenant.number, document=copy.number, stdout=again
    )

    assert not gitstore.repository_path(migrated_tenant.number, copy.number).exists()
    with schema_context(migrated_tenant.number):
        assert not Document.objects.filter(pk=copy.pk).exists()
        assert not Version.objects.filter(document_id=copy.pk).exists()
        assert not PartIndex.objects.filter(document_id=copy.pk).exists()
        assert not HeadingIndex.objects.filter(version__document_id=copy.pk).exists()
    (removed,) = AuditEvent.objects.filter(action="document.stopped_copy_removed")
    assert removed.after == {"number": copy.number} and removed.actor_id is None
    assert f"document {copy.number}" in out.getvalue()
    assert "nothing to remove" in again.getvalue()


def test_a_template_creation_is_never_removed_as_a_copy(
    migrated_tenant: Any, member_of: Any, repo_root: Any
) -> None:
    from documents import services
    from documents.models import Document, DocumentType, Folder
    from identity.models import Language

    Language.objects.get_or_create(code="uk", defaults={"label": "uk", "actor_kind": "system"})
    _, user, _ = member_of("an.author@example.test")
    with schema_context(migrated_tenant.number):
        with pytest.raises(services.InjectedFault):
            services.create_document(
                user,
                "Synthetic example",
                "uk",
                DocumentType.objects.get(code="document"),
                Folder.objects.get(number=1),
                fault_at=2,
            )
        document = Document.objects.get()
        Document.objects.filter(pk=document.pk).update(
            created_at=timezone.now() - timedelta(hours=1)
        )

    with pytest.raises(CommandError, match="not a stopped copy"):
        call_command("remove_stopped_copy", tenant=migrated_tenant.number, document=document.number)
    with schema_context(migrated_tenant.number):
        assert Document.objects.filter(pk=document.pk).exists()


def test_a_copy_finished_while_the_operator_waited_is_kept(
    migrated_tenant: Any, member_of: Any, source: Any, monkeypatch: Any
) -> None:
    """The copy's own process, slow but alive, finishes it while the command waits for its lock:
    the command reads the row again under the lock and refuses, the copy and its repository kept."""
    from contextlib import contextmanager

    from audit.models import AuditEvent
    from documents import gitstore, services
    from documents.management.commands import remove_stopped_copy as command
    from documents.models import Document, DocumentTemplate
    from notifications.models import Event

    copy = _stopped(migrated_tenant, source, 4)
    user, _ = source
    held = command.document_lock

    @contextmanager
    def finished_first(tenant: int, number: int) -> Any:
        with held(tenant, number):
            services.resume_creation(
                copy,
                migrated_tenant,
                DocumentTemplate.objects.get(),
                user,
                event=Event.DOCUMENT_COPIED,
            )
        with held(tenant, number):
            yield

    monkeypatch.setattr(command, "document_lock", finished_first)

    with pytest.raises(CommandError, match="not a stopped copy"):
        call_command("remove_stopped_copy", tenant=migrated_tenant.number, document=copy.number)

    assert gitstore.repository_path(migrated_tenant.number, copy.number).exists()
    with schema_context(migrated_tenant.number):
        assert Document.objects.get(pk=copy.pk).state == "active"
    assert not AuditEvent.objects.filter(action="document.stopped_copy_removed").exists()


def test_the_source_row_is_read_under_its_lock(
    migrated_tenant: Any, member_of: Any, source: Any, waiting_on_a_lock: Any
) -> None:
    """The copy reads its source's state and the copier's rights under the source's row lock, as
    archive and restore change them: a transaction holding that row makes the copy wait."""
    import threading

    from django.db import connection, transaction

    from documents import copying
    from documents.models import Document, DocumentType, Folder

    user, document = source
    held, release = threading.Event(), threading.Event()
    outcome: dict[str, Any] = {}

    def hold_the_row() -> None:
        try:
            with schema_context(migrated_tenant.number), transaction.atomic():
                # `NO KEY`: the copy's own row, naming its source, waits on nothing here; only
                # the source's row lock does.
                Document.objects.select_for_update(no_key=True, of=("self",)).get(pk=document.pk)
                held.set()
                release.wait(timeout=30)
        finally:
            connection.close()

    def copy() -> None:
        try:
            with schema_context(migrated_tenant.number):
                outcome["copy"] = copying.copy_document(
                    user,
                    document,
                    title="Synthetic copy",
                    document_type=DocumentType.objects.get(code="document"),
                    folder=Folder.objects.get(number=1),
                    view="accepted",
                    number="0.0",
                    appendices=[],
                ).number
        finally:
            connection.close()

    holder = threading.Thread(target=hold_the_row)
    holder.start()
    assert held.wait(timeout=10)
    copier = threading.Thread(target=copy)
    copier.start()
    waited = waiting_on_a_lock()
    release.set()
    holder.join(timeout=30)
    copier.join(timeout=30)

    assert waited
    assert "copy" in outcome


def test_the_operator_removes_a_copys_entities_and_images(
    migrated_tenant: Any, member_of: Any, source: Any
) -> None:
    """A copy stopped after its version was derived, from a source carrying an image and a marked
    entity: the copy's `ENTITY` and `IMAGE` rows exist, and `remove_stopped_copy` removes them
    with the rest."""
    import hashlib

    from documents import bundle, copying, gitstore, services
    from documents.identity import identity_for
    from documents.locks import document_lock
    from documents.models import Document, DocumentType, Entity, Folder, Image

    user, document = source
    picture = b"\x89PNG synthetic removed picture"
    path = f"images/{hashlib.sha256(picture).hexdigest()}.png"
    body = (
        "# Terms\n\n[The synthetic head]{.role #synthetic-head} approves it.\n\n"
        f"![A synthetic picture]({path})\n"
    )
    declared = "- kind: role\n  key: synthetic-head\n  label: Synthetic head\n"
    number = migrated_tenant.number
    with schema_context(number):
        repo = gitstore.open_repository(number, document.number)
        with document_lock(number, document.number):
            head = gitstore.head(repo)
            assert head is not None
            frontmatter, _ = bundle.parse(gitstore.read(repo, "document.md", head).decode())
            sha = gitstore.commit(
                repo,
                {
                    "document.md": bundle.render(frontmatter, body).encode(),
                    path: picture,
                    "entities.yaml": declared.encode(),
                },
                identity_for(user),
                "Synthetic edit",
                gitstore.Kind.EDIT,
            )
            services.derive_version(document, gitstore.commit_at(repo, sha), user)
        with pytest.raises(copying.CopyStopped):
            copying.copy_document(
                user,
                document,
                title="Synthetic copy",
                document_type=DocumentType.objects.get(code="document"),
                folder=Folder.objects.get(number=1),
                view="pending_edits",
                number="0.0-1",
                appendices=[],
                fault_at=4,
            )
        copy = Document.objects.exclude(pk=document.pk).get()
        Document.objects.filter(pk=copy.pk).update(created_at=timezone.now() - timedelta(hours=1))
        assert Entity.objects.filter(document=copy).exists()
        assert Image.objects.filter(document=copy).exists()

    call_command("remove_stopped_copy", tenant=number, document=copy.number, stdout=StringIO())

    with schema_context(number):
        assert not Entity.objects.filter(document_id=copy.pk).exists()
        assert not Image.objects.filter(document_id=copy.pk).exists()
        assert Entity.objects.filter(document=document).exists()
