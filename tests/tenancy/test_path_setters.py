"""Who sets the `search_path` (ADR-0017, DL-0290): the context manager's module and the
middleware define and call the setter; the context manager is used by the migration command, by
the reconciler, the operator's commands on a hold, a draft, a loaded document, an edition and the
mail key, and the tasks — never a request — and, inside a request, by the service that creates an
organisation, by the notifications' writer, which writes a platform administrator's notification
to the shared schema, by the mail's queue, which reads the platform's sender (DL-0367, DL-0382),
by the platform's mail page, which reads the shared rows whatever organisation the session
names (DL-0393), by a reset's request, which queues its email where its place is decided
(DL-0383, DL-0401), and by a block, which ends holds in every organisation it closes (DL-0256,
DL-0401); nothing else."""

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
        "editing/management/commands/release_hold.py",
        "editing/management/commands/inspect_draft.py",
        "documents/management/commands/load_document.py",
        "editions/management/commands/make_canonical.py",
        "editions/management/commands/end_freeze.py",
        "editing/tasks.py",
        "rendering/tasks.py",
        "notifications/services.py",
        "mail/services.py",
        "mail/tasks.py",
        "mail/management/commands/rotate_mail_key.py",
        "mail/views/platform.py",
        "identity/resets.py",
        "identity/blocking.py",
        # The operator's removal of a stopped copy, in its organisation's schema.
        "documents/management/commands/remove_stopped_copy.py",
    }
