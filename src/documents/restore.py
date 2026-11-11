"""The target of a whole-host restore of the database (ADR-0019, DL-0294, DL-0314).

Always a time: the earlier of the newest clean marker's start and the last moment known to be
good. The end of the archive is known only roughly — the markers record when a segment was last
archived, and `pgbackrest verify` shows a damaged or missing file a backup needs, not a segment
missing between two that are present (DL-0545) — so it never sets the target; it only warns.
When PostgreSQL then ends recovery before reaching the time, the operator runs again to the end
of the archive (DL-0314). A newer marker that lists failures is named; the
operator alone may choose it, giving up the repositories it lists.

The plan's last line holds each variable as one word, a time target as `YYYY-MM-DDTHH:MM:SS+00`;
`scripts/restore-database.sh` passes it to pgBackRest with a space in place of the `T`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

START_FORMAT = "%Y%m%dT%H%M%SZ"
# `pgbackrest verify --verbose` prints a summary per archive and per backup: what it checked, what
# was valid, four counts of what was wrong, and a status (pgBackRest 2.59; the default output
# prints no summary at all).
VERIFY_COUNTS = re.compile(r"total (?:WAL|files) checked: (\d+), total valid (?:WAL|files): (\d+)")
VERIFY_FAULTS = re.compile(r"(?:missing|checksum invalid|size invalid|other): (\d+)")
VERIFY_STATUS = re.compile(r"status: (\S+)")


class NoTarget(Exception):
    """No point the database may be restored to without passing the repositories."""


def _moment(start: str) -> datetime:
    return datetime.strptime(start, START_FORMAT).replace(tzinfo=UTC)


def _shown(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%d %H:%M:%S UTC")


def shown(start: str) -> str:
    """A marker's start as an operator reads it."""
    try:
        return _shown(_moment(start))
    except ValueError:
        return start


def _repositories(marker: dict[str, Any]) -> list[str]:
    return [f"tenant {f['tenant']} document {f['document']}" for f in marker.get("failures", [])]


def gap_in(verify: str) -> bool:
    """Whether `pgbackrest verify --verbose`'s summary fails to show the archive whole: anything
    counted wrong, a status other than `ok` or `valid`, or no summary to read."""
    counts = VERIFY_COUNTS.findall(verify)
    if not counts:
        return True
    statuses = [status.rstrip(",") for status in VERIFY_STATUS.findall(verify)]
    return (
        any(int(checked) != int(valid) for checked, valid in counts)
        or any(int(n) for n in VERIFY_FAULTS.findall(verify))
        or any(status not in ("ok", "valid") for status in statuses)
    )


@dataclass
class Plan:
    clean: datetime
    good: datetime | None
    archive_end: datetime | None
    gap: bool
    governs: str
    recovery: dict[str, str]
    newer: dict[str, Any] | None = None
    gives_up: list[str] = field(default_factory=list)
    database_only: bool = False
    # The time recovery aims at; `None` when it runs to the end of the archive.
    target: datetime | None = None

    def warnings(self) -> list[str]:
        if self.target is None:
            return []
        if not (self.gap or (self.archive_end is not None and self.archive_end < self.target)):
            return []
        return [
            "the archive may end before this target"
            + (" (`pgbackrest verify` does not show the archive whole)" if self.gap else "")
            + ": if PostgreSQL stops with `recovery ended before configured recovery target was"
            " reached`, run this again with --end-of-archive"
        ]

    def describe(self) -> str:
        if self.database_only:
            return "\n".join(
                [
                    "a database-only restore: the repositories on the host bound nothing",
                    "the last good moment: "
                    + (_shown(self.good) if self.good else "not given — the end of the archive"),
                    f"governs: {self.governs}",
                    " ".join(f"{key}={value}" for key, value in self.recovery.items()),
                ]
            )
        lines = [
            f"the newest clean marker: {_shown(self.clean)}",
            "the last good moment: "
            + (_shown(self.good) if self.good else "not given (--good to give one)"),
            "the end of the archive: "
            + (
                f"about {_shown(self.archive_end)}, by the markers"
                if self.archive_end
                else "not known from the markers"
            )
            + ("; `pgbackrest verify` does not show it whole" if self.gap else ""),
            f"governs: {self.governs}",
            *self.warnings(),
        ]
        if self.newer:
            lines.append(
                f"a newer marker, {_shown(_moment(self.newer['start']))}, lists failures: "
                + ", ".join(self.newer["repositories"])
                + f" — --marker {self.newer['start']} aims at it, and those repositories lose"
                " their commits since their last bundle"
            )
        if self.gives_up:
            lines.append("given up by the chosen marker: " + ", ".join(self.gives_up))
        lines.append(" ".join(f"{key}={value}" for key, value in self.recovery.items()))
        return "\n".join(lines)


def plan(
    markers: list[dict[str, Any]],
    *,
    verify: str,
    good: str | None,
    marker: str | None = None,
    end_of_archive: bool = False,
    database_only: bool = False,
) -> Plan:
    """Where to restore the database to, from the markers in the store and `pgbackrest verify`.

    `database_only` is the restore of a database whose repositories are intact on the host: no
    marker bounds it, and it recovers to the last good moment, or else to the end of the archive.
    """
    if database_only:
        good_moment = _moment(good) if good else None
        moment_only = good_moment is not None and not end_of_archive
        return Plan(
            clean=good_moment or datetime.min.replace(tzinfo=UTC),
            good=good_moment,
            archive_end=None,
            gap=gap_in(verify),
            governs="the last good moment" if moment_only else "the end of the archive",
            recovery=(
                {
                    "PGBACKREST_TYPE": "time",
                    "PGBACKREST_TARGET": good_moment.strftime("%Y-%m-%dT%H:%M:%S+00"),
                    "PGBACKREST_TARGET_ACTION": "promote",
                }
                if good_moment is not None and not end_of_archive
                else {"PGBACKREST_TYPE": "default"}
            ),
            database_only=True,
            target=good_moment if moment_only else None,
        )
    ordered = sorted(
        (m for m in markers if isinstance(m.get("start"), str) and _valid(m["start"])),
        key=lambda m: m["start"],
    )
    clean = [m for m in ordered if not m.get("failures")]
    if marker is not None:
        chosen = next((m for m in ordered if m["start"] == marker), None)
        if chosen is None:
            raise NoTarget(f"no marker {marker}")
    elif clean:
        chosen = clean[-1]
    else:
        raise NoTarget("no clean marker; nothing bounds the database by the repositories")
    newest_clean = clean[-1] if clean else chosen
    ends = [m["archived_until"] for m in ordered if _valid(m.get("archived_until"))]
    good_moment = _moment(good) if good else None
    bound, governs = (
        _moment(chosen["start"]),
        ("the chosen marker" if marker else "the newest clean marker"),
    )
    if good_moment is not None and good_moment < bound:
        bound, governs = good_moment, "the last good moment"
    if end_of_archive:
        governs = "the end of the archive"
        recovery = {"PGBACKREST_TYPE": "default"}
    else:
        recovery = {
            "PGBACKREST_TYPE": "time",
            "PGBACKREST_TARGET": bound.strftime("%Y-%m-%dT%H:%M:%S+00"),
            "PGBACKREST_TARGET_ACTION": "promote",
        }
    newer_markers = [m for m in ordered if m["start"] > newest_clean["start"] and m.get("failures")]
    newer = (
        {"start": newer_markers[-1]["start"], "repositories": _repositories(newer_markers[-1])}
        if newer_markers and marker is None
        else None
    )
    return Plan(
        clean=_moment(newest_clean["start"]),
        good=good_moment,
        archive_end=_moment(max(ends)) if ends else None,
        gap=gap_in(verify),
        governs=governs,
        recovery=recovery,
        newer=newer,
        gives_up=_repositories(chosen) if marker else [],
        target=None if end_of_archive else bound,
    )


def _valid(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        _moment(value)
    except ValueError:
        return False
    return True
