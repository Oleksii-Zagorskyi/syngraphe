"""The text files of a document's bundle (ADR-0005): `document.md`'s frontmatter and body, the
passport's header, and the tree a new document starts with.

The frontmatter is YAML read with `safe_load` and written here, its keys in a fixed order and every
string quoted, so that what the platform writes reads back to the same bytes (DL-0309).
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

import yaml

KEYS = ("title", "language", "title_page", "appendices", "attachments")
APPENDIX_KEYS = ("number", "title")
ATTACHMENT_KEYS = ("number", "title", "file_name", "sha256", "bytes")
DELIMITER = "---\n"
# Characters a YAML reader refuses or reads as a line break, written as escapes instead.
UNPRINTABLE = re.compile("[\x7f-\x9f\u2028\u2029\ufffe\uffff]")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
TITLE_MAX = 500
NUMBER_MAX = 2**31 - 1


def valid_title(title: str) -> bool:
    """A title the frontmatter and the row both hold: one line of printable text."""
    return (
        bool(title.strip())
        and len(title) <= TITLE_MAX
        and not any(unicodedata.category(ch) in ("Cc", "Cs", "Cn") for ch in title)
    )


class _UniqueKeyLoader(yaml.SafeLoader):
    """The safe loader, refusing a mapping that names one key twice."""


def _mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode) -> dict[Any, Any]:
    keys = [loader.construct_object(key) for key, _ in node.value]
    if len(keys) != len(set(keys)):
        raise yaml.constructor.ConstructorError(None, None, "a key is repeated", node.start_mark)
    return loader.construct_mapping(node)


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


@dataclass
class Frontmatter:
    """What `document.md` says about the document: the cache a row keeps, and the parts."""

    title: str
    language: str
    title_page: bool = False
    appendices: list[dict[str, Any]] = field(default_factory=list)
    attachments: list[dict[str, Any]] = field(default_factory=list)


def _string(value: str) -> str:
    # A JSON string is a YAML double-quoted scalar once what YAML cannot hold raw is escaped.
    return UNPRINTABLE.sub(
        lambda match: f"\\u{ord(match.group()):04x}", json.dumps(value, ensure_ascii=False)
    )


def _scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return _string(str(value))


def _items(name: str, items: list[dict[str, Any]], keys: tuple[str, ...]) -> list[str]:
    if not items:
        return [f"{name}: []"]
    lines = [f"{name}:"]
    for item in items:
        present = [key for key in keys if key in item]
        for n, key in enumerate(present):
            lines.append(f"{'  - ' if n == 0 else '    '}{key}: {_scalar(item[key])}")
    return lines


def render(frontmatter: Frontmatter, body: str) -> str:
    """`document.md` from its frontmatter and body."""
    lines = [
        f"title: {_string(frontmatter.title)}",
        f"language: {_string(frontmatter.language)}",
        f"title_page: {_scalar(frontmatter.title_page)}",
        *_items("appendices", frontmatter.appendices, APPENDIX_KEYS),
        *_items("attachments", frontmatter.attachments, ATTACHMENT_KEYS),
    ]
    return DELIMITER + "\n".join(lines) + "\n" + DELIMITER + "\n" + body


def _checked_items(value: Any, keys: tuple[str, ...], name: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(f"{name} is a list")
    for item in value:
        number = item.get("number") if isinstance(item, dict) else None
        if (
            not isinstance(item, dict)
            or set(item) - set(keys)
            or type(number) is not int
            or not 1 <= number <= NUMBER_MAX
            or not isinstance(item.get("title"), str)
            or not valid_title(item["title"])
        ):
            raise ValueError(f"an entry of {name} is not a part")
        if keys is ATTACHMENT_KEYS:
            size = item.get("bytes")
            if (
                not isinstance(item.get("file_name"), str)
                or not isinstance(item.get("sha256"), str)
                or not SHA256.match(item["sha256"])
                or type(size) is not int
                or size < 0
            ):
                raise ValueError(f"an entry of {name} is not an attachment")
    return value


def parse(text: str) -> tuple[Frontmatter, str]:
    """The frontmatter and the body of `document.md`; `ValueError` for anything else.

    The body follows one blank line, which `render` writes and `parse` removes.
    """
    if not text.startswith(DELIMITER):
        raise ValueError("document.md starts with its frontmatter")
    end = text.find("\n" + DELIMITER, len(DELIMITER) - 1)
    if end < 0:
        raise ValueError("the frontmatter is not closed")
    source = text[len(DELIMITER) : end + 1]
    body = text[end + 1 + len(DELIMITER) :].removeprefix("\n")
    try:
        data = yaml.load(source, Loader=_UniqueKeyLoader)
    except yaml.YAMLError as error:
        raise ValueError("the frontmatter is not YAML") from error
    if not isinstance(data, dict) or set(data) - set(KEYS):
        raise ValueError("the frontmatter holds the document's own keys only")
    title, language = data.get("title"), data.get("language")
    title_page = data.get("title_page", False)
    if not isinstance(title, str) or not valid_title(title):
        raise ValueError("the frontmatter names a title of one printable line")
    if not isinstance(language, str) or not language:
        raise ValueError("the frontmatter names a language")
    if not isinstance(title_page, bool):
        raise ValueError("title_page is true or false")
    return (
        Frontmatter(
            title=title,
            language=language,
            title_page=title_page,
            appendices=_checked_items(data.get("appendices", []), APPENDIX_KEYS, "appendices"),
            attachments=_checked_items(data.get("attachments", []), ATTACHMENT_KEYS, "attachments"),
        ),
        body,
    )


def passport_header(tenant: int, document: int) -> str:
    """The passport as a new document has it: numbers only, never a name (DL-0088)."""
    return f"{DELIMITER}document: {document}\ntenant: {tenant}\n{DELIMITER}"


def initial_tree(
    *, tenant: int, document: int, title: str, language: str, title_page: bool, outline: str
) -> dict[str, bytes]:
    """The files of a new document's first commit: `document.md` from the organisation's
    template, the passport's header, and an empty list of entities."""
    frontmatter = Frontmatter(title=title, language=language, title_page=title_page)
    return {
        "document.md": render(frontmatter, outline).encode("utf-8"),
        "passport.md": passport_header(tenant, document).encode("utf-8"),
        "entities.yaml": b"[]\n",
    }
