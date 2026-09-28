"""No interface string is typed in Ukrainian outside the catalogue."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.fast

SRC = Path(__file__).resolve().parents[2] / "src"
CYRILLIC = re.compile(r"[Ѐ-ӿ]")
# The catalogue is where Ukrainian lives; seed data and the help pages are Ukrainian by design.
EXEMPT_PARTS = ("migrations", "fixtures")
EXEMPT_DIRS = (SRC / "editing" / "help",)


def scanned_files() -> list[Path]:
    files = []
    for path in SRC.rglob("*"):
        if path.suffix not in (".html", ".py", ".js") or not path.is_file():
            continue
        if any(part in EXEMPT_PARTS for part in path.relative_to(SRC).parts):
            continue
        if any(path.is_relative_to(d) for d in EXEMPT_DIRS):
            continue
        files.append(path)
    return files


def test_no_cyrillic_outside_the_catalogue() -> None:
    files = scanned_files()
    assert files, "the tree under src/ is scanned"

    offenders = [
        f"{path.relative_to(SRC)}:{n}"
        for path in files
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if CYRILLIC.search(line)
    ]

    assert offenders == []


def test_the_lint_bites(tmp_path: Path) -> None:
    planted = tmp_path / "planted.html"
    planted.write_text("<p>Привіт</p>", encoding="utf-8")

    assert CYRILLIC.search(planted.read_text(encoding="utf-8"))
