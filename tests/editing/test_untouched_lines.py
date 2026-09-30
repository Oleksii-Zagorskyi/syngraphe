"""A stored line the edit did not touch is byte-identical after normalisation (ASR-20), and the
commit names the normalizer that wrote it."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from editing.normalizer import normalize, run
from editing.normalizer.splitter import Lists
from editing.normalizer.version import RULESET, lists_revision, trailer

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "tests" / "fixtures" / "corpus" / "document-ukr.md"
LANGUAGES = ROOT / "src" / "identity" / "fixtures" / "languages"


def lists_for(code: str) -> Lists:
    data = json.loads((LANGUAGES / f"{code}.json").read_text(encoding="utf-8"))
    return Lists(data["code"], tuple(data["never_final"]), tuple(data["may_be_final"]))


def corpus_body() -> str:
    """The corpus document's body. Its frontmatter carries `synthetic: true`, which the platform's
    frontmatter parser refuses, so it is split off here the way that parser splits it: the body
    follows the closing delimiter and one blank line."""
    text = CORPUS.read_text(encoding="utf-8")
    _, _, rest = text.partition("\n---\n")
    return rest.removeprefix("\n")


ORIGINAL = "Керівник напряму надає реєстр наданих доступів."
EDITED = "Керівник напряму щокварталу надає реєстр наданих доступів."


@pytest.mark.invariant
@pytest.mark.parametrize("path", ["editor", "source view"])
def test_one_edit_touches_one_line(path: str) -> None:
    body = corpus_body()
    stored = body.split("\n")
    assert stored.count(ORIGINAL) == 1
    submitted = body.replace(ORIGINAL, EDITED)
    if path == "source view":
        submitted = join_paragraphs(submitted)

    result = run(body.encode(), submitted, lists_for("uk"))
    out = result.text.split("\n")

    assert len(out) == len(stored)
    differing = [i for i, (a, b) in enumerate(zip(stored, out, strict=True)) if a != b]
    assert differing == [stored.index(ORIGINAL)]
    assert out[differing[0]] == EDITED
    assert result.touched == frozenset(differing)


def join_paragraphs(text: str) -> str:
    """Each plain top-level paragraph on one line, as the source view submits it."""
    blocks = text.split("\n\n")
    plain = [
        " ".join(block.split("\n"))
        if not block.lstrip().startswith(("#", "|", ">", "-", "1."))
        else block
        for block in blocks
    ]
    return "\n\n".join(plain)


@pytest.mark.fast
def test_version_trailer_names_the_lists() -> None:
    uk = lists_for("uk")
    line = trailer(RULESET, uk)
    assert line == f"Normalizer: {RULESET}@{lists_revision(uk)}"
    assert lists_revision(uk) == lists_revision(lists_for("uk"))
    assert lists_revision(uk) != lists_revision(lists_for("en"))
    grown = replace(uk, never_final=(*uk.never_final, "рис"))
    assert lists_revision(grown) != lists_revision(uk)
    moved = replace(uk, may_be_final=(*uk.may_be_final, "рис"))
    assert lists_revision(moved) != lists_revision(grown)
    assert normalize(b"", "", uk) == b""


@pytest.mark.invariant
def test_normalising_the_corpus_stays_within_its_share_of_finishing() -> None:
    """ASR-21 gives finishing five seconds; the normalizer's share on the forty-page corpus, with
    one sentence edited through the source view, is kept under one."""
    import time

    body = corpus_body()
    submitted = join_paragraphs(body.replace(ORIGINAL, EDITED))
    started = time.perf_counter()
    run(body.encode(), submitted, lists_for("uk"))
    assert time.perf_counter() - started < 1.0


@pytest.mark.fast
@pytest.mark.parametrize(
    "text",
    [
        "Вступ. **Перше речення. Друге речення.**\n",
        "Вступ. *Перше речення. Друге речення.*\n",
        "Вступ. **Перше речення** і далі.\n",
    ],
)
def test_a_mark_opening_a_new_line_stays_a_mark(text: str) -> None:
    """A sentence that moves to a line's start and opens with a mark keeps the mark: only a
    literal `+`, `-`, `>` or a number's stop is escaped there, and a literal `*` is escaped
    already, so a bare one is always markup. The stored form is a fixed point."""
    stored = normalize(b"", text, lists_for("uk")).decode()

    assert "\\*" not in stored
    assert stored.replace("\n", " ").replace("  ", " ").strip() == text.strip()
