"""Edit authors on a comparison of two versions (DL-0528): with *Show edit authors* on, each
changed paragraph of the newer text names who last edited it between the two versions; past a span
of versions the page draws no names and says so; two documents compared carry no authors.

People, documents and texts are synthetic examples."""

from __future__ import annotations

import re
from typing import Any

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

BASE = (
    "# General provisions\n\n"
    "A request for approval is made in writing.\n\n"
    "A request is answered within ten days.\n\n"
    "A refused request may be made again.\n"
)
BY_A = BASE.replace("in writing", "by email")
BY_B = BY_A.replace("ten days", "five days")
LONG = "Edit authors are not shown for a span this long."


@pytest.fixture(autouse=True)
def in_english(settings: Any) -> None:
    settings.LANGUAGE_CODE = "en"


def _two_authors(edition_cast: Any, commit_version: Any) -> Any:
    from identity.models import User

    people = edition_cast(editors=("a", "b"))
    for name, shown in (("a", "Synthetic Author A"), ("b", "Synthetic Author B")):
        User.objects.filter(pk=people[name].pk).update(display_name=shown)
    commit_version(people.document, people["a"], BASE, "edit")
    commit_version(people.document, people["a"], BY_A, "edit")
    commit_version(people.document, people["b"], BY_B, "edit")
    return people


def _named(page: str) -> dict[str, str]:
    return {
        re.sub(r"<[^>]+>", "", body).strip(): who
        for _tag, who, body in re.findall(
            r'<(p|span)\b[^>]*data-author="([^"]+)"[^>]*>(.*?)</\1>', page, re.S
        )
    }


def test_a_pair_names_its_authors(edition_cast: Any, commit_version: Any) -> None:
    people = _two_authors(edition_cast, commit_version)
    client = people.clients["r"]
    url = f"/document/{people.document.number}/compare/?from=0.0-1&to=0.0-3"

    off = client.get(url).content.decode()
    assert "data-author" not in off
    assert 'action="/preferences/show-author/"' in off
    client.post("/preferences/show-author/", {"show_author": "on"})
    page = client.get(url).content.decode()
    named = _named(page)

    # The marked text interleaves removed and added words: each sentence by its unchanged ones.
    by_email = next(k for k in named if "request for approval" in k)
    five_days = next(k for k in named if "answered within" in k)
    assert named[by_email] == "Synthetic Author A"
    assert named[five_days] == "Synthetic Author B"
    assert not any("may be made again" in k for k in named)


def test_past_the_span_no_names_and_a_sentence(
    edition_cast: Any, commit_version: Any, monkeypatch: Any
) -> None:
    people = _two_authors(edition_cast, commit_version)
    client = people.clients["r"]
    client.post("/preferences/show-author/", {"show_author": "on"})
    monkeypatch.setattr("rendering.views.PAIR_SPAN_MAX", 1)
    url = f"/document/{people.document.number}/compare/?from=0.0-1&to=0.0-3"

    page = client.get(url).content.decode()

    assert "data-author" not in page and LONG in page


def test_two_documents_carry_no_authors(
    edition_cast: Any, commit_version: Any, new_document: Any
) -> None:
    people = _two_authors(edition_cast, commit_version)
    client = people.clients["a"]
    client.post("/preferences/show-author/", {"show_author": "on"})
    other = new_document(people["a"])
    commit_version(other, people["a"], BY_B, "edit")

    page = client.get(f"/document/{people.document.number}/compare/?with={other.number}")
    body = page.content.decode()

    assert page.status_code == 200
    assert 'action="/preferences/show-author/"' not in body and "data-author" not in body


def test_the_sentence_reads_in_ukrainian(
    edition_cast: Any, commit_version: Any, monkeypatch: Any, settings: Any
) -> None:
    people = _two_authors(edition_cast, commit_version)
    client = people.clients["r"]
    client.post("/preferences/show-author/", {"show_author": "on"})
    monkeypatch.setattr("rendering.views.PAIR_SPAN_MAX", 1)
    settings.LANGUAGE_CODE = "uk"

    page = client.get(f"/document/{people.document.number}/compare/?from=0.0-1&to=0.0-3")

    body = page.content.decode()
    assert "Автори правок не показуються" in body and LONG not in body


def _rows_for(people: Any, number: str, tenant: Any) -> None:
    """The older version's own authorship rows, as its historical page leaves them."""
    from documents import gitstore
    from editing import authorship
    from review.history import reachable
    from tenancy.schemas import schema_context

    with schema_context(tenant.number):
        version = dict(reachable(people["r"], people.document))[number]
        authorship.compute(
            people.document,
            version.commit_sha,
            repository_path=gitstore.repository_path(tenant.number, people.document.number),
        )


def test_a_paragraph_moved_inside_the_span_names_nobody(
    edition_cast: Any, commit_version: Any, migrated_tenant: Any
) -> None:
    """A move keeps the line's writer, who wrote it before the span: a comparison names only
    who edited a line between its two versions."""
    people = _two_authors(edition_cast, commit_version)
    moved = BY_B.replace(
        "A request is answered within five days.\n\nA refused request may be made again.\n",
        "A refused request may be made again.\n\nA request is answered within five days.\n",
    )
    commit_version(people.document, people["b"], moved, "edit")
    _rows_for(people, "0.0-3", migrated_tenant)
    client = people.clients["r"]
    client.post("/preferences/show-author/", {"show_author": "on"})

    page = client.get(f"/document/{people.document.number}/compare/?from=0.0-3&to=0.0-4")

    assert _named(page.content.decode()) == {}


def test_a_failed_blame_draws_without_names(
    edition_cast: Any, commit_version: Any, monkeypatch: Any
) -> None:
    from editing import past_authors
    from editing.authorship import AuthorshipError

    people = _two_authors(edition_cast, commit_version)
    client = people.clients["r"]
    client.post("/preferences/show-author/", {"show_author": "on"})

    def failing(*_args: Any, **_kwargs: Any) -> Any:
        raise AuthorshipError("a synthetic failure")

    monkeypatch.setattr(past_authors, "blame_at", failing)
    page = client.get(f"/document/{people.document.number}/compare/?from=0.0-1&to=0.0-3")

    assert page.status_code == 200 and "data-author" not in page.content.decode()
