"""Creating an organisation, and the hosts it and the platform answer on (ST-0001, ADR-0008,
ADR-0017, DL-0280, DL-0290)."""

from __future__ import annotations

import logging
import re
from io import StringIO
from typing import TYPE_CHECKING, Any

from django.core.management import call_command
from django.db import connection, transaction
from django.db.models import QuerySet
from django.utils.translation import gettext as _

from audit.record import record
from syngraphe.provenance import ActorKind
from tenancy.middleware import invalidate_host_cache
from tenancy.models import PlatformHost, Tenant, TenantDomain, TenantState
from tenancy.schemas import create_schema, schema_context, schema_exists

if TYPE_CHECKING:
    from identity.models import User

logger = logging.getLogger(__name__)

HOST = re.compile(r"^[a-z0-9]([a-z0-9.-]*[a-z0-9])?(:(?P<port>[0-9]{1,5}))?$")
HOST_MAX = 253
# An arbitrary constant naming the hosts among PostgreSQL's advisory locks: every change to either
# set of hosts holds it, so a check and the write it guards are never interleaved.
HOSTS_LOCK = 0x5E7_0002


class Refused(Exception):
    """A change the rules do not allow; the message is for the person who asked for it."""


def checked_host(value: str) -> str:
    """A host as stored — lowercase, an optional port — or `Refused`."""
    host = value.strip().lower()
    match = HOST.match(host)
    port = match.group("port") if match else None
    if match is None or len(host) > HOST_MAX or (port is not None and not 1 <= int(port) <= 65535):
        raise Refused(_("Not a host name."))
    return host


def create_tenant(name: str, first_administrator: User, by: User) -> Tenant:
    """The organisation, its first administrator's membership and the audit event are committed
    first, the organisation `migrating`; then its schema is created and migrated, which makes it
    active. A failure leaves it `migrating` — resolved by no request — until `migrate_schemas
    --tenant N` completes it; nothing is dropped (DL-0280, DL-0290)."""
    from identity.models import Membership

    if connection.in_atomic_block:
        raise RuntimeError("create_tenant commits before its fallible step; call it outside one")
    # The shared schema alone, whatever organisation the request resolved: the rows written here
    # are the platform's, and the migration below restores exactly this path when it leaves.
    with schema_context(None):
        with transaction.atomic():
            tenant = Tenant.objects.create(
                name=name, state=TenantState.MIGRATING, created_by=by, actor_kind=ActorKind.USER
            )
            Membership.objects.create(
                tenant=tenant,
                user=first_administrator,
                is_tenant_admin=True,
                granted_by=by,
                created_by=by,
                actor_kind=ActorKind.USER,
            )
            record(
                actor=by,
                action="tenant.created",
                obj=tenant,
                before=None,
                after={
                    "number": tenant.number,
                    "name": tenant.name,
                    "first_administrator": str(first_administrator.id),
                },
            )
        failure: str | None = None
        try:
            # A number is new, so a schema already named for it is someone else's leftover:
            # refuse it rather than adopt its rows.
            if schema_exists(tenant.number):
                raise RuntimeError("a schema already carries the new organisation's number")
            create_schema(tenant.number)
            migrate_new_schema(tenant.number)
        except Exception as error:  # any failure: the organisation stays unreachable, and says why
            logger.exception("migrating a new organisation's schema failed")
            failure = type(error).__name__
        tenant.refresh_from_db()
        if failure is None and tenant.state != TenantState.ACTIVE:
            failure = "incomplete"
        if failure is not None:
            record(
                actor=by,
                action="tenant.migration_failed",
                obj=tenant,
                before=None,
                after={"error": failure},
            )
    return tenant


def migrate_new_schema(number: int) -> None:
    """The one migration a request runs: `migrate_schemas` sets the path through the schema
    context manager and restores the caller's on leaving (DL-0290)."""
    call_command("migrate_schemas", tenant=[number], stdout=StringIO())


def _lock_hosts() -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [HOSTS_LOCK])


def _bare(host: str) -> str:
    return host.rsplit(":", 1)[0]


def add_host(host: str, tenant: Tenant | None, by: User | None) -> PlatformHost | TenantDomain:
    """A host for the platform or for one organisation; the first of an organisation's is its
    default. A name belongs to one set only, whatever its port: a browser's cookies do not tell
    ports apart."""
    host = checked_host(host)
    kind = ActorKind.USER if by else ActorKind.SYSTEM
    row: PlatformHost | TenantDomain
    with transaction.atomic():
        _lock_hosts()
        taken = [
            (row_host, owner)
            for row_host, owner in [
                *((h, None) for h in PlatformHost.objects.values_list("host", flat=True)),
                *TenantDomain.objects.values_list("host", "tenant_id"),
            ]
            if _bare(row_host) == _bare(host)
        ]
        owner_id = None if tenant is None else tenant.pk
        if any(row_host == host or owner != owner_id for row_host, owner in taken):
            raise Refused(_("That host is already in use."))
        if tenant is None:
            row = PlatformHost.objects.create(host=host, created_by=by, actor_kind=kind)
        else:
            first = not tenant.domains.exists()
            row = TenantDomain.objects.create(
                tenant=tenant, host=host, is_default=first, created_by=by, actor_kind=kind
            )
        record(actor=by, action="host.added", obj=row, before=None, after=_described(row))
    invalidate_host_cache()
    return row


def make_default(row: PlatformHost | TenantDomain, by: User | None) -> None:
    """The row becomes the one default of its set."""
    with transaction.atomic():
        _lock_hosts()
        row = _reread(row)
        if row.is_default:
            return
        siblings = _siblings(row)
        previous = siblings.filter(is_default=True).first()
        siblings.filter(is_default=True).update(is_default=False)
        row.is_default = True
        row.save(update_fields=["is_default"])
        record(
            actor=by,
            action="host.made_default",
            obj=row,
            before={"default": previous.host if previous else None},
            after=_described(row),
        )
    invalidate_host_cache()


def remove_host(row: PlatformHost | TenantDomain, by: User) -> None:
    """Remove a host. The platform always keeps one, and its default stays until another is made
    default; an organisation may be left with no domain, and a default among others stays until
    another is made default."""
    with transaction.atomic():
        _lock_hosts()
        row = _reread(row)
        if isinstance(row, PlatformHost) and PlatformHost.objects.count() <= 1:
            raise Refused(_("The platform keeps at least one host."))
        if row.is_default and _siblings(row).exclude(pk=row.pk).exists():
            raise Refused(_("Make another host the default first."))
        described = _described(row)
        row.delete()
        record(actor=by, action="host.removed", obj=None, before=described, after=None)
    invalidate_host_cache()


def _reread(row: PlatformHost | TenantDomain) -> PlatformHost | TenantDomain:
    """The row as it is now, under the hosts' lock; `Refused` if it has gone."""
    found = type(row).objects.filter(pk=row.pk).first()
    if found is None:
        raise Refused(_("That host is no longer there."))
    return found


def _siblings(row: PlatformHost | TenantDomain) -> QuerySet[Any]:
    if isinstance(row, PlatformHost):
        return PlatformHost.objects.all()
    return TenantDomain.objects.filter(tenant_id=row.tenant_id)


def _described(row: PlatformHost | TenantDomain) -> dict[str, object]:
    belongs_to = "platform" if isinstance(row, PlatformHost) else row.tenant.number
    return {"host": row.host, "belongs_to": belongs_to, "default": row.is_default}
