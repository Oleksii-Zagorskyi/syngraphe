"""The one place the connection's `search_path` is set outside a request (ADR-0017).

`schema_context` is the setter for tasks, commands and tests; `TenancyMiddleware` is the setter in
a request. Nothing else calls `set_search_path`. Schemas are named by the tenant's number, never by
the organisation (ADR-0008).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from django.db import connection
from django.db.backends.base.base import BaseDatabaseWrapper
from django.db.backends.signals import connection_created
from django.dispatch import receiver

PUBLIC = "public"
_STATE = "syngraphe_search_path"


def schema_name(number: int) -> str:
    return f"tenant_{number}"


def create_schema(number: int) -> None:
    with connection.cursor() as cursor:
        name = connection.ops.quote_name(schema_name(number))
        cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {name}")


def schema_exists(number: int) -> bool:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_namespace WHERE nspname = %s", [schema_name(number)])
        return cursor.fetchone() is not None


def _path(number: int | None, public: bool) -> list[str]:
    names = [] if number is None else [schema_name(number)]
    if public or number is None:
        names.append(PUBLIC)
    return names


def set_search_path(db: BaseDatabaseWrapper, number: int | None, *, public: bool = True) -> None:
    """Set the `search_path`: the tenant's schema first, then `public` unless told otherwise.

    `None` sets the shared schema alone. Called by `schema_context` and `TenancyMiddleware` only.
    """
    state = (number, public)
    setattr(db, _STATE, state)
    if db.connection is None:
        # The receiver below applies the path when the connection opens.
        return
    if db.needs_rollback:
        # No statement runs in a failed transaction; its rollback also undoes any SET made in it,
        # and the receiver restores the recorded path if the connection is reopened.
        return
    with db.cursor() as cursor:
        cursor.execute(
            "SET search_path TO " + ", ".join(db.ops.quote_name(n) for n in _path(number, public))
        )


def current_tenant(db: BaseDatabaseWrapper) -> int | None:
    """The tenant number the `search_path` starts with, or `None` for `public` alone."""
    state: tuple[int | None, bool] | None = getattr(db, _STATE, None)
    return None if state is None else state[0]


@contextmanager
def schema_context(number: int | None, *, public: bool = True) -> Iterator[None]:
    """Run the block with the `search_path` set for the tenant; the previous path is restored."""
    previous: tuple[int | None, bool] = getattr(connection, _STATE, (None, True))
    set_search_path(connection, number, public=public)
    try:
        yield
    finally:
        set_search_path(connection, previous[0], public=previous[1])


@receiver(connection_created)
def _reapply_after_reconnect(sender: Any, connection: BaseDatabaseWrapper, **kwargs: Any) -> None:
    """A connection opened or reopened keeps the path the code believes it has."""
    state: tuple[int | None, bool] | None = getattr(connection, _STATE, None)
    if state is None:
        return
    with connection.cursor() as cursor:
        cursor.execute(
            "SET search_path TO " + ", ".join(connection.ops.quote_name(n) for n in _path(*state))
        )
