"""The single-writer lock: a file beside the repository, taken with `flock` by every process that
writes (DL-0111)."""

from __future__ import annotations

import fcntl
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from documents import gitstore
from documents.locks import LockTimeout, document_lock, lock_path

pytestmark = pytest.mark.integration

SRC = Path(__file__).resolve().parents[2] / "src"

# One writer: notes that it waits, takes the lock, notes it, commits, then holds the lock until the
# test writes its `go` file (the first writer only), and notes when it lets go.
WRITER = """
import os, sys, time, uuid
import django
django.setup()
from documents import gitstore
from documents.gitstore import Kind
from documents.identity import identity_for
from documents.locks import document_lock
from identity.models import User

name, marks, hold = sys.argv[1], sys.argv[2], sys.argv[3] == "hold"
def mark(what):
    with open(os.path.join(marks, name + "." + what), "w") as f:
        f.write(repr(time.time()))
user = User(id=uuid.UUID(int=len(name)), email="w@example.test")
mark("waiting")
with document_lock(3, 12):
    mark("acquired")
    repo = gitstore.open_repository(3, 12)
    gitstore.commit(repo, {"document.md": name.encode()}, identity_for(user), name, Kind.EDIT)
    while hold and not os.path.exists(os.path.join(marks, "go")):
        time.sleep(0.02)
    mark("released")
"""


def _writer(name: str, marks: Path, root: Path, *, hold: bool) -> subprocess.Popen[bytes]:
    env = {
        **os.environ,
        "GIT_REPO_ROOT": str(root),
        "DJANGO_SETTINGS_MODULE": "syngraphe.settings",
        "PYTHONPATH": str(SRC),
    }
    argv = [sys.executable, "-c", WRITER, name, str(marks), "hold" if hold else "go"]
    return subprocess.Popen(argv, env=env)


def _wait_for(path: Path, seconds: float = 30) -> None:
    deadline = time.monotonic() + seconds
    while not path.exists():
        assert time.monotonic() < deadline, f"{path.name} never appeared"
        time.sleep(0.02)


@contextmanager
def _held_elsewhere(path: Path) -> Iterator[None]:
    """The lock held through a descriptor of its own, as another process would hold it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o640)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def test_two_writers_serialise(repo_root: Path, tmp_path: Path) -> None:
    repo = gitstore.init(tenant=3, document=12)
    marks = tmp_path / "marks"
    marks.mkdir()
    first = _writer("first", marks, repo_root, hold=True)
    second = None
    try:
        _wait_for(marks / "first.acquired")
        second = _writer("second", marks, repo_root, hold=False)
        _wait_for(marks / "second.waiting")
        # The second writer is at the lock while the first still holds it.
        time.sleep(0.5)
        assert not (marks / "second.acquired").exists()
        (marks / "go").write_text("")
        assert first.wait(30) == 0
        assert second.wait(30) == 0
    finally:
        for process in (first, second):
            if process is not None and process.poll() is None:
                process.kill()

    released = float((marks / "first.released").read_text())
    acquired = float((marks / "second.acquired").read_text())
    assert acquired >= released
    head = repo[repo.references["refs/heads/main"].target]
    assert head.message.startswith("second")
    assert repo[head.parents[0].id].message.startswith("first")
    assert not repo[head.parents[0].id].parents


def test_lock_creates_the_tenant_directory(repo_root: Path) -> None:
    with document_lock(7, 1):
        assert (repo_root / "tenant-7" / "document-1.lock").exists()
    assert (repo_root / "tenant-7").stat().st_mode & 0o007 == 0


@pytest.mark.budget
def test_lock_times_out_when_held(repo_root: Path) -> None:
    with _held_elsewhere(lock_path(3, 12)):
        started = time.monotonic()
        with pytest.raises(LockTimeout), document_lock(3, 12, timeout=0.2):
            pass
        elapsed = time.monotonic() - started

    assert 0.2 <= elapsed < 1.0


def test_lock_is_released_when_the_block_raises(repo_root: Path) -> None:
    with pytest.raises(RuntimeError, match="inside"), document_lock(3, 12):
        raise RuntimeError("inside")

    with document_lock(3, 12, timeout=0.1):
        pass


def test_lock_refuses_to_wait_on_itself(repo_root: Path) -> None:
    with document_lock(3, 12), pytest.raises(RuntimeError, match="already locked"):
        with document_lock(3, 12):
            pass


def test_lock_never_follows_a_link(repo_root: Path, tmp_path: Path) -> None:
    (repo_root / "tenant-3").mkdir()
    target = tmp_path / "elsewhere"
    (repo_root / "tenant-3" / "document-12.lock").symlink_to(target)

    with pytest.raises(OSError), document_lock(3, 12):
        pass
    assert not target.exists()


@pytest.mark.parametrize("numbers", [(0, 1), (1, -1), ("3", 12), (True, 1), (3, "../x")])
def test_lock_takes_numbers_only(repo_root: Path, numbers: tuple[object, object]) -> None:
    with pytest.raises(ValueError), document_lock(*numbers):  # type: ignore[arg-type]
        pass


@pytest.mark.skipif(shutil.which("flock") is None, reason="no flock binary on this system")
def test_lock_visible_to_the_shell(repo_root: Path) -> None:
    with document_lock(3, 12):
        path = repo_root / "tenant-3" / "document-12.lock"
        result = subprocess.run(["flock", "-n", str(path), "true"])

    assert result.returncode == 1
