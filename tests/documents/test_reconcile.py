"""The reconciler: git is the commit point and the rows are its cache; report first, repair what
is safe, delete a row only when told to (DL-0111)."""

from __future__ import annotations

import io
import os
import subprocess
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from django.core.management import call_command
from django.utils import timezone

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]


def _commit_by_hand(path: Path, message: str) -> str:
    """A commit written with the git binary, by someone the platform does not know."""
    env = {
        "GIT_AUTHOR_NAME": "operator",
        "GIT_AUTHOR_EMAIL": "operator@example.test",
        "GIT_COMMITTER_NAME": "operator",
        "GIT_COMMITTER_EMAIL": "operator@example.test",
        "PATH": os.environ["PATH"],
    }
    tree = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "main^{tree}"], capture_output=True, check=True
    ).stdout.strip()
    sha = subprocess.run(
        ["git", "-C", str(path), "commit-tree", tree, "-p", "main", "-m", message],
        capture_output=True,
        check=True,
        env=env,
    ).stdout.strip()
    subprocess.run(["git", "-C", str(path), "update-ref", "refs/heads/main", sha], check=True)
    return sha.decode()


def _edit(tenant: int, document: Any, user: Any, sentence: str) -> str:
    from documents import bundle, gitstore
    from documents.gitstore import Kind
    from documents.identity import identity_for
    from documents.locks import document_lock

    repo = gitstore.open_repository(tenant, document.number)
    text = gitstore.read(repo, "document.md", str(repo.head.target)).decode()
    frontmatter, body = bundle.parse(text)
    with document_lock(tenant, document.number):
        return gitstore.commit(
            repo,
            {"document.md": bundle.render(frontmatter, body + f"\n{sentence}\n").encode()},
            identity_for(user),
            "Edited",
            Kind.EDIT,
        )


@pytest.fixture
def created(migrated_tenant: Any, member_of: Any, repo_root: Path) -> Any:
    """A healthy document, created through the service; `(document, author)`."""
    from documents import services
    from documents.models import DocumentType, Folder
    from identity.models import Language

    Language.objects.get_or_create(code="uk", defaults={"label": "uk", "actor_kind": "system"})
    _, user, _ = member_of("an.author@example.test")
    with schema_context(migrated_tenant.number):
        document = services.create_document(
            user,
            "Synthetic example",
            "uk",
            DocumentType.objects.get(code="document"),
            Folder.objects.get(number=1),
        )
        _authored(migrated_tenant.number, document)
    return document, user


def _authored(tenant: int, document: Any) -> None:
    """The head's authorship written, as the worker writes it after a commit (DL-0326)."""
    from documents import gitstore
    from editing import authorship

    repo = gitstore.open_repository(tenant, document.number)
    head = gitstore.head(repo)
    assert head is not None
    authorship.compute(
        document, head, repository_path=gitstore.repository_path(tenant, document.number)
    )


def test_healthy_is_silent(migrated_tenant: Any, created: Any) -> None:
    from documents import reconcile

    out = io.StringIO()

    assert reconcile.run(tenant=migrated_tenant.number) == []
    call_command("reconcile", f"--tenant={migrated_tenant.number}", stdout=out)
    assert out.getvalue().strip() == "nothing to report"


def test_a_recreated_document_notifies_the_administrators(
    migrated_tenant: Any, created: Any, member_of: Any
) -> None:
    """Both administrators told of the recreated document, marked as recreated; the reconciler
    is the actor, so nobody is left out."""
    from documents import reconcile
    from documents.models import Document, HeadingIndex, Version
    from notifications.models import Notification

    document, _ = created
    _, first, _ = member_of("first.admin@example.test", is_tenant_admin=True)
    _, second, _ = member_of("second.admin@example.test", is_tenant_admin=True)
    with schema_context(migrated_tenant.number):
        Notification.objects.all().delete()
        HeadingIndex.objects.all().delete()
        Version.objects.all().delete()
        Document.objects.all().delete()

    reconcile.run(tenant=migrated_tenant.number, repair=True)

    with schema_context(migrated_tenant.number):
        told = list(Notification.objects.filter(event="document_created").order_by("user__email"))
        recreated = Document.objects.get(number=document.number)
    assert [row.user_id for row in told] == [first.pk, second.pk]
    assert all(row.document_id == recreated.pk for row in told)
    assert all(row.facts == {"recreated": True} for row in told)


def test_report_mode_exits_one_and_changes_nothing(migrated_tenant: Any, created: Any) -> None:
    from documents.models import Document

    document, _ = created
    with schema_context(migrated_tenant.number):
        Document.objects.filter(pk=document.pk).update(title="Changed by hand")

    with pytest.raises(SystemExit) as exit_:
        call_command("reconcile", f"--tenant={migrated_tenant.number}", stdout=io.StringIO())

    assert exit_.value.code == 1
    with schema_context(migrated_tenant.number):
        assert Document.objects.get(pk=document.pk).title == "Changed by hand"


def test_orphan_recreated_fail_closed(migrated_tenant: Any, created: Any) -> None:
    from access.models import DocumentGroup
    from audit.models import AuditEvent
    from documents import reconcile
    from documents.models import Document, HeadingIndex, Version, next_document_number

    document, user = created
    with schema_context(migrated_tenant.number):
        HeadingIndex.objects.all().delete()
        Version.objects.all().delete()
        Document.objects.all().delete()

    report = reconcile.run(tenant=migrated_tenant.number)
    repaired = reconcile.run(tenant=migrated_tenant.number, repair=True)

    assert [(f.kind, f.document) for f in report] == [("orphan_repository", document.number)]
    assert [(f.kind, f.repaired) for f in repaired] == [
        ("orphan_repository", True),
        ("commit_without_row", True),
    ]
    with schema_context(migrated_tenant.number):
        row = Document.objects.get(number=document.number)
        assert (row.title, row.language_id, row.author_only, row.state) == (
            "Synthetic example",
            "uk",
            False,
            "active",
        )
        assert row.created_by_id == user.id
        assert row.document_type.code == "document" and row.folder.number == 1
        assert not DocumentGroup.objects.filter(document=row).exists()
        assert Version.objects.filter(document=row).count() == 1
        # The next document never takes the recreated one's number, even from a sequence reset.
        assert next_document_number() > document.number
    events = list(AuditEvent.objects.filter(action="reconcile.orphan_repository"))
    assert len(events) == 1
    assert events[0].after["number"] == document.number
    assert events[0].after["document_type"] == "document"
    assert events[0].after["folder"] == 1
    # The recreated head's authorship went with its version row; the next run asks for it again.
    assert [f.kind for f in reconcile.run(tenant=migrated_tenant.number)] == ["authorship_missing"]
    with schema_context(migrated_tenant.number):
        _authored(migrated_tenant.number, Document.objects.get(number=document.number))
    assert reconcile.run(tenant=migrated_tenant.number) == []


def test_prune_rows_is_explicit(migrated_tenant: Any, created: Any) -> None:
    from datetime import UTC, datetime

    from documents import reconcile
    from documents.models import Version

    document, user = created
    missing = "0" * 40
    with schema_context(migrated_tenant.number):
        Version.objects.create(
            document=document,
            commit_sha=missing,
            author=user,
            summary="lost",
            kind="edit",
            committed_at=datetime(2026, 9, 1, tzinfo=UTC),
            actor_kind="system",
        )

    repaired = reconcile.run(tenant=migrated_tenant.number, repair=True)
    with schema_context(migrated_tenant.number):
        survived = Version.objects.filter(commit_sha=missing).exists()
    pruned = reconcile.run(tenant=migrated_tenant.number, repair=True, prune_rows=True)
    with schema_context(migrated_tenant.number):
        gone = not Version.objects.filter(commit_sha=missing).exists()

    assert [(f.kind, f.repaired) for f in repaired] == [("row_without_commit", False)]
    assert survived
    assert [(f.kind, f.repaired) for f in pruned] == [("row_without_commit", True)]
    assert gone


def test_a_pruned_version_takes_the_exports_that_name_it(
    migrated_tenant: Any, created: Any
) -> None:
    """An export job is a record of a download, not of the text: a version pruned after a restore
    takes the jobs that exported it or marked against it, counted in the audit."""
    from datetime import UTC, datetime

    from audit.models import AuditEvent
    from documents import reconcile
    from documents.models import Version
    from rendering.models import ExportJob

    document, user = created
    with schema_context(migrated_tenant.number):
        kept = Version.objects.filter(document=document).first()
        lost = Version.objects.create(
            document=document,
            commit_sha="0" * 40,
            author=user,
            summary="lost",
            kind="edit",
            committed_at=datetime(2026, 9, 1, tzinfo=UTC),
            actor_kind="system",
        )
        common = {"document": document, "include_document": True, "format": "pdf",
                  "view": "pending_edits", "requested_by": user}  # fmt: skip
        ExportJob.objects.create(version=lost, changes="clean", **common)
        ExportJob.objects.create(version=kept, changes="marked", baseline_version=lost, **common)
        ExportJob.objects.create(version=kept, changes="clean", **common)

    pruned = reconcile.run(tenant=migrated_tenant.number, repair=True, prune_rows=True)

    assert [(f.kind, f.repaired) for f in pruned] == [("row_without_commit", True)]
    with schema_context(migrated_tenant.number):
        assert not Version.objects.filter(commit_sha="0" * 40).exists()
        assert ExportJob.objects.count() == 1
    event = AuditEvent.objects.get(action="reconcile.row_without_commit")
    assert event.before["exports"] == 2
    assert reconcile.run(tenant=migrated_tenant.number) == []


def test_prune_rows_needs_repair() -> None:
    from documents import reconcile

    with pytest.raises(ValueError):
        reconcile.run(prune_rows=True)


def test_row_is_a_cache_of_the_file(migrated_tenant: Any, created: Any) -> None:
    from audit.models import AuditEvent
    from documents import reconcile
    from documents.models import Document

    document, _ = created
    with schema_context(migrated_tenant.number):
        Document.objects.filter(pk=document.pk).update(title="Changed by hand", language_id="uk")

    report = reconcile.run(tenant=migrated_tenant.number)
    reconcile.run(tenant=migrated_tenant.number, repair=True)

    assert [f.kind for f in report] == ["frontmatter_differs"]
    with schema_context(migrated_tenant.number):
        assert Document.objects.get(pk=document.pk).title == "Synthetic example"
    event = AuditEvent.objects.get(action="reconcile.frontmatter_differs")
    # Numbers and what changed, never a title.
    assert event.after == {"number": document.number, "language": "uk", "changed": ["title"]}
    assert "title" not in event.before


def test_commits_without_rows_are_replayed(migrated_tenant: Any, created: Any) -> None:
    from documents import bundle, gitstore, reconcile
    from documents.gitstore import Kind
    from documents.identity import identity_for
    from documents.locks import document_lock
    from documents.models import Version

    document, user = created
    repo = gitstore.open_repository(migrated_tenant.number, document.number)
    text = gitstore.read(repo, "document.md", str(repo.head.target)).decode()
    frontmatter, body = bundle.parse(text)
    with document_lock(migrated_tenant.number, document.number):
        sha = gitstore.commit(
            repo,
            {"document.md": bundle.render(frontmatter, body + "\nA new sentence.\n").encode()},
            identity_for(user),
            "Edited",
            Kind.EDIT,
        )

    report = reconcile.run(tenant=migrated_tenant.number)
    reconcile.run(tenant=migrated_tenant.number, repair=True)

    assert [(f.kind, f.detail) for f in report] == [("commit_without_row", sha)]
    with schema_context(migrated_tenant.number):
        version = Version.objects.get(commit_sha=sha)
    assert (version.kind, version.author_id, version.summary) == ("edit", user.id, "Edited")
    # The replayed edit's per-line authorship is asked of the worker; nothing else is left.
    assert [(f.kind, f.detail) for f in reconcile.run(tenant=migrated_tenant.number)] == [
        ("authorship_missing", sha)
    ]


def test_passport_entries_are_reported(migrated_tenant: Any, created: Any) -> None:
    from documents import gitstore, reconcile
    from documents.gitstore import Kind
    from documents.identity import identity_for
    from documents.locks import document_lock

    document, user = created
    repo = gitstore.open_repository(migrated_tenant.number, document.number)
    passport = gitstore.read(repo, "passport.md", str(repo.head.target)).decode()
    entry = f"\n## acceptance 1.1\n\nat: 2026-09-01T00:00:00Z\nby: {user.id}\nversion: x\n"
    with document_lock(migrated_tenant.number, document.number):
        gitstore.commit(
            repo,
            {"passport.md": (passport + entry).encode()},
            identity_for(user),
            "Accepted",
            Kind.ACCEPTANCE,
        )
    found = [(f.kind, f.detail) for f in reconcile.run(tenant=migrated_tenant.number)]

    # A passport's kinds are never derived from a commit's trailer alone.
    assert found == [
        ("commit_without_row", str(repo.head.target)),
        ("passport_entry_without_row", "acceptance"),
    ]


def test_one_document_only(migrated_tenant: Any, created: Any) -> None:
    from documents import reconcile
    from documents.models import Document

    document, _ = created
    with schema_context(migrated_tenant.number):
        Document.objects.filter(pk=document.pk).update(title="Changed by hand")

    assert reconcile.run(tenant=migrated_tenant.number, document=document.number + 1) == []
    assert len(reconcile.run(tenant=migrated_tenant.number, document=document.number)) == 1


def test_the_hourly_task_repairs_without_pruning(
    migrated_tenant: Any, created: Any, monkeypatch: Any
) -> None:
    from django.conf import settings

    from documents import reconcile, tasks

    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(reconcile, "run", lambda **kwargs: calls.append(kwargs) or [])

    tasks.reconcile_hourly()

    assert calls == [{"repair": True, "prune_rows": False}]
    entry = settings.CELERY_BEAT_SCHEDULE["reconcile-hourly"]
    assert entry["task"] == "documents.reconcile_hourly"


def test_creation_never_takes_over_an_existing_repository(
    migrated_tenant: Any, created: Any, repo_root: Path
) -> None:
    import shutil

    from documents import reconcile, services
    from documents.models import Document, DocumentType, Folder

    document, user = created
    shutil.copytree(
        repo_root / f"tenant-{migrated_tenant.number}" / f"document-{document.number}",
        repo_root / f"tenant-{migrated_tenant.number}" / f"document-{document.number + 1}",
    )

    with schema_context(migrated_tenant.number):
        with pytest.raises(services.CreationStopped):
            services.create_document(
                user,
                "Another",
                "uk",
                DocumentType.objects.get(code="document"),
                Folder.objects.get(number=1),
            )
        assert Document.objects.get(number=document.number + 1).state == "creating"
        Document.objects.filter(number=document.number + 1).update(
            created_at=timezone.now() - timedelta(hours=1)
        )

    # Nor does the reconciler: the copy's passport names another document.
    found = reconcile.run(tenant=migrated_tenant.number, repair=True)

    assert [(f.kind, f.document, f.repaired) for f in found] == [
        ("identity_mismatch", document.number + 1, False)
    ]
    with schema_context(migrated_tenant.number):
        assert Document.objects.get(number=document.number + 1).state == "creating"


def test_a_copied_repository_is_never_trusted(
    migrated_tenant: Any, created: Any, repo_root: Path
) -> None:
    import shutil

    from documents import reconcile
    from documents.models import Document, next_document_number

    document, _ = created
    tenant_dir = repo_root / f"tenant-{migrated_tenant.number}"
    shutil.copytree(tenant_dir / f"document-{document.number}", tenant_dir / "document-7")

    found = reconcile.run(tenant=migrated_tenant.number, repair=True)

    # Never recreated, and never a number a new document would collide with.
    assert [(f.kind, f.document) for f in found] == [
        ("identity_mismatch", 7),
        ("sequence_behind", 7),
    ]
    with schema_context(migrated_tenant.number):
        assert not Document.objects.filter(number=7).exists()
        assert next_document_number() == 8


def test_a_linked_repository_is_ignored(
    migrated_tenant: Any, created: Any, repo_root: Path
) -> None:
    from documents import reconcile

    document, _ = created
    tenant_dir = repo_root / f"tenant-{migrated_tenant.number}"
    (tenant_dir / "document-8").symlink_to(tenant_dir / f"document-{document.number}")

    assert reconcile.run(tenant=migrated_tenant.number, repair=True) == []


def test_one_bad_repository_stops_nothing_else(
    migrated_tenant: Any, created: Any, repo_root: Path, make_tenant_schema: Any
) -> None:
    from documents import reconcile, services
    from documents.models import Document, DocumentType, Folder

    document, user = created
    path = repo_root / f"tenant-{migrated_tenant.number}" / f"document-{document.number}"
    _commit_by_hand(path, "By hand")
    (repo_root / f"tenant-{migrated_tenant.number}" / "document-9").mkdir()
    other = make_tenant_schema("Other Org")
    with schema_context(other.number):
        Document.objects.create(
            number=1,
            title="Another",
            language_id="uk",
            document_type=DocumentType.objects.get(code="document"),
            folder=Folder.objects.get(number=1),
            state="active",
            actor_kind="system",
        )

    found = reconcile.run(repair=True)

    kinds = {(f.tenant, f.document, f.kind) for f in found}
    assert (migrated_tenant.number, document.number, "commit_without_row") in kinds
    assert (migrated_tenant.number, 9, "unreadable") in kinds
    assert (other.number, 1, "repository_missing") in kinds
    assert services is not None


def test_pruning_never_follows_a_missing_repository(
    migrated_tenant: Any, created: Any, repo_root: Path
) -> None:
    import shutil

    from documents import reconcile
    from documents.models import Version

    document, _ = created
    shutil.rmtree(repo_root / f"tenant-{migrated_tenant.number}" / f"document-{document.number}")

    found = reconcile.run(tenant=migrated_tenant.number, repair=True, prune_rows=True)

    assert [f.kind for f in found] == ["repository_missing"]
    with schema_context(migrated_tenant.number):
        assert Version.objects.filter(document=document).count() == 1


def test_a_sequence_behind_its_repositories_is_moved_past_them(
    migrated_tenant: Any, created: Any
) -> None:
    from django.db import connection

    from audit.models import AuditEvent
    from documents import reconcile
    from documents.models import next_document_number

    document, _ = created
    with schema_context(migrated_tenant.number), connection.cursor() as cursor:
        cursor.execute("SELECT setval('documents_document_number', 1, false)")

    report = reconcile.run(tenant=migrated_tenant.number)
    reconcile.run(tenant=migrated_tenant.number, repair=True)

    assert [(f.kind, f.document) for f in report] == [("sequence_behind", document.number)]
    with schema_context(migrated_tenant.number):
        assert next_document_number() == document.number + 1
    event = AuditEvent.objects.get(action="reconcile.sequence_behind")
    assert event.after == {"number": document.number}


def test_report_mode_writes_nothing(migrated_tenant: Any, created: Any, repo_root: Path) -> None:
    import shutil

    from audit.models import AuditEvent
    from documents import reconcile
    from documents.models import Document, Version

    document, _ = created
    shutil.rmtree(repo_root / f"tenant-{migrated_tenant.number}" / f"document-{document.number}")
    (repo_root / f"tenant-{migrated_tenant.number}" / f"document-{document.number}.lock").unlink()
    with schema_context(migrated_tenant.number):
        Document.objects.filter(pk=document.pk).update(title="Changed by hand")
        versions = Version.objects.count()
    events = AuditEvent.objects.count()

    reconcile.run(tenant=migrated_tenant.number)

    assert AuditEvent.objects.count() == events
    with schema_context(migrated_tenant.number):
        assert Version.objects.count() == versions
    assert not (
        repo_root / f"tenant-{migrated_tenant.number}" / f"document-{document.number}.lock"
    ).exists()


def test_a_tenant_being_set_up_is_skipped(migrated_tenant: Any, created: Any) -> None:
    from documents import reconcile
    from documents.models import Document

    document, _ = created
    with schema_context(migrated_tenant.number):
        Document.objects.filter(pk=document.pk).update(title="Changed by hand")
    migrated_tenant.state = "migrating"
    migrated_tenant.save()

    assert reconcile.run() == []


def test_the_command_refuses_what_it_cannot_do(migrated_tenant: Any, created: Any) -> None:
    from django.core.management.base import CommandError

    for argv in (["--tenant=999"], ["--prune-rows"], ["--document=1"]):
        with pytest.raises(CommandError):
            call_command("reconcile", *argv, stdout=io.StringIO())


def test_repair_exits_one_while_anything_is_left(
    migrated_tenant: Any, created: Any, repo_root: Path
) -> None:
    import shutil

    document, _ = created
    shutil.rmtree(repo_root / f"tenant-{migrated_tenant.number}" / f"document-{document.number}")

    with pytest.raises(SystemExit) as exit_:
        call_command(
            "reconcile", f"--tenant={migrated_tenant.number}", "--repair", stdout=io.StringIO()
        )

    assert exit_.value.code == 1


def test_replay_stops_at_the_first_commit_it_cannot_derive(
    migrated_tenant: Any, created: Any, repo_root: Path
) -> None:
    from documents import reconcile
    from documents.models import Version

    document, user = created
    path = repo_root / f"tenant-{migrated_tenant.number}" / f"document-{document.number}"
    unknown = _commit_by_hand(path, "By hand")
    later = _edit(migrated_tenant.number, document, user, "A later sentence.")

    first = reconcile.run(tenant=migrated_tenant.number, repair=True)
    second = reconcile.run(tenant=migrated_tenant.number, repair=True)

    # Derived past the unknown commit, the later one would leave a hole no run could fill.
    for found in (first, second):
        assert [(f.kind, f.detail, f.repaired) for f in found] == [
            ("commit_without_row", f"{unknown} (author not of this tenant)", False),
            ("commit_without_row", later, False),
        ]
    with schema_context(migrated_tenant.number):
        assert not Version.objects.filter(commit_sha=later).exists()


def test_a_blocked_creators_stopped_creation_is_finished(
    migrated_tenant: Any, member_of: Any, repo_root: Path
) -> None:
    from access.rights import rights_on
    from documents import reconcile, services
    from documents.models import Document, DocumentType, Folder
    from identity.models import Language

    Language.objects.get_or_create(code="uk", defaults={"label": "uk", "actor_kind": "system"})
    _, user, membership = member_of("an.author@example.test")
    with schema_context(migrated_tenant.number):
        with pytest.raises(services.InjectedFault):
            services.create_document(
                user,
                "Synthetic example",
                "uk",
                DocumentType.objects.get(code="document"),
                Folder.objects.get(number=1),
                fault_at=4,
            )
        Document.objects.update(created_at=timezone.now() - timedelta(hours=1))
    membership.change("state", "blocked", by=None)

    found = reconcile.run(tenant=migrated_tenant.number, repair=True)

    assert [(f.kind, f.repaired) for f in found] == [("creating_unfinished", True)]
    with schema_context(migrated_tenant.number):
        document = Document.objects.get()
        assert (document.state, document.author_only) == ("active", True)
        # It reaches nobody while its creator is blocked (DL-0308).
        assert not rights_on(user, document)


def test_a_restored_repository_is_replayed_by_the_reconciler(
    migrated_tenant: Any, created: Any, repo_root: Path, store: Any, state_dir: Path
) -> None:
    import shutil

    from documents import backup, gitstore, reconcile
    from documents.models import Version

    document, user = created
    edit = _edit(migrated_tenant.number, document, user, "A new sentence.")
    backup.run(store, start="20260929T100000Z")
    path = gitstore.repository_path(migrated_tenant.number, document.number)
    shutil.rmtree(path)
    with schema_context(migrated_tenant.number):
        # The database restored to before the edit: its row is gone.
        Version.objects.filter(commit_sha=edit).delete()

    # The runbook's step 5, then step 6.
    chain = backup.chains_in(store)[(migrated_tenant.number, document.number)]
    outcome = backup.restore_repository(store, migrated_tenant.number, document.number, chain)
    report = reconcile.run(tenant=migrated_tenant.number)
    repaired = reconcile.run(tenant=migrated_tenant.number, repair=True)

    assert outcome == "restored"
    # Initialised from an empty template, as the platform initialises one.
    assert not (path / "hooks").exists() or not any((path / "hooks").iterdir())
    assert [(f.kind, f.detail) for f in report] == [("commit_without_row", edit)]
    assert [(f.kind, f.repaired) for f in repaired] == [
        ("commit_without_row", True),
        ("authorship_missing", True),
    ]
    # Until the worker has written the edit's authorship, that is all that is left.
    assert [f.kind for f in reconcile.run(tenant=migrated_tenant.number)] == ["authorship_missing"]


def test_a_head_of_any_kind_without_rows_is_asked_for(
    migrated_tenant: Any, member_of: Any, repo_root: Path, queued_authorship: list[Any]
) -> None:
    """A created document's head, without rows, is reported and queued; one whose body is blank
    has no rows by design and is never asked for (DL-0326)."""
    from documents import bundle, gitstore, reconcile, services
    from documents.identity import identity_for
    from documents.locks import document_lock
    from documents.models import DocumentType, Folder
    from identity.models import Language

    Language.objects.get_or_create(code="uk", defaults={"label": "uk", "actor_kind": "system"})
    _, user, _ = member_of("an.author@example.test")
    with schema_context(migrated_tenant.number):
        document = services.create_document(
            user,
            "Synthetic example",
            "uk",
            DocumentType.objects.get(code="document"),
            Folder.objects.get(number=1),
        )
    head = _head(migrated_tenant.number, document)

    repaired = reconcile.run(tenant=migrated_tenant.number, repair=True)

    assert [(f.kind, f.detail, f.repaired) for f in repaired] == [
        ("authorship_missing", head, True)
    ]
    assert (migrated_tenant.number, document.number, head) in queued_authorship

    with schema_context(migrated_tenant.number):
        repo = gitstore.open_repository(migrated_tenant.number, document.number)
        frontmatter, _ = bundle.parse(gitstore.read(repo, "document.md", head).decode())
        with document_lock(migrated_tenant.number, document.number):
            blank = gitstore.commit(
                repo,
                {"document.md": bundle.render(frontmatter, "\n\n").encode()},
                identity_for(user),
                "Emptied",
                gitstore.Kind.EDIT,
            )
        services.derive_version(document, gitstore.commit_at(repo, blank), user)
    assert reconcile.run(tenant=migrated_tenant.number) == []


def _head(tenant: int, document: Any) -> str:
    from documents import gitstore

    with schema_context(tenant):
        head = gitstore.head(gitstore.open_repository(tenant, document.number))
    assert head is not None
    return head
