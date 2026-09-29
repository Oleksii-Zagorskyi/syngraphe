"""Housekeeping for many small repositories: a repack and a prune per repository, under its lock.

A library that writes commits never repacks, so each version leaves loose objects. Pruning removes
only unreachable objects, and in an append-only linear history the only unreachable objects are
debris from failed writes: it cannot remove a version (ASR-02, V-08).
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from documents.gitstore import repository_path
from documents.locks import document_lock

# The binary's own configuration is never the operator's: no hooks, no signing, no pager. It is a
# global file of the platform's own, since git reads its ownership exception from no other place:
# the repositories are the application's own, whoever a shared folder reports as their owner.
# In a directory of its own, mode 0700, so no other account can plant or change it.
_CONFIG = Path(tempfile.mkdtemp(prefix="syngraphe-git-")) / "config"
with _CONFIG.open("x", encoding="ascii") as _handle:
    _handle.write("[safe]\n\tdirectory = *\n")
GIT_ENV = {"GIT_CONFIG_GLOBAL": str(_CONFIG), "GIT_CONFIG_NOSYSTEM": "1"}


class HousekeepingFailure(Exception):
    """A git command of the housekeeping failed; the message is git's own, its last lines."""


def git(path: str, *args: str) -> None:
    result = subprocess.run(
        ["git", "-C", path, *args], capture_output=True, env={**os.environ, **GIT_ENV}
    )
    if result.returncode != 0:
        raise HousekeepingFailure(result.stderr.decode(errors="replace").strip()[-300:])


def repack_and_prune(tenant: int, document: int, *, timeout: float | None = None) -> None:
    """Repack one repository and prune what nothing reaches, holding its writer lock."""
    with document_lock(tenant, document, timeout=timeout):
        path = str(repository_path(tenant, document))
        git(path, "repack", "-a", "-d", "-q")
        git(path, "prune", "--expire=now")
