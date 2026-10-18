"""The names an exported file carries (DL-0275, DL-0357): what people call the document, the version
and the stance the file shows, and the marks when it carries them — one token in a shell or a mail
client, and never a character a filesystem refuses.
"""

from __future__ import annotations

import re

# Characters Windows, macOS or Linux refuse in a file name.
REFUSED = re.compile(r'[/\\:*?"<>|]')
# Control characters: a file system refuses some and a zip entry or a terminal misreads the rest;
# a direction control or a line separator makes a name read as another one.
CONTROL = re.compile("[\x00-\x1f\x7f-\x9f\u061c\u200e\u200f\u2028\u2029\u202a-\u202e\u2066-\u2069]")
SEPARATOR = "_—_"
TITLE_MOST = 80


def _safe(text: str) -> str:
    return REFUSED.sub("-", CONTROL.sub("", text)).replace(" ", "_")


def file_name(title: str, version: str, stance: str, ext: str, *, marks: str = "") -> str:
    """`<title>_—_<version>_—_<stance>.<ext>`, the stance followed by `-<marks>` for a marked
    export; the title cut at eighty characters as typed, before anything is replaced."""
    shown = f"{_safe(stance)}-{_safe(marks)}" if marks else _safe(stance)
    return f"{_safe(title[:TITLE_MOST])}{SEPARATOR}{_safe(version)}{SEPARATOR}{shown}.{ext}"


def part_name(word: str, number: int, name: str) -> str:
    """A part inside a zip: `<word>-<number>_—_<name>`."""
    return f"{_safe(word)}-{number}{SEPARATOR}{_safe(name)}"
