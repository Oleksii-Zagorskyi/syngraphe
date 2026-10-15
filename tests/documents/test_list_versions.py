"""The document list's two version columns (DL-0208, DL-0233): *Canonical* the latest edition's
number, *Latest* the latest version the person may see beyond it — the column drawn only for
someone who may see beyond canonical text on at least one listed document.

People and groups are synthetic examples; the text is invented.
"""

from __future__ import annotations

import html
import importlib.util
import re
import sys
from pathlib import Path
from typing import Any

import pytest

from access.rights import Right
from review import services as review
from tenancy.schemas import schema_context

# The editions tests' cast and the review tests' document, groups and versions, shared rather than
# copied a third time.
_spec = importlib.util.spec_from_file_location(
    "editions_fixtures", Path(__file__).resolve().parents[1] / "editions" / "conftest.py"
)
assert _spec is not None and _spec.loader is not None
_fixtures = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _fixtures
_spec.loader.exec_module(_fixtures)
edition_cast = _fixtures.edition_cast
new_document = _fixtures.new_document
link_group = _fixtures.link_group
commit_version = _fixtures.commit_version

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

FIRST = "A request for approval is made in writing.\n"
SECOND = FIRST + "\nA copy of the decision goes to the applicant that day.\n"
THIRD = SECOND + "\nThe register of requests is kept by the officer in charge.\n"


def _cells(body: str, number: int) -> dict[str, str]:
    row = re.search(rf'<tr class="document" data-number="{number}">(.*?)</tr>', body, re.S)
    assert row is not None, body
    return {
        name: html.unescape(re.sub(r"<[^>]+>", "", value)).strip()
        for name, value in re.findall(r'<td class="(canonical|latest)">(.*?)</td>', row.group(1))
    }


def test_version_columns_by_rights(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    settings: Any,
) -> None:
    from editions import services as editions

    settings.LANGUAGE_CODE = "en"
    people = edition_cast()
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
        editions.freeze(document, people["p"])
        editions.make_canonical(document, people["p"])
    commit_version(document, people["a"], SECOND, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
    commit_version(document, people["a"], THIRD, "edit")

    clients = {}
    for name, right in (
        ("pending", Right.VIEW_PENDING),
        ("accepted", Right.VIEW_ACCEPTED),
        ("canonical", Right.VIEW_CANONICAL),
    ):
        client, _, membership = member_of(f"{name}.synthetic@example.test")
        link_group(document, [right], [membership], people["a"])
        clients[name] = client

    pages = {name: client.get("/folder/1/").content.decode() for name, client in clients.items()}

    assert _cells(pages["pending"], document.number) == {"canonical": "1.0", "latest": "1.1-1"}
    assert _cells(pages["accepted"], document.number) == {"canonical": "1.0", "latest": "1.1"}
    assert _cells(pages["canonical"], document.number) == {"canonical": "1.0"}
    assert "<th>Latest</th>" in pages["pending"]
    assert "<th>Latest</th>" not in pages["canonical"]


def test_latest_is_empty_at_the_edition(
    migrated_tenant: Any, edition_cast: Any, member_of: Any, link_group: Any, commit_version: Any
) -> None:
    from editions import services as editions

    people = edition_cast()
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
        editions.freeze(document, people["p"])
        editions.make_canonical(document, people["p"])
    client, _, membership = member_of("pending.synthetic@example.test")
    link_group(document, [Right.VIEW_PENDING], [membership], people["a"])

    cells = _cells(client.get("/folder/1/").content.decode(), document.number)

    # Nothing beyond the edition: the column is drawn, the cell empty.
    assert cells == {"canonical": "1.0", "latest": ""}
