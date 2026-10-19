"""The built-in sample a stylesheet is tried on (DL-0466): invented, saying so in its first
paragraph, inside the whitelist, and holding every construct the whitelist allows — in each
language it is written in."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.fast

SAMPLES = Path(__file__).resolve().parents[2] / "src" / "rendering" / "samples"


@pytest.mark.parametrize(
    ("language", "example"), [("en", "invented example"), ("uk", "вигаданий приклад")]
)
def test_the_sample_holds_every_construct(language: str, example: str) -> None:
    from editing.markdown import load_spec
    from editing.markdown.parser import parser
    from editing.markdown.validator import validate

    text = (SAMPLES / f"{language}.md").read_text(encoding="utf-8")
    spec = load_spec()

    assert validate(text) == []
    tokens = parser().parse(text)
    types = {token.type for token in tokens}
    children = [child for token in tokens for child in token.children or []]
    kinds = {(child.meta or {}).get("kind") for child in children if child.type.endswith("_open")}
    assert set(spec.spans) <= kinds
    # A mention among them, by its own kind, not only as a link.
    assert "document" in kinds
    callouts = {token.info for token in tokens if token.type == "callout_open"}
    assert callouts == set(spec.callout_types)
    assert {f"h{n}" for n in range(1, spec.heading_max_depth + 1)} <= {
        token.tag for token in tokens if token.type == "heading_open"
    }
    # A list item stands one level below its list: depth `d` is level `2d - 1`.
    deepest = max(token.level for token in tokens if token.type == "list_item_open")
    assert (deepest + 1) // 2 == spec.list_max_depth
    assert {"table_open", "blockquote_open", "ordered_list_open", "bullet_list_open"} <= types
    assert any(child.type == "link_open" for child in children)
    (image,) = [child for child in children if child.type == "image"]
    path = image.attrGet("src")
    assert isinstance(path, str)
    data = (SAMPLES / path).read_bytes()
    assert path == f"images/{hashlib.sha256(data).hexdigest()}.png"
    first = re.split(r"\n\s*\n", text.split("\n", 1)[1].strip())[0]
    assert example in first.lower()
