"""Every refusal the specification names has a name the interface shows, and nothing else does."""

from __future__ import annotations

import pytest

from editing.markdown import load_spec
from editing.messages import CONSTRUCTS, LABELS, NOTICES

pytestmark = pytest.mark.fast


def test_every_refusal_code_has_a_name() -> None:
    assert set(CONSTRUCTS) == set(load_spec().refusals)


def test_every_control_and_notice_has_its_words() -> None:
    spec = load_spec()
    # One label serves every heading level the specification allows, the level filled in.
    assert "%(level)s" in str(LABELS["heading"]) and spec.heading_max_depth >= 1
    assert set(spec.callout_types) <= set(LABELS)
    assert {"refused", "help", "images", "link_refused", "busy"} <= set(NOTICES)
