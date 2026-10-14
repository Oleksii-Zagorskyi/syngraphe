"""The authorship worker's budget: one cold run over a forty-page, two-hundred-commit history in
under five seconds (DL-0135).

The corpus is the invented one of `tests/fixtures/corpus/`, loaded by the shared
`platform_corpus` fixture.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

BUDGET_SECONDS = 5.0


@pytest.mark.budget
def test_cold_run_within_budget(
    platform_corpus: dict[str, Any], migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    from documents.models import Version, VersionKind
    from editing import authorship
    from editing.models import LineAuthorship

    users = {n: member_of(f"corpus.author.{n}@example.test")[1] for n in (1, 2, 3)}
    document = make_document(title="Синтетичний корпус", created_by=users[1])
    with schema_context(migrated_tenant.number):
        versions = Version.objects.bulk_create(
            Version(
                document=document,
                commit_sha=commit["sha"],
                author=users[commit["author"]],
                summary="Commit",
                kind=VersionKind.CREATED if position == 0 else VersionKind.EDIT,
                committed_at=datetime.fromtimestamp(commit["at"], UTC),
                created_by=users[commit["author"]],
                actor_kind="user",
            )
            for position, commit in enumerate(platform_corpus["commits"])
        )
        head = versions[-1]
        assert not LineAuthorship.objects.exists()

        started = time.perf_counter()
        result = authorship.compute(
            document, head.commit_sha, repository_path=platform_corpus["repo"]
        )
        elapsed = time.perf_counter() - started

        assert result.base is None
        assert result.rows == LineAuthorship.objects.filter(version=head).count() > 1000
    print(f"cold run: {elapsed:.3f} s, {result.rows} rows, {result.moves} moves followed")
    assert elapsed < BUDGET_SECONDS
