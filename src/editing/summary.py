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
# The line breaks a line can end in unseen by a split on it: the next line, the line and the
# paragraph separators.
SEPARATORS = re.compile("[\x85\u2028\u2029]")
SUMMARY_MAX = 500
# The whole summary, its body included (DL-0535): the first line keeps `SUMMARY_MAX`.
SUMMARY_WHOLE_MAX = 5000


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


def normalised(summary: str) -> str:
    """The summary as a browser posts it, every line ending a line feed: a `<textarea>` joins its
    lines with CRLF, which a commit's message refuses."""
    return summary.replace("\r\n", "\n").replace("\r", "\n")


def as_message(summary: str) -> str:
    """The commit's message for a summary: its first line the subject, the rest its body after a
    blank line, as git reads a message (DL-0532)."""
    first, _, rest = normalised(summary).strip().partition("\n")
    rest = rest.strip("\n")
    return f"{first.strip()}\n\n{rest}" if rest else first.strip()


def first_line(summary: str) -> str:
    """The line every list reads (DL-0532)."""
    return summary.strip().split("\n", 1)[0]


def problem(summary: str) -> str | None:
    """What is wrong with a summary as the holder left it, or `None`: the first line required, at
    most `SUMMARY_MAX` and not shaped like a trailer; every line free of control characters and of
    every line break but the line feed, none shaped like a trailer; the whole at most
    `SUMMARY_WHOLE_MAX` (DL-0532, DL-0535)."""
    text = normalised(summary).strip()
    if not text:
        return _("Write a summary of the change.")
    lines = text.split("\n")
    # Every character a line splits on but the line feed: the version's summary is read back from
    # the commit by the same split.
    if (
        CONTROL.search(text)
        or SEPARATORS.search(text)
        or any(len(line.splitlines()) > 1 for line in lines)
    ):
        return _("The summary holds a character that is not text.")
    if len(lines[0].strip()) > SUMMARY_MAX:
        return _("The summary's first line is at most %(count)s characters.") % {
            "count": SUMMARY_MAX
        }
    if len(text) > SUMMARY_WHOLE_MAX:
        return _("The summary is at most %(count)s characters.") % {"count": SUMMARY_WHOLE_MAX}
    if TRAILER_SHAPE.match(lines[0]):
        return _("The summary cannot begin with a word and a colon.")
    for n, line in enumerate(lines[1:], 2):
        if TRAILER_SHAPE.match(line.strip()):
            return _("Line %(number)s of the summary cannot begin with a word and a colon.") % {
                "number": n
            }
    return None
