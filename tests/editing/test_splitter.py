"""The sentence splitter against the marked samples (ADR-0012, V-09, DL-0246)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from editing.markdown.parser import parser
from editing.normalizer import invariant, splitter
from editing.normalizer.splitter import Lists

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "tests" / "fixtures" / "splitter"
LANGUAGES = ROOT / "src" / "identity" / "fixtures" / "languages"
MARK = "¦"


def lists_for(code: str) -> Lists:
    """The language's two lists as the seed fixture holds them, loaded without a database."""
    data = json.loads((LANGUAGES / f"{code}.json").read_text(encoding="utf-8"))
    return Lists(data["code"], tuple(data["never_final"]), tuple(data["may_be_final"]))


def body(text: str) -> str:
    """The text after its frontmatter; the samples carry `synthetic: true`, which the platform's
    frontmatter parser refuses."""
    _, _, rest = text.partition("\n---\n")
    return rest.removeprefix("\n")


def marked_blocks(path: Path) -> list[tuple[str, list[int]]]:
    """Each inline block the splitter sees — a paragraph, a list item's, a quote's or a callout's
    paragraph; never a heading or a table cell — as its text without the marks and the offset of
    every mark in that text."""
    tokens = parser().parse(body(path.read_text(encoding="utf-8")))
    blocks = []
    for index, token in enumerate(tokens):
        if token.type != "inline" or tokens[index - 1].type != "paragraph_open":
            continue
        pieces = token.content.split(MARK)
        offsets, at = [], 0
        for piece in pieces[:-1]:
            at += len(piece)
            offsets.append(at)
        blocks.append(("".join(pieces), offsets))
    return blocks


@pytest.mark.fast
@pytest.mark.parametrize(("sample", "code", "marked"), [("ukr", "uk", 1015), ("eng", "en", 1012)])
def test_disagreement_rate_within_threshold(sample: str, code: str, marked: int) -> None:
    lists = lists_for(code)
    blocks = marked_blocks(SAMPLES / f"sample-{sample}.marked.md")
    assert sum(len(offsets) for _, offsets in blocks) == marked

    disagreements, inside = [], []
    for text, offsets in blocks:
        placed = splitter.boundaries(text, lists)
        found = {b.end for b in placed}
        for end in found.symmetric_difference(offsets):
            disagreements.append(text[max(0, end - 40) : end] + MARK + text[end : end + 40])
        inside += [text for b in placed if not invariant.preserves_parse(text, b.end)]

    assert len(disagreements) <= 5, disagreements
    assert inside == []


@pytest.mark.fast
def test_rules_on_hard_cases() -> None:
    uk = lists_for("uk")
    cases = {
        "Відповідно до п. 4.2 цього Положення строк становить 10 днів. Далі діє наказ.": [
            "Відповідно до п. 4.2 цього Положення строк становить 10 днів.",
            "Далі діє наказ.",
        ],
        "Акт підписує Т. Г. Мельник. Копію передають до архіву.": [
            "Акт підписує Т. Г. Мельник.",
            "Копію передають до архіву.",
        ],
        "Звіт подають до кінця поточного р. Після цього звіт не приймають.": [
            "Звіт подають до кінця поточного р.",
            "Після цього звіт не приймають.",
        ],
        "Сума становить 5 тис. грн на рік.": ["Сума становить 5 тис. грн на рік."],
        "Голова зазначив: «Перевірка завершена. Зауважень немає.» Рішення внесено до протоколу.": [
            "Голова зазначив: «Перевірка завершена.",
            "Зауважень немає.»",
            "Рішення внесено до протоколу.",
        ],
        "Чи подано заяву? так, подано.": ["Чи подано заяву?", "так, подано."],
        "Далі буде… і так щодня. Строк сплив… Нове речення.": [
            "Далі буде… і так щодня.",
            "Строк сплив…",
            "Нове речення.",
        ],
        "Див. [додаток 3](https://example.org/forms/annex.3.pdf). Форма є обов'язковою.": [
            "Див. [додаток 3](https://example.org/forms/annex.3.pdf).",
            "Форма є обов'язковою.",
        ],
    }
    for text, sentences in cases.items():
        assert splitter.split(text, uk) == sentences, text


@pytest.mark.fast
def test_mask_keeps_length_and_hides_syntax() -> None:
    text = "Див. [строк]{.term #strok} і [форму](https://example.org/a.b). ![Схема. Етап](s.png)"
    masked = splitter.mask(text)
    assert len(masked) == len(text)
    assert ".term" not in masked and "example" not in masked and "Схема" not in masked
    assert masked.startswith("Див. [строк]")
