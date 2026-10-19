"""The access history's cost: each answer runs a fixed number of queries whatever the number of
groups, members and changes — the same count at five and at fifty. No time is asserted and no
`budget` marker carried.

Groups, people and documents are synthetic examples; addresses end in `@example.test`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

START = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)


def _history(tenant: Any, document: Any, admin: Any, size: int, label: str) -> None:
    """`size` groups linked to `document`, each with `size` right changes and `size` members,
    every member with a state row; the history dated before now, in the order made."""
    from access.models import AccessChange, AccessGroup
    from access.rights import GRID
    from identity.models import Membership, MembershipHistory, User

    clock = iter(START + timedelta(seconds=n) for n in range(10**6))
    memberships = [
        Membership.objects.create(
            tenant=tenant,
            user=User.objects.create(email=f"person{n}.{label}@example.test", actor_kind="system"),
            actor_kind="system",
        )
        for n in range(size)
    ]
    MembershipHistory.objects.bulk_create(
        MembershipHistory(
            membership=membership,
            field="state",
            before="blocked",
            after="active",
            at=next(clock),
            by=admin,
            actor_kind="user",
        )
        for membership in memberships
    )
    changes = []
    for n in range(size):
        group = AccessGroup.objects.create(
            name=f"{label} group {n:03d}", created_by=admin, actor_kind="user"
        )
        changes.append(
            AccessChange(
                kind="link",
                group=group,
                document=document,
                action="added",
                at=next(clock),
                by=admin,
                actor_kind="user",
            )
        )
        for index in range(size):
            changes.append(
                AccessChange(
                    kind="right",
                    group=group,
                    right=GRID[index % len(GRID)],
                    action="added" if (index // len(GRID)) % 2 == 0 else "removed",
                    at=next(clock),
                    by=admin,
                    actor_kind="user",
                )
            )
        changes.extend(
            AccessChange(
                kind="member",
                group=group,
                membership=membership,
                action="added",
                at=next(clock),
                by=admin,
                actor_kind="user",
            )
            for membership in memberships
        )
    AccessChange.objects.bulk_create(changes)
    # Archived and restored by turns, as many times as the history is large: inserted, as the
    # audit trail cannot be back-dated.
    from audit.models import AuditEvent

    AuditEvent.objects.bulk_create(
        AuditEvent(
            tenant=tenant,
            actor=admin,
            actor_kind="user",
            action="document.archived" if n % 2 == 0 else "document.restored",
            object_type="document",
            object_id=document.pk,
            after={"number": document.number},
            at=next(clock),
        )
        for n in range(size)
    )


def test_answers_cost_a_fixed_number_of_queries(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    """Row 9: the queries of `readers_at`, of `changes_until` for a document and of `changes_until`
    for any document, captured at 5 and at 50 groups, members and changes — the same count."""
    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    small = make_document(created_by=admin, author_only=False, title="Synthetic small")
    large = make_document(created_by=admin, author_only=False, title="Synthetic large")

    from access.history import changes_until, readers_at

    def counts(document: Any) -> tuple[int, int, int]:
        at = timezone.now()
        with CaptureQueriesContext(connection) as readers:
            answer = readers_at(document, at)
        with CaptureQueriesContext(connection) as of_document:
            changes = changes_until(at, document=document)
        with CaptureQueriesContext(connection) as of_any:
            every = changes_until(at)
        assert len(answer.groups) == len({then.group.name for then in answer.groups}) > 0
        assert any(c.kind == "archive" for c in changes)
        assert any(c.kind == "archive" for c in every)
        return len(readers), len(of_document), len(of_any)

    with schema_context(migrated_tenant.number):
        _history(migrated_tenant, small, admin, 5, "small")
        # A first call fills whatever caches a later one reads.
        counts(small)
        at_five = counts(small)
        # The organisation's whole history grows before *any document* is asked again.
        _history(migrated_tenant, large, admin, 50, "large")
        at_fifty = counts(large)

    assert at_five == at_fifty
    assert all(count > 0 for count in at_five)
