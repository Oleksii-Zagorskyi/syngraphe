"""Fixtures for the notifications tests: notifications of every category written straight into the
tables, so the page and the count are tested apart from the acts that cause them; and the review
tests' document, groups and versions, loaded from their own conftest, for the acts themselves.

People, groups and titles are synthetic examples."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from tenancy.schemas import schema_context

_spec = importlib.util.spec_from_file_location(
    "notifications_review_fixtures", Path(__file__).resolve().parents[1] / "review" / "conftest.py"
)
assert _spec is not None and _spec.loader is not None
_review = importlib.util.module_from_spec(_spec)
# Registered before it runs: its dataclass looks its own module up by name.
sys.modules[_spec.name] = _review
_spec.loader.exec_module(_review)

new_document = _review.new_document
link_group = _review.link_group
commit_version = _review.commit_version
cast = _review.cast

# Fixed moments, one minute apart, so *newest first* is never a tie.
EPOCH = datetime(2026, 3, 2, 9, 0, tzinfo=UTC)


def moment(n: int) -> datetime:
    return EPOCH + timedelta(minutes=n)


@pytest.fixture
def written(migrated_tenant: Any) -> Callable[..., Any]:
    """`written(user, event, *, document=None, at=0, facts=None)`: one `Notification` in the
    migrated tenant's schema, its category the event's."""

    def write(
        user: Any, event: str, *, document: Any = None, at: int = 0, facts: Any = None
    ) -> Any:
        from notifications.events import EVENTS
        from notifications.models import Event, Notification

        with schema_context(migrated_tenant.number):
            return Notification.objects.create(
                user=user,
                document=document,
                category=EVENTS[Event(event)].category,
                event=event,
                facts=facts or {},
                created_at=moment(at),
            )

    return write


@pytest.fixture
def written_platform() -> Callable[..., Any]:
    """`written_platform(user, event, *, at=0, facts=None)`: one `PlatformNotification`."""

    def write(user: Any, event: str, *, at: int = 0, facts: Any = None) -> Any:
        from tenancy.models import PlatformNotification

        return PlatformNotification.objects.create(
            user=user, event=event, facts=facts or {}, created_at=moment(at)
        )

    return write
