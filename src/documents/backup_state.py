"""The backup's state, three small JSON files on the state volume (ADR-0019, DL-0305).

`base-backup` — the newest base backup's label and stop time, written by the `backup` service.
`wal` — the log waiting to be archived and the time of the last segment archived, written by
`backup` every minute. `run` — the newest marker and its failures, the newest clean marker, and
the conditions already observed and announced, written by the worker. Each writer has a folder of
its own, and each file is written to a temporary name and renamed, so a reader sees a whole file
or the previous one.
"""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from django.conf import settings

# Each file in its writer's own folder: the `backup` service's, and the worker's.
NAMES = {"base-backup": "backup", "wal": "backup", "run": "worker"}


def _path(name: str) -> Path:
    if name not in NAMES:
        raise ValueError(f"no state file {name!r}")
    return Path(settings.BACKUP_STATE_DIR) / NAMES[name] / name


def folder_ready(name: str) -> bool:
    """Whether the writer's folder is there, made now if the volume lets this process make it.
    The `backup` service makes the worker's folder, so the worker can start before it exists."""
    try:
        _path(name).parent.mkdir(exist_ok=True)
    except PermissionError:
        return False
    return True


def read(name: str) -> dict[str, Any] | None:
    """The file's content, or `None` when it is absent or unreadable."""
    try:
        data = json.loads(_path(name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def write(name: str, data: dict[str, Any]) -> None:
    """Replace the file whole."""
    path = _path(name)
    path.parent.mkdir(exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


@contextmanager
def updating(name: str) -> Iterator[dict[str, Any]]:
    """Read, change and write one file with no other writer in between; the worker's run and its
    watch both change `run`."""
    lock = _path(name).with_name(f".{name}.lock")
    lock.parent.mkdir(exist_ok=True)
    fd = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o640)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        data = read(name) or {}
        yield data
        write(name, data)
    finally:
        os.close(fd)
