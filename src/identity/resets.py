"""Password reset (ST-0055, DL-0107, DL-0373, DL-0383): a request that answers alike for any
address, and a single-use link of one hour.

The request is counted per client on a throttle row of its own, so an address cannot be flooded
with mail from one client and nobody's sign-in delay grows. The email leaves where DL-0383 places
it: on an organisation's domain, that organisation's outbox; on the platform host, the outbox of
the person's one active membership, else the platform's.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from audit.record import record
from identity import throttle
from identity.language import language_of
from identity.models import Membership, PasswordReset, SignInAttempt, User, fold_email
from identity.tokens import hash_token, new_token
from mail import services as mail
from mail.models import Kind
from tenancy.schemas import schema_context

if TYPE_CHECKING:
    from tenancy.models import Tenant

# DL-0373.
RESET_LIFETIME = timedelta(hours=1)


def request_reset(email: str, reset_key: str, *, tenant: Tenant | None) -> None:
    """Ask for a reset of `email`'s password. `tenant` is the organisation whose domain the request
    came to, `None` on the platform host. Returns nothing that tells a known address from an
    unknown one: only a person with a usable password, not erased, gets a row and an email."""
    charged = throttle.charge([(reset_key, SignInAttempt.KeyKind.RESET)])
    # Drawn whatever follows, so an unknown address costs what a known one does up to the rows.
    token = new_token()
    token_hash = hash_token(token)
    if not charged.allowed:
        return
    user = User.objects.filter(email=fold_email(email), is_tombstoned=False).first()
    if user is None or not user.has_usable_password():
        return
    place = tenant if tenant is not None else _sole_organisation(user)
    with schema_context(place.number if place is not None else None), transaction.atomic():
        row = PasswordReset.objects.create(
            user=user, token_hash=token_hash, expires_at=timezone.now() + RESET_LIFETIME
        )
        subject, body = _email(place, user, token)
        if mail.queue(place, user.email, subject, body, kind=Kind.RESET) is None:
            # No sender where the email belongs: the row stays so an administrator can tell
            # why no email came (DL-0383).
            record(
                actor=None,
                action="password.reset_requested",
                obj=row,
                before=None,
                after={"user": str(user.pk), "tenant": place.number if place else None},
                tenant=place,
            )


def _sole_organisation(user: User) -> Tenant | None:
    """The organisation of the person's one active membership, or `None` with several or none."""
    memberships = list(Membership.objects.active().filter(user=user).select_related("tenant")[:2])
    return memberships[0].tenant if len(memberships) == 1 else None


def _email(place: Tenant | None, user: User, token: str) -> tuple[str, str]:
    """The reset's subject and body in its person's language (DL-0501), with the one link."""
    with translation.override(language_of(user)):
        subject = _("Reset your password")
        lines = [
            _("Someone asked for a new password for this address."),
            _("Follow the link to set one; it works once, for an hour:"),
            mail.link(place, f"/reset/{token}/"),
            _("If you did not ask for it, ignore this email: your password stays as it is."),
        ]
    return subject, "\n".join(lines) + "\n"


def person_of(token: str) -> User | None:
    """The person a known, unexpired and unused reset is for, or `None` — one query."""
    opening = PasswordReset.objects.filter(
        token_hash=hash_token(token), expires_at__gt=timezone.now(), used_at__isnull=True
    ).values("user_id")
    return User.objects.filter(pk__in=opening, is_tombstoned=False).first()


def reset(token: str, password: str) -> User | None:
    """Spend the reset: the person's password set and the link marked used, in one transaction;
    `None` when the token no longer opens one. Every other link the person holds — another reset,
    an invitation to their address — ends with it. A changed password signs every other session of
    the person out, by the framework's own check of the password's hash."""
    from identity.invitations import end_open_links

    # Hashed before the rows are locked: the hash is slow on purpose.
    hashed = make_password(password)
    with transaction.atomic():
        # The person first, then the link, as every writer of a person's links takes them: a link
        # locked before its person would wait on a spend of another link that ends this one.
        owner = person_of(token)
        if owner is None:
            return None
        user = User.objects.select_for_update().filter(pk=owner.pk, is_tombstoned=False).first()
        if user is None:
            return None
        row = (
            PasswordReset.objects.select_for_update()
            .filter(
                token_hash=hash_token(token),
                user=user,
                expires_at__gt=timezone.now(),
                used_at__isnull=True,
            )
            .first()
        )
        if row is None:
            return None
        user.password = hashed
        user.save(update_fields=["password"])
        row.used_at = timezone.now()
        row.save(update_fields=["used_at"])
        end_open_links(user, row.used_at)
        record(
            actor=user,
            action="password.reset",
            obj=row,
            before=None,
            after={"user": str(user.pk)},
            tenant=None,
        )
    return user
