"""What became of each attachment between two versions (DL-0208): added, changed — its file's
hash differs — removed, or unchanged, matched by its number, as the compare page lists them.

The texts, titles and files are invented examples.
"""

from __future__ import annotations

from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

BODY = "# General provisions\n\nA request for approval is made in writing.\n"


def test_changes_between_two_versions(
    migrated_tenant: Any, operator: Any, commit_parts: Any
) -> None:
    from documents import services
    from documents.models import DocumentType, Folder
    from documents.parts import changed_between
    from identity.models import Language

    Language.objects.get_or_create(code="uk", defaults={"label": "uk", "actor_kind": "system"})
    with schema_context(migrated_tenant.number):
        document = services.create_document(
            operator.user,
            "Synthetic procedure (example)",
            "uk",
            DocumentType.objects.get(code="document"),
            Folder.objects.get(number=1),
        )
    older = commit_parts(
        document,
        operator.user,
        BODY,
        [("Table", "table.txt", b"one\n"), ("Diagram", "scheme.txt", b"two\n")],
    )
    newer = commit_parts(
        document,
        operator.user,
        BODY,
        [
            ("Table", "table.txt", b"one, revised\n"),
            ("Diagram", "scheme.txt", b"two\n"),
            ("List", "list.txt", b"three\n"),
        ],
    )
    with schema_context(migrated_tenant.number):
        found = {c.number: c for c in changed_between(older, newer)}
        assert {n: c.change for n, c in found.items()} == {
            1: "changed",
            2: "unchanged",
            3: "added",
        }
        assert found[1].older is not None and found[1].newer is not None
        assert found[3].older is None and found[3].newer is not None
        # The other way round: the third was removed.
        back = {c.number: c.change for c in changed_between(newer, older)}
        assert back == {1: "changed", 2: "unchanged", 3: "removed"}
        assert [c.number for c in changed_between(older, newer)] == [1, 2, 3]
