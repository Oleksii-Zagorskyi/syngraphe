"""No personal data in a commit: the author is a user id and a non-routable address (DL-0088,
DL-0093)."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pygit2
import pytest

from documents import gitstore
from documents.gitstore import Kind
from documents.identity import identity_for
from identity.models import User

pytestmark = pytest.mark.integration

ADDRESS = re.compile(r"^[0-9a-f-]{36}@users\.noreply\.syngraphe\.local$")
# The corpus's three authors, mapped to fixed people with display names that must never reach git.
PEOPLE = {
    1: User(
        id=uuid.UUID("11111111-1111-4111-8111-111111111111"),
        email="first.author@example.test",
        display_name="First Author",
    ),
    2: User(
        id=uuid.UUID("22222222-2222-4222-8222-222222222222"),
        email="second.author@example.test",
        display_name="Second Author",
    ),
    3: User(
        id=uuid.UUID("33333333-3333-4333-8333-333333333333"),
        email="third.author@example.test",
        display_name="Third Author",
    ),
}


def test_identity_is_the_id_and_a_non_routable_address() -> None:
    at = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)

    sig = identity_for(PEOPLE[1], at=at)

    assert sig.name == "11111111-1111-4111-8111-111111111111"
    assert sig.email == "11111111-1111-4111-8111-111111111111@users.noreply.syngraphe.local"
    assert sig.time == int(at.timestamp())
    assert sig.offset == 0


def test_a_naive_time_is_refused() -> None:
    with pytest.raises(ValueError):
        identity_for(PEOPLE[1], at=datetime(2026, 9, 1, 12, 0))


def test_no_personal_data_in_history(repo_root: Path, corpus_ukr: dict[str, Any]) -> None:
    source = pygit2.Repository(str(corpus_ukr["repo"]))
    history = list(
        source.walk(
            source.references["refs/heads/main"].target,
            pygit2.enums.SortMode.TOPOLOGICAL | pygit2.enums.SortMode.REVERSE,
        )
    )
    assert len(history) == len(corpus_ukr["truth"]["commits"]) == 203
    repo = gitstore.init(tenant=1, document=1)

    for n, original in enumerate(history):
        person = PEOPLE[int(original.author.name)]
        at = datetime.fromtimestamp(original.author.time, tz=UTC)
        gitstore.commit(
            repo,
            {"document.md": original.tree["document.md"].data},
            identity_for(person, at=at),
            original.message.strip(),
            Kind.CREATED if n == 0 else Kind.EDIT,
        )

    replayed = list(repo.walk(repo.head.target))
    assert len(replayed) == 203
    forbidden = [p.display_name for p in PEOPLE.values()] + [p.email for p in PEOPLE.values()]
    for commit in replayed:
        for sig in (commit.author, commit.committer):
            assert uuid.UUID(sig.name)
            assert ADDRESS.match(sig.email)
            assert not any(value in sig.name or value in sig.email for value in forbidden)
    assert replayed[0].tree["document.md"].data == history[-1].tree["document.md"].data
