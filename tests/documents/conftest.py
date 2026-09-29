"""The generated corpus, built once per run from its generator into a temporary directory."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

CORPUS = Path(__file__).resolve().parents[1] / "fixtures" / "corpus"


@pytest.fixture(scope="session")
def corpus_ukr(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """The Ukrainian history as a bare repository, and its record of who wrote what."""
    out = tmp_path_factory.mktemp("corpus")
    repo = out / "corpus-ukr.git"
    truth = out / "truth-ukr.json"
    result = subprocess.run(
        [
            sys.executable,
            str(CORPUS / "corpus.py"),
            "--lang",
            "ukr",
            "--repo",
            str(repo),
            "--truth",
            str(truth),
        ],
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    return {"repo": repo, "truth": json.loads(truth.read_text(encoding="utf-8"))}


class DirStore:
    """A backup store in a local directory, standing in for the off-host one."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.puts: list[str] = []

    def put(self, local: Path, name: str) -> None:
        target = self.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(local.read_bytes())
        self.puts.append(name)

    def names(self, prefix: str) -> list[str]:
        base = self.root / prefix
        if not base.exists():
            return []
        return sorted(str(p.relative_to(self.root)) for p in base.rglob("*") if p.is_file())

    def get(self, name: str) -> bytes:
        return (self.root / name).read_bytes()

    def delete(self, name: str) -> None:
        (self.root / name).unlink()


@pytest.fixture
def store(tmp_path: Path) -> DirStore:
    root = tmp_path / "store"
    root.mkdir()
    return DirStore(root)


@pytest.fixture
def state_dir(tmp_path: Path, settings: Any) -> Path:
    directory = tmp_path / "backup-state"
    directory.mkdir()
    settings.BACKUP_STATE_DIR = directory
    return directory
