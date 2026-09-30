"""Fixtures for the editions tests: the review tests' document, groups, versions and cast, loaded
from their own conftest so the two folders build documents alike; and a cast for an edition — an
editor, a reviewer and an approver holding *freeze* and *make canonical*.

People, group names and titles are synthetic examples; every text is invented.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

_spec = importlib.util.spec_from_file_location(
    "review_fixtures", Path(__file__).resolve().parents[1] / "review" / "conftest.py"
)
assert _spec is not None and _spec.loader is not None
_review = importlib.util.module_from_spec(_spec)
# Registered before it runs: its dataclass looks its own module up by name.
sys.modules[_spec.name] = _review
_spec.loader.exec_module(_review)

Cast = _review.Cast
new_document = _review.new_document
link_group = _review.link_group
commit_version = _review.commit_version
cast = _review.cast
repository = _review.repository

BODY = "Перше синтетичне речення.\n\nДруге синтетичне речення.\n"


@pytest.fixture
def edition_cast(member_of: Any, new_document: Any, link_group: Any) -> Callable[..., Cast]:
    """`edition_cast(editors=("a",), reviewers=("r",), approvers=("p",))`: a document linked to
    one group per role that has anyone in it — `edit`, `accept`, and `freeze` with
    `make_canonical` — each member signed in as `<name>.synthetic@example.test`. A name may stand
    in several roles; it is then a member of each role's group."""

    def make(
        editors: tuple[str, ...] = ("a",),
        reviewers: tuple[str, ...] = ("r",),
        approvers: tuple[str, ...] = ("p",),
    ) -> Cast:
        from access.rights import Right

        people: dict[str, Any] = {}
        memberships: dict[str, Any] = {}
        clients: dict[str, Any] = {}
        for name in dict.fromkeys((*editors, *reviewers, *approvers)):
            clients[name], people[name], memberships[name] = member_of(
                f"{name}.synthetic@example.test"
            )
        creator = people[(editors or reviewers or approvers)[0]]
        document = new_document(creator)
        made = Cast(document, people, memberships)
        made.clients = clients  # type: ignore[attr-defined]
        roles = (
            ("editors", editors, [Right.EDIT]),
            ("reviewers", reviewers, [Right.ACCEPT]),
            ("approvers", approvers, [Right.FREEZE, Right.MAKE_CANONICAL]),
        )
        for role, names, rights in roles:
            if names:
                made.groups[role] = link_group(
                    document, rights, [memberships[n] for n in names], creator
                )
        return made

    return make
