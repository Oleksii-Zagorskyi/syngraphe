"""The parse-preservation invariant catches a line break inside an inline construct (V-09)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from editing.normalizer import invariant

PLANTED = Path(__file__).resolve().parents[1] / "fixtures" / "splitter" / "planted-breaks.json"
MARK = "¦"

pytestmark = pytest.mark.fast


def test_planted_breaks_caught_controls_pass() -> None:
    cases = json.loads(PLANTED.read_text(encoding="utf-8"))
    assert [case["kind"] for case in cases].count("break") == 6
    assert [case["kind"] for case in cases].count("control") == 2
    for case in cases:
        block = case["block"].replace(MARK, "")
        boundary = case["block"].index(MARK)
        assert invariant.preserves_parse(block, boundary) is (case["kind"] == "control"), case["id"]


def test_continuation_keeps_the_blocks_prefix() -> None:
    assert invariant.preserves_parse("- Перше речення. Друге речення.", len("- Перше речення."))
    assert invariant.preserves_parse("> Перше речення. Друге речення.", len("> Перше речення."))
    assert not invariant.preserves_parse("- Перше речення. - друге", len("- Перше речення."))
