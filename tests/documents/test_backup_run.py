"""The ten-minute bundle run: only what moved, a marker every time listing what failed, full
bundles after a new base backup until each lands, two chains kept per repository (ADR-0019)."""

from __future__ import annotations

import fcntl
import json
import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from documents import backup, backup_state, gitstore
from documents.gitstore import Kind
from documents.identity import identity_for
from documents.locks import document_lock, lock_path
from identity.models import User

pytestmark = pytest.mark.integration

AUTHOR = User(id=uuid.UUID("00000000-0000-4000-8000-000000000001"), email="a@example.test")
T = [f"20260929T10{m:02d}00Z" for m in range(0, 60, 10)]


def _document(tenant: int, number: int) -> None:
    repo = gitstore.init(tenant=tenant, document=number)
    gitstore.commit(repo, {"document.md": b"# 1\n"}, identity_for(AUTHOR), "v1", Kind.CREATED)


def _commit(tenant: int, number: int, text: str) -> None:
    repo = gitstore.open_repository(tenant, number)
    with document_lock(tenant, number):
        gitstore.commit(
            repo, {"document.md": text.encode()}, identity_for(AUTHOR), "edit", Kind.EDIT
        )


@contextmanager
def _held_elsewhere(tenant: int, number: int) -> Iterator[None]:
    """The writer lock held as another process holds it: through a descriptor of its own."""
    fd = os.open(lock_path(tenant, number), os.O_RDWR | os.O_CREAT, 0o640)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def _marker(store: Any, start: str) -> dict[str, Any]:
    marker: dict[str, Any] = json.loads(store.get(f"repos/complete/{start}"))
    return marker


def _bundles(store: Any, tenant: int, number: int) -> list[str]:
    return [n.rsplit("/", 1)[1] for n in store.names(f"repos/tenant-{tenant}/document-{number}/")]


def test_run_bundles_only_what_moved(repo_root: Path, store: Any, state_dir: Path) -> None:
    for number in (1, 2, 3):
        _document(1, number)
    backup.run(store, start=T[0])
    before = {n: (repo_root / "tenant-1" / f"document-{n}.bundled").read_text() for n in (1, 2, 3)}
    _commit(1, 2, "# 2\n")

    result = backup.run(store, start=T[1])

    assert result is not None
    assert [(b.tenant, b.document) for b in result.bundled] == [(1, 2)]
    assert _marker(store, T[1]) == {"start": T[1], "failures": []}
    after = {n: (repo_root / "tenant-1" / f"document-{n}.bundled").read_text() for n in (1, 2, 3)}
    assert after[1] == before[1] and after[3] == before[3] and after[2] != before[2]
    assert _bundles(store, 1, 2) == [f"{T[0]}-full.bundle", f"{T[1]}.bundle"]
    run_state = backup_state.read("run")
    assert run_state is not None
    assert run_state["newest_marker"] == {"start": T[1], "failures": []}
    assert run_state["newest_clean"] == T[1]


def test_empty_run_writes_its_marker(repo_root: Path, store: Any, state_dir: Path) -> None:
    _document(1, 1)
    backup.run(store, start=T[0])
    puts = len(store.puts)

    backup.run(store, start=T[1])

    assert store.puts[puts:] == [f"repos/complete/{T[1]}"]
    assert _marker(store, T[1])["failures"] == []


def test_failures_are_listed_and_retried(
    repo_root: Path, store: Any, state_dir: Path, monkeypatch: pytest.MonkeyPatch, settings: Any
) -> None:
    settings.BACKUP_LOCK_TIMEOUT = 0.2
    _document(1, 1)
    _document(1, 2)
    backup.run(store, start=T[0])
    _commit(1, 1, "# 2\n")
    _commit(1, 2, "# 2\n")
    real_verify = backup._verify

    def fails_for_one(path: Path, bundle: Path) -> None:
        if path.name == "document-1":
            raise backup.BundleFailure("verification", "planted")
        real_verify(path, bundle)

    monkeypatch.setattr(backup, "_verify", fails_for_one)
    bundled_before = (repo_root / "tenant-1" / "document-1.bundled").read_text()

    backup.run(store, start=T[1])

    assert _marker(store, T[1])["failures"] == [
        {"tenant": 1, "document": 1, "stage": "verification", "since": T[1]}
    ]
    assert (repo_root / "tenant-1" / "document-1.bundled").read_text() == bundled_before
    assert not any(n.endswith(f"{T[1]}.bundle") for n in _bundles(store, 1, 1))

    # A second run while one holds the run lock does not start.
    with backup.run_lock() as held:
        assert held
        assert backup.run(store, start=T[2]) is None
    assert not store.names(f"repos/complete/{T[2]}")

    # The first repository still fails, and keeps the start of its failures.
    backup.run(store, start=T[3])
    assert _marker(store, T[3])["failures"] == [
        {"tenant": 1, "document": 1, "stage": "verification", "since": T[1]}
    ]

    # The first recovers; the second moved, and its lock is held past the timeout.
    monkeypatch.setattr(backup, "_verify", real_verify)
    _commit(1, 2, "# 3\n")
    with _held_elsewhere(1, 2):
        backup.run(store, start=T[4])
    assert _marker(store, T[4])["failures"] == [
        {"tenant": 1, "document": 2, "stage": "lock", "since": T[4]}
    ]
    assert _bundles(store, 1, 1)[-1] == f"{T[4]}.bundle"

    backup.run(store, start=T[5])
    assert _marker(store, T[5])["failures"] == []
    assert _bundles(store, 1, 2)[-1] == f"{T[5]}.bundle"


def test_new_base_backup_starts_new_chains_until_each_lands(
    repo_root: Path, store: Any, state_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for number in (1, 2, 3):
        _document(1, number)
    backup.run(store, start=T[0])
    backup_state.write("base-backup", {"label": "20260929-100500F", "stop": "20260929T100500Z"})
    real_verify = backup._verify
    failed: list[str] = []

    def fails_once(path: Path, bundle: Path) -> None:
        if path.name == "document-3" and not failed:
            failed.append(path.name)
            raise backup.BundleFailure("verification", "planted")
        real_verify(path, bundle)

    monkeypatch.setattr(backup, "_verify", fails_once)

    backup.run(store, start=T[1])
    first = {n: _bundles(store, 1, n)[-1] for n in (1, 2, 3)}
    backup.run(store, start=T[2])

    assert first[1] == first[2] == f"{T[1]}-full.bundle"
    assert first[3] == f"{T[0]}-full.bundle"
    assert [f["document"] for f in _marker(store, T[1])["failures"]] == [3]
    assert _bundles(store, 1, 3)[-1] == f"{T[2]}-full.bundle"
    assert _bundles(store, 1, 1)[-1] == f"{T[1]}-full.bundle"
    assert _marker(store, T[2])["failures"] == []


def test_retention_keeps_two_chains_and_never_the_newest(
    repo_root: Path, store: Any, state_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _document(1, 1)
    _document(1, 2)
    backup.run(store, start=T[0])
    backup_state.write("base-backup", {"label": "b1", "stop": "20260929T100500Z"})
    backup.run(store, start=T[1])
    _commit(1, 1, "# 2\n")
    _commit(1, 2, "# 2\n")
    backup.run(store, start=T[2])
    # Each repository now holds two chains: T0's, and T1's with T2's increment.
    backup_state.write("base-backup", {"label": "b2", "stop": "20260929T102500Z"})
    real_verify = backup._verify

    def second_fails(path: Path, bundle: Path) -> None:
        if path.name == "document-2":
            raise backup.BundleFailure("verification", "planted")
        real_verify(path, bundle)

    monkeypatch.setattr(backup, "_verify", second_fails)
    second_before = _bundles(store, 1, 2)

    backup.run(store, start=T[3])

    assert _bundles(store, 1, 1) == [
        f"{T[1]}-full.bundle",
        f"{T[2]}.bundle",
        f"{T[3]}-full.bundle",
    ]
    assert second_before == [f"{T[0]}-full.bundle", f"{T[1]}-full.bundle", f"{T[2]}.bundle"]
    assert _bundles(store, 1, 2) == second_before


def test_a_repository_that_cannot_be_read_is_a_failure(
    repo_root: Path, store: Any, state_dir: Path
) -> None:
    _document(1, 1)
    _document(1, 2)
    (repo_root / "tenant-1" / "document-2" / "HEAD").write_text("not a ref\n")

    backup.run(store, start=T[0])

    assert _marker(store, T[0])["failures"] == [
        {"tenant": 1, "document": 2, "stage": "read", "since": T[0]}
    ]
    assert _bundles(store, 1, 1) == [f"{T[0]}-full.bundle"]


def test_an_error_outside_the_bundle_never_stops_the_run(
    repo_root: Path, store: Any, state_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _document(1, 1)
    _document(1, 2)
    real_record = backup._record

    def full_disk(tenant: int, document: int, data: dict[str, Any]) -> None:
        if document == 1:
            raise OSError("no space left on device")
        real_record(tenant, document, data)

    monkeypatch.setattr(backup, "_record", full_disk)

    backup.run(store, start=T[0])

    assert _marker(store, T[0])["failures"] == [
        {"tenant": 1, "document": 1, "stage": "run", "since": T[0]}
    ]
    assert (repo_root / "tenant-1" / "document-2.bundled").exists()


def test_a_marker_the_store_refuses_leaves_the_backup_behind(
    repo_root: Path, store: Any, state_dir: Path
) -> None:
    _document(1, 1)
    backup.run(store, start=T[0])
    put = store.put

    def refuses_markers(local: Path, name: str) -> None:
        if name.startswith("repos/complete/"):
            raise RuntimeError("the store is unreachable")
        put(local, name)

    store.put = refuses_markers

    with pytest.raises(RuntimeError):
        backup.run(store, start=T[1])

    state = backup_state.read("run")
    assert state is not None
    assert state["newest_marker"]["start"] == T[1]
    assert state["newest_clean"] == T[0]


def test_a_truncated_bundle_fails_verification(repo_root: Path, tmp_path: Path) -> None:
    import subprocess

    _document(1, 1)
    path = gitstore.repository_path(1, 1)
    bundle = tmp_path / "b.bundle"
    subprocess.run(
        ["git", "-C", str(path), "bundle", "create", "-q", str(bundle), "--all"], check=True
    )
    data = bundle.read_bytes()
    bundle.write_bytes(data[: len(data) - 40])

    with pytest.raises(backup.BundleFailure) as failure:
        backup._verify(path, bundle)

    assert failure.value.stage == "verification"


def test_a_store_that_cannot_be_listed_is_never_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    rclone = backup.RcloneStore({})

    def unreachable(*args: str) -> bytes:
        raise RuntimeError("couldn't connect SSH: handshake failed")

    def missing(*args: str) -> bytes:
        raise RuntimeError("error listing: directory not found")

    monkeypatch.setattr(rclone, "_rclone", unreachable)
    with pytest.raises(RuntimeError):
        rclone.names("repos/")
    monkeypatch.setattr(rclone, "_rclone", missing)
    assert rclone.names("repos/") == []


def test_markers_older_than_every_kept_chain_are_deleted(
    repo_root: Path, store: Any, state_dir: Path
) -> None:
    _document(1, 1)
    _document(1, 2)
    backup.run(store, start=T[0])
    backup_state.write("base-backup", {"label": "b1", "stop": "20260929T100500Z"})
    backup.run(store, start=T[1])
    _commit(1, 1, "# 2\n")
    backup.run(store, start=T[2])
    backup_state.write("base-backup", {"label": "b2", "stop": "20260929T102500Z"})

    backup.run(store, start=T[3])

    # T0's chains are gone from both repositories, and its marker with them (DL-0316).
    assert store.names("repos/complete/") == [f"repos/complete/{t}" for t in T[1:4]]


def test_the_newest_clean_marker_is_never_deleted(store: Any, state_dir: Path) -> None:
    for t in T[:4]:
        (store.root / "repos" / "complete").mkdir(parents=True, exist_ok=True)
        (store.root / "repos" / "complete" / t).write_text("{}")
    chain = store.root / "repos" / "tenant-1" / "document-1"
    chain.mkdir(parents=True)
    (chain / f"{T[2]}-full.bundle").write_bytes(b"")
    backup_state.write("run", {"newest_clean": T[0]})

    backup._retain_markers(store)

    assert store.names("repos/complete/") == [f"repos/complete/{t}" for t in (T[0], T[2], T[3])]


@pytest.mark.skipif(os.geteuid() == 0, reason="root makes any folder")
def test_the_worker_waits_for_its_state_folder(
    repo_root: Path, store: Any, state_dir: Path
) -> None:
    from documents import tasks

    _document(1, 1)
    # The volume as it is before the `backup` service has made the worker's folder.
    state_dir.chmod(0o555)
    try:
        skipped = backup.run(store, start=T[0])
        tasks.watch_backup()
    finally:
        state_dir.chmod(0o755)

    assert skipped is None
    assert store.puts == []
