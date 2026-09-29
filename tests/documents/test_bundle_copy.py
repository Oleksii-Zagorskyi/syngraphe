"""A repository's bundle: written under its writer lock, verified and copied after the lock is
released, full or incremental from the refs recorded last (ADR-0019, DL-0301)."""

from __future__ import annotations

import subprocess
import threading
import uuid
from pathlib import Path
from typing import Any

import pytest

from documents import backup, gitstore
from documents.gitstore import Kind
from documents.identity import identity_for
from documents.locks import document_lock
from identity.models import User

pytestmark = pytest.mark.integration

AUTHOR = User(id=uuid.UUID("00000000-0000-4000-8000-000000000001"), email="a@example.test")
START = "20260929T101000Z"


def _commit(n: int, tag: str | None = None) -> str:
    repo = gitstore.open_repository(3, 12)
    sha = gitstore.commit(
        repo, {"document.md": f"# {n}\n".encode()}, identity_for(AUTHOR), f"v{n}", Kind.EDIT
    )
    if tag:
        gitstore.tag(repo, tag, sha, identity_for(AUTHOR), "edition")
    return sha


def _refs(path: Path) -> dict[str, str]:
    out = subprocess.run(
        ["git", "-C", str(path), "for-each-ref", "--format=%(refname) %(objectname)"],
        capture_output=True,
        check=True,
    ).stdout.decode()
    return dict(line.split(" ") for line in out.splitlines())


def _restore(store: Any, names: list[str], into: Path) -> Path:
    """A clone from the full bundle, then a fetch of each later one, in order."""
    first, *rest = names
    subprocess.run(["git", "clone", "--bare", "-q", str(store.root / first), str(into)], check=True)
    for name in rest:
        subprocess.run(
            ["git", "-C", str(into), "fetch", "-q", str(store.root / name), "+refs/*:refs/*"],
            check=True,
        )
    return into


def test_lock_covers_only_the_write(repo_root: Path, store: Any, tmp_path: Path) -> None:
    gitstore.init(tenant=3, document=12)
    _commit(1, tag="1.0")
    copying, release = threading.Event(), threading.Event()
    put = store.put

    def blocking_put(local: Path, name: str) -> None:
        copying.set()
        assert release.wait(20)
        put(local, name)

    store.put = blocking_put
    result: dict[str, Any] = {}
    worker = threading.Thread(
        target=lambda: result.update(copied=backup.bundle_copy(3, 12, store, START, since=None))
    )
    worker.start()
    assert copying.wait(20)
    # The copy blocks on the store; a writer takes the lock and commits meanwhile.
    with document_lock(3, 12, timeout=5):
        late = _commit(2)
    release.set()
    worker.join(20)

    copied = result["copied"]
    assert copied.name == f"repos/tenant-3/document-12/{START}-full.bundle"
    assert late not in copied.refs.values()
    subprocess.run(["git", "bundle", "verify", "-q", str(store.root / copied.name)], check=True)
    clone = _restore(store, [copied.name], tmp_path / "clone.git")
    assert _refs(clone) == copied.refs


def test_incremental_chain_restores_every_ref(repo_root: Path, store: Any, tmp_path: Path) -> None:
    gitstore.init(tenant=3, document=12)
    _commit(1)
    full = backup.bundle_copy(3, 12, store, START, since=None)
    _commit(2)
    _commit(3, tag="1.1")

    later = backup.bundle_copy(3, 12, store, "20260929T102000Z", since=full.refs)

    assert later.name.endswith("20260929T102000Z.bundle")
    listed = subprocess.run(
        ["git", "bundle", "list-heads", str(store.root / later.name)],
        capture_output=True,
        check=True,
    ).stdout.decode()
    assert "refs/tags/1.1" in listed
    clone = _restore(store, [full.name, later.name], tmp_path / "clone.git")
    assert _refs(clone) == _refs(gitstore.repository_path(3, 12))


def test_a_bundle_that_fails_verification_is_not_copied(
    repo_root: Path, store: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    gitstore.init(tenant=3, document=12)
    _commit(1)

    def broken(*args: Any) -> None:
        raise backup.BundleFailure("verification", "planted")

    monkeypatch.setattr(backup, "_verify", broken)

    with pytest.raises(backup.BundleFailure) as failure:
        backup.bundle_copy(3, 12, store, START, since=None)

    assert failure.value.stage == "verification"
    assert store.puts == []


def test_the_store_names_every_missing_key() -> None:
    from syngraphe.config import ConfigurationError

    with pytest.raises(ConfigurationError) as sftp:
        backup.store_from_environment({"BACKUP_TARGET": "sftp", "BACKUP_SFTP_HOST": "???"})
    with pytest.raises(ConfigurationError) as other:
        backup.store_from_environment({"BACKUP_TARGET": "ftp"})

    assert sftp.value.missing == [
        "BACKUP_BUNDLE_CRYPT_PASSWORD",
        "BACKUP_SFTP_HOST",
        "BACKUP_SFTP_KNOWN_HOSTS",
        "BACKUP_SFTP_PATH",
        "BACKUP_SFTP_USER",
    ]
    assert other.value.malformed == ["BACKUP_TARGET"]


def test_a_repository_comes_back_from_its_chain(
    repo_root: Path, store: Any, state_dir: Path
) -> None:
    import shutil

    gitstore.init(tenant=3, document=12)
    _commit(1)
    backup.run(store, start=START)
    _commit(2, tag="1.1")
    backup.run(store, start="20260929T102000Z")
    before = _refs(gitstore.repository_path(3, 12))
    shutil.rmtree(gitstore.repository_path(3, 12))

    chains = backup.chains_in(store)
    outcome = backup.restore_repository(store, 3, 12, chains[(3, 12)])
    again = backup.restore_repository(store, 3, 12, chains[(3, 12)])

    assert chains[(3, 12)] == [
        f"repos/tenant-3/document-12/{START}-full.bundle",
        "repos/tenant-3/document-12/20260929T102000Z.bundle",
    ]
    assert (outcome, again) == ("restored", "present")
    assert _refs(gitstore.repository_path(3, 12)) == before
