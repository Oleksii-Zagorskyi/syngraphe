"""The stylesheet draws what the templates mark: a class a template sets for a state the reader
must see has a rule in `shell.css`."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.fast

SRC = Path(__file__).resolve().parents[2] / "src"
SHELL_CSS = (SRC / "shell/static/shell.css").read_text("utf-8")


def rule(selector: str) -> str | None:
    """The declarations of `selector` in the shell's stylesheet, or `None`."""
    found = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", SHELL_CSS)
    return found.group(1) if found else None


def test_an_absent_part_in_the_list_is_drawn_faint() -> None:
    # pages.md § Document list: appendices and attachments present or absent, "drawn as dark and
    # faint icons" — the list's template marks the absent one `part … absent`.
    template = (SRC / "documents/templates/documents/list.html").read_text("utf-8")
    assert 'class="part attachments{% if not row.attachments %} absent' in template
    declarations = rule(".part.absent")
    assert declarations is not None
    opacity = re.search(r"opacity\s*:\s*([0-9.]+)", declarations)
    assert opacity is not None and float(opacity.group(1)) < 0.5


def test_no_page_wears_a_class_the_shell_hides_until_opened() -> None:
    # `shell.css` hides some classes until a script opens them (`.x{display:none}`, `.x.on{…}`).
    # A template that gives its own content such a class is never seen.
    hidden = set(re.findall(r"^\.([\w-]+)\{[^}]*display:none", SHELL_CSS, re.M))
    assert {"help", "overlay", "pop"} <= hidden
    worn = []
    for template in sorted(SRC.glob("*/templates/**/*.html")):
        for classes in re.findall(r'class="([^"]*)"', template.read_text("utf-8")):
            # The words outside any template tag: `{% if … %} absent{% endif %}` keeps `absent`.
            plain = re.sub(r"\{[%{].*?[%}]\}", " ", classes)
            for name in plain.split():
                if name in hidden:
                    worn.append(f"{template.relative_to(SRC)}: {name}")
    assert worn == []


def test_the_help_list_stands_beside_the_page() -> None:
    # pages.md § Help, DL-0365: the list of pages beside the page it opened.
    declarations = rule(".help-page")
    assert declarations is not None and "display:grid" in declarations.replace(" ", "")
