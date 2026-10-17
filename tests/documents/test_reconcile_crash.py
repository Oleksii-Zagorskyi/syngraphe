"""The reconciler finishes every creation a crash stopped (DL-0111)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from django.utils import timezone

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.crash,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

EXPECTED = {
    1: "creating_without_repository",
    2: "creating_without_commit",
    3: "creating_without_version",
    4: "creating_unfinished",
}


@pytest.mark.parametrize("step", [1, 2, 3, 4])
def test_each_crash_state_repaired(
    migrated_tenant: Any, member_of: Any, repo_root: Path, step: int
) -> None:
    from audit.models import AuditEvent
    from documents import gitstore, reconcile, services
    from documents.gitstore import Kind
    from documents.models import Document, DocumentType, Folder, Version
    from identity.models import Language

    Language.objects.get_or_create(code="uk", defaults={"label": "uk", "actor_kind": "system"})
    _, user, _ = member_of("an.author@example.test")
    with schema_context(migrated_tenant.number):
        kind = DocumentType.objects.get(code="document")
        root = Folder.objects.get(number=1)
        with pytest.raises(services.InjectedFault):
            services.create_document(user, "Synthetic example", "uk", kind, root, fault_at=step)
        document = Document.objects.get()
        # Leave nothing for the grace period to protect: the creation stopped an hour ago.
        Document.objects.filter(pk=document.pk).update(
            created_at=timezone.now() - timedelta(hours=1)
        )

    report = reconcile.run(tenant=migrated_tenant.number)
    repaired = reconcile.run(tenant=migrated_tenant.number, repair=True)
    after = reconcile.run(tenant=migrated_tenant.number)

    assert [(f.kind, f.document) for f in report] == [(EXPECTED[step], document.number)]
    assert [f.kind for f in repaired] == [EXPECTED[step]]
    assert all(f.repaired for f in repaired)
    # The finished creation's head waits for the worker's authorship, which the next pass asks
    # for (DL-0326); nothing else is left.
    assert [f.kind for f in after] == ["authorship_missing"]
    with schema_context(migrated_tenant.number):
        document.refresh_from_db()
        versions = list(Version.objects.filter(document=document))
    assert (document.state, document.author_only) == ("active", True)
    repo = gitstore.open_repository(migrated_tenant.number, document.number)
    history = list(gitstore.history(repo))
    assert len(history) == 1
    assert gitstore.kind_of(history[0].message) is Kind.CREATED
    assert [(v.commit_sha, v.kind, v.author_id) for v in versions] == [
        (str(history[0].id), "created", user.id)
    ]
    assert AuditEvent.objects.filter(action="document.created").count() == 1
    assert AuditEvent.objects.filter(action=f"reconcile.{EXPECTED[step]}").count() == 1


def test_a_young_creation_is_left_to_finish(
    migrated_tenant: Any, member_of: Any, repo_root: Path
) -> None:
    from documents import reconcile, services
    from documents.models import Document, DocumentType, Folder
    from identity.models import Language

    Language.objects.get_or_create(code="uk", defaults={"label": "uk", "actor_kind": "system"})
    _, user, _ = member_of("an.author@example.test")
    with schema_context(migrated_tenant.number):
        kind = DocumentType.objects.get(code="document")
        root = Folder.objects.get(number=1)
        with pytest.raises(services.InjectedFault):
            services.create_document(user, "Synthetic example", "uk", kind, root, fault_at=1)

    assert reconcile.run(tenant=migrated_tenant.number, repair=True) == []
    with schema_context(migrated_tenant.number):
        assert Document.objects.get().state == "creating"


def test_a_stopped_creation_is_finished_beside_a_stopped_copy(
    migrated_tenant: Any, member_of: Any, repo_root: Path
) -> None:
    """A creation stopped at step 3 is finished as before; a copy stopped beside it is reported
    and left (DL-0455)."""
    from access.models import AccessGroup
    from access.rights import Right
    from documents import copying, reconcile, services
    from documents.models import Document, DocumentType, Folder
    from identity.models import Language

    Language.objects.get_or_create(code="uk", defaults={"label": "uk", "actor_kind": "system"})
    _, user, membership = member_of("an.author@example.test")
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(name="Creators", created_by=user, actor_kind="user")
        group.grant(Right.CREATE_AND_EDIT, by=user)
        group.add_member(membership, by=user)
        kind = DocumentType.objects.get(code="document")
        root = Folder.objects.get(number=1)
        source = services.create_document(user, "Synthetic source", "uk", kind, root)
        with pytest.raises(services.InjectedFault):
            services.create_document(user, "Synthetic example", "uk", kind, root, fault_at=3)
        created = Document.objects.get(title="Synthetic example")
        with pytest.raises(copying.CopyStopped):
            copying.copy_document(
                user,
                source,
                title="Synthetic copy",
                document_type=kind,
                folder=root,
                view="accepted",
                number="0.0",
                appendices=[],
                fault_at=3,
            )
        copy = Document.objects.get(title="Synthetic copy")
        Document.objects.filter(pk__in=[created.pk, copy.pk]).update(
            created_at=timezone.now() - timedelta(hours=1)
        )

    repaired = reconcile.run(tenant=migrated_tenant.number, repair=True)

    kinds = {f.document: f.kind for f in repaired if f.document in (created.number, copy.number)}
    assert kinds == {created.number: "creating_without_version", copy.number: "copy_stopped"}
    with schema_context(migrated_tenant.number):
        assert Document.objects.get(pk=created.pk).state == "active"
        assert Document.objects.get(pk=copy.pk).state == "creating"
