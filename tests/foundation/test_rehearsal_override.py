"""A restore rehearsed beside a running installation: the rehearsal override read last, over the
base file and the production override, archives nothing, starts no writer and publishes nothing
(DL-0496)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Any

# The production override's harness, loaded by its path: the suite imports test modules in
# importlib mode, where one test module cannot import another by name.
_spec = importlib.util.spec_from_file_location(
    "production_override_harness", Path(__file__).with_name("test_production_override.py")
)
assert _spec is not None and _spec.loader is not None
_harness = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_harness)

ROOT: Path = _harness.ROOT
DOCKER: str | None = _harness.DOCKER
environment = _harness.environment
needs_docker = _harness.needs_docker

WRITERS = ("front", "worker", "backup", "render")
KEPT = ("db", "web", "redis")


def rehearsal_config(folder: Path) -> dict[str, Any]:
    env_file = folder / ".env"
    env_file.write_text("".join(f"{k}={v}\n" for k, v in environment(folder).items()))
    made = subprocess.run(
        [
            str(DOCKER),
            "compose",
            "--project-directory",
            str(ROOT),
            "-p",
            "rehearsal-test",
            "--env-file",
            str(env_file),
            "-f",
            str(ROOT / "compose.yaml"),
            "-f",
            str(ROOT / "deploy" / "compose.prod.yaml"),
            "-f",
            str(ROOT / "deploy" / "compose.rehearsal.yaml"),
            "config",
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"},
    )
    assert made.returncode == 0, made.stderr
    config: dict[str, Any] = json.loads(made.stdout)
    return config


@needs_docker
def test_rehearsal_archives_nothing(tmp_path: Path) -> None:
    """The rehearsal's database never pushes a segment into the store it shares with the running
    installation."""
    command = rehearsal_config(tmp_path)["services"]["db"]["command"]

    assert "archive_mode=off" in command
    assert not any("archive_command" in part for part in command)
    assert "archive_mode=on" not in command


@needs_docker
def test_rehearsal_starts_no_writer_and_publishes_nothing(tmp_path: Path) -> None:
    """`up` starts the database, the application and the broker alone, and nothing is reachable
    from outside the host; `run` still reaches every service for the restore scripts."""
    services = rehearsal_config(tmp_path)["services"]
    # Compose may list a profiled service with its profile or leave it out; either way `up`
    # starts only the services without one, and a service added to the base file later, which
    # may write the store, must be named here before a rehearsal starts it.
    started = {name for name, service in services.items() if not service.get("profiles")}

    for name in WRITERS:
        assert name not in services or services[name].get("profiles") == ["never"], (
            f"{name} would start with `up`; read `docker compose version` against the "
            "behaviour of `profiles`"
        )
    assert started == set(KEPT)
    assert not [name for name in started if services[name].get("ports")]
