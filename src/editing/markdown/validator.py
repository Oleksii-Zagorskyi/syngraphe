"""Whether a text stands inside the whitelist, and if not, every refusal with its code and line."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
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


_ONCE: ContextVar[dict[str, tuple[Refusal, ...]] | None] = ContextVar(
    "validated_once", default=None
)


@contextmanager
def validating_once() -> Iterator[None]:
    """Within the block, each text is validated once against the specification: a page that asks
    of one draft in several places parses it once. Nothing outlives the block; an inner block
    shares the outer one's."""
    if _ONCE.get() is not None:
        yield
        return
    token = _ONCE.set({})
    try:
        yield
    finally:
        _ONCE.reset(token)


def validate(text: str, spec: Spec | None = None) -> list[Refusal]:
    """Every refusal in `text`, by line then code; empty when the text is inside the whitelist.
    A text over the specification's size is refused before it is parsed."""
    once = _ONCE.get() if spec is None else None
    if once is not None and text in once:
        return list(once[text])
    refusals = _refusals(text, spec or load_spec())
    if once is not None:
        once[text] = tuple(refusals)
    return refusals


def _refusals(text: str, spec: Spec) -> list[Refusal]:
    if len(text.encode("utf-8")) > spec.max_bytes:
        return [Refusal(1, "too-large")]
    env: dict[str, Any] = {}
    tokens = parser().parse(text, env)
    return [Refusal(line, code) for code, line in walk(tokens, lines_of(text), env, spec)]
