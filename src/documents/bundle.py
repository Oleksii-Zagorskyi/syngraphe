"""The text files of a document's bundle (ADR-0005): `document.md`'s frontmatter and body, the
passport's header and its sections, and the tree a new document starts with.

The frontmatter is YAML read with `safe_load` and written here, its keys in a fixed order and every
string quoted, so that what the platform writes reads back to the same bytes (DL-0309).
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import yaml

KEYS = ("title", "language", "title_page", "title_page_text", "appendices", "attachments")
APPENDIX_KEYS = ("number", "title")
ATTACHMENT_KEYS = ("number", "title", "file_name", "sha256", "bytes")
DELIMITER = "---\n"
# Characters a YAML reader refuses or reads as a line break, written as escapes instead.
UNPRINTABLE = re.compile("[\x7f-\x9f\u2028\u2029\ufffe\uffff]")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
# Marks that change the order a name is displayed in, so a file name would read as another.
DIRECTION = re.compile("[\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]")
TITLE_MAX = 500
NUMBER_MAX = 2**31 - 1
# The document's own title-page text (DL-0476): plain lines, as many as a title page holds.
TITLE_PAGE_TEXT_MAX = 500
TITLE_PAGE_TEXT_LINES = 8


def valid_title(title: str) -> bool:
    """A title the frontmatter and the row both hold: one line of printable text."""
    return (
        bool(title.strip())
        and len(title) <= TITLE_MAX
        and not any(unicodedata.category(ch) in ("Cc", "Cs", "Cn") for ch in title)
    )


def clean_title_page_text(text: str) -> str:
    """The title-page text as stored: its line endings one, each line's trailing white space and
    the empty lines at either end removed; an indent is the holder's and stays."""
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def valid_title_page_text(text: str) -> bool:
    """Plain text of at most `TITLE_PAGE_TEXT_MAX` characters on `TITLE_PAGE_TEXT_LINES` lines: no
    control character but the line break, no mark reordering the text around it; empty is none."""
    return (
        len(text) <= TITLE_PAGE_TEXT_MAX
        and text.count("\n") < TITLE_PAGE_TEXT_LINES
        and not DIRECTION.search(text)
        and not any(
            unicodedata.category(ch) in ("Cc", "Cs", "Cn", "Zl", "Zp") and ch != "\n" for ch in text
        )
    )


class UniqueKeyLoader(yaml.SafeLoader):
    """The safe loader, refusing a mapping that names one key twice."""


def _mapping(loader: UniqueKeyLoader, node: yaml.MappingNode) -> dict[Any, Any]:
    keys = [loader.construct_object(key) for key, _ in node.value]
    if len(keys) != len(set(keys)):
        raise yaml.constructor.ConstructorError(None, None, "a key is repeated", node.start_mark)
    return loader.construct_mapping(node)


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


@dataclass
class Frontmatter:
    """What `document.md` says about the document: the cache a row keeps, and the parts."""

    title: str
    language: str
    title_page: bool = False
    appendices: list[dict[str, Any]] = field(default_factory=list)
    attachments: list[dict[str, Any]] = field(default_factory=list)
    # Last, so every construction by position stands; empty means the document has none.
    title_page_text: str = ""


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
        # Written only when there is one, so a document without it reads as it always did.
        *(
            [f"title_page_text: {_string(frontmatter.title_page_text)}"]
            if frontmatter.title_page_text
            else []
        ),
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
        data = yaml.load(source, Loader=UniqueKeyLoader)
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
    title_page_text = data.get("title_page_text", "")
    if not isinstance(title_page_text, str) or not valid_title_page_text(title_page_text):
        raise ValueError("title_page_text is plain text of a few lines")
    return (
        Frontmatter(
            title=title,
            language=language,
            title_page=title_page,
            title_page_text=title_page_text,
            appendices=_checked_items(data.get("appendices", []), APPENDIX_KEYS, "appendices"),
            attachments=_checked_items(data.get("attachments", []), ATTACHMENT_KEYS, "attachments"),
        ),
        body,
    )


def passport_header(tenant: int, document: int) -> str:
    """The passport as a new document has it: numbers only, never a name (DL-0088)."""
    return f"{DELIMITER}document: {document}\ntenant: {tenant}\n{DELIMITER}"


# One section per passport commit (ADR-0005): `## <kind>[ <number>]`, a blank line, then its
# fields one per line, `name: value`, identifiers only (DL-0088).
PASSPORT_KINDS = ("acceptance", "return", "approval")
PASSPORT_FIELDS = {
    "acceptance": {"at", "by", "version"},
    "return": {"at", "by", "version", "reason"},
    "approval": {"at", "by", "version", "edition"},
}
PASSPORT_SECTION = re.compile(r"## (?P<kind>[a-z]+)(?: (?P<number>[0-9]{1,10}\.[0-9]{1,10}))?")
PASSPORT_FIELD = re.compile(r"(?P<name>[a-z]+): (?P<value>\S(?:.*\S)?)")
PASSPORT_NUMBER = re.compile(r"[0-9]{1,10}\.[0-9]{1,10}")
PASSPORT_SHA = re.compile(r"[0-9a-f]{40}")
PASSPORT_AT_SHAPE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
PASSPORT_AT = "%Y-%m-%dT%H:%M:%SZ"
# Everything a line-oriented reader may take for a line's end, and every other control character.
PASSPORT_BREAK = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029\u202a-\u202e\u2066-\u2069]")
# A person is named by their identifier alone (DL-0088).
PASSPORT_BY = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


@dataclass(frozen=True)
class PassportEntry:
    """One decision the passport records: its kind, the number it gave, when (UTC, to the
    second), who by — a user's identifier — and the content commit it decides on."""

    kind: str
    number: str | None
    at: datetime
    by: str
    version: str
    reason: str | None = None
    edition: str | None = None

    def section(self) -> str:
        head = f"## {self.kind}" + (f" {self.number}" if self.number else "")
        fields = [
            ("at", self.at.astimezone(UTC).strftime(PASSPORT_AT)),
            ("by", self.by),
            ("version", self.version),
            ("reason", self.reason),
            ("edition", self.edition),
        ]
        lines = [f"{name}: {value}" for name, value in fields if value is not None]
        return head + "\n\n" + "\n".join(lines) + "\n"


def _checked_entry(entry: PassportEntry) -> PassportEntry:
    if entry.kind not in PASSPORT_KINDS or not PASSPORT_SHA.fullmatch(entry.version):
        raise ValueError("not a passport entry")
    if entry.at.tzinfo is None or entry.at.microsecond:
        raise ValueError("a passport's time carries its zone and counts whole seconds")
    if {"reason": entry.reason, "edition": entry.edition}.keys() & PASSPORT_FIELDS[entry.kind] != {
        name for name, value in (("reason", entry.reason), ("edition", entry.edition)) if value
    }:
        raise ValueError("a passport entry carries the fields of its kind")
    for number in (entry.number, entry.edition):
        if number is not None and not PASSPORT_NUMBER.fullmatch(number):
            raise ValueError("a passport number is N.M")
    if not PASSPORT_BY.fullmatch(entry.by):
        raise ValueError("a passport names a person by their identifier")
    for value in (entry.by, entry.reason):
        if value is not None and (
            PASSPORT_BREAK.search(value) or not PASSPORT_FIELD.fullmatch(f"by: {value}")
        ):
            raise ValueError("a passport field is one line of text, without edge spaces")
    return entry


def append_passport(text: str, entry: PassportEntry) -> str:
    """The passport with `entry` appended as its last section: append-only, every earlier byte
    kept (ADR-0005). The section is read back before it is returned, so the passport never holds
    one its reader refuses."""
    if not text.startswith(DELIMITER):
        raise ValueError("passport.md starts with its frontmatter")
    try:
        section = _checked_entry(entry).section()
    except OverflowError as error:
        raise ValueError("a passport's time out of range") from error
    if passport_entries(DELIMITER + DELIMITER + "\n" + section) != [entry]:
        raise ValueError("a passport section that does not read back")
    body = text if text.endswith("\n") else text + "\n"
    return body + "\n" + section


def passport_entries(text: str) -> list[PassportEntry]:
    """Every section of the passport, in order; `ValueError` for anything it cannot read: text
    between the header and the first section, an unknown field, a field twice or missing."""
    entries: list[PassportEntry] = []
    header, *chunks = re.split(r"(?m)^(?=## )", text)
    if not header.startswith(DELIMITER) or header[len(DELIMITER) :].find(DELIMITER) < 0:
        raise ValueError("passport.md starts with its frontmatter")
    closing = header.index(DELIMITER, len(DELIMITER)) + len(DELIMITER)
    if header[closing:].strip("\n"):
        raise ValueError("text between the passport's header and its first section")
    for chunk in chunks:
        head, *rest = chunk.strip("\n").split("\n")
        match = PASSPORT_SECTION.fullmatch(head)
        if match is None or match.group("kind") not in PASSPORT_KINDS:
            raise ValueError("a passport section of no known kind")
        kind = match.group("kind")
        fields: dict[str, str] = {}
        for line in rest:
            if not line:
                continue
            found = PASSPORT_FIELD.fullmatch(line)
            if (
                found is None
                or found.group("name") in fields
                or found.group("name") not in PASSPORT_FIELDS[kind]
            ):
                raise ValueError("a passport field that does not read")
            fields[found.group("name")] = found.group("value")
        if set(fields) != PASSPORT_FIELDS[kind]:
            raise ValueError("a passport section lacks a field")
        if not PASSPORT_AT_SHAPE.fullmatch(fields["at"]):
            raise ValueError("a passport time that does not read")
        try:
            at = datetime.strptime(fields["at"], PASSPORT_AT).replace(tzinfo=UTC)
            entry = PassportEntry(
                kind=match.group("kind"),
                number=match.group("number"),
                at=at,
                by=fields["by"],
                version=fields["version"],
                reason=fields.get("reason"),
                edition=fields.get("edition"),
            )
        except ValueError as error:
            raise ValueError("a passport time that does not read") from error
        entries.append(_checked_entry(entry))
    return entries


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
