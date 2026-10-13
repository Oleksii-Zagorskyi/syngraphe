"""The backup's three conditions: each change logged once, announced once as it begins and once as
it clears, and counted as announced only once delivery is accepted (DL-0295, DL-0306)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from documents import backup_state, backup_watch

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)


def _stamp(moment: datetime) -> str:
    return moment.strftime("%Y%m%dT%H%M%SZ")


def _marker(age_minutes: int, failures: list[dict[str, Any]] | None = None) -> None:
    start = _stamp(NOW - timedelta(minutes=age_minutes))
    with backup_state.updating("run") as state:
        state["newest_marker"] = {"start": start, "failures": failures or []}
        if not failures:
            state["newest_clean"] = start


def _recording(monkeypatch: pytest.MonkeyPatch, delivered: bool) -> list[tuple[str, str, Any]]:
    calls: list[tuple[str, str, Any]] = []

    def notify(condition: str, change: str, facts: dict[str, Any]) -> bool:
        calls.append((condition, change, facts))
        return delivered

    monkeypatch.setattr(backup_watch, "notify_backup_condition", notify)
    return calls


def test_conditions_notify_on_transition_only(
    state_dir: Path, monkeypatch: pytest.MonkeyPatch, settings: Any
) -> None:
    settings.BACKUP_WAL_ALERT = 1000
    calls = _recording(monkeypatch, delivered=True)
    backup_state.write("wal", {"waiting_bytes": 10, "last_archived": "20260929T115900Z"})

    _marker(age_minutes=20)
    backup_watch.check(now=NOW)
    backup_watch.check(now=NOW + timedelta(minutes=1))
    _marker(age_minutes=0)
    backup_watch.check(now=NOW)
    backup_state.write("wal", {"waiting_bytes": 5000, "last_archived": "20260929T115900Z"})
    backup_watch.check(now=NOW)
    backup_watch.check(now=NOW)
    backup_state.write("wal", {"waiting_bytes": 5, "last_archived": "20260929T115900Z"})
    backup_watch.check(now=NOW)

    assert [(c, change) for c, change, _ in calls] == [
        ("backup_behind", "began"),
        ("backup_behind", "cleared"),
        ("archive_waiting", "began"),
        ("archive_waiting", "cleared"),
    ]
    assert calls[0][2] == {"clean_marker_age_seconds": 1200}
    assert calls[2][2] == {"wal_waiting_bytes": 5000}


def test_an_undelivered_announcement_is_tried_again_and_logged_once(
    state_dir: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    calls = _recording(monkeypatch, delivered=False)
    _marker(age_minutes=20)

    for minute in range(3):
        backup_watch.check(now=NOW + timedelta(minutes=minute))

    assert [c for c, _, _ in calls] == ["backup_behind"] * 3
    changes = [r for r in caplog.records if r.getMessage() == "the backup's condition changed"]
    assert len(changes) == 1 and changes[0].levelname == "ERROR"


def test_each_failing_repository_is_announced_with_numbers(
    state_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _recording(monkeypatch, delivered=True)
    since = _stamp(NOW - timedelta(minutes=30))
    first = {"tenant": 2, "document": 7, "stage": "copy", "since": since}
    second = {"tenant": 2, "document": 8, "stage": "lock", "since": _stamp(NOW)}
    _marker(age_minutes=5)
    _marker(age_minutes=5, failures=[first])
    backup_watch.check(now=NOW)
    _marker(age_minutes=1, failures=[first, second])
    backup_watch.check(now=NOW)

    failing = [(c, change, f) for c, change, f in calls if c == "repository_failing"]
    assert failing == [
        ("repository_failing", "began", {"tenant": 2, "document": 7, "failing_seconds": 1800}),
        ("repository_failing", "began", {"tenant": 2, "document": 8, "failing_seconds": 0}),
    ]


def test_no_state_is_a_backup_behind(state_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _recording(monkeypatch, delivered=True)

    backup_watch.check(now=NOW)

    assert [c for c, _, _ in calls] == ["backup_behind"]


def test_garbled_state_is_read_as_unknown(state_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _recording(monkeypatch, delivered=False)
    backup_state.write("run", {"newest_clean": "yesterday", "newest_marker": "broken"})
    backup_state.write("wal", {"waiting_bytes": "many", "last_archived": 12})

    entry = backup_watch.health_entry(now=NOW)
    backup_watch.check(now=NOW)

    assert entry == {
        "clean_marker_age_seconds": None,
        "repositories_failing": False,
        "last_archived": None,
        "wal_waiting_bytes": None,
    }


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_a_condition_notifies_every_platform_administrator(
    state_dir: Path, migrated_tenant: Any, member_of: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each change, begun and cleared, one notification to each platform administrator in the
    shared schema; an organisation's administrator is told nothing."""
    from identity.models import User
    from notifications.models import Notification
    from tenancy.models import PlatformNotification
    from tenancy.schemas import schema_context

    first = User.objects.create_user("first.p.admin@example.test", is_platform_admin=True)
    second = User.objects.create_user("second.p.admin@example.test", is_platform_admin=True)
    _, tenant_admin, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    calls: list[bool] = []
    original = backup_watch.notify_backup_condition

    def counted(condition: str, change: str, facts: dict[str, Any]) -> bool:
        calls.append(original(condition, change, facts))
        return calls[-1]

    monkeypatch.setattr(backup_watch, "notify_backup_condition", counted)
    _marker(age_minutes=20)
    backup_watch.check(NOW)
    _marker(age_minutes=5)
    backup_watch.check(NOW)

    assert calls == [True, True]
    with schema_context(None):
        rows = list(PlatformNotification.objects.order_by("created_at", "user__email"))
    assert {(row.user_id, row.facts["change"]) for row in rows} == {
        (first.pk, "began"),
        (second.pk, "began"),
        (first.pk, "cleared"),
        (second.pk, "cleared"),
    }
    assert {row.facts["condition"] for row in rows} == {"backup_behind"}
    with schema_context(migrated_tenant.number):
        assert not Notification.objects.filter(user=tenant_admin).exists()


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_nothing_delivered_without_a_platform_administrator(
    state_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """With nobody to tell, nothing is delivered and the watch logs the change as before."""
    from tenancy.models import PlatformNotification

    delivered = backup_watch.notify_backup_condition(
        "backup_behind", "began", {"clean_marker_age_seconds": 1200}
    )
    assert delivered is False
    _marker(age_minutes=20)
    backup_watch.check(now=NOW)

    assert not PlatformNotification.objects.exists()
    changes = [r for r in caplog.records if r.getMessage() == "the backup's condition changed"]
    assert len(changes) == 1 and changes[0].levelname == "ERROR"


def test_a_failure_to_tell_one_condition_repeats_no_other(
    state_dir: Path, monkeypatch: pytest.MonkeyPatch, settings: Any
) -> None:
    """A condition whose telling raises is logged and tried again on the next run; the one told
    before it in the same run is not told twice."""
    settings.BACKUP_WAL_ALERT = 1000
    told: list[str] = []

    def notify(condition: str, change: str, facts: dict[str, Any]) -> bool:
        if condition == "backup_behind" and len(told) < 2:
            told.append("refused")
            raise RuntimeError("synthetic failure")
        told.append(condition)
        return True

    monkeypatch.setattr(backup_watch, "notify_backup_condition", notify)
    _marker(age_minutes=20)
    with backup_state.updating("wal") as wal:
        wal["waiting_bytes"] = 5000
    backup_watch.check(NOW)
    backup_watch.check(NOW)

    assert told.count("archive_waiting") == 1
    assert told.count("backup_behind") == 1


def test_a_cleared_failure_names_its_repository_by_number(
    state_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _recording(monkeypatch, delivered=True)
    failing = [{"tenant": 3, "document": 7, "since": _stamp(NOW - timedelta(minutes=5))}]
    _marker(age_minutes=5, failures=failing)
    backup_watch.check(NOW)
    _marker(age_minutes=5)
    backup_watch.check(NOW)

    cleared = [facts for condition, change, facts in calls if change == "cleared"]
    assert {"tenant": 3, "document": 7}.items() <= cleared[-1].items()


def test_a_garbled_failure_carries_no_value_but_numbers(
    state_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _recording(monkeypatch, delivered=True)
    failing = [{"tenant": "Синтетична назва", "document": [1], "since": "broken"}]
    _marker(age_minutes=5, failures=failing)
    backup_watch.check(NOW)

    [(condition, change, facts)] = [c for c in calls if c[0] == "repository_failing"]
    assert facts["tenant"] is None and facts["document"] is None
