"""The organisation's document template as text (DL-0169): what may stand in its outline, and the
body a new document's first version holds — the outline in normal form for its language."""

from __future__ import annotations

import functools
from dataclasses import dataclass
from typing import Any

from editing.markdown.parser import parser
from editing.markdown.validator import validate
from editing.normalizer import NormalizerDefect, normalize
from editing.normalizer.spellings import OutsideWhitelist
from editing.normalizer.splitter import Lists

# A template is headings and a few sentences, and the normaliser's cost on one long paragraph grows
# faster than its length: the editor's size would let a save, and every creation, run for minutes.
MAX_BYTES = 20_000


@dataclass(frozen=True, order=True)
class TemplateRefusal:
    """One thing the template may not hold: the line it starts on, from 1, and its code — a
    whitelist code, or `first-block`, `image` or `normal-form`. `language` names the language a
    `normal-form` refusal is about."""

    line: int
    code: str
    language: str = ""


class TemplateRefused(Exception):
    """The template's outline does not pass; nothing was created from it."""

    def __init__(self, refusals: list[TemplateRefusal]) -> None:
        super().__init__(", ".join(f"{r.code} at line {r.line}" for r in refusals))
        self.refusals = refusals


def refusals(outline: str) -> list[TemplateRefusal]:
    """Every refusal of `outline`, by line then code: past `MAX_BYTES`, that alone; else the
    whitelist's, then the template's own — its first block a `#` heading, since a template never
    produces text before the first heading, and no image, since a template carries no file an image
    could name."""
    if len(outline.encode("utf-8")) > MAX_BYTES:
        return [TemplateRefusal(1, "too-large")]
    found = [TemplateRefusal(r.line, r.code) for r in validate(outline)]
    if any(r.code == "too-large" for r in found):
        return found
    tokens = parser().parse(outline, {})
    if not tokens or tokens[0].type != "heading_open" or tokens[0].tag != "h1":
        found.append(TemplateRefusal(1, "first-block"))
    for token in tokens:
        if token.type == "inline" and token.map is not None:
            found += [
                TemplateRefusal(token.map[0] + 1, "image")
                for child in token.children or []
                if child.type == "image"
            ]
    # Two images in one paragraph name its line once.
    return sorted(set(found))


def starting_body(outline: str, language: Any, *, strict: bool = True) -> str:
    """The first version's body for a document in `language` (a `Language` row): the outline in
    normal form, as every later version's body is. Strictly, an outline the normaliser cannot
    take raises `TemplateRefused`; otherwise it stands verbatim — only the reconciler finishing a
    creation asks that, so a whitelist changed since the save never leaves a document stuck."""
    try:
        return _normal_form(outline, Lists.of(language))
    except (OutsideWhitelist, NormalizerDefect):
        if strict:
            raise TemplateRefused([TemplateRefusal(1, "normal-form", language.code)]) from None
        return outline


# Remembered per outline and lists: a creation checks the outline before its row and commits it
# at step 3, and the normaliser's cost grows faster than the length of a long paragraph.
@functools.lru_cache(maxsize=16)
def _normal_form(outline: str, lists: Lists) -> str:
    return normalize(b"", outline, lists).decode("utf-8")


def checked(outline: str, languages: list[Any]) -> list[TemplateRefusal]:
    """What a save refuses: `refusals`, and then the outline put in normal form in each of
    `languages`, so a saved template creates a document in every language."""
    found = refusals(outline)
    if found:
        return found
    for language in languages:
        try:
            starting_body(outline, language)
        except TemplateRefused as refused:
            found += refused.refusals
    return found
