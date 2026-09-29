"""Every one-spelling rewrite of DL-0240 reaches the stored spelling through the normalizer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from editing.markdown.parser import parser
from editing.normalizer import normalize
from editing.normalizer.splitter import Lists

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "tests" / "fixtures" / "whitelist" / "cases.json"
LANGUAGES = ROOT / "src" / "identity" / "fixtures" / "languages"

pytestmark = pytest.mark.fast


def lists_for(code: str) -> Lists:
    data = json.loads((LANGUAGES / f"{code}.json").read_text(encoding="utf-8"))
    return Lists(data["code"], tuple(data["never_final"]), tuple(data["may_be_final"]))


def one_line_paragraphs(text: str) -> bool:
    """Whether no paragraph of `text` breaks a line: where one does, where its sentences end is the
    splitter's to decide, not the serialiser's."""
    return not any(
        child.type == "softbreak"
        for token in parser().parse(text)
        if token.type == "inline"
        for child in token.children or []
    )


def respellings() -> list[tuple[str, str]]:
    """The suite's re-spelling cases — the contract both serialisers are held to (ADR-0010) — and
    the two escapes of DL-0240 that the case list does not carry."""
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    pairs = [
        (c["input"], c["stored"])
        for c in cases
        if c["kind"] == "respell" and one_line_paragraphs(c["stored"])
    ]
    return pairs + [
        ("Строк x < y.\n", "Строк x \\< y.\n"),
        ("Знак \\&copy; лишається буквальним.\n", "Знак \\&copy; лишається буквальним.\n"),
    ]


def test_one_spelling_idempotent() -> None:
    uk = lists_for("uk")
    pairs = respellings()
    assert len(pairs) >= 12
    for submitted, stored in pairs:
        first = normalize(b"", submitted, uk)
        assert first == stored.encode(), submitted
        assert normalize(first, first.decode(), uk) == first, submitted
        assert normalize(first, submitted, uk) == first, submitted
