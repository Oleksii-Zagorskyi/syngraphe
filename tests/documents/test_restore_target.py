"""Where a whole-host restore takes the database: always a time, the earlier of the newest clean
marker's start and the last good moment, warned when the archive may end first; the end of the
archive only on the operator's word; a newer marker listing failures named, and chosen only by the
operator (ADR-0019, DL-0294, DL-0314)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from documents import restore

pytestmark = pytest.mark.fast

CLEAN = {"start": "20260929T100000Z", "failures": [], "archived_until": "20260929T100400Z"}
NEWER = {
    "start": "20260929T101000Z",
    "failures": [{"tenant": 2, "document": 7, "stage": "copy", "since": "20260929T101000Z"}],
    "archived_until": "20260929T101300Z",
}
# `pgbackrest verify --verbose`'s summary as pgBackRest 2.59.1 printed it, its log line dropped.
NO_GAP = """stanza: syngraphe
    status: ok
      archiveId: 16-1, total WAL checked: 52, total valid WAL: 52
        missing: 0, checksum invalid: 0, size invalid: 0, other: 0
      backup: 20260929-020001F, status: valid, total files checked: 1481, total valid files: 1481
        missing: 0, checksum invalid: 0, size invalid: 0, other: 0
"""
GAP = (
    NO_GAP.replace("status: ok", "status: error")
    .replace("total valid WAL: 52", "total valid WAL: 49")
    .replace("missing: 0, checksum", "missing: 3, checksum", 1)
)
AT_TEN = {
    "PGBACKREST_TYPE": "time",
    "PGBACKREST_TARGET": "2026-09-29T10:00:00+00",
    "PGBACKREST_TARGET_ACTION": "promote",
}


def test_target_is_the_earliest_of_three() -> None:
    # The markers saw the archive end before the clean marker's start.
    short = {**CLEAN, "archived_until": "20260929T095500Z"}
    first = restore.plan([short], verify=NO_GAP, good=None)
    # The archive reaches past it.
    second = restore.plan([CLEAN], verify=NO_GAP, good=None)
    # A gap in the archive.
    third = restore.plan([CLEAN], verify=GAP, good=None)
    # A newer marker listing a failure.
    fourth = restore.plan([CLEAN, NEWER], verify=NO_GAP, good=None)

    # Recovery never runs to the archive's end on the markers' word: it aims at the time, and
    # warns that the archive may end first.
    assert (first.governs, first.recovery) == ("the newest clean marker", AT_TEN)
    assert first.warnings()
    assert (second.governs, second.recovery, second.warnings()) == (
        "the newest clean marker",
        AT_TEN,
        [],
    )
    assert third.gap and third.recovery == AT_TEN and third.warnings()
    assert fourth.newer == {"start": "20260929T101000Z", "repositories": ["tenant 2 document 7"]}
    assert fourth.governs == "the newest clean marker"


def test_the_end_of_the_archive_only_when_the_operator_says() -> None:
    chosen = restore.plan([CLEAN], verify=GAP, good=None, end_of_archive=True)

    assert (chosen.governs, chosen.recovery) == (
        "the end of the archive",
        {"PGBACKREST_TYPE": "default"},
    )


def test_the_last_good_moment_can_govern() -> None:
    chosen = restore.plan([CLEAN], verify=NO_GAP, good="20260929T095000Z")

    assert chosen.governs == "the last good moment"
    assert chosen.recovery["PGBACKREST_TARGET"] == "2026-09-29T09:50:00+00"


def test_the_operator_may_choose_the_newer_marker() -> None:
    chosen = restore.plan([CLEAN, NEWER], verify=NO_GAP, good=None, marker="20260929T101000Z")

    assert chosen.governs == "the chosen marker"
    assert chosen.recovery["PGBACKREST_TARGET"] == "2026-09-29T10:10:00+00"
    assert chosen.gives_up == ["tenant 2 document 7"]


def test_no_clean_marker_refuses() -> None:
    with pytest.raises(restore.NoTarget):
        restore.plan([NEWER], verify=NO_GAP, good=None)


def test_a_marker_that_is_not_there_refuses() -> None:
    with pytest.raises(restore.NoTarget):
        restore.plan([CLEAN, NEWER], verify=NO_GAP, good=None, marker="20260929T235900Z")


def test_a_garbled_marker_is_ignored() -> None:
    garbled = {"start": "yesterday", "failures": []}

    with_it = restore.plan([CLEAN, garbled], verify=NO_GAP, good=None)
    without = restore.plan([CLEAN], verify=NO_GAP, good=None)

    assert with_it.clean == without.clean


def test_the_plan_prints_all_three_and_ends_with_the_recovery() -> None:
    text = restore.plan([CLEAN, NEWER], verify=NO_GAP, good="20260929T110000Z").describe()

    for expected in (
        "the newest clean marker: 2026-09-29 10:00:00 UTC",
        "the last good moment: 2026-09-29 11:00:00 UTC",
        "the end of the archive: about 2026-09-29 10:13:00 UTC",
        "governs: the newest clean marker",
        "tenant 2 document 7",
    ):
        assert expected in text
    assert text.splitlines()[-1] == (
        "PGBACKREST_TYPE=time PGBACKREST_TARGET=2026-09-29T10:00:00+00 "
        "PGBACKREST_TARGET_ACTION=promote"
    )


FAKE_COMPOSE = """#!/bin/sh
for arg in "$@"; do printf '<%s>' "$arg"; done >> "$CALLS"; echo >> "$CALLS"
case "$*" in
  *backup*verify*) echo "archiveId: 16-1, total WAL checked: 3, total valid WAL: 3";
                   exit "$VERIFY_EXIT" ;;
  *restore_plan*) cat > /dev/null; echo "governs: the newest clean marker";
                  echo "PGBACKREST_TYPE=time PGBACKREST_TARGET=2026-09-29T10:00:00+00" \\
                       "PGBACKREST_TARGET_ACTION=promote" ;;
esac
"""
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "restore-database.sh"


def _script(tmp_path: Path, *argv: str, answer: str = "", verify_exit: int = 0) -> tuple[Any, str]:
    fake = tmp_path / "compose"
    fake.write_text(FAKE_COMPOSE)
    fake.chmod(0o755)
    calls = tmp_path / "calls"
    result = subprocess.run(
        ["sh", str(SCRIPT), *argv],
        input=answer.encode(),
        capture_output=True,
        env={
            "COMPOSE": str(fake),
            "CALLS": str(calls),
            "VERIFY_EXIT": str(verify_exit),
            "PATH": os.environ["PATH"],
        },
    )
    return result, calls.read_text() if calls.exists() else ""


def test_the_dry_run_prints_the_plan_and_writes_nothing(tmp_path: Path) -> None:
    result, logged = _script(tmp_path, "--dry-run", "--good", "20260929T110000Z")

    assert result.returncode == 0, result.stderr.decode()
    # Only the verbose run prints the summary the plan reads.
    assert "verify --verbose" in logged
    assert "governs: the newest clean marker" in result.stdout.decode()
    assert "<--good><20260929T110000Z>" in logged
    assert "--delta restore" not in logged


def test_the_restore_passes_the_target_whole(tmp_path: Path) -> None:
    result, logged = _script(tmp_path, answer="restore\n")

    assert result.returncode == 0, result.stderr.decode()
    restore_call = next(line for line in logged.splitlines() if "--delta restore" in line)
    # pgBackRest reads a time target only with a space between the date and the time: one
    # argument, the space kept.
    assert "<-e><PGBACKREST_TARGET=2026-09-29 10:00:00+00>" in restore_call
    assert "<-e><PGBACKREST_TYPE=time>" in restore_call


def test_nothing_is_written_without_the_word(tmp_path: Path) -> None:
    result, logged = _script(tmp_path, answer="yes\n")

    assert result.returncode == 1
    assert "--delta restore" not in logged


def test_a_failed_verify_stops_the_restore(tmp_path: Path) -> None:
    result, logged = _script(tmp_path, "--dry-run", verify_exit=1)

    assert result.returncode == 1
    assert "restore_plan" not in logged


@pytest.mark.parametrize("argument", ["2026-09-29", "20260929T100000Z; rm -rf /", ""])
def test_the_script_takes_times_only(tmp_path: Path, argument: str) -> None:
    result, logged = _script(tmp_path, "--dry-run", "--good", argument)

    assert result.returncode == 2
    assert logged == ""


def test_a_database_only_restore_needs_no_marker() -> None:
    to_moment = restore.plan([], verify=NO_GAP, good="20260929T095000Z", database_only=True)
    to_end = restore.plan([], verify=NO_GAP, good=None, database_only=True)

    assert to_moment.governs == "the last good moment"
    assert to_moment.recovery["PGBACKREST_TARGET"] == "2026-09-29T09:50:00+00"
    assert (to_end.governs, to_end.recovery) == (
        "the end of the archive",
        {"PGBACKREST_TYPE": "default"},
    )
    assert to_end.describe().splitlines()[-1] == "PGBACKREST_TYPE=default"


@pytest.mark.parametrize(
    ("verify", "gap"),
    [
        (NO_GAP, False),
        (GAP, True),
        (NO_GAP.replace("size invalid: 0", "size invalid: 1"), True),
        (NO_GAP.replace("status: valid", "status: invalid"), True),
        # The default output: log lines and no summary, so nothing shows the archive whole.
        ("P00   INFO: verify command end: completed successfully", True),
    ],
)
def test_the_gap_is_read_from_the_verbose_summary(verify: str, gap: bool) -> None:
    assert restore.gap_in(verify) is gap


def test_the_warning_follows_the_chosen_marker() -> None:
    # The archive ends between the clean marker and the newer one the operator chooses.
    ends_between = {**NEWER, "archived_until": "20260929T100500Z"}

    chosen = restore.plan(
        [CLEAN, ends_between], verify=NO_GAP, good=None, marker="20260929T101000Z"
    )

    assert chosen.recovery["PGBACKREST_TARGET"] == "2026-09-29T10:10:00+00"
    assert chosen.warnings()
