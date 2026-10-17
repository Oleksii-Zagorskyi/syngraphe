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


def test_bullet_numbered_items_are_a_numbered_list() -> None:
    """An author's `- 1. Text` is the numbered list they meant (DL-0441), stored as one."""
    uk = lists_for("uk")
    submitted = "- 1. The first item.\n- 2. The second item.\n"

    stored = normalize(b"", submitted, uk)

    assert stored == b"1. The first item.\n2. The second item.\n"
    assert normalize(stored, stored.decode(), uk) == stored


def test_joined_reads_every_line_break_and_trailing_space() -> None:
    from editing.normalizer import joined

    en = lists_for("en")

    assert joined("A sentence broken\nacross two lines.\n\nAnother one.\n", en) == [1]
    assert joined("A sentence broken\r\nacross two lines.\r\n\r\nAnother one.\r\n", en) == [1]
    assert joined("A sentence broken \nacross two lines.\n\nOther. \n", en) == [1]


def test_a_numbered_bullet_list_renders_as_it_is_stored() -> None:
    """A draft not yet normalised renders as its stored form does, a loose item included."""
    from rendering.renderer import render

    uk = lists_for("uk")
    submitted = "- 1. A one.\n\n     More.\n- 1. B two.\n"
    stored = normalize(b"", submitted, uk).decode()

    assert render(submitted) == render(stored)


@pytest.mark.budget
def test_numbered_bullets_are_rewritten_in_linear_time() -> None:
    import time

    body = "- 1. a\n\nb\n\n" * 28000
    started = time.perf_counter()
    parser().parse(body)
    assert time.perf_counter() - started < 3.0
