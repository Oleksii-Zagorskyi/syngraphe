"""Migrate the shared schema and every tenant schema, each with its own migration record (ADR-0017).

In a tenant schema the shared-only apps are recorded as applied without running, so a tenant app's
dependency on a shared app resolves without a shared table appearing there; an app on both lists
is never faked. A `migrating` tenant becomes `active` once its schema is complete (DL-0280).
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from typing import Any

from django.apps import apps
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder

from tenancy.models import Tenant, TenantState, TenantStateHistory
from tenancy.routers import labels
from tenancy.schemas import PUBLIC, create_schema, schema_context, schema_exists


def _with_migrations(app_labels: Iterable[str]) -> list[str]:
    migrated = MigrationLoader(None, ignore_no_migrations=True).migrated_apps
    return [label for label in app_labels if label in migrated]


def _ordered_labels(entries: Iterable[str]) -> list[str]:
    by_name = {config.name: config.label for config in apps.get_app_configs()}
    return [by_name[name] for name in entries if name in by_name]


def plan_for_public() -> list[str]:
    """The shared apps with migrations, applied to the shared schema."""
    return _with_migrations(_ordered_labels(settings.SHARED_APPS))


def plan_for_tenant_schema() -> tuple[list[str], list[str]]:
    """The apps migrated in a tenant schema and the apps recorded there without running."""
    tenant = labels(settings.TENANT_APPS)
    migrated = _with_migrations(_ordered_labels(settings.TENANT_APPS))
    faked = _with_migrations(
        [label for label in _ordered_labels(settings.SHARED_APPS) if label not in tenant]
    )
    return migrated, faked


def _migrate(label: str) -> None:
    call_command("migrate", label, interactive=False, verbosity=0)


def _record_without_running(faked: Iterable[str]) -> None:
    """Record every migration of the faked apps in the current schema, and only those.

    `migrate --fake` would fake the app's whole forwards plan, which may reach a tenant app; the
    recorder writes exactly the shared-only apps' rows.
    """
    wanted = set(faked)
    recorder = MigrationRecorder(connection)
    applied = recorder.applied_migrations()
    for app_label, name in MigrationLoader(None).graph.nodes:
        if app_label in wanted and (app_label, name) not in applied:
            recorder.record_applied(app_label, name)


def _plan_is_empty(app_labels: Iterable[str] | None = None) -> bool:
    executor = MigrationExecutor(connection)
    targets = executor.loader.graph.leaf_nodes()
    if app_labels is not None:
        wanted = set(app_labels)
        targets = [node for node in targets if node[0] in wanted]
    return not executor.migration_plan(targets)


class Command(BaseCommand):
    help = "Migrate the shared schema, then every tenant schema; --tenant N for one tenant."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--tenant",
            action="append",
            type=int,
            dest="tenants",
            metavar="N",
            help="migrate only this tenant's schema; may be repeated",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        numbers: list[int] | None = options["tenants"]
        if numbers is None:
            self.migrate_public()
            tenants = Tenant.objects.order_by("number")
        else:
            with schema_context(None):
                if not _plan_is_empty(plan_for_public()):
                    raise CommandError(
                        "the shared schema is behind; run migrate_schemas without --tenant first"
                    )
            tenants = Tenant.objects.filter(number__in=numbers).order_by("number")
            missing = set(numbers) - {t.number for t in tenants}
            if missing:
                raise CommandError(f"no tenant numbered {', '.join(map(str, sorted(missing)))}")
        for tenant in tenants:
            self.migrate_tenant(tenant)

    def migrate_public(self) -> None:
        started = time.perf_counter()
        with schema_context(None):
            for label in plan_for_public():
                _migrate(label)
        self.stdout.write(f"{PUBLIC} OK ({time.perf_counter() - started:.2f}s)")

    def migrate_tenant(self, tenant: Tenant) -> None:
        started = time.perf_counter()
        if not schema_exists(tenant.number):
            create_schema(tenant.number)
        # The recorder's table is created with the tenant's schema alone on the path: with `public`
        # there too, the recorder would see `public.django_migrations` and record everything in it.
        with schema_context(tenant.number, public=False):
            MigrationRecorder(connection).ensure_schema()
        migrated, faked = plan_for_tenant_schema()
        with schema_context(tenant.number):
            _record_without_running(faked)
            for label in migrated:
                _migrate(label)
            complete = _plan_is_empty()
        if complete and tenant.state == TenantState.MIGRATING:
            self.activate(tenant)
        elapsed = time.perf_counter() - started
        outcome = "OK" if complete else "INCOMPLETE"
        self.stdout.write(f"{tenant.schema_name} {outcome} ({elapsed:.2f}s, {tenant.state})")

    @staticmethod
    def activate(tenant: Tenant) -> None:
        with transaction.atomic():
            tenant.state = TenantState.ACTIVE
            tenant.save(update_fields=["state", "updated_at"])
            TenantStateHistory.objects.create(
                tenant=tenant, before=TenantState.MIGRATING, after=TenantState.ACTIVE, by=None
            )
