"""`entities.yaml`: the roles, actions and terms a document declares (DL-0073, ADR-0005).

A list of declarations, each a kind, a key and a label. The text marks an entity with a span whose
id is the key; a span naming a key the file does not declare is declared at commit, labelled with
its first span's words (DL-0440). Written by `dump` with its keys in a fixed order and every string
quoted, so that what the platform writes reads back to the same bytes, as the frontmatter is.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any, Literal

import yaml

from documents.bundle import UniqueKeyLoader, _string
from editing.markdown import load_spec
from editing.markdown.parser import parser
from editing.markdown.words import span_words

logger = logging.getLogger(__name__)

# The span kinds that name an entity: the specification's spans, less the underline, which is
# formatting, and the mention, which names a document.
KINDS = ("role", "action", "term")
KEY = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
LABEL_MAX = 200
FIELDS = ("kind", "key", "label")
# The file is held to the size the body is: a commit derived from a body at its limit stays a
# commit of seconds under the writer lock.
MAX_BYTES = load_spec().max_bytes


@dataclass(frozen=True)
class Declared:
    kind: str
    key: str
    label: str


@dataclass(frozen=True)
class EntityChange:
    """An entity added, relabelled or removed between two files; `before` and `after` are its
    labels, empty on the side it is absent from."""

    kind: str
    key: str
    change: Literal["added", "relabelled", "removed"]
    before: str
    after: str


def valid_label(label: str) -> bool:
    """One printable line of 1 to 200 characters."""
    return (
        0 < len(label) <= LABEL_MAX
        and label == label.strip()
        and not any(unicodedata.category(ch) in ("Cc", "Cs", "Cn", "Zl", "Zp") for ch in label)
    )


def _declared(number: int, entry: Any) -> Declared:
    if not isinstance(entry, dict) or set(entry) != set(FIELDS):
        raise ValueError(f"entry {number}: not a kind, a key and a label")
    kind, key, label = (entry[field] for field in FIELDS)
    if kind not in KINDS:
        raise ValueError(f"entry {number}: an unknown kind")
    if not isinstance(key, str) or not KEY.fullmatch(key):
        raise ValueError(f"entry {number}: a key outside letters, digits, '-' and '_'")
    if not isinstance(label, str) or not valid_label(label):
        raise ValueError(f"entry {number}: a label that is not one line of 1 to 200 characters")
    return Declared(kind, key, label)


def parse(text: str) -> list[Declared]:
    """The declarations of `text`; `ValueError` for anything that does not read as one, naming
    the first entry that breaks a rule."""
    if not isinstance(text, str):
        raise ValueError("entry 1: the file is not text")
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise ValueError("entry 1: the file is longer than the platform accepts")
    try:
        loaded = yaml.load(text, Loader=UniqueKeyLoader)  # noqa: S506 — the safe loader's subclass
    except (yaml.YAMLError, TypeError, RecursionError) as error:
        # The entry is the number of list items started up to the error's line.
        mark = getattr(error, "problem_mark", None)
        line = mark.line if mark is not None else 0
        number = sum(1 for row in text.splitlines()[: line + 1] if row.startswith("- "))
        raise ValueError(f"entry {max(number, 1)}: {error}") from error
    if loaded is None:
        return []
    if not isinstance(loaded, list):
        raise ValueError("entry 1: the file is not a list")
    found = [_declared(n, entry) for n, entry in enumerate(loaded, 1)]
    seen: set[tuple[str, str]] = set()
    for number, declared in enumerate(found, 1):
        if (declared.kind, declared.key) in seen:
            raise ValueError(f"entry {number}: declared twice")
        seen.add((declared.kind, declared.key))
    return found


def dump(entries: list[Declared]) -> str:
    """The file's text for `entries`; `parse(dump(x)) == x`."""
    if not entries:
        return "[]\n"
    return "".join(
        f"- kind: {_string(e.kind)}\n  key: {_string(e.key)}\n  label: {_string(e.label)}\n"
        for e in entries
    )


def label(children: list[Any], start: int) -> str:
    """The label a span declares: its words, cut where a label is."""
    return span_words(children, start)[:LABEL_MAX].strip()


def spans(*bodies: str) -> Iterator[tuple[str, str | None, str]]:
    """Every role, action or term span of `bodies`, in order: its kind, its id or `None`, and its
    label (`label`)."""
    for body in bodies:
        for token in parser().parse(body):
            if token.type != "inline" or not token.children:
                continue
            children = token.children
            for i, child in enumerate(children):
                if child.type == "entity_open" and child.meta.get("kind") in KINDS:
                    yield child.meta["kind"], child.meta.get("id"), label(children, i)


def with_spans(
    entries: list[Declared], found: Iterable[tuple[str, str | None, str]]
) -> list[Declared]:
    """`entries` with a declaration appended for each span of `found` (`spans`) whose kind and id
    they lack, in the order of first occurrence, labelled with that span's words. A span without
    an id declares nothing."""
    known = {(e.kind, e.key) for e in entries}
    added = []
    for kind, key, label in found:
        if key is None or (kind, key) in known or not valid_label(label):
            continue
        known.add((kind, key))
        added.append(Declared(kind, key, label))
    return entries + added


def declared_with(text: str, *bodies: str) -> str:
    """`text` with the declarations `with_spans` adds for the spans of `bodies`; `text` itself
    when nothing is missing."""
    entries = parse(text)
    found = with_spans(entries, spans(*bodies))
    return text if len(found) == len(entries) else dump(found)


def readable(text: str, document: int) -> list[Declared] | None:
    """The declarations of `text`; `None` for a file that does not read, logged so the operator
    learns of it — for a page that shows what it can rather than fail."""
    try:
        return parse(text)
    except ValueError:
        logger.warning("entities.yaml does not read", extra={"document": document})
        return None


def changes(old: str, new: str) -> list[EntityChange]:
    """What changed from the file `old` to the file `new` (`compare`)."""
    return compare(parse(old), parse(new))


def compare(old: list[Declared], new: list[Declared]) -> list[EntityChange]:
    """What changed from `old` to `new`: in the new list's order, then the removed ones'."""
    before = {(e.kind, e.key): e for e in old}
    after = new
    found = []
    for entry in after:
        earlier = before.get((entry.kind, entry.key))
        if earlier is None:
            found.append(EntityChange(entry.kind, entry.key, "added", "", entry.label))
        elif earlier.label != entry.label:
            found.append(
                EntityChange(entry.kind, entry.key, "relabelled", earlier.label, entry.label)
            )
    kept = {(e.kind, e.key) for e in after}
    found.extend(
        EntityChange(e.kind, e.key, "removed", e.label, "")
        for key, e in before.items()
        if key not in kept
    )
    return found
