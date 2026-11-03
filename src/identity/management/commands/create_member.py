"""`create_member`: a person and an active membership in one organisation, by an operator's
command, with a generated password printed once (ST-0073, DL-0343)."""

from __future__ import annotations

from typing import Any

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.core.validators import validate_email
from django.db import transaction

from audit.record import record
from identity import generated, names
from identity.managers import fold_email
from identity.models import Membership, MembershipState, User
from syngraphe.provenance import ActorKind
from tenancy.models import Tenant, TenantState

ATTEMPTS = 10


class Command(BaseCommand):
    help = (
        "Add a person to an organisation as an ordinary member. A new person gets a generated "
        "password, printed once; an existing person's password is never changed."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--tenant", type=int, required=True, help="the organisation's number")
        parser.add_argument("--email", required=True, help="the person's address")
        parser.add_argument("--name", default="", help="the display name of a new person")

    def handle(self, *args: Any, tenant: int, email: str, name: str, **options: Any) -> None:
        try:
            validate_email(email.strip())
        except ValidationError:
            raise CommandError(f"not an address: {email!r}") from None
        address = fold_email(email)
        organisation = Tenant.objects.filter(number=tenant, state=TenantState.ACTIVE).first()
        if organisation is None:
            raise CommandError(f"no active tenant numbered {tenant}")
        lines: list[str] = []
        with transaction.atomic():
            user = User.objects.select_for_update().filter(email=address).first()
            password = None
            if user is None:
                name = name.strip()
                if name:
                    # Unique within the organisation, as the account page checks it (DL-0523).
                    names.lock(name)
                    if names.taken(name, [organisation]) is not None:
                        raise CommandError(
                            f"the display name {name!r} is already used in {organisation.name}"
                        )
                user = User.objects.create_user(address, None, display_name=name)
                password = _drawn(user)
                user.set_password(password)
                user.save(update_fields=["password"])
                # The person by id, never the address the log could not erase (DL-0108); their
                # creation is the platform's event, not the organisation's.
                record(
                    actor=None,
                    action="user.created",
                    obj=user,
                    before=None,
                    after={"user": str(user.pk)},
                    tenant=None,
                )
                lines.append(f"created user {address}")
            elif (
                user.display_name
                and not Membership.objects.filter(tenant=organisation, user=user).exists()
                and _taken(user, organisation)
            ):
                raise CommandError(
                    f"{address}'s display name is already used in {organisation.name}"
                )
            elif user.self_blocked:
                raise CommandError(f"{address} is self-blocked")
            elif user.is_tombstoned:
                raise CommandError(f"{address} is tombstoned")
            else:
                lines.append(f"{address} already registered; password unchanged")
            membership = Membership.objects.filter(tenant=organisation, user=user).first()
            if membership is None:
                membership = Membership.objects.create(
                    tenant=organisation,
                    user=user,
                    is_tenant_admin=False,
                    granted_by=None,
                    actor_kind=ActorKind.SYSTEM,
                )
                record(
                    actor=None,
                    action="membership.created",
                    obj=membership,
                    before=None,
                    after={"user": str(user.pk), "tenant": organisation.number},
                    tenant=organisation,
                )
                lines.append(f"membership in tenant {organisation.number}")
            elif membership.state != MembershipState.ACTIVE:
                raise CommandError(
                    f"{address}'s membership in tenant {tenant} is {membership.state}"
                )
            else:
                lines.append(f"already a member of tenant {organisation.number}")
        for line in lines:
            self.stdout.write(line)
        if password is not None:
            self.stdout.write(f"password: {password}")


def _drawn(user: User) -> str:
    """A generated password the validators accept for `user`; the command aborts, writing nothing,
    when ten draws in a row are refused."""
    for _ in range(ATTEMPTS):
        password = generated.password()
        try:
            validate_password(password, user)
        except ValidationError:
            continue
        return password
    raise CommandError(f"no generated password passed the validators in {ATTEMPTS} draws")


def _taken(user: User, organisation: Tenant) -> bool:
    """Whether joining would give the organisation two members of one name (DL-0537)."""
    names.lock(user.display_name)
    return names.taken(user.display_name, [organisation], besides=user) is not None
