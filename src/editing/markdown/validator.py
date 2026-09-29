"""Whether a text stands inside the whitelist, and if not, every refusal with its code and line."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from editing.markdown import Spec, load_spec
from editing.markdown.parser import parser
from editing.markdown.rules import lines_of, walk


@dataclass(frozen=True, order=True)
class Refusal:
    """One construct outside the whitelist: the line it starts on, from 1, and its stable code."""

    line: int
    code: str


def validate(text: str, spec: Spec | None = None) -> list[Refusal]:
    """Every refusal in `text`, by line then code; empty when the text is inside the whitelist.
    A text over the specification's size is refused before it is parsed."""
    spec = spec or load_spec()
    if len(text.encode("utf-8")) > spec.max_bytes:
        return [Refusal(1, "too-large")]
    env: dict[str, Any] = {}
    tokens = parser().parse(text, env)
    return [Refusal(line, code) for code, line in walk(tokens, lines_of(text), env, spec)]
