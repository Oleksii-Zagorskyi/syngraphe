"""`member_rights(membership)`: the rights a membership holds on each active document through its
groups and the documents' links, with the author's own reach, read from the rows alone — never
through `_person()`, so neither the membership's state nor the person's own block changes it, and
an administrator's membership gets its groups' rights, not the administrators' reading (DD-8 of
the interface touches, DL-0398).

People, groups and titles are synthetic examples.
"""

from __future__ import annotations

from typing import Any

import pytest

from access.rights import Right
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

VIEWS = {Right.VIEW_CANONICAL, Right.VIEW_ACCEPTED, Right.VIEW_PENDING}
AUTHOR_ONLY = VIEWS | {Right.EDIT, Right.UPLOAD_ATTACHMENT, Right.REPLACE_ATTACHMENT}


def _group(name: str, rights: list[Right], members: list[Any], admin: Any) -> Any:
    from access.models import AccessGroup

    group = AccessGroup.objects.create(name=name, created_by=admin, actor_kind="user")
    for right in rights:
        group.grant(right, by=admin)
    for membership in members:
        group.add_member(membership, by=admin)
    return group


def test_member_rights_reads_the_groups_alone(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    """Row 13: the union of `implied()` group by group over the linked groups, plus the author's
    reach on an unlinked author-only document; active documents only; a document reached by
    nothing absent. A self-blocked person, a blocked membership and an administrator each get the
    groups' rights and nothing else."""
    from access import rights
    from access.models import DocumentGroup
    from identity.models import MembershipState, User

    member_rights = getattr(rights, "member_rights", None)
    assert member_rights is not None, "access.rights.member_rights does not exist yet"

    _, admin, admin_membership = member_of("t.admin@example.test", is_tenant_admin=True)
    _, user, membership = member_of("a.member@example.test")
    _, _, blocked = member_of("b.member@example.test")
    _, self_blocked_user, self_blocked = member_of("s.member@example.test")
    both = make_document(title="Synthetic rules", created_by=admin, author_only=False)
    read_only = make_document(title="Synthetic notice", created_by=admin, author_only=False)
    own = make_document(title="Synthetic draft", created_by=user, author_only=True)
    archived = make_document(
        title="Synthetic archive", created_by=admin, author_only=False, state="archived"
    )
    creating = make_document(
        title="Synthetic beginning", created_by=user, author_only=True, state="creating"
    )
    unreached = make_document(title="Synthetic elsewhere", created_by=admin, author_only=False)
    with schema_context(migrated_tenant.number):
        everyone = [membership, blocked, self_blocked, admin_membership]
        editors = _group("Editors", [Right.EDIT], everyone, admin)
        # A part right without `edit` in the same group is inert: the union is taken per group.
        readers = _group(
            "Readers", [Right.VIEW_CANONICAL, Right.UPLOAD_ATTACHMENT], [membership], admin
        )
        for document, group in (
            (both, editors),
            (both, readers),
            (read_only, readers),
            (archived, editors),
        ):
            DocumentGroup.link(document, group, by=admin)
    blocked.change("state", MembershipState.BLOCKED, by=admin)
    User.objects.filter(pk=self_blocked_user.pk).update(self_blocked=True)

    with schema_context(migrated_tenant.number):
        of_member = member_rights(membership)
        of_blocked = member_rights(blocked)
        of_self_blocked = member_rights(self_blocked)
        of_admin = member_rights(admin_membership)

    # Archived, being created, and linked to nothing: absent, not present with an empty set.
    assert of_member == {
        both.pk: frozenset(VIEWS | {Right.EDIT}),
        read_only.pk: frozenset({Right.VIEW_CANONICAL}),
        own.pk: frozenset(AUTHOR_ONLY),
    }
    assert {archived.pk, creating.pk, unreached.pk}.isdisjoint(of_member)
    assert of_blocked == {both.pk: frozenset(VIEWS | {Right.EDIT})}
    assert of_self_blocked == {both.pk: frozenset(VIEWS | {Right.EDIT})}
    assert of_admin == {both.pk: frozenset(VIEWS | {Right.EDIT})}
    assert Right.VIEW_ALL_HISTORY not in of_admin[both.pk]
    for result in (of_member, of_blocked, of_self_blocked, of_admin):
        assert all(isinstance(held, frozenset) for held in result.values())
