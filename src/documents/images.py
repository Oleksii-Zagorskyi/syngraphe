"""The images of a document's tree (DL-0439): each named by its content's hash and its extension,
`images/<sha256>.<ext>`, and kept by the commit exactly while a text references it.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from django.http import HttpResponse

from editing.markdown.parser import parser
from editing.markdown.rules import lines_of

FOLDER = "images"
NAME = re.compile(r"[0-9a-f]{64}\.(png|jpg|gif)")
CONTENT_TYPES = {"png": "image/png", "jpg": "image/jpeg", "gif": "image/gif"}


@dataclass(frozen=True)
class Reference:
    """An image a text references: its `src` as written, the file it is written in, and its line
    there, from 1."""

    src: str
    file: str
    line: int


def is_image_path(src: str) -> bool:
    """Whether `src` is the path of an image the platform names, `images/<sha256>.<ext>`."""
    folder, _, name = src.partition("/")
    return folder == FOLDER and NAME.fullmatch(name) is not None


def referenced(texts: Mapping[str, str]) -> list[Reference]:
    """Every image each text references, by the platform's own parser: for each `(file, text)` —
    `document.md`, then every appendix — each image token's `src` and the line of its source it is
    written on, in order. The line is found in the source, since a callout's marker leaves the
    parsed paragraph a line short."""
    found = []
    for file, text in texts.items():
        lines = lines_of(text)
        for token in parser().parse(text):
            if token.type != "inline" or not token.children or token.map is None:
                continue
            start, end = token.map
            cursor = start
            for child in token.children:
                if child.type != "image":
                    continue
                src = str(child.attrGet("src") or "")
                # A destination is written as it stands or in angle brackets.
                at = next(
                    (
                        n
                        for n in range(cursor, end)
                        if f"({src}" in lines[n] or f"(<{src}>" in lines[n]
                    ),
                    cursor,
                )
                cursor = at
                found.append(Reference(src, file, at + 1))
    return found


def served(data: bytes, name: str) -> HttpResponse:
    """An image's bytes as every image route answers them: the type its checked extension names,
    never the client's or the bytes' guess, and private to the reader; the routes are `never_cache`
    too, so a right lost is lost at the next request."""
    response = HttpResponse(data, content_type=CONTENT_TYPES[name.rsplit(".", 1)[1]])
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Disposition"] = "inline"
    response["Cache-Control"] = "private"
    return response
