"""A past version's authorship on demand (DL-0266): its rows written with an expiry and kept beside
the head's, the kept versions' rows never expiring, and the expired swept in every organisation.

People, documents and their text are synthetic examples; the text is invented."""

from __future__ import annotations

import importlib.util
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from django.utils import timezone

from tenancy.schemas import schema_context

_spec = importlib.util.spec_from_file_location(
    "past_authorship_review_fixtures",
    Path(__file__).resolve().parents[1] / "review" / "conftest.py",
)
assert _spec is not None and _spec.loader is not None
_review = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _review
_spec.loader.exec_module(_review)

# The review tests' fixture: a body committed on the document's head, its version derived.
commit_version = _review.commit_version

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

BODIES = [
    "# Purpose\n\nThe first synthetic sentence.\n",
    "# Purpose\n\nThe first synthetic sentence.\nThe second synthetic sentence.\n",
    "# Purpose\n\nThe first synthetic sentence.\nThe second synthetic sentence.\n\n# Scope\n",
    "# Purpose\n\nThe first synthetic sentence, revised.\nThe second synthetic sentence.\n",
]


def _history(member_of: Any, new_document: Any, commit_version: Any) -> tuple[Any, list[Any]]:
    _, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    return document, [commit_version(document, author, body) for body in BODIES]


def _compute(tenant: Any, document: Any, version: Any, **keywords: Any) -> None:
    from documents import gitstore
    from editing import authorship

    with schema_context(tenant.number):
        authorship.compute(
            document,
            version.commit_sha,
            repository_path=gitstore.repository_path(tenant.number, document.number),
            **keywords,
        )


def _expiries(tenant: Any, version: Any) -> set[Any]:
    from editing.models import LineAuthorship

    with schema_context(tenant.number):
        return set(
            LineAuthorship.objects.filter(version=version).values_list("expires_at", flat=True)
        )


def test_on_demand_rows_survive_the_head(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    document, versions = _history(member_of, new_document, commit_version)
    second, head = versions[1], versions[-1]
    later = timezone.now() + timedelta(hours=24)

    _compute(migrated_tenant, document, second, expires_at=later)
    _compute(migrated_tenant, document, head)

    assert _expiries(migrated_tenant, second) == {later}
    assert _expiries(migrated_tenant, head) == {None}


def test_a_kept_version_never_expires(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    document, versions = _history(member_of, new_document, commit_version)

    _compute(
        migrated_tenant, document, versions[-1], expires_at=timezone.now() + timedelta(hours=1)
    )

    assert _expiries(migrated_tenant, versions[-1]) == {None}


def _rows_in_another_organisation(make_tenant_schema: Any, author: Any) -> tuple[Any, Any]:
    """A second organisation with one document, one version and two lines' rows."""
    from documents.models import Document, DocumentType, Folder, Version, next_document_number
    from editing.models import LineAuthorship

    other = make_tenant_schema("Other Org")
    with schema_context(other.number):
        document = Document.objects.create(
            number=next_document_number(),
            title="Synthetic other document",
            language_id="uk",
            document_type=DocumentType.objects.get(code="document"),
            folder=Folder.objects.get(number=1),
            created_by=author,
            actor_kind="user",
        )
        version = Version.objects.create(
            document=document,
            commit_sha="c" * 40,
            author=author,
            summary="Synthetic edit",
            kind="edit",
            committed_at=timezone.now(),
            created_by=author,
            actor_kind="user",
        )
        now = timezone.now()
        for line, expires in ((1, now - timedelta(minutes=1)), (2, now + timedelta(hours=1))):
            LineAuthorship.objects.create(
                version=version,
                file="document.md",
                line=line,
                introduced_by=version,
                expires_at=expires,
            )
    return other, version


def test_the_sweep(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    commit_version: Any,
    make_tenant_schema: Any,
) -> None:
    from editing.models import LineAuthorship
    from editing.tasks import sweep_authorship

    document, versions = _history(member_of, new_document, commit_version)
    _compute(
        migrated_tenant, document, versions[0], expires_at=timezone.now() - timedelta(seconds=1)
    )
    _compute(migrated_tenant, document, versions[1], expires_at=timezone.now() + timedelta(hours=1))
    _compute(migrated_tenant, document, versions[-1])
    expired_here = len(_lines(migrated_tenant, versions[0]))
    assert expired_here > 0
    other, elsewhere = _rows_in_another_organisation(make_tenant_schema, document.created_by)

    swept = sweep_authorship()

    assert swept == expired_here + 1
    assert _lines(migrated_tenant, versions[0]) == []
    assert _lines(migrated_tenant, versions[1]) != []
    assert _lines(migrated_tenant, versions[-1]) != []
    with schema_context(other.number):
        assert list(
            LineAuthorship.objects.filter(version=elsewhere).values_list("line", flat=True)
        ) == [2]


def _lines(tenant: Any, version: Any) -> list[int]:
    from editing.models import LineAuthorship

    with schema_context(tenant.number):
        return list(LineAuthorship.objects.filter(version=version).values_list("line", flat=True))


accepted_directly = _review.accepted_directly


def test_the_latest_accepted_version_never_expires(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    commit_version: Any,
    accepted_directly: Any,
) -> None:
    from editing.models import LineAuthorship

    document, versions = _history(member_of, new_document, commit_version)
    _, reviewer, _ = member_of("the.reviewer@example.test")
    accepted_directly(document, reviewer)
    _, author, _ = member_of("another.author@example.test")
    commit_version(document, author, BODIES[0])

    _compute(
        migrated_tenant, document, versions[-1], expires_at=timezone.now() + timedelta(hours=1)
    )

    assert _expiries(migrated_tenant, versions[-1]) == {None}
    with schema_context(migrated_tenant.number):
        assert LineAuthorship.objects.filter(version=versions[-1]).exists()
