"""The numbering twins against one oracle: every case of
`tests/fixtures/render/numbering-cases.json` numbered by the editor's gutter in Chromium, and its
sequence equal both to the case's labels and to the reading view's (DL-0065, DL-0330).

Every text is invented.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from rendering.numbering import labels
from rendering.renderer import RENDERER

CASES_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "render" / "numbering-cases.json"


def python_sequence(text: str) -> list[str]:
    """The reading view's numbers: its own parse, as `renderer.labelled` numbers it."""
    found = labels(RENDERER.parse(text))
    return [found[index] for index in sorted(found)]


@pytest.mark.conformance
def test_twins_agree(browser_server: str, page: Any) -> None:
    cases: list[dict[str, Any]] = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    page.goto(browser_server + "/editing/conformance/")
    editor = page.evaluate(
        "texts => SyngrapheEditor.numbering(texts)", [case["input"] for case in cases]
    )
    failures = []
    for case, gutter in zip(cases, editor, strict=True):
        server = python_sequence(case["input"])
        if gutter != case["labels"] or gutter != server:
            failures.append((case["id"], {"gutter": gutter, "python": server}))
    assert not failures, "\n".join(map(repr, failures))
