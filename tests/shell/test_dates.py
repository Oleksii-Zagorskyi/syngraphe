"""One form for every date and time the interface draws (DL-0511): `j E Y, H:i`, a date alone
`j E Y` — *30 вересня 2026, 13:53* in Ukrainian, *30 September 2026, 13:53* in English. The
exports' dates are the document's text and keep their own (`src/rendering/`)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.fast

SRC = Path(__file__).resolve().parents[2] / "src"
FORMS = {"j E Y, H:i", "j E Y"}
# Where a date is the document's text, not the interface's.
EXPORTS = {"rendering/title_page.py", "rendering/sample.py"}


def test_every_date_the_interface_draws_takes_one_form() -> None:
    templates = list(SRC.rglob("*.html"))
    assert templates, "the templates are read"
    odd = [
        f"{path.relative_to(SRC)}: {found}"
        for path in templates
        for found in re.findall(r'\|date:"([^"]*)"', path.read_text("utf-8"))
        if found not in FORMS
    ]
    assert odd == []
    named = [
        f"{path.relative_to(SRC)}"
        for path in SRC.rglob("*.py")
        if path.relative_to(SRC).as_posix() not in EXPORTS
        and re.search(r'"(?:SHORT_)?DATE(?:TIME)?_FORMAT"', path.read_text("utf-8"))
    ]
    assert named == []
