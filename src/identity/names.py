"""A person's display name, which they set themselves and which is unique within each organisation
they belong to (DL-0523): compared in Unicode's compatibility form, without case, without
invisible format characters and with every run of spaces read as one, so two names a reader could
not tell apart on a page are one name. Letters of other scripts that look alike are not folded.

The uniqueness spans memberships, which several organisations share, so no constraint holds it:
every writer takes the person's row, then a transaction-level lock keyed by the normal form,
before it checks, and a second writer of the same name waits for the first to commit, then sees
it."""

from __future__ import annotations

import hashlib
import unicodedata

from django.db import connection, transaction

from audit.record import record
from identity.models import Membership, MembershipState, User
from tenancy.models import Tenant

# The longest name, as the user's field holds it.
NAME_MAX = 200
HELD = (MembershipState.ACTIVE, MembershipState.BLOCKED)


def visible(name: str) -> str:
    """The name without its invisible format characters (zero-width spaces and joiners, the
    byte-order mark), stripped: the form it is kept in."""
    return "".join(c for c in name if unicodedata.category(c) != "Cf").strip()


def normal(name: str) -> str:
    """The form two names are compared in."""
    return " ".join(unicodedata.normalize("NFKC", visible(name)).split()).casefold()


def drawable(name: str) -> bool:
    """Whether every character of the name can be drawn on a page: no control character."""
    return not any(unicodedata.category(c) == "Cc" for c in name)


def lock(name: str) -> None:
    """Hold the name's lock until the current transaction ends."""
    key = int.from_bytes(hashlib.sha256(normal(name).encode()).digest()[:8], "big", signed=True)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [key])


def taken(name: str, tenants: list[Tenant], *, besides: User | None = None) -> Tenant | None:
    """The first of `tenants` where another active or blocked member holds `name`, or `None`."""
    wanted = normal(name)
    rows = (
        Membership.objects.filter(tenant__in=tenants, state__in=HELD)
        .exclude(user=besides)
        .exclude(user__display_name="")
        .values_list("tenant_id", "user__display_name")
    )
    clashes = {tenant_id for tenant_id, held in rows if normal(held) == wanted}
    return next((tenant for tenant in tenants if tenant.pk in clashes), None)


def organisations_of(person: User) -> list[Tenant]:
    """Every organisation the person is an active or blocked member of, by number."""
    return list(
        Tenant.objects.filter(memberships__user=person, memberships__state__in=HELD)
        .distinct()
        .order_by("number")
    )


def rename(person: User, name: str) -> Tenant | None:
    """Set the person's display name, stripped, unless another member of one of their
    organisations holds it: then nothing is written and that organisation is returned. The
    change is audited by the person's id alone, never the names, which erasure clears (DL-0108)."""
    name = visible(name)
    with transaction.atomic():
        # The person's row before the name, in the order a join takes them: a join holding the row
        # is waited for, then the organisation it joined is seen.
        person = User.objects.select_for_update().get(pk=person.pk)
        lock(name)
        clash = taken(name, organisations_of(person), besides=person)
        if clash is not None:
            return clash
        if person.display_name != name:
            person.display_name = name
            person.save(update_fields=["display_name"])
            record(
                actor=person,
                action="user.renamed",
                obj=person,
                before=None,
                after={"user": str(person.pk)},
                tenant=None,
            )
    return None
