"""The rights vocabulary and what each right includes (ADR-0007, ADR-0016, DL-0234).

Stored rows hold what was granted; every check and every page uses `implied()`.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from django.db import connection
from django.utils.translation import gettext_lazy as _

from tenancy.schemas import current_tenant

if TYPE_CHECKING:
    from documents.models import Document
    from identity.models import Membership, User
    from tenancy.models import Tenant


class Right(StrEnum):
    VIEW_CANONICAL = "view_canonical"
    VIEW_ACCEPTED = "view_accepted"
    VIEW_PENDING = "view_pending"
    EDIT = "edit"
    CREATE_AND_EDIT = "create_and_edit"
    VIEW_PREVIOUS_CANONICAL = "view_previous_canonical"
    VIEW_ALL_HISTORY = "view_all_history"
    ACCEPT = "accept"
    FREEZE = "freeze"
    MAKE_CANONICAL = "make_canonical"
    RESERVE_FOR_EDITING = "reserve_for_editing"
    CREATE_APPENDIX = "create_appendix"
    DELETE_APPENDIX = "delete_appendix"
    UPLOAD_ATTACHMENT = "upload_attachment"
    REPLACE_ATTACHMENT = "replace_attachment"
    DELETE_ATTACHMENT = "delete_attachment"


# The viewing ladder: each step includes those below it.
LADDER = (
    Right.VIEW_CANONICAL,
    Right.VIEW_ACCEPTED,
    Right.VIEW_PENDING,
    Right.EDIT,
    Right.CREATE_AND_EDIT,
)
# History: never beyond what the ladder reaches; neither includes the other.
HISTORY = (Right.VIEW_PREVIOUS_CANONICAL, Right.VIEW_ALL_HISTORY)
# Acts: three include `edit`; *make canonical* includes `view accepted` alone.
ACTS = (Right.ACCEPT, Right.FREEZE, Right.MAKE_CANONICAL, Right.RESERVE_FOR_EDITING)
EDITING_ACTS = frozenset({Right.ACCEPT, Right.FREEZE, Right.RESERVE_FOR_EDITING})
# Parts: usable only where the group can edit.
PARTS = (
    Right.CREATE_APPENDIX,
    Right.DELETE_APPENDIX,
    Right.UPLOAD_ATTACHMENT,
    Right.REPLACE_ATTACHMENT,
    Right.DELETE_ATTACHMENT,
)
# The columns of the groups page, in this order.
GRID = LADDER + HISTORY + ACTS + PARTS

LABELS = {
    Right.VIEW_CANONICAL: _("view canonical"),
    Right.VIEW_ACCEPTED: _("view accepted"),
    Right.VIEW_PENDING: _("view pending"),
    Right.EDIT: _("edit"),
    Right.CREATE_AND_EDIT: _("create and edit"),
    Right.VIEW_PREVIOUS_CANONICAL: _("view previous canonical versions"),
    Right.VIEW_ALL_HISTORY: _("view all history"),
    Right.ACCEPT: _("accept"),
    Right.FREEZE: _("freeze and unfreeze"),
    Right.MAKE_CANONICAL: _("make canonical"),
    Right.RESERVE_FOR_EDITING: _("reserve for editing"),
    Right.CREATE_APPENDIX: _("create appendix"),
    Right.DELETE_APPENDIX: _("delete appendix"),
    Right.UPLOAD_ATTACHMENT: _("upload attachment"),
    Right.REPLACE_ATTACHMENT: _("replace attachment"),
    Right.DELETE_ATTACHMENT: _("delete attachment"),
}


def implied(rights: Iterable[Right]) -> frozenset[Right]:
    """The rights a group effectively holds, given the rights it was granted."""
    result = set(rights)
    if result & EDITING_ACTS:
        result.add(Right.EDIT)
    if Right.MAKE_CANONICAL in result:
        result.add(Right.VIEW_ACCEPTED)
    steps = [LADDER.index(r) for r in result if r in LADDER]
    if steps:
        result.update(LADDER[: max(steps) + 1])
    if Right.EDIT not in result:
        result.difference_update(PARTS)
    return frozenset(result)


# The author's own reach while nobody else is linked (ADR-0007): with the attachments a new group
# starts with, so the document's forms travel with its first draft (DL-0445).
AUTHOR_ONLY = frozenset(
    {
        Right.EDIT,
        Right.VIEW_PENDING,
        Right.VIEW_ACCEPTED,
        Right.VIEW_CANONICAL,
        Right.UPLOAD_ATTACHMENT,
        Right.REPLACE_ATTACHMENT,
    }
)
# An administrator reads every document of the organisation and holds no other right on it;
# administration's own acts are not rights (ADR-0007).
ADMINISTRATOR = frozenset(
    {
        Right.VIEW_CANONICAL,
        Right.VIEW_ACCEPTED,
        Right.VIEW_PENDING,
        Right.VIEW_PREVIOUS_CANONICAL,
        Right.VIEW_ALL_HISTORY,
    }
)


def _person(user: Any) -> User | None:
    """The signed-in person as the database now holds them; `None` for anyone who holds no right:
    signed out, blocked by themselves, or a former user (DL-0308)."""
    from identity.models import User

    if not getattr(user, "is_authenticated", False):
        return None
    return User.objects.filter(pk=user.pk, self_blocked=False, is_tombstoned=False).first()


def _active_membership(user: User, tenant_number: int) -> Membership | None:
    from identity.models import Membership

    return Membership.objects.active().filter(user=user, tenant__number=tenant_number).first()


def rights_on(user: Any, document: Document) -> frozenset[Right]:
    """Every right `user` holds on `document`, in the tenant the connection is set to.

    The union of: each linked group's implied rights, taken group by group; the author's own reach
    while the document is author-only; the administrators' reading. A document being created
    reaches nobody; an archived one only administrators. The document's state is read again in
    the current schema, so a stale or foreign instance grants nothing it no longer does. Views and
    controls decide from this function alone.
    """
    return rights_on_many(user, [document.pk])[document.pk]


def rights_on_many(user: Any, document_ids: Iterable[Any]) -> dict[Any, frozenset[Right]]:
    """`rights_on` for several documents at once, in a fixed number of queries."""
    from access.models import DocumentGroup, GroupRight
    from documents.models import Document, DocumentState

    ids = list(document_ids)
    result: dict[Any, frozenset[Right]] = {pk: frozenset() for pk in ids}
    tenant_number = current_tenant(connection)
    person = _person(user)
    if tenant_number is None or person is None:
        return result
    membership = _active_membership(person, tenant_number)
    administrator = person.acts_as_platform_admin or bool(
        membership is not None and membership.is_tenant_admin
    )
    rows = Document.objects.filter(pk__in=ids).values("id", "state", "author_only", "created_by_id")
    links = list(
        DocumentGroup.objects.filter(
            document_id__in=ids, group__members__membership=membership
        ).values_list("document_id", "group_id")
    )
    granted: dict[Any, set[Right]] = {}
    for group_id, right in GroupRight.objects.filter(
        group_id__in={link[1] for link in links}
    ).values_list("group_id", "right"):
        granted.setdefault(group_id, set()).add(Right(right))
    groups_of: dict[Any, list[Any]] = {}
    for document_id, group_id in links:
        groups_of.setdefault(document_id, []).append(group_id)
    for row in rows:
        if row["state"] == DocumentState.CREATING:
            continue
        rights: set[Right] = set(ADMINISTRATOR) if administrator else set()
        if membership is not None and row["state"] == DocumentState.ACTIVE:
            # Per group: a part right stands only where the same group can edit (ADR-0007).
            for group_id in groups_of.get(row["id"], []):
                rights |= implied(granted.get(group_id, set()))
            if row["author_only"] and row["created_by_id"] == person.pk:
                rights |= AUTHOR_ONLY
        result[row["id"]] = frozenset(rights)
    return result


# Every step of the ladder above canonical text lets a person read a document as it now stands.
BEYOND_CANONICAL = frozenset(LADDER[1:])


def readable(user: Any, document_ids: Iterable[Any]) -> set[Any]:
    """The documents `user` may open at all: a viewing right beyond canonical text, or canonical
    text where an edition exists (DL-0209). A history right alone opens nothing (ADR-0007)."""
    from editions.models import Edition

    rights = rights_on_many(user, document_ids)
    # From the rows, not the approval's commit: a stopped approval opens nothing until its
    # edition is derived.
    with_edition = set(
        Edition.objects.filter(version__document_id__in=list(rights)).values_list(
            "version__document_id", flat=True
        )
    )
    return {
        pk
        for pk, held in rights.items()
        if held & BEYOND_CANONICAL or (Right.VIEW_CANONICAL in held and pk in with_edition)
    }


def can_create(user: Any, tenant: Tenant) -> bool:
    """Whether `user` may create and copy documents in `tenant`: `create_and_edit` held through
    any of their groups, linked to nothing (ADR-0007)."""
    from access.models import GroupRight

    person = _person(user)
    if person is None or current_tenant(connection) != tenant.number:
        return False
    membership = _active_membership(person, tenant.number)
    if membership is None:
        return False
    rights = GroupRight.objects.filter(group__members__membership=membership).values_list(
        "right", flat=True
    )
    # `create_and_edit` is never implied by another right, so the stored rows answer alone.
    return Right.CREATE_AND_EDIT in {Right(r) for r in rights}


def holders_of(rights: Iterable[Right], document_ids: Iterable[Any]) -> dict[Any, set[Any]]:
    """For each document, the people whose groups linked to it imply any of `rights`, members of
    the current organisation in good standing (DL-0308) — who an act on the document tells.
    Only an active document reaches its groups, as in `rights_on_many`; the author's own reach
    and the administrators' reading are not groups and are not here."""
    from access.models import DocumentGroup, GroupMember, GroupRight
    from documents.models import DocumentState
    from identity.models import member_in_good_standing_q

    wanted = set(rights)
    ids = list(document_ids)
    result: dict[Any, set[Any]] = {pk: set() for pk in ids}
    tenant_number = current_tenant(connection)
    if tenant_number is None:
        return result
    links = list(
        DocumentGroup.objects.filter(
            document_id__in=ids, document__state=DocumentState.ACTIVE
        ).values_list("document_id", "group_id")
    )
    granted: dict[Any, set[Right]] = {}
    for group_id, right in GroupRight.objects.filter(
        group_id__in={link[1] for link in links}
    ).values_list("group_id", "right"):
        granted.setdefault(group_id, set()).add(Right(right))
    holding = {group for group, held in granted.items() if implied(held) & wanted}
    members: dict[Any, set[Any]] = {}
    for group_id, user_id in GroupMember.objects.filter(
        member_in_good_standing_q("membership__"),
        group_id__in=holding,
        membership__tenant__number=tenant_number,
    ).values_list("group_id", "membership__user_id"):
        members.setdefault(group_id, set()).add(user_id)
    for document_id, group_id in links:
        result[document_id] |= members.get(group_id, set())
    return result


def administrators(tenant_number: int) -> list[User]:
    """The organisation's tenant administrators in good standing — who its administrative events,
    and every document's freeze and edition, tell."""
    from identity.models import Membership, User, member_in_good_standing_q

    return list(
        User.objects.filter(
            pk__in=Membership.objects.filter(
                member_in_good_standing_q(), tenant__number=tenant_number, is_tenant_admin=True
            ).values("user_id")
        )
    )


def holds_anywhere(user: Any, right: Right) -> bool:
    """Whether `user` holds `right` on some active document of the current organisation, through
    a group or as an author-only document's author, as `rights_on_many` grants it — who is
    offered a view of the documents that right acts on (DL-0194, DL-0197)."""
    from access.models import DocumentGroup, GroupRight
    from documents.models import Document, DocumentState

    tenant_number = current_tenant(connection)
    person = _person(user)
    if tenant_number is None or person is None:
        return False
    membership = _active_membership(person, tenant_number)
    if membership is None:
        return False
    if (
        right in AUTHOR_ONLY
        and Document.objects.filter(
            state=DocumentState.ACTIVE, author_only=True, created_by=person
        ).exists()
    ):
        return True
    linked = DocumentGroup.objects.filter(
        group__members__membership=membership, document__state=DocumentState.ACTIVE
    ).values("group_id")
    granted: dict[Any, set[Right]] = {}
    for group_id, held in GroupRight.objects.filter(group_id__in=linked).values_list(
        "group_id", "right"
    ):
        granted.setdefault(group_id, set()).add(Right(held))
    return any(right in implied(held) for held in granted.values())
