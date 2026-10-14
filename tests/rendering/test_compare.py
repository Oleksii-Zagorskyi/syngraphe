"""Comparing two versions (ST-0033, DL-0208, DL-0233): a page of its own, the newer version's whole
text with its changes against the older marked in place, whichever order the pair is asked in; the
attachments of both with each file at each version and whether it changed; nothing for a pair the
reader may not see, and no comparison for a reader who may see one version.

People, groups and texts are synthetic examples; every text is invented.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from access.rights import Right
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

FIRST = "# General provisions\n\nA request for approval is made in writing.\n"
CHANGED = FIRST.replace("in writing", "by email")


def _pair(migrated_tenant: Any, edition_cast: Any, commit_version: Any, kit: Any) -> Any:
    """`0.1` with an attachment, then `0.1-1` with a sentence changed and the attachment replaced;
    a reader holding *view all history* and *view pending*."""
    from review import services as review

    people = edition_cast()
    kit.attach(migrated_tenant.number, people, FIRST, b"first table\n")
    with schema_context(migrated_tenant.number):
        review.accept(people.document, people["r"])
    kit.attach(migrated_tenant.number, people, CHANGED, b"second table\n")
    return people


def _unmasked(page: bytes) -> bytes:
    """A page without its CSRF token, which every response masks afresh."""
    return re.sub(rb'name="csrfmiddlewaretoken" value="[^"]+"', b"", page)


def _text(page: str) -> str:
    """The page's text without its tags."""
    return re.sub(r"<[^>]+>", "", page)


def _reader(member_of: Any, link_group: Any, people: Any, rights: list[Any], name: str) -> Any:
    client, _user, membership = member_of(f"{name}.synthetic@example.test")
    link_group(people.document, rights, [membership], people["a"])
    return client


def test_compare_two_versions(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    kit: Any,
    member_of: Any,
    link_group: Any,
    settings: Any,
) -> None:
    settings.LANGUAGE_CODE = "en"
    people = _pair(migrated_tenant, edition_cast, commit_version, kit)
    client = _reader(
        member_of, link_group, people, [Right.VIEW_ALL_HISTORY, Right.VIEW_PENDING], "h"
    )
    n = people.document.number
    page = client.get(f"/document/{n}/compare/?from=0.1&to=0.1-1")
    assert page.status_code == 200
    body = page.content.decode()
    assert "Comparing 0.1 with 0.1-1 — read only" in _text(body)
    assert f'href="/document/{n}/version/0.1/"' in body
    assert f'href="/document/{n}/version/0.1-1/"' in body
    assert "<del>in</del><ins>by</ins>" in body and "<del>writing.</del><ins>email.</ins>" in body
    # The attachment, changed, with its file at each version (DL-0421).
    assert 'data-change="changed"' in body
    assert f'href="/document/{n}/version/0.1/attachment/1/"' in body
    assert f'href="/document/{n}/version/0.1-1/attachment/1/"' in body
    # The choosers and the button that opens the chosen pair.
    assert 'name="from"' in body and 'name="to"' in body


def test_order_does_not_matter(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    kit: Any,
    member_of: Any,
    link_group: Any,
    settings: Any,
) -> None:
    settings.LANGUAGE_CODE = "en"
    people = _pair(migrated_tenant, edition_cast, commit_version, kit)
    client = _reader(
        member_of, link_group, people, [Right.VIEW_ALL_HISTORY, Right.VIEW_PENDING], "h"
    )
    n = people.document.number
    forward = client.get(f"/document/{n}/compare/?from=0.1&to=0.1-1").content.decode()
    backward = client.get(f"/document/{n}/compare/?from=0.1-1&to=0.1").content.decode()
    assert "Comparing 0.1 with 0.1-1" in _text(backward)
    assert "<ins>by</ins>" in backward and "<ins>email.</ins>" in backward
    marked = forward[forward.index('<div class="changes') :]
    assert marked == backward[backward.index('<div class="changes') :]


def test_no_comparison_without_two_visible_versions(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    kit: Any,
    member_of: Any,
    link_group: Any,
    settings: Any,
) -> None:
    settings.LANGUAGE_CODE = "en"
    people = _pair(migrated_tenant, edition_cast, commit_version, kit)
    n = people.document.number
    # *View accepted* alone reaches `0.1` and nothing else: no comparison, nothing offered.
    accepted = _reader(member_of, link_group, people, [Right.VIEW_ACCEPTED], "acc")
    assert accepted.get(f"/document/{n}/compare/?from=0.1&to=0.1-1").status_code == 404
    # One version against itself is no comparison: it opens that version's page.
    alone = accepted.get(f"/document/{n}/compare/?from=0.1&to=0.1")
    assert alone.status_code == 302 and alone["Location"] == f"/document/{n}/version/0.1/"
    version_page = accepted.get(f"/document/{n}/version/0.1/").content.decode()
    assert "/compare/" not in version_page
    # A pair with a number no version carries, or none at all.
    history = _reader(
        member_of, link_group, people, [Right.VIEW_ALL_HISTORY, Right.VIEW_PENDING], "h"
    )
    missing = history.get("/document/999999/").content
    for query in ("?from=0.1&to=9.9", "?from=0.1", ""):
        answer = history.get(f"/document/{n}/compare/{query}")
        assert answer.status_code == 404, query
        assert _unmasked(answer.content) == _unmasked(missing)
