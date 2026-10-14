"""Blocking and what a block ends (ST-0004, ST-0072, DL-0256).

A block ends the person's holds and reservations on the documents it closes to them: each is
released as `blocked`, its draft kept, the document free. One function ends them for every level of
block — a membership's, a person's own, an organisation's — under the locks every writer of a
document takes, in their order: the document's writer lock, then its row.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from django.db import DatabaseError, transaction

from audit.record import record
from identity.models import Membership, MembershipState, User, member_in_good_standing_q
from tenancy.schemas import schema_context

if TYPE_CHECKING:
    from tenancy.models import Tenant

logger = logging.getLogger(__name__)

# The cause a release records; a person's own block names nobody as its releaser.
BLOCKED = "blocked"
SELF_BLOCKED = "self_blocked"
TENANT_BLOCKED = "tenant_blocked"


class BlockRefused(Exception):
    """A block the rules do not allow now: `reason` is `last_administrator`, `busy`,
    `not_administrator` — the acting person no longer administers the organisation — or
    `last_platform_administrator`, the platform's last administrator blocking their own account
    (DL-0315). Nothing is written."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def end_holds(
    tenants: Iterable[Tenant], *, by: User | None, cause: str, user: User | None = None
) -> int:
    """Release every open hold in each organisation — `user`'s when given, everyone's otherwise —
    as `blocked`, the drafts kept; how many it released. Called inside the block's transaction,
    so a block and its releases are written together or not at all. A document whose writer lock
    stays busy refuses the whole block (`BlockRefused("busy")`) rather than wait without bound."""
    from documents.locks import LockTimeout, document_lock
    from documents.models import Document
    from editing import holds
    from editing.models import Hold, ReleaseKind

    released_by = None if cause == SELF_BLOCKED else by
    count = 0
    for tenant in tenants:
        with schema_context(tenant.number):
            found = Hold.objects.filter(released_at__isnull=True).select_related("document")
            if user is not None:
                found = found.filter(user=user)
            for listed in list(found.order_by("document__number")):
                try:
                    with (
                        document_lock(
                            tenant.number, listed.document.number, timeout=holds.LOCK_WAIT_SECONDS
                        ),
                        transaction.atomic(),
                    ):
                        Document.objects.select_for_update().get(pk=listed.document_id)
                        # Read again under the locks: the hold listed may have been finished and
                        # another taken meanwhile.
                        hold = Hold.objects.filter(
                            document_id=listed.document_id, released_at__isnull=True
                        ).first()
                        if hold is None or (user is not None and hold.user_id != user.pk):
                            continue
                        if holds.release(
                            hold,
                            ReleaseKind.BLOCKED,
                            actor=by,
                            released_by=released_by,
                            reason=cause,
                        ):
                            count += 1
                except LockTimeout as error:
                    raise BlockRefused("busy") from error
    return count


def is_last_administrator(membership: Membership) -> bool:
    """Whether blocking `membership` would leave its organisation with no active administrator
    while someone else is still an active member — the one block the rules refuse (ST-0004).
    Memberships are counted by their own state, the one the organisation's pages draw: a person's
    own block changes nothing an administrator can see or do (DL-0398, DL-0409)."""
    tenant_members = Membership.objects.filter(
        state=MembershipState.ACTIVE, tenant_id=membership.tenant_id
    )
    if not tenant_members.filter(pk=membership.pk, is_tenant_admin=True).exists():
        return False
    others = tenant_members.exclude(pk=membership.pk)
    return not others.filter(is_tenant_admin=True).exists() and others.exists()


def administers(person: User, tenant_id: Any) -> bool:
    """Whether `person` may block and lift memberships of the organisation: a platform
    administrator, or an active administrator of it in good standing — read again inside the
    act, under its locks."""
    if person.acts_as_platform_admin:
        return True
    return Membership.objects.filter(
        member_in_good_standing_q(), tenant_id=tenant_id, user=person, is_tenant_admin=True
    ).exists()


def block_membership(membership: Membership, *, by: User, tell: bool = True) -> None:
    """Block `membership`: its state and history row, every hold the person has there ended, the
    organisation's open invitations to them ended, the act audited, and — unless `tell` is false,
    when the caller tells once for several — the platform's administrators told what the block
    left; one transaction. `BlockRefused` and nothing written when it is the organisation's last
    active administrator and others remain, a document stays busy, or `by` no longer
    administers it."""
    with transaction.atomic():
        # Every administrator's row first, in one order: two administrators blocking each other
        # at once cannot both pass the check and leave none.
        list(
            Membership.objects.select_for_update()
            .filter(tenant_id=membership.tenant_id, is_tenant_admin=True)
            .order_by("pk")
        )
        locked = (
            Membership.objects.select_for_update(of=("self",))
            .select_related("tenant", "user")
            .get(pk=membership.pk)
        )
        if not administers(by, locked.tenant_id):
            raise BlockRefused("not_administrator")
        if locked.state == MembershipState.BLOCKED:
            return
        if is_last_administrator(locked):
            raise BlockRefused("last_administrator")
        was_administrator = locked.is_tenant_admin and not locked.user.self_blocked
        locked.change("state", MembershipState.BLOCKED, by=by)
        end_open_invitations(locked)
        end_holds([locked.tenant], by=by, cause=BLOCKED, user=locked.user)
        record(
            actor=by,
            action="membership.blocked",
            obj=locked,
            before={"state": MembershipState.ACTIVE},
            after={"user": str(locked.user_id), "tenant": locked.tenant.number},
            tenant=locked.tenant,
        )
        if tell:
            tell_the_platform(
                locked.user,
                [locked.tenant],
                by=by,
                administered=[locked.tenant] if was_administrator else [],
            )


def lift_membership_block(membership: Membership, *, by: User) -> None:
    """Lift the block on `membership`: the person's groups were never touched, so their reach is
    as it stood. A person's own block is theirs, and stays (DL-0254)."""
    with transaction.atomic():
        locked = (
            Membership.objects.select_for_update(of=("self",))
            .select_related("tenant")
            .get(pk=membership.pk)
        )
        if not administers(by, locked.tenant_id):
            raise BlockRefused("not_administrator")
        if locked.state != MembershipState.BLOCKED:
            return
        locked.change("state", MembershipState.ACTIVE, by=by)
        record(
            actor=by,
            action="membership.block_lifted",
            obj=locked,
            before={"state": MembershipState.BLOCKED},
            after={"user": str(locked.user_id), "tenant": locked.tenant.number},
            tenant=locked.tenant,
        )


def end_open_invitations(membership: Membership) -> None:
    """The organisation's open invitations to the person end with the block: a link sent before
    it would otherwise still sign them in to an organisation closed to them."""
    from django.utils import timezone

    from identity.models import Invitation

    now = timezone.now()
    Invitation.objects.filter(
        tenant_id=membership.tenant_id,
        email=membership.user.email,
        accepted_at__isnull=True,
        expires_at__gt=now,
    ).update(expires_at=now)


def tell_the_platform(
    person: User,
    tenants: Iterable[Tenant],
    *,
    by: User | None,
    administered: Iterable[Tenant] = (),
) -> None:
    """What platform administrators are told once a block is written (the data model's rule): a
    person blocked in `tenants` and still active in another, and each organisation of
    `administered` — where the person was an active administrator — left with none. Never the
    organisation's own administrators (ASR-17). Written in a savepoint of the block's transaction:
    a failure here is logged, the block kept."""
    from notifications.models import Event
    from notifications.services import notify_platform

    blocked = list(tenants)
    try:
        with transaction.atomic():
            elsewhere = (
                Membership.objects.active()
                .filter(user=person)
                .exclude(tenant__in=[tenant.pk for tenant in blocked])
                .exists()
            )
            for tenant in blocked:
                if elsewhere:
                    notify_platform(
                        event=Event.USER_PARTIALLY_BLOCKED,
                        actor=by,
                        facts={"user": str(person.pk), "tenant": tenant.number},
                    )
            for tenant in administered:
                still = Membership.objects.filter(
                    member_in_good_standing_q(), tenant=tenant, is_tenant_admin=True
                ).exists()
                if not still:
                    notify_platform(
                        event=Event.TENANT_WITHOUT_ADMIN,
                        actor=by,
                        facts={"tenant": tenant.number},
                    )
    except DatabaseError:
        logger.exception("the platform's administrators were not told of a block")


def is_last_platform_administrator(person: User) -> bool:
    """Whether `person` is the platform's last administrator — whose own block is refused, so
    the platform keeps someone who can lift a block (DL-0315)."""
    from tenancy.services import platform_administrators

    holders = list(platform_administrators().values_list("pk", flat=True)[:2])
    return holders == [person.pk]


def self_block(person: User) -> None:
    """A person's own block (ST-0066): every membership closed by the account's flag and its
    history row, every hold in every organisation they reach ended with the drafts kept and no
    releaser named, audited — one transaction. `BlockRefused("last_platform_administrator")`
    and nothing written for the platform's last administrator (DL-0315). Lifting it has no
    control in release 0.1 (DL-0254)."""
    from identity.models import AccountBlockHistory
    from tenancy.models import TenantState, visited_by_background_work
    from tenancy.services import platform_administrators

    with transaction.atomic():
        if person.is_platform_admin:
            # Every holder of the platform's role locked in one order: two last administrators
            # blocking themselves at once cannot both pass the check.
            list(platform_administrators().select_for_update(no_key=True).order_by("pk"))
        locked = User.objects.select_for_update(no_key=True).get(pk=person.pk)
        if locked.self_blocked:
            return
        # The person's memberships next, as a membership's block takes its row: a take running
        # now waits for this block and then sees it — no hold outlives a block (DL-0256). In
        # organisation-number order, the one order every writer of several takes them in.
        list(
            Membership.objects.select_for_update(no_key=True, of=("self",))
            .filter(user=locked)
            .order_by("tenant__number")
        )
        if is_last_platform_administrator(locked):
            raise BlockRefused("last_platform_administrator")
        administered = [
            membership.tenant
            for membership in Membership.objects.filter(
                user=locked,
                state=MembershipState.ACTIVE,
                is_tenant_admin=True,
                tenant__state=TenantState.ACTIVE,
            ).select_related("tenant")
        ]
        locked.self_blocked = True
        locked.save(update_fields=["self_blocked"])
        AccountBlockHistory.objects.create(
            user=locked, action=AccountBlockHistory.Action.SELF_BLOCKED, by=locked
        )
        record(
            actor=locked,
            action="user.self_blocked",
            obj=locked,
            before={"self_blocked": False},
            after={"user": str(locked.pk)},
            tenant=None,
        )
        reached = visited_by_background_work().filter(memberships__user=locked).distinct()
        end_holds(list(reached), by=locked, cause=SELF_BLOCKED, user=locked)
        tell_the_platform(locked, [], by=locked, administered=administered)


def organisations_to_block(person: User, by: User) -> list[Any]:
    """The organisations `by` administers in which `person` holds an active membership, in number
    order — every such organisation for a platform administrator."""
    from tenancy.models import Tenant, TenantState

    held = Tenant.objects.filter(
        state=TenantState.ACTIVE,
        memberships__user=person,
        memberships__state=MembershipState.ACTIVE,
    )
    if not by.acts_as_platform_admin:
        administered = Membership.objects.active().filter(user=by, is_tenant_admin=True)
        held = held.filter(pk__in=administered.values("tenant_id"))
    return list(held.distinct().order_by("number"))
