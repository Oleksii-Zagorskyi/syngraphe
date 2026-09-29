"""The single writer lock of a document (DL-0111): the file `tenant-N/document-M.lock` beside its
repository, taken with `flock`, so the `web` and `worker` containers, which mount the same
repository root, and an operator's shell all take the same lock.
"""

from __future__ import annotations

import fcntl
import os
import stat
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from django.conf import settings

POLL_SECONDS = 0.05
# Other accounts on the host cannot enter a tenant's directory, whatever the umask.
DIRECTORY_MODE = 0o750

_held = threading.local()


class LockTimeout(Exception):
    """The lock was not free within the time allowed."""


def checked_number(value: object) -> int:
    """A tenant's or a document's number: a positive integer, never a string or a boolean."""
    if type(value) is not int or value < 1:
        raise ValueError(f"not a number of a tenant or a document: {value!r}")
    return value


def tenant_directory(tenant_number: int) -> Path:
    """`tenant-N` under the repository root, created with `DIRECTORY_MODE` when missing."""
    root = Path(settings.GIT_REPO_ROOT)
    directory = root / f"tenant-{checked_number(tenant_number)}"
    directory.mkdir(mode=DIRECTORY_MODE, parents=False, exist_ok=True)
    return directory


def lock_path(tenant_number: int, document_number: int) -> Path:
    root = Path(settings.GIT_REPO_ROOT)
    return (
        root
        / f"tenant-{checked_number(tenant_number)}"
        / f"document-{checked_number(document_number)}.lock"
    )


def _open(path: Path) -> int:
    """The lock file, never through a symbolic link and never anything but a regular file."""
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o640)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise OSError(f"{path.parent.name}/{path.name} is not a regular file")
    return fd


@contextmanager
def document_lock(
    tenant_number: int, document_number: int, *, timeout: float | None = None
) -> Iterator[None]:
    """Hold the document's writer lock for the block; wait for it, or at most `timeout` seconds.

    The tenant's directory is created when missing: a tenant's first document is locked before its
    repository exists. Taking a lock this thread already holds raises `RuntimeError` rather than
    waiting on itself.
    """
    key = (checked_number(tenant_number), checked_number(document_number))
    held: set[tuple[int, int]] = _held.__dict__.setdefault("keys", set())
    if key in held:
        raise RuntimeError(f"tenant-{key[0]}/document-{key[1]} is already locked by this thread")
    tenant_directory(key[0])
    path = lock_path(*key)
    fd = _open(path)
    try:
        if timeout is None:
            fcntl.flock(fd, fcntl.LOCK_EX)
        else:
            deadline = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise LockTimeout(f"tenant-{key[0]}/document-{key[1]}") from None
                    time.sleep(POLL_SECONDS)
        held.add(key)
        try:
            yield
        finally:
            held.discard(key)
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
