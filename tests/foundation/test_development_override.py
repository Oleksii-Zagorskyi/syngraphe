"""The developer's shape: the override read over the base file, its ports from the environment, so
several checkouts' stacks run side by side on one workstation."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCKER = shutil.which("docker")
pytestmark = pytest.mark.skipif(DOCKER is None, reason="docker is not installed here")


def redis_ports(folder: Path, values: dict[str, str]) -> list[dict[str, Any]]:
    env_file = folder / ".env"
    env_file.write_text("".join(f"{k}={v}\n" for k, v in values.items()))
    made = subprocess.run(
        [
            str(DOCKER),
            "compose",
            "--project-directory",
            str(ROOT),
            "--env-file",
            str(env_file),
            "-f",
            str(ROOT / "compose.yaml"),
            "-f",
            str(ROOT / "deploy" / "compose.dev.yaml"),
            "config",
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"},
    )
    assert made.returncode == 0, made.stderr
    ports: list[dict[str, Any]] = json.loads(made.stdout)["services"]["redis"]["ports"]
    return ports


@pytest.mark.parametrize(("values", "published"), [({}, "6379"), ({"REDIS_PORT": "6411"}, "6411")])
def test_redis_port_from_the_environment(
    tmp_path: Path, values: dict[str, str], published: str
) -> None:
    ports = redis_ports(tmp_path, {"BACKUP_KEY_FILE": "/dev/null", **values})
    assert [(p["host_ip"], p["published"], p["target"]) for p in ports] == [
        ("127.0.0.1", published, 6379)
    ]
