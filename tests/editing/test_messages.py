"""Every refusal the specification names has a name the interface shows, and nothing else does."""

from __future__ import annotations

import pytest

from editing.markdown import load_spec
from editing.messages import CONSTRUCTS, LABELS, NOTICES, SPAN_NAMES

pytestmark = pytest.mark.fast


def test_every_refusal_code_has_a_name() -> None:
    assert set(CONSTRUCTS) == set(load_spec().refusals)
    # The mention's own refusal, and its span's name on the allowed-Markdown page (DL-0436).
    assert "mention-id" in CONSTRUCTS
    assert "document" in SPAN_NAMES and "document" in load_spec().spans


def test_every_control_and_notice_has_its_words() -> None:
    spec = load_spec()
    # One label serves every heading level the specification allows, the level filled in.
    assert "%(level)s" in str(LABELS["heading"]) and spec.heading_max_depth >= 1
    assert set(spec.callout_types) <= set(LABELS)
    assert {"refused", "help", "images", "link_refused", "busy"} <= set(NOTICES)
