"""Repack and prune per repository under its lock: in an append-only linear history the only
unreachable objects are debris from failed writes, so pruning cannot remove a version (ASR-02)."""

from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path

import pytest

from documents import gitstore, housekeeping
from documents.gitstore import Kind
from documents.identity import identity_for
from identity.models import User

pytestmark = pytest.mark.integration

AUTHOR = User(id=uuid.UUID("00000000-0000-4000-8000-000000000001"), email="a@example.test")


def _git(repo: Path, *args: str, stdin: bytes | None = None) -> str:
    env = {
        "GIT_AUTHOR_NAME": "x",
        "GIT_AUTHOR_EMAIL": "x@example.test",
        "GIT_COMMITTER_NAME": "x",
        "GIT_COMMITTER_EMAIL": "x@example.test",
        "PATH": os.environ["PATH"],
    }
    result = subprocess.run(
        ["git", "-C", str(repo), *args], input=stdin, capture_output=True, check=True, env=env
    )
    return result.stdout.decode().strip()


def test_prune_keeps_every_version(repo_root: Path) -> None:
    repo = gitstore.init(tenant=3, document=12)
    for n in range(5):
        sha = gitstore.commit(
            repo, {"document.md": f"# {n}\n".encode()}, identity_for(AUTHOR), f"v{n}", Kind.EDIT
        )
        if n % 2:
            gitstore.tag(repo, f"1.{n}", sha, identity_for(AUTHOR), "edition")
    path = Path(repo.path)
    blob = _git(path, "hash-object", "-w", "--stdin", stdin=b"debris of a failed write\n")
    tree = _git(path, "rev-parse", "main^{tree}")
    dangling = _git(path, "commit-tree", tree, "-m", "never referenced")
    reachable = set(_git(path, "rev-list", "--objects", "--all").split("\n"))

    housekeeping.repack_and_prune(3, 12)

    assert set(_git(path, "rev-list", "--objects", "--all").split("\n")) == reachable
    _git(path, "fsck", "--strict", "--no-dangling")
    for gone in (blob, dangling):
        missing = subprocess.run(["git", "-C", str(path), "cat-file", "-e", gone])
        assert missing.returncode != 0
    assert list(gitstore.history(gitstore.open_repository(3, 12)))[-1].message.startswith("v4")


def test_housekeeping_waits_for_the_writer(repo_root: Path) -> None:
    import fcntl
    import os

    from documents.locks import LockTimeout, lock_path

    gitstore.init(tenant=3, document=12)
    # Held as another process holds it: a descriptor of its own.
    fd = os.open(lock_path(3, 12), os.O_RDWR | os.O_CREAT, 0o640)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        with pytest.raises(LockTimeout):
            housekeeping.repack_and_prune(3, 12, timeout=0.1)
    finally:
        os.close(fd)


def test_the_nightly_task_visits_every_repository(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from documents import tasks

    for tenant, document in ((1, 1), (1, 2), (4, 7)):
        gitstore.init(tenant=tenant, document=document)
    seen: list[tuple[int, int]] = []
    monkeypatch.setattr(housekeeping, "repack_and_prune", lambda t, d, **_: seen.append((t, d)))

    tasks.repack_nightly()

    assert sorted(seen) == [(1, 1), (1, 2), (4, 7)]
