"""ST-0041 end to end: a holder of *view previous canonical versions* and *view canonical* sees the
editions alone on the History tab, opens a past edition, and compares two editions — and never a
pending or an accepted version's number on any of the three pages (DL-0209, DL-0286).

People and their documents are synthetic examples; the text is invented."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import Any

import pytest

from access.rights import Right
from tenancy.schemas import schema_context

_spec = importlib.util.spec_from_file_location(
    "editions_list_history", Path(__file__).resolve().parent / "test_history.py"
)
assert _spec is not None and _spec.loader is not None
_history = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _history
_spec.loader.exec_module(_history)

# The History tests' fixture: the cast of a document's editors, reviewers and approvers.
edition_cast = _history.edition_cast

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

SEVENTH = _history.SIXTH + "\nA decision is recorded in the register the same day.\n"
EIGHTH = SEVENTH + "\nThe register is kept for five years.\n"
VERSION_NUMBER = re.compile(r"(?<![\d.-])(\d+\.\d+(?:-\d+)?)(?!\d)")


def test_editions_listed_and_compared(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    member_of: Any,
    link_group: Any,
) -> None:
    from editions import services as editions
    from review import services as review

    history = _history.standard_history(migrated_tenant, edition_cast, commit_version)
    people, document = history.people, history.document
    # After 1.0: the run accepted, made canonical as 2.0; then accepted and pending work after it.
    with schema_context(migrated_tenant.number):
        assert review.accept(document, people["r"]).number == "1.1"
        editions.freeze(document, people["p"], _history.REASON)
        assert editions.make_canonical(document, people["p"]).number == "2.0"
    commit_version(document, people["a"], SEVENTH, "edit")
    with schema_context(migrated_tenant.number):
        assert review.accept(document, people["r"]).number == "2.1"
    commit_version(document, people["b"], EIGHTH, "edit")
    client, _, membership = member_of("the.reader@example.test")
    link_group(
        document, [Right.VIEW_PREVIOUS_CANONICAL, Right.VIEW_CANONICAL], [membership], people["a"]
    )
    number = document.number

    tab = client.get(f"/document/{number}/history/")
    past = client.get(f"/document/{number}/version/1.0/")
    compared = client.get(f"/document/{number}/compare/?from=1.0&to=2.0")

    assert [r.status_code for r in (tab, past, compared)] == [200, 200, 200]
    listed = set(re.findall(rf'href="/document/{number}/version/([^/"]+)/"', tab.content.decode()))
    assert listed == {"1.0", "2.0"}
    # 2.0's whole text, the lines added since 1.0 marked, and nothing of the work after it.
    changes = compared.content.decode().split('class="changes document-text"', 1)[1]
    changes = changes.split("</div>\n", 1)[0]
    for line in _history.SIXTH.splitlines():
        if line.strip() and not line.startswith("#"):
            assert line in _history.text_of(changes), line
    for added in _history.SIXTH.splitlines()[len(_history.FOURTH.splitlines()) :]:
        if added.strip():
            assert re.search(rf"<ins>[^<]*{re.escape(added[:20])}", changes), added
    assert SEVENTH.splitlines()[-1] not in compared.content.decode()
    # The editions alone, on each page, in its text and in its links and fields.
    for page in (tab, past, compared):
        body = page.content.decode()
        shown = set(VERSION_NUMBER.findall(_history.text_of(body)))
        drawn = set(VERSION_NUMBER.findall(" ".join(re.findall(r'(?:href|value)="([^"]*)"', body))))
        assert shown == {"1.0", "2.0"}, shown
        assert drawn <= {"1.0", "2.0"}, drawn
    assert re.search(
        r'<form class="compare-with"[^>]*>.*?<option value="2\.0">', past.content.decode(), re.S
    )
