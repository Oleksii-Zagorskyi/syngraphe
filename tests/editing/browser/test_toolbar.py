"""The editor's toolbar in Chromium (DL-0531): its first three controls are *undo*, *redo*
and *Clear formatting*, in that order. Invented text."""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.browser


def test_the_first_three(editing: Any, page: Any) -> None:
    editing("A synthetic sentence.\n")
    commands = page.eval_on_selector_all(
        ".toolbar[role=toolbar] button[data-command]",
        "buttons => buttons.map(b => b.dataset.command)",
    )
    assert commands[:3] == ["undo", "redo", "clear_formatting"]
