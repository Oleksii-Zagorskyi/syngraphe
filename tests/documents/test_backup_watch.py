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


def test_garbled_state_is_read_as_unknown(state_dir: Path) -> None:
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


def test_the_stub_reports_nothing_delivered() -> None:
    delivered = backup_watch.notify_backup_condition(
        "backup_behind", "began", {"clean_marker_age_seconds": 1200}
    )

    assert delivered is False
