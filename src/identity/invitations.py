"""Invitation by email (DL-0107, DL-0374): the person and the membership at once, a single-use link
that sets the password.

A new address and one registered elsewhere are invited by the same steps and leave the same rows a
tenant administrator can see, so nothing tells the two apart (ASR-17). A person who blocked their
own account is invited as anyone; the block keeps them out until it is lifted (DL-0308).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import IntegrityError, connection, transaction
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from audit.record import record
from identity.models import Invitation, Membership, MembershipState, User, fold_email
from identity.tokens import hash_token, new_token
from mail import services as mail
from mail.models import Kind
from syngraphe.provenance import ActorKind
from tenancy.schemas import current_tenant

if TYPE_CHECKING:
    from tenancy.models import Tenant

# DL-0373.
INVITATION_LIFETIME = timedelta(days=7)


class Refused(Exception):
    """The invitation cannot be sent: no sending address, the organisation is blocked, or the
    person's membership in it is. Nothing is written, and the page says one sentence either way."""


def invite(tenant: Tenant, email: str, groups: Iterable[Any], *, by: User) -> Membership:
    """Invite `email` to `tenant` with `groups`: the person created with no usable password when
    the address is new, the membership created or the active one kept, the groups joined, the
    invitation and its email — one transaction, so a stop anywhere writes nothing. Called inside
    the organisation's schema. Inviting an active member again sends a fresh link and ends the
    organisation's earlier ones."""
    if current_tenant(connection) != tenant.number:
        raise RuntimeError("an invitation is written inside its organisation's schema")
    if mail.sender_for_queue() is None:
        raise Refused
    from tenancy.models import TenantState

    address = fold_email(email)
    with transaction.atomic():
        # The organisation's row first and shared, as take holds it: a block of the organisation
        # being written is waited for and then seen, and no invitation enters a blocked one.
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT state FROM tenancy_tenant WHERE number = %s FOR SHARE", [tenant.number]
            )
            (state,) = cursor.fetchone()
        if state != TenantState.ACTIVE:
            raise Refused
        user = _person(address, by)
        membership = Membership.objects.select_for_update().filter(tenant=tenant, user=user).first()
        if membership is None:
            membership = Membership.objects.create(
                tenant=tenant,
                user=user,
                is_tenant_admin=False,
                granted_by=by,
                created_by=by,
                actor_kind=ActorKind.USER,
            )
            record(
                actor=by,
                action="membership.created",
                obj=membership,
                before=None,
                after={"user": str(user.pk), "tenant": tenant.number},
                tenant=tenant,
            )
        elif membership.state == MembershipState.BLOCKED:
            raise Refused
        chosen = list(groups)
        for group in chosen:
            group.add_member(membership, by=by, email=False)
        now = timezone.now()
        _open(address).filter(tenant=tenant).update(expires_at=now)
        token = new_token()
        invitation = Invitation.objects.create(
            tenant=tenant,
            email=address,
            token_hash=hash_token(token),
            expires_at=now + INVITATION_LIFETIME,
            invited_by=by,
            created_by=by,
            actor_kind=ActorKind.USER,
        )
        subject, body = _email(tenant, by, token)
        if mail.queue(tenant, address, subject, body, kind=Kind.INVITATION) is None:
            # The sender went between the check and the queue: nothing may stay written.
            raise Refused
        record(
            actor=by,
            action="invitation.sent",
            obj=invitation,
            before=None,
            after={
                "user": str(user.pk),
                "tenant": tenant.number,
                "groups": sorted(str(group.pk) for group in chosen),
            },
            tenant=tenant,
        )
    return membership


def _person(address: str, by: User) -> User:
    """The person with this address, or a new one with no usable password; a creation is the
    platform's event, recorded by id alone (DL-0108)."""
    user = User.objects.select_for_update().filter(email=address).first()
    if user is not None:
        return user
    try:
        with transaction.atomic():
            user = User.objects.create_user(address, None, created_by=by)
    except IntegrityError:
        # Another invitation created the person a moment ago.
        return User.objects.select_for_update().get(email=address)
    record(
        actor=by,
        action="user.created",
        obj=user,
        before=None,
        after={"user": str(user.pk)},
        tenant=None,
    )
    return user


def _email(tenant: Tenant, by: User, token: str) -> tuple[str, str]:
    """The invitation's subject and body in the installation's language: the organisation, who
    invited, and the one link; nothing about the person's life elsewhere."""
    with translation.override(settings.LANGUAGE_CODE):
        inviter = by.display_name or by.email
        subject = _("Invitation to %(organisation)s") % {"organisation": tenant.name}
        lines = [
            _("%(inviter)s has invited you to %(organisation)s.")
            % {"inviter": inviter, "organisation": tenant.name},
            # One sentence for an address with an account and one without (ASR-17, DL-0511).
            _("Follow the link to join %(organisation)s; it works once, for seven days:")
            % {"organisation": tenant.name},
            mail.link(tenant, f"/invitation/{token}/"),
        ]
    return subject, "\n".join(lines) + "\n"


def _open(address: str) -> Any:
    """The address's invitations that a link can still spend."""
    return Invitation.objects.filter(
        email=address, accepted_at__isnull=True, expires_at__gt=timezone.now()
    )


def end_open_links(user: User, now: datetime) -> None:
    """End every link `user` still holds — their open resets and the open invitations to their
    address: one spent link shuts the others, which a resent or forwarded email would otherwise
    keep alive."""
    from identity.models import PasswordReset

    _open(user.email).update(expires_at=now)
    PasswordReset.objects.filter(user=user, used_at__isnull=True, expires_at__gt=now).update(
        expires_at=now
    )


def person_of(token: str) -> User | None:
    """The person a known, unexpired and unused invitation is for, or `None` — one query."""
    opening = Invitation.objects.filter(
        token_hash=hash_token(token), expires_at__gt=timezone.now(), accepted_at__isnull=True
    ).values("email")
    return User.objects.filter(email__in=opening, is_tombstoned=False).first()


def accept(token: str, password: str) -> tuple[User, Invitation] | None:
    """Spend the invitation: the person's password set, the invitation marked accepted and every
    other open link to the address ended — a resent or forwarded one would set the password again
    — in one transaction; `None` when the token no longer opens one."""
    # Hashed before the rows are locked: the hash is slow on purpose.
    hashed = make_password(password)
    with transaction.atomic():
        # The person first, then the link, as `invite` and every other writer of a person's links
        # take them: a link locked before its person would wait on a spend of another link that
        # ends this one.
        owner = person_of(token)
        if owner is None:
            return None
        user = User.objects.select_for_update().filter(pk=owner.pk, is_tombstoned=False).first()
        if user is None:
            return None
        invitation = (
            Invitation.objects.select_for_update(of=("self",))
            .select_related("tenant")
            .filter(
                token_hash=hash_token(token),
                email=user.email,
                expires_at__gt=timezone.now(),
                accepted_at__isnull=True,
            )
            .first()
        )
        if invitation is None:
            return None
        user.password = hashed
        user.save(update_fields=["password"])
        now = timezone.now()
        invitation.accepted_at = now
        invitation.save(update_fields=["accepted_at"])
        end_open_links(user, now)
        record(
            actor=user,
            action="invitation.accepted",
            obj=invitation,
            before=None,
            after={"user": str(user.pk), "tenant": invitation.tenant.number},
            tenant=invitation.tenant,
        )
    return user, invitation
