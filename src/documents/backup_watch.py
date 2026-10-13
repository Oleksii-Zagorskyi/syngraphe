"""The operator is told when the backup falls behind (DL-0295, DL-0306).

Three conditions, read from the state volume each minute: a repository failing in the newest
marker, each repository its own; no clean marker newer than fifteen minutes; the log waiting to be
archived past its alert size. Each change is logged once at error level as it is seen, and
announced once as it begins and once as it clears, with numbers and ages, never a title; a change
counts as announced only once its notification is accepted. The notifications commit before the
state file records them, which cannot join their transaction, so a failure between the two
announces the change again: at least once, never lost.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from django.conf import settings

from documents import backup_state

logger = logging.getLogger(__name__)

START_FORMAT = "%Y%m%dT%H%M%SZ"
BEHIND = timedelta(minutes=15)


def _moment(value: Any) -> datetime | None:
    """A time from a state file, or `None` for anything that is not one."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, START_FORMAT).replace(tzinfo=UTC)
    except ValueError:
        return None


def notify_backup_condition(condition: str, change: str, facts: dict[str, Any]) -> bool:
    """Every platform administrator told of a condition's change (DL-0295); `True` once at least
    one was told, `False` with nobody to tell — the watch has logged the change and tries again
    on its next run."""
    from notifications.models import Event
    from notifications.services import notify_platform

    told = notify_platform(
        event=Event.BACKUP_CONDITION, facts={"condition": condition, "change": change, **facts}
    )
    return bool(told)


def conditions(now: datetime) -> dict[str, dict[str, Any] | None]:
    """Each condition's facts while it holds, `None` while it does not; a failing repository is
    the condition `repository_failing:<tenant>:<document>`."""
    run = backup_state.read("run") or {}
    wal = backup_state.read("wal") or {}
    found: dict[str, dict[str, Any] | None] = {}
    marker = run.get("newest_marker") if isinstance(run.get("newest_marker"), dict) else {}
    for failure in (marker or {}).get("failures") or []:
        if not isinstance(failure, dict):
            continue
        since = _moment(failure.get("since"))
        key = f"repository_failing:{failure.get('tenant')}:{failure.get('document')}"
        found[key] = {
            "tenant": _number(failure.get("tenant")),
            "document": _number(failure.get("document")),
            "failing_seconds": int((now - since).total_seconds()) if since else None,
        }
    clean = _moment(run.get("newest_clean"))
    age = int((now - clean).total_seconds()) if clean else None
    found["backup_behind"] = (
        {"clean_marker_age_seconds": age} if age is None or age > BEHIND.total_seconds() else None
    )
    waiting = wal.get("waiting_bytes")
    found["archive_waiting"] = (
        {"wal_waiting_bytes": waiting}
        if isinstance(waiting, int) and waiting > int(settings.BACKUP_WAL_ALERT)
        else None
    )
    return found


def _numbers_of(key: str) -> dict[str, Any]:
    """The numbers a condition's key carries — a failing repository's tenant and document — so a
    clear names what cleared."""
    parts = key.split(":")
    if parts[0] != "repository_failing" or len(parts) != 3:
        return {}
    return {"tenant": _number(parts[1]), "document": _number(parts[2])}


def _number(value: Any) -> int | None:
    """`value` as an integer when it is one, else `None`: a garbled state file carries no text
    into a notification (DL-0370)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _announce(condition: str, change: str, facts: dict[str, Any]) -> bool:
    """`notify_backup_condition`, a failure logged and counted as not delivered, so the run's
    state is written and only this condition is tried again."""
    try:
        return notify_backup_condition(condition, change, facts)
    except Exception:  # noqa: BLE001 — the next run tries again; the others stay announced
        logger.exception("a backup condition was not announced", extra={"condition": condition})
        return False


def check(now: datetime | None = None) -> None:
    """Log every condition whose state changed, and announce what is not yet announced."""
    moment = now or datetime.now(UTC)
    current = conditions(moment)
    with backup_state.updating("run") as state:
        observed: dict[str, bool] = state.setdefault("observed", {})
        announced: dict[str, bool] = state.setdefault("announced", {})
        for key in sorted(set(current) | set(observed) | set(announced)):
            facts = current.get(key)
            holding = facts is not None
            condition = key.split(":", 1)[0]
            if holding != observed.get(key, False):
                logger.error(
                    "the backup's condition changed",
                    extra={
                        "condition": condition,
                        "change": "began" if holding else "cleared",
                        "facts": facts or {},
                    },
                )
                observed[key] = holding
            if holding != announced.get(key, False) and _announce(
                condition, "began" if holding else "cleared", facts or _numbers_of(key)
            ):
                announced[key] = holding
            if not holding and not observed.get(key) and not announced.get(key):
                observed.pop(key, None)
                announced.pop(key, None)


def health_entry(now: datetime | None = None) -> dict[str, Any]:
    """The `backup` entry of `/health/`: whether any repository is failing, never which nor how
    many — the endpoint answers anyone (DL-0295). A value it cannot read is `null`."""
    moment = now or datetime.now(UTC)
    run = backup_state.read("run") or {}
    wal = backup_state.read("wal") or {}
    clean = _moment(run.get("newest_clean"))
    archived = _moment(wal.get("last_archived"))
    waiting = wal.get("waiting_bytes")
    marker = run.get("newest_marker") if isinstance(run.get("newest_marker"), dict) else {}
    return {
        "clean_marker_age_seconds": int((moment - clean).total_seconds()) if clean else None,
        "repositories_failing": bool((marker or {}).get("failures")),
        "last_archived": archived.strftime("%Y-%m-%dT%H:%M:%SZ") if archived else None,
        "wal_waiting_bytes": waiting if isinstance(waiting, int) else None,
    }
