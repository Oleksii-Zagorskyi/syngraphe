"""Who sets the `search_path` (ADR-0017, DL-0290): the context manager's module and the
middleware define and call the setter; the context manager is used by the migration command, by
the reconciler — a command and a task, never a request — and, inside one request, by the service
that creates an organisation; nothing else."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.fast

SRC = Path(__file__).resolve().parents[2] / "src"
SETTER = re.compile(r"set_search_path\(|search_path\s*=|set_config\('search_path'|SET search_path")
CONTEXT = re.compile(r"schema_context\(")


def users_of(pattern: re.Pattern[str]) -> set[str]:
    return {
        str(path.relative_to(SRC))
        for path in SRC.rglob("*.py")
        if "migrations" not in path.parts and pattern.search(path.read_text(encoding="utf-8"))
    }


def test_only_the_context_manager_and_the_middleware_set_the_path() -> None:
    assert users_of(SETTER) == {"tenancy/schemas.py", "tenancy/middleware.py"}


def test_the_context_manager_is_used_where_the_decisions_allow() -> None:
    assert users_of(CONTEXT) == {
        "tenancy/schemas.py",
        "tenancy/management/commands/migrate_schemas.py",
        "tenancy/services.py",
        "documents/reconcile.py",
    }
