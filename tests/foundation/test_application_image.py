"""The application's image fetches its pinned downloads with a client the download servers serve:
rclone's release server refuses Python's own `urllib` with 403, so a build without its cache could
not finish (DL-0546). Each download is fetched by `curl -fsSL` into one path and that same path is
checked against its pinned SHA-256 before anything uses it (DL-0312, ADR-0013)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.fast

DOCKERFILE = Path(__file__).resolve().parents[2] / "deploy" / "Dockerfile"
HOSTS = ("downloads.rclone.org", "hackage.haskell.org")


def _final_stage() -> list[str]:
    """The last stage's instructions, each `RUN` one line, its comments left out."""
    lines = DOCKERFILE.read_text(encoding="utf-8").splitlines()
    final = max(i for i, line in enumerate(lines) if line.lstrip().upper().startswith("FROM "))
    kept = [line for line in lines[final:] if not line.lstrip().startswith("#")]
    return "\n".join(kept).replace("\\\n", " ").splitlines()


def _steps(host: str) -> list[str]:
    """The `&&` steps of the one `RUN` that names `host`."""
    runs = [line for line in _final_stage() if line.lstrip().startswith("RUN ") and host in line]
    assert len(runs) == 1, runs
    return [step.strip() for step in runs[0].lstrip().removeprefix("RUN ").split("&&")]


def test_curl_is_installed() -> None:
    installs = [
        word
        for line in _final_stage()
        for command in re.findall(r"apt-get install ([^&;]*)", line)
        for word in command.split()
        if not word.startswith("-")
    ]

    assert "curl" in installs
    assert not any("urlretrieve" in line or "urlopen" in line for line in _final_stage())


@pytest.mark.parametrize("host", HOSTS)
def test_each_download_is_fetched_by_curl_and_checked(host: str) -> None:
    steps = _steps(host)
    fetch = next(i for i, step in enumerate(steps) if host in step)
    # `curl -fsSL -o <path> <url>`: a refused request fails the step, a redirect is followed.
    match = re.fullmatch(
        r'curl\s+-fsSL\s+-o\s+(\S+)\s+"https://' + re.escape(host) + r'/\S+"', steps[fetch]
    )
    assert match, steps[fetch]
    path = match.group(1).strip('"')
    # The same file checked, exactly, in a later step, its failure failing the build.
    checks = [
        step
        for step in steps[fetch + 1 :]
        if re.fullmatch(r'echo "\$\S+ {2}' + re.escape(path) + r'" \| sha256sum -c -', step)
    ]
    assert len(checks) == 1, steps[fetch + 1 :]
