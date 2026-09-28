"""The tenant-query guard (ADR-0017): a tenant-schema model is never queried with no tenant set.

The guard sits in the router, which the ORM consults for every query; `QuerySet.using()`,
`Manager.raw()` and a raw cursor go past it, where a `search_path` of `public` alone still fails
closed for a table that exists only in tenant schemas.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from django.apps import apps
from django.conf import settings
from django.core.checks import Error, register
from django.db import connection
from django.db.models import Model

from tenancy.schemas import current_tenant


class TenantRequired(RuntimeError):
    """A tenant-app model was queried while the connection's `search_path` was `public` alone."""


def labels(entries: Iterable[str]) -> set[str]:
    """The app labels of the dotted names an app list holds."""
    names = set(entries)
    return {config.label for config in apps.get_app_configs() if config.name in names}


_split_cache: dict[tuple[tuple[str, ...], tuple[str, ...]], tuple[set[str], set[str]]] = {}


def _split() -> tuple[set[str], set[str]]:
    """The tenant-only and shared-only labels for the current app lists."""
    key = (tuple(settings.SHARED_APPS), tuple(settings.TENANT_APPS))
    if key not in _split_cache:
        shared, tenant = labels(key[0]), labels(key[1])
        _split_cache[key] = (tenant - shared, shared - tenant)
    return _split_cache[key]


def tenant_only_labels() -> set[str]:
    return _split()[0]


def shared_only_labels() -> set[str]:
    return _split()[1]


@register()
def check_app_lists(app_configs: Any, **kwargs: Any) -> list[Error]:
    """Every installed app is on a list, and every list entry names an installed app."""
    errors = []
    listed = labels(settings.SHARED_APPS) | labels(settings.TENANT_APPS)
    for config in apps.get_app_configs():
        if config.label not in listed:
            errors.append(
                Error(
                    f"{config.name} is installed but on neither SHARED_APPS nor TENANT_APPS",
                    id="tenancy.E001",
                )
            )
    names = {config.name for config in apps.get_app_configs()}
    for entry in [*settings.SHARED_APPS, *settings.TENANT_APPS]:
        if entry not in names:
            errors.append(
                Error(
                    f"{entry} in SHARED_APPS or TENANT_APPS is not an installed app's name",
                    id="tenancy.E002",
                )
            )
    return errors


class TenantGuardRouter:
    def _guard(self, model: type[Model]) -> None:
        label = model._meta.app_label
        if label in tenant_only_labels() and current_tenant(connection) is None:
            raise TenantRequired(
                f"{model._meta.label} lives in a tenant schema and no tenant is set"
            )

    def db_for_read(self, model: type[Model], **hints: Any) -> None:
        self._guard(model)
        return None

    def db_for_write(self, model: type[Model], **hints: Any) -> None:
        self._guard(model)
        return None

    def allow_migrate(
        self, db: str, app_label: str, model_name: str | None = None, **hints: Any
    ) -> bool:
        """In the shared schema only shared apps migrate; in a tenant schema, only tenant apps.

        An app on both lists migrates in both.
        """
        if current_tenant(connection) is None:
            return app_label not in tenant_only_labels()
        return app_label not in shared_only_labels()
