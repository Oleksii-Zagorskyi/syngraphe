"""The mechanical change summary (DL-0261, DL-0321): the sections an edit touched, named by their
headings in document order, drafted in the interface's language for the holder to edit."""

from __future__ import annotations

import re

from django.utils.translation import gettext as _

from documents.gitstore import CONTROL
from editing.diffview import opcodes

HEADING = re.compile(r"^#{1,6}[ \t]+(.*?)[ \t]*$")
# A line a commit's trailers would read as their own: a word of letters and hyphens, a colon.
TRAILER_SHAPE = re.compile(r"^[A-Za-z][A-Za-z0-9-]*:[ \t]")
SUMMARY_MAX = 500


def _sections(lines: list[str]) -> list[str | None]:
    """The heading text each line falls under, `None` before the first heading."""
    found: list[str | None] = []
    current: str | None = None
    for line in lines:
        m = HEADING.match(line)
        if m:
            current = m.group(1)
        found.append(current)
    return found


def sections_touched(old: str, new: str) -> list[str | None]:
    """Each section a changed line falls under, once, in the order first met; `None` for the text
    before the first heading."""
    old_lines, new_lines = old.split("\n"), new.split("\n")
    old_sections, new_sections = _sections(old_lines), _sections(new_lines)
    found: list[str | None] = []
    for tag, i1, i2, j1, j2 in opcodes(old_lines, new_lines):
        if tag == "equal":
            continue
        places = new_sections[j1:j2] or old_sections[i1:i2]
        for place in places:
            if place not in found:
                found.append(place)
    return found


def drafted(old: str, new: str, *, appendices: list[str] | tuple[str, ...] = ()) -> str:
    """The summary the finishing screen starts from: the body's sections touched, then the titles
    of the appendices whose text changed."""
    names = [
        name if name is not None else _("the opening text") for name in sections_touched(old, new)
    ] + list(appendices)
    # As many sections as fit the summary's limit, so the drafted text is one the form accepts.
    for count in range(len(names), 0, -1):
        listed = "; ".join(names[:count]) + ("; …" if count < len(names) else "")
        text = _("Sections touched: %(sections)s") % {"sections": listed}
        if len(text) <= SUMMARY_MAX:
            return text
    return _("Sections touched: %(sections)s") % {"sections": "…"}


def problem(summary: str) -> str | None:
    """What is wrong with a summary as the holder left it, or `None`."""
    text = summary.strip()
    if not text:
        return _("Write a summary of the change.")
    # Every character a line splits on, not the newline alone: the version's summary is the
    # commit's first line, read back by the same split.
    if len(text.splitlines()) != 1 or CONTROL.search(text):
        return _("The summary is one line.")
    if len(text) > SUMMARY_MAX:
        return _("The summary is at most %(count)s characters.") % {"count": SUMMARY_MAX}
    if TRAILER_SHAPE.match(text):
        return _("Begin the summary with something other than a word and a colon.")
    return None
