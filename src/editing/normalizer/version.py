"""The normalizer version each commit records (DL-0112, ADR-0012): the rule set and the revision
of the two lists it loaded, so a list edit is a new normalizer version and a line's split can be
traced to the lists that made it."""

from __future__ import annotations

import hashlib
import json

from editing.normalizer.splitter import Lists

# Raised whenever a rule of any stage changes what the normalizer writes.
RULESET = "1"


def lists_revision(lists: Lists) -> str:
    """A hash of the two lists as loaded, in their order: twelve hexadecimal digits of SHA-256."""
    payload = json.dumps(
        {"never_final": list(lists.never_final), "may_be_final": list(lists.may_be_final)},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def trailer(ruleset: str, lists: Lists) -> str:
    """The commit trailer: `Normalizer: <ruleset>@<lists revision>`."""
    return f"Normalizer: {ruleset}@{lists_revision(lists)}"
