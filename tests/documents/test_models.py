"""The document tables of the tenant schema, and what every new tenant schema starts with."""

from __future__ import annotations

from typing import Any

import pytest
from django.db import IntegrityError, transaction

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]


def test_tenant_seeds(migrated_tenant: Any) -> None:
    from documents.models import DocumentTemplate, DocumentType, Folder

    with schema_context(migrated_tenant.number):
        types = list(DocumentType.objects.values_list("code", flat=True))
        folders = list(Folder.objects.values_list("number", "name", "parent"))
        templates = list(DocumentTemplate.objects.values_list("outline", "title_page"))

    assert types == ["document"]
    assert folders == [(1, "", None)]
    assert templates == [("# Загальні положення\n", False)]


def test_numbers_come_from_the_tenants_sequence(migrated_tenant: Any) -> None:
    from documents.models import next_document_number

    with schema_context(migrated_tenant.number):
        first = next_document_number()
        with pytest.raises(RuntimeError), transaction.atomic():
            next_document_number()
            raise RuntimeError("the creation fails")
        third = next_document_number()

    assert (first, third) == (1, 3)


def test_document_number_is_unique(migrated_tenant: Any, make_document: Any) -> None:
    from documents.models import Document

    document = make_document(title="First")

    with schema_context(migrated_tenant.number):
        with pytest.raises(IntegrityError), transaction.atomic():
            Document.objects.create(
                number=document.number,
                title="Second",
                language_id="uk",
                document_type=document.document_type,
                folder=document.folder,
                actor_kind="system",
            )


def test_caches_rebuild_from_the_commit(
    migrated_tenant: Any, member_of: Any, make_document: Any, repo_root: Any
) -> None:
    from datetime import UTC, datetime

    from documents import caches, gitstore
    from documents.gitstore import Kind
    from documents.identity import identity_for
    from documents.models import HeadingIndex, PartIndex, Version

    _, author, _ = member_of("an.author@example.test")
    document = make_document(created_by=author)
    repo = gitstore.init(migrated_tenant.number, document.number)
    from documents.bundle import Frontmatter, render

    frontmatter = Frontmatter(
        title="T",
        language="uk",
        appendices=[{"number": 1, "title": "Appendix"}],
        attachments=[
            {"number": 1, "title": "Scheme", "file_name": "a.pdf", "sha256": "0" * 64, "bytes": 5}
        ],
    )
    text = render(frontmatter, "# First\n\nText.\n\n## Second ##\n\n```\n# not a heading\n```\n")
    sha = gitstore.commit(
        repo,
        {"document.md": text.encode(), "appendices/1.md": b"# Appendix\n"},
        identity_for(author),
        "Created",
        Kind.CREATED,
    )

    with schema_context(migrated_tenant.number):
        version = Version.objects.create(
            document=document,
            commit_sha=sha,
            author=author,
            summary="Created",
            kind="created",
            committed_at=datetime(2026, 9, 1, tzinfo=UTC),
            actor_kind="system",
        )
        caches.rebuild(document, version)
        caches.rebuild(document, version)
        rows = list(
            HeadingIndex.objects.filter(version=version).values_list(
                "file", "position", "depth", "heading", "line"
            )
        )
        part_rows = list(
            PartIndex.objects.filter(version=version).values_list(
                "kind", "part_number", "position", "title"
            )
        )

    assert rows == [
        ("appendices/1.md", 1, 1, "Appendix", 1),
        ("document.md", 1, 1, "First", 16),
        ("document.md", 2, 2, "Second", 20),
    ]
    assert part_rows == [("appendix", 1, 1, "Appendix"), ("attachment", 1, 1, "Scheme")]


def test_the_sequence_is_each_tenants_own(migrated_tenant: Any, make_tenant_schema: Any) -> None:
    from django.db import connection

    from documents.models import next_document_number

    other = make_tenant_schema("Other Org")
    with schema_context(migrated_tenant.number):
        first = next_document_number()
    with schema_context(other.number):
        other_first = next_document_number()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT n.nspname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
            " WHERE c.relname = 'documents_document_number' ORDER BY n.nspname"
        )
        schemas = [row[0] for row in cursor.fetchall()]

    assert (first, other_first) == (1, 1)
    assert "public" not in schemas
    assert set(schemas) == {migrated_tenant.schema_name, other.schema_name}


def test_a_missing_appendix_leaves_the_rest(
    migrated_tenant: Any, member_of: Any, make_document: Any, repo_root: Any
) -> None:
    from datetime import UTC, datetime

    from documents import caches, gitstore
    from documents.gitstore import Kind
    from documents.identity import identity_for
    from documents.models import HeadingIndex, PartIndex, Version

    _, author, _ = member_of("an.author@example.test")
    document = make_document(created_by=author)
    repo = gitstore.init(migrated_tenant.number, document.number)
    from documents.bundle import Frontmatter, render

    text = render(
        Frontmatter(title="T", language="uk", appendices=[{"number": 2, "title": "Gone"}]),
        "# One\n",
    )
    sha = gitstore.commit(
        repo, {"document.md": text.encode()}, identity_for(author), "Created", Kind.CREATED
    )

    with schema_context(migrated_tenant.number):
        version = Version.objects.create(
            document=document,
            commit_sha=sha,
            author=author,
            summary="Created",
            kind="created",
            committed_at=datetime(2026, 9, 1, tzinfo=UTC),
            actor_kind="system",
        )
        caches.rebuild(document, version)
        headings = list(HeadingIndex.objects.filter(version=version).values_list("heading"))
        parts = PartIndex.objects.filter(version=version).count()

    assert headings == [("One",)]
    assert parts == 1
