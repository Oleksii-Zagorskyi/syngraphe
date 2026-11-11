"""The repositories' backup: a `git bundle` of each repository that moved, every ten minutes, and a
marker for every run listing what failed (ADR-0018, ADR-0019).

The writer lock is held only while a bundle file is written; the bundle is verified and copied
after it is released, and the refs it holds are recorded beside the repository only once the copy
is confirmed (DL-0301). A repository with no full bundle since the newest base backup gets one on
every run until one lands, and each repository keeps its newest two chains (DL-0299, DL-0303). A
marker is kept until it is older than the oldest chain any repository keeps (DL-0316).
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from django.conf import settings

from documents import backup_state, gitstore
from documents.housekeeping import GIT_ENV
from documents.locks import LockTimeout, document_lock

logger = logging.getLogger(__name__)

START_FORMAT = "%Y%m%dT%H%M%SZ"
START = re.compile(r"^[0-9]{8}T[0-9]{6}Z$")
MARKERS = "repos/complete/"
CHAINS_KEPT = 2


class Store(Protocol):
    """Where the bundles and markers go; its names are paths under one root."""

    def put(self, local: Path, name: str) -> None: ...

    def names(self, prefix: str) -> list[str]: ...

    def get(self, name: str) -> bytes: ...

    def delete(self, name: str) -> None: ...


class BundleFailure(Exception):
    """A repository's bundle failed at one stage: `lock`, `write`, `verification` or `copy`."""

    def __init__(self, stage: str, reason: str) -> None:
        super().__init__(f"{stage}: {reason}")
        self.stage = stage


@dataclass(frozen=True)
class Bundled:
    tenant: int
    document: int
    name: str
    refs: dict[str, str]
    full: bool


@dataclass
class RunResult:
    start: str
    bundled: list[Bundled] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)


def now() -> str:
    return datetime.now(UTC).strftime(START_FORMAT)


def _git(path: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(path), *args],
        capture_output=True,
        env={**os.environ, **GIT_ENV},
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode(errors="replace").strip())
    return result.stdout


def refs_of(path: Path) -> dict[str, str]:
    """Every ref of a repository and the object it names."""
    out = _git(path, "for-each-ref", "--format=%(refname) %(objectname)").decode()
    return dict(line.split(" ", 1) for line in out.splitlines() if line)


def _recorded_path(tenant: int, document: int) -> Path:
    return gitstore.repository_path(tenant, document).with_name(f"document-{document}.bundled")


def recorded(tenant: int, document: int) -> dict[str, Any] | None:
    """The refs of the newest bundle that reached the store, and the start of its chain."""
    try:
        data = json.loads(_recorded_path(tenant, document).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _record(tenant: int, document: int, data: dict[str, Any]) -> None:
    path = _recorded_path(tenant, document)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def _verify(path: Path, bundle: Path) -> None:
    """The bundle read whole: `git bundle verify` checks its header and that the repository holds
    its prerequisites, and `git index-pack` reads every object of its pack and the pack's checksum,
    in a scratch repository that borrows the source's objects for a thin pack's bases."""
    try:
        _git(path, "bundle", "verify", "-q", str(bundle))
        data = bundle.read_bytes()
        _, separator, pack = data.partition(b"\n\n")
        if not separator or not pack.startswith(b"PACK"):
            raise RuntimeError("a bundle with no pack")
        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory) / "scratch.git"
            subprocess.run(
                ["git", "init", "-q", "--bare", str(scratch)],
                check=True,
                capture_output=True,
                env={**os.environ, **GIT_ENV},
            )
            (scratch / "objects" / "info" / "alternates").write_text(
                str(path / "objects") + "\n", encoding="utf-8"
            )
            result = subprocess.run(
                ["git", "-C", str(scratch), "index-pack", "--stdin", "--fix-thin", "--strict"],
                input=pack,
                capture_output=True,
                env={**os.environ, **GIT_ENV},
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.decode(errors="replace").strip())
    except (RuntimeError, subprocess.CalledProcessError) as error:
        raise BundleFailure("verification", str(error)[-300:]) from error


def bundle_copy(
    tenant: int,
    document: int,
    store: Store,
    start: str,
    since: dict[str, str] | None = None,
    *,
    lock_timeout: float | None = None,
) -> Bundled:
    """Bundle one repository — whole, or what its refs gained since `since` — and copy it.

    Raises `BundleFailure` naming the stage; nothing is copied after a failed verification.
    """
    path = gitstore.repository_path(tenant, document)
    full = not since
    name = f"repos/tenant-{tenant}/document-{document}/{start}{'-full' if full else ''}.bundle"
    with tempfile.TemporaryDirectory() as directory:
        bundle = Path(directory) / "repository.bundle"
        try:
            with document_lock(tenant, document, timeout=lock_timeout):
                refs = refs_of(path)
                excluded = [f"^{sha}" for sha in sorted(set((since or {}).values()))]
                _git(path, "bundle", "create", "-q", str(bundle), "--all", *excluded)
        except LockTimeout as error:
            raise BundleFailure("lock", "the writer lock was not free") from error
        except RuntimeError as error:
            raise BundleFailure("write", str(error)) from error
        _verify(path, bundle)
        try:
            store.put(bundle, name)
        except Exception as error:
            raise BundleFailure("copy", type(error).__name__) from error
    return Bundled(tenant, document, name, refs, full)


@contextmanager
def run_lock() -> Iterator[bool]:
    """The run's own lock, beside its state; yields whether it was taken."""
    path = Path(settings.BACKUP_STATE_DIR) / "worker" / ".bundle-run.lock"
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o640)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _retain(store: Store, tenant: int, document: int) -> None:
    """Keep the repository's newest chains, a chain being a full bundle and what follows it."""
    names = sorted(store.names(f"repos/tenant-{tenant}/document-{document}/"))
    chains: list[list[str]] = []
    for name in names:
        if name.endswith("-full.bundle") or not chains:
            chains.append([])
        chains[-1].append(name)
    for chain in chains[:-CHAINS_KEPT]:
        for name in chain:
            try:
                store.delete(name)
            except Exception:
                # A chain left behind costs space, never history; the next full bundle retries.
                logger.warning(
                    "an old bundle was not deleted",
                    extra={"tenant": tenant, "document": document},
                )
                return


def run(store: Store, *, start: str | None = None) -> RunResult | None:
    """One run over every repository; `None` when another run holds the run lock, or before the
    `backup` service has made the worker's state folder."""
    if not backup_state.folder_ready("run"):
        logger.warning("the backup's state folder is not there yet; this start is skipped")
        return None
    with run_lock() as held:
        if not held:
            logger.warning("a bundle run is still running; this start is skipped")
            return None
        return _run(store, start or now())


def _repository(
    store: Store,
    start: str,
    tenant: int,
    document: int,
    base_stop: str | None,
    lock_timeout: float,
) -> Bundled | None:
    """One repository's part of a run; `None` when nothing moved."""
    path = gitstore.repository_path(tenant, document)
    try:
        current = refs_of(path)
    except RuntimeError as error:
        raise BundleFailure("read", str(error)) from error
    if not current:
        # Nothing is lost from a repository that holds nothing yet.
        return None
    was = recorded(tenant, document)
    full = was is None or not was.get("full") or bool(base_stop and was["full"] < base_stop)
    if not full and was is not None and was.get("refs") == current:
        return None
    bundled = bundle_copy(
        tenant,
        document,
        store,
        start,
        since=None if full else (was or {}).get("refs"),
        lock_timeout=lock_timeout,
    )
    _record(
        tenant,
        document,
        {"refs": bundled.refs, "full": start if full else (was or {}).get("full")},
    )
    if full:
        _retain(store, tenant, document)
    return bundled


def _run(store: Store, start: str) -> RunResult:
    base = backup_state.read("base-backup") or {}
    base_stop = base.get("stop") if isinstance(base.get("stop"), str) else None
    previous = backup_state.read("run") or {}
    failing = {
        (f.get("tenant"), f.get("document")): f.get("since", start)
        for f in (previous.get("newest_marker") or {}).get("failures", [])
        if isinstance(f, dict)
    }
    lock_timeout = float(settings.BACKUP_LOCK_TIMEOUT)
    result = RunResult(start)
    for tenant, document in gitstore.repositories():
        try:
            bundled = _repository(store, start, tenant, document, base_stop, lock_timeout)
        except Exception as error:
            stage = error.stage if isinstance(error, BundleFailure) else "run"
            logger.error(
                "a repository's bundle failed",
                extra={"tenant": tenant, "document": document, "stage": stage},
            )
            result.failures.append(
                {
                    "tenant": tenant,
                    "document": document,
                    "stage": stage,
                    "since": failing.get((tenant, document), start),
                }
            )
            continue
        if bundled is not None:
            result.bundled.append(bundled)
    marker: dict[str, Any] = {"start": start, "failures": result.failures}
    wal = backup_state.read("wal")
    if wal and isinstance(wal.get("last_archived"), str):
        marker["archived_until"] = wal["last_archived"]
    # The failures are known before the marker leaves: a store that refuses it still shows them.
    with backup_state.updating("run") as state:
        state["newest_marker"] = {"start": start, "failures": result.failures}
    with tempfile.TemporaryDirectory() as directory:
        local = Path(directory) / "marker"
        local.write_text(json.dumps(marker, sort_keys=True), encoding="utf-8")
        store.put(local, f"{MARKERS}{start}")
    if not result.failures:
        with backup_state.updating("run") as state:
            state["newest_clean"] = start
    # Chains move only when a full bundle lands, and the markers' bound with them.
    if any(bundled.full for bundled in result.bundled):
        _retain_markers(store)
    return result


def _retain_markers(store: Store) -> None:
    """Delete the markers older than the oldest chain any repository keeps, never the newest
    clean one (DL-0316)."""
    oldest: str | None = None
    for name in store.names("repos/"):
        match = BUNDLE.match(name)
        if match and match["name"].endswith("-full.bundle"):
            start = match["name"].removesuffix("-full.bundle")
            oldest = start if oldest is None else min(oldest, start)
    if oldest is None:
        return
    clean = (backup_state.read("run") or {}).get("newest_clean")
    for name in store.names(MARKERS):
        start = name.rsplit("/", 1)[-1]
        if START.match(start) and start < oldest and start != clean:
            try:
                store.delete(name)
            except Exception:
                # A marker left behind costs a read at restore, never a moment; the next run
                # retries.
                logger.warning("an old marker was not deleted")
                return


class RcloneStore:
    """The off-host store through `rclone`, its bundles encrypted by an `rclone crypt` remote
    over the target (DL-0277). The remotes are configured from the environment, never a file."""

    def __init__(self, environment: dict[str, str]) -> None:
        self.environment = environment

    def _rclone(self, *args: str) -> bytes:
        result = subprocess.run(
            ["rclone", "--config", os.devnull, *args],
            capture_output=True,
            env={**os.environ, **self.environment},
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.decode(errors="replace").strip()[-500:])
        return result.stdout

    def put(self, local: Path, name: str) -> None:
        self._rclone("copyto", str(local), f"bundles:{name}")

    def names(self, prefix: str) -> list[str]:
        """The names under `prefix`; none for a folder that does not exist, and `RuntimeError`
        for a store that cannot be read — never an empty answer in its place."""
        try:
            out = self._rclone("lsf", "-R", "--files-only", f"bundles:{prefix}")
        except RuntimeError as error:
            if "directory not found" in str(error).lower():
                return []
            raise
        return sorted(prefix + line for line in out.decode().splitlines() if line)

    def get(self, name: str) -> bytes:
        return self._rclone("cat", f"bundles:{name}")

    def delete(self, name: str) -> None:
        self._rclone("deletefile", f"bundles:{name}")


# Where the key is inside a container; compose mounts it there.
KEY_IN_CONTAINER = "/run/backup/key"


def _algorithm(line: str) -> str:
    """The key algorithm a known_hosts line pins: its second field."""
    fields = line.split()
    return fields[1] if len(fields) >= 3 else ""


_KNOWN_HOSTS: dict[str, str] = {}


def _known_hosts(line: str) -> str:
    """The store's pinned host key as a file rclone reads, written once per process, private."""
    if not line:
        return ""
    if line not in _KNOWN_HOSTS:
        fd, path = tempfile.mkstemp(prefix="known_hosts.")
        with os.fdopen(fd, "w", encoding="ascii") as handle:
            handle.write(line.strip() + "\n")
        _KNOWN_HOSTS[line] = path
    return _KNOWN_HOSTS[line]


def store_from_environment(environ: dict[str, str] | None = None) -> RcloneStore:
    """The off-host store the installation names in `.env`: `sftp` or `s3`, its bundles under
    `bundles/` in an `rclone crypt` remote. Raises `ConfigurationError` naming every key missing."""
    from syngraphe.config import ConfigurationError, _Reader

    reader = _Reader(environ if environ is not None else dict(os.environ))
    target = reader.string("BACKUP_TARGET")
    password = reader.string("BACKUP_BUNDLE_CRYPT_PASSWORD")
    remote: dict[str, str] = {}
    if target == "sftp":
        path = reader.string("BACKUP_SFTP_PATH")
        remote = {
            "TYPE": "sftp",
            "HOST": reader.string("BACKUP_SFTP_HOST"),
            "PORT": reader.string("BACKUP_SFTP_PORT", "22"),
            "USER": reader.string("BACKUP_SFTP_USER"),
            "KEY_FILE": KEY_IN_CONTAINER,
            "KNOWN_HOSTS_FILE": _known_hosts(reader.string("BACKUP_SFTP_KNOWN_HOSTS")),
            # rclone runs no command on the store and asks it for no hash, so a store that offers
            # file transfer alone serves.
            "SHELL_TYPE": "none",
            # Only the pinned key's algorithm is offered, so the pin is what is checked.
            "HOST_KEY_ALGORITHMS": _algorithm(reader.raw("BACKUP_SFTP_KNOWN_HOSTS", "") or ""),
        }
        root = path.strip("/")
    elif target == "s3":
        remote = {
            "TYPE": "s3",
            "PROVIDER": "Other",
            "ENDPOINT": reader.string("BACKUP_S3_ENDPOINT"),
            "REGION": reader.string("BACKUP_S3_REGION", "us-east-1"),
            "ACCESS_KEY_ID": reader.string("BACKUP_S3_ACCESS_KEY"),
            "SECRET_ACCESS_KEY": reader.string("BACKUP_S3_SECRET_KEY"),
            # The bucket is the operator's, made with the controls DL-0298 relies on; the
            # platform's key may not create one, and rclone otherwise asks to (DL-0543).
            "NO_CHECK_BUCKET": "true",
        }
        root = "/".join(
            p.strip("/")
            for p in (reader.string("BACKUP_S3_BUCKET"), reader.string("BACKUP_S3_PATH"))
            if p.strip("/")
        )
    else:
        if target:
            reader.malformed.append("BACKUP_TARGET")
        root = ""
    if reader.missing or reader.malformed:
        raise ConfigurationError(reader.missing, reader.malformed)
    obscured = (
        subprocess.run(
            ["rclone", "obscure", "-"], input=password.encode(), capture_output=True, check=True
        )
        .stdout.decode()
        .strip()
    )
    environment = {f"RCLONE_CONFIG_STORE_{key}": value for key, value in remote.items()}
    environment.update(
        {
            "RCLONE_CONFIG_BUNDLES_TYPE": "crypt",
            "RCLONE_CONFIG_BUNDLES_REMOTE": f"store:{root}/bundles",
            "RCLONE_CONFIG_BUNDLES_PASSWORD": obscured,
            "RCLONE_CONFIG_BUNDLES_FILENAME_ENCRYPTION": "standard",
        }
    )
    return RcloneStore(environment)


def markers(store: Store) -> list[dict[str, Any]]:
    """Every marker in the store, oldest first."""
    found = []
    for name in store.names(MARKERS):
        if START.match(name.rsplit("/", 1)[-1]):
            found.append(json.loads(store.get(name)))
    return sorted(found, key=lambda m: m["start"])


BUNDLE = re.compile(
    r"^repos/tenant-(?P<tenant>[0-9]+)/document-(?P<document>[0-9]+)/(?P<name>[^/]+)$"
)


def chains_in(store: Store) -> dict[tuple[int, int], list[str]]:
    """Each repository's newest chain in the store: its newest full bundle and every bundle after
    it, in order."""
    found: dict[tuple[int, int], list[str]] = {}
    for name in store.names("repos/"):
        match = BUNDLE.match(name)
        if match and name.endswith(".bundle"):
            found.setdefault((int(match["tenant"]), int(match["document"])), []).append(name)
    chains = {}
    for key, names in found.items():
        names.sort()
        fulls = [n for n, name in enumerate(names) if name.endswith("-full.bundle")]
        if fulls:
            chains[key] = names[fulls[-1] :]
    return chains


def restore_repository(store: Store, tenant: int, document: int, chain: list[str]) -> str:
    """Bring one repository back from its chain: the full bundle cloned, each later one fetched
    in order, under the document's writer lock. Returns `restored`, or `present` when a repository
    is already there, which is left alone."""
    path = gitstore.repository_path(tenant, document)
    with document_lock(tenant, document):
        if path.exists():
            return "present"
        building = path.with_name(f".{path.name}.restoring")
        # What a restore that stopped half way left behind.
        shutil.rmtree(building, ignore_errors=True)
        with tempfile.TemporaryDirectory() as directory:
            local = [Path(directory) / f"{n}.bundle" for n in range(len(chain))]
            for name, file in zip(chain, local, strict=True):
                file.write_bytes(store.get(name))
            # An empty template, as `gitstore.init` uses: no sample hooks in a restored repository.
            template = Path(directory) / "template"
            template.mkdir()
            try:
                subprocess.run(
                    [
                        "git",
                        "clone",
                        "--bare",
                        "-q",
                        f"--template={template}",
                        str(local[0]),
                        str(building),
                    ],
                    check=True,
                    capture_output=True,
                    env={**os.environ, **GIT_ENV},
                )
                for file in local[1:]:
                    _git(building, "fetch", "-q", str(file), "+refs/*:refs/*")
                # A clone names its source as a remote; the repository has none.
                _git(building, "remote", "remove", "origin")
                _git(building, "fsck", "--strict", "--no-dangling")
            except (subprocess.CalledProcessError, RuntimeError):
                shutil.rmtree(building, ignore_errors=True)
                raise
        os.rename(building, path)
    return "restored"
