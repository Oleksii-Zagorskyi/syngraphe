"""The one spelling per construct (DL-0240): a text inside the whitelist but spelled otherwise —
`*` bullets, `_italic_`, a setext heading, a table without edge pipes — is parsed with the
platform's markdown-it-py and written back by `editing.markdown.serializer`, the Python twin of the
editor's, which the conformance suite holds in step (ADR-0010)."""

from __future__ import annotations

from editing.markdown.serializer import serialize
from editing.markdown.validator import validate


class OutsideWhitelist(ValueError):
    """The submitted text holds a construct the whitelist refuses; the validator names each."""


def respell(text: str) -> str:
    """`text` in its stored spelling. Refused text never reaches the normalizer: the editor and
    the source view validate before capture, and this is the last guard, not a message."""
    refusals = validate(text)
    if refusals:
        raise OutsideWhitelist(", ".join(f"{r.code} at line {r.line}" for r in refusals))
    return serialize(text)
