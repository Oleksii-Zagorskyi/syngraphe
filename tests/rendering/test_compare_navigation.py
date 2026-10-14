"""Stepping through a history edit by edit (ST-0032, DL-0361): on a comparison of two consecutive
versions — consecutive among the content versions the reader may see, whatever passport or freeze
entries fall between them — *previous* and *next* move the pair one version back and forward,
skipping what the reader may not see, and stand disabled at the ends.

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

BODY = "# General provisions\n\nA request for approval is made in writing.\n"


def _body(n: int) -> str:
    return BODY + "".join(
        f"\nSynthetic sentence number {k} on how a request is considered.\n" for k in range(n)
    )


def _steps(page: str) -> dict[str, str | None]:
    """Where *previous* and *next* lead, `None` for one drawn disabled."""
    found: dict[str, str | None] = {}
    for step in ("previous", "next"):
        link = re.search(rf'<a class="step {step}" href="([^"]+)"', page)
        disabled = re.search(rf'<button class="step {step}"[^>]*disabled', page)
        assert link or disabled, step
        found[step] = link.group(1).replace("&amp;", "&") if link else None
    return found


def test_previous_and_next_move_the_pair(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    member_of: Any,
    link_group: Any,
    settings: Any,
) -> None:
    from editions import services as editions

    settings.LANGUAGE_CODE = "en"
    people = edition_cast()
    document = people.document
    for k in range(1, 4):
        commit_version(document, people["a"], _body(k), "edit")
    with schema_context(migrated_tenant.number):
        # A freeze and its unfreeze between 0.0-3 and 0.0-4: no version, no break in the pair.
        editions.freeze(document, people["p"], "Synthetic reason")
        editions.end_freeze(document, user=people["p"])
    for k in range(4, 6):
        commit_version(document, people["a"], _body(k), "edit")
    client, _user, membership = member_of("h.synthetic@example.test")
    link_group(document, [Right.VIEW_ALL_HISTORY, Right.VIEW_PENDING], [membership], people["a"])
    n = document.number

    page = client.get(f"/document/{n}/compare/?from=0.0-3&to=0.0-4").content.decode()
    steps = _steps(page)
    assert steps["previous"] == f"/document/{n}/compare/?from=0.0-2&to=0.0-3"
    assert steps["next"] == f"/document/{n}/compare/?from=0.0-4&to=0.0-5"
    last = _steps(client.get(f"/document/{n}/compare/?from=0.0-4&to=0.0-5").content.decode())
    assert last["next"] is None and last["previous"] is not None
    first = _steps(client.get(f"/document/{n}/compare/?from=0.0&to=0.0-1").content.decode())
    assert first["previous"] is None
    assert first["next"] == f"/document/{n}/compare/?from=0.0-1&to=0.0-2"
    # A pair that is not consecutive has no stepping.
    apart = client.get(f"/document/{n}/compare/?from=0.0-1&to=0.0-4").content.decode()
    assert 'class="step' not in apart


def test_versions_the_reader_may_not_see_are_skipped(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    member_of: Any,
    link_group: Any,
    kit: Any,
    settings: Any,
) -> None:
    settings.LANGUAGE_CODE = "en"
    people = edition_cast()
    tenant = migrated_tenant.number
    for k in range(1, 4):
        kit.canonical(tenant, people, commit_version, _body(k))
        # Pending work between the editions, which the reader below never sees.
        commit_version(people.document, people["a"], _body(k) + "\nA draft.\n", "edit")
    client, _user, membership = member_of("c.synthetic@example.test")
    link_group(
        people.document,
        [Right.VIEW_PREVIOUS_CANONICAL, Right.VIEW_CANONICAL],
        [membership],
        people["a"],
    )
    n = people.document.number
    page = client.get(f"/document/{n}/compare/?from=1.0&to=2.0").content.decode()
    steps = _steps(page)
    assert steps["next"] == f"/document/{n}/compare/?from=2.0&to=3.0"
    assert steps["previous"] is None
    later = client.get(f"/document/{n}/compare/?from=2.0&to=3.0")
    assert later.status_code == 200
    assert _steps(later.content.decode())["next"] is None
