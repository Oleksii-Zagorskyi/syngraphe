"""The number pending work carries before any acceptance (DL-0198, DL-0267, DL-0268, DL-0272)."""

from __future__ import annotations

from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]


def test_pending_number(migrated_tenant: Any, member_of: Any, new_document: Any) -> None:
    from django.utils import timezone

    from documents.models import Version
    from editing import numbering

    _, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    with schema_context(migrated_tenant.number):
        assert numbering.pending(document) == "0.0-1"
        for n in range(2):
            Version.objects.create(
                document=document,
                commit_sha=f"{n + 1:040x}",
                author=author,
                summary="Правка",
                kind="edit",
                committed_at=timezone.now(),
                actor_kind="user",
                created_by=author,
            )
        assert numbering.pending(document) == "0.0-3"
        assert numbering.latest(document) == "0.0-2"
