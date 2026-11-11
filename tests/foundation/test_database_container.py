"""The database container archives to the off-host store and keeps serving when the store fails
(ADR-0018, ADR-0019): its image can verify a TLS store, and an init process, not PostgreSQL,
adopts what pgBackRest detaches (DL-0544)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

pytestmark = pytest.mark.fast

ROOT = Path(__file__).resolve().parents[2]


class _ComposeLoader(yaml.SafeLoader):
    """YAML as Compose reads it: its merge tags (`!reset`, `!override`) kept as plain values."""


def _merge_tag(loader: yaml.SafeLoader, node: yaml.Node) -> Any:
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    assert isinstance(node, yaml.ScalarNode)
    return loader.construct_scalar(node)


for _tag in ("!reset", "!override"):
    _ComposeLoader.add_constructor(_tag, _merge_tag)


def _installed_packages(dockerfile: Path) -> set[str]:
    """The packages the final stage's `apt-get install` names, its line continuations joined and
    its comments left out."""
    lines = dockerfile.read_text(encoding="utf-8").splitlines()
    final = max(i for i, line in enumerate(lines) if line.lstrip().upper().startswith("FROM "))
    kept = [line for line in lines[final:] if not line.lstrip().startswith("#")]
    text = "\n".join(kept).replace("\\\n", " ")
    packages: set[str] = set()
    for command in re.findall(r"apt-get install ([^&;\n]*)", text):
        packages |= {word for word in command.split() if not word.startswith("-")}
    return packages


def test_the_database_image_verifies_a_tls_store() -> None:
    """pgBackRest reaches an S3 store over TLS and refuses a certificate it cannot verify; the
    store's chain is verified against the system's certificate authorities, which an install
    without recommended packages leaves out."""
    assert "ca-certificates" in _installed_packages(ROOT / "deploy" / "Dockerfile.db")


def test_the_database_runs_under_an_init_process() -> None:
    """pgBackRest's asynchronous archive-push detaches a process; with PostgreSQL as PID 1 it is
    adopted by the postmaster, whose failure the postmaster takes for a crashed backend and
    restarts every connection — at each attempt while the store is unreachable."""
    services: dict[str, Any] = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))[
        "services"
    ]
    assert services["db"].get("init") is True

    # Every shape keeps it: no override read over the base file sets it otherwise.
    for override in sorted((ROOT / "deploy").glob("compose.*.yaml")):
        loaded = yaml.load(override.read_text(encoding="utf-8"), Loader=_ComposeLoader) or {}
        db = (loaded.get("services") or {}).get("db") or {}
        assert "init" not in db, override.name
