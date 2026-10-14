"""The ceiling holds at its edges (ADR-0007, ADR-0008, DL-0209, DL-0286): a reader of canonical
text with *view all history* learns nothing of accepted work beyond the edition — neither from the
accepted boundary nor from past freezes; a forbidden number costs what a missing one does; a crafted
number resolves to nothing; the history lists its entries in the order they happened, a return
under the number it returned; a history that does not read answers as a missing page.

People, groups and texts are synthetic examples; every text is invented.
"""

from __future__ import annotations

import time
from typing import Any

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

from access.rights import Right
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

FIRST = "# General provisions\n\nAn application is made in writing.\n"
SECOND = FIRST + "\nThe decision is sent the same day.\n"
THIRD = SECOND + "\nA copy is kept in the register.\n"
REASON = "Synthetic reason for the example"


def signed_in(tenant: Any, user: Any) -> Client:
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(user)
    session = client.session
    session["tenant_number"] = tenant.number
    session.save()
    return client


def _people(cast: Any, link_group: Any) -> Any:
    people = cast(editors=("a",), reviewers=("r",))
    link_group(
        people.document,
        [Right.FREEZE, Right.MAKE_CANONICAL],
        [people.memberships["r"]],
        people["a"],
    )
    return people


def _reader(member_of: Any, link_group: Any, people: Any, rights: list[Any], name: str) -> Any:
    _client, user, membership = member_of(f"{name}.synthetic@example.test")
    link_group(people.document, rights, [membership], people["a"])
    return user


def test_a_canonical_reader_learns_nothing_beyond_the_edition(
    migrated_tenant: Any, cast: Any, link_group: Any, member_of: Any, commit_version: Any
) -> None:
    from editions import services as editions
    from review import services
    from review.history import entries

    people = _people(cast, link_group)
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        services.accept(document, people["r"])
        editions.freeze(document, people["r"], REASON)
        editions.make_canonical(document, people["r"])
    canonical = _reader(
        member_of, link_group, people, [Right.VIEW_CANONICAL, Right.VIEW_ALL_HISTORY], "ch"
    )
    with schema_context(migrated_tenant.number):
        before = entries(canonical, document)
    assert not [e for e in before if e.boundary]
    commit_version(document, people["a"], SECOND, "edit")
    with schema_context(migrated_tenant.number):
        services.accept(document, people["r"])
        editions.freeze(document, people["r"], REASON)
        editions.end_freeze(document, user=people["r"])
        after = entries(canonical, document)
    assert not [e for e in after if e.boundary]
    # The one freeze its stance reaches: the one the edition ended. Nothing of the later one.
    assert [e.event for e in after if e.version is None] == ["freeze"]
    assert [(e.number, e.event) for e in after] == [(e.number, e.event) for e in before]


def test_a_forbidden_number_costs_what_a_missing_one_does(
    migrated_tenant: Any,
    cast: Any,
    link_group: Any,
    member_of: Any,
    commit_version: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from editing import numbering
    from review import history, services

    people = _people(cast, link_group)
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        services.accept(document, people["r"])
    commit_version(document, people["a"], SECOND, "edit")
    accepted = _reader(member_of, link_group, people, [Right.VIEW_ACCEPTED], "acc")
    walks: list[str] = []
    real = numbering.history
    monkeypatch.setattr(numbering, "history", lambda d: walks.append("walk") or real(d))
    costs = []
    with schema_context(migrated_tenant.number):
        for number in ("0.1-1", "0.1-9"):
            walks.clear()
            with CaptureQueriesContext(connection) as queries:
                assert history.version_for(accepted, document, number) is None
            costs.append((len(queries), len(walks)))
    assert costs[0] == costs[1], costs


def test_a_crafted_number_resolves_to_nothing(
    migrated_tenant: Any, cast: Any, link_group: Any, member_of: Any, commit_version: Any
) -> None:
    from review import services
    from review.history import version_for

    people = _people(cast, link_group)
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        services.accept(document, people["r"])
        assert version_for(people["r"], document, "0.1") is not None
        for crafted in ("00.1", "0.01", "0.0-0", "0.0-01", "٠.١", "0.1\n", " 0.1", "0.1-"):
            assert version_for(people["r"], document, crafted) is None, repr(crafted)


def test_a_freeze_is_listed_where_it_began(
    migrated_tenant: Any, cast: Any, link_group: Any, member_of: Any, commit_version: Any
) -> None:
    from editions import services as editions
    from review import services
    from review.history import entries

    people = _people(cast, link_group)
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        editions.freeze(document, people["r"], REASON)
    # A freeze counts whole seconds; the version after it falls in a later one.
    time.sleep(1.1)
    # While frozen, a holder of *accept* still commits and accepts (ADR-0016).
    commit_version(document, people["r"], SECOND, "reviewer_edit")
    with schema_context(migrated_tenant.number):
        services.accept(document, people["r"])
        editions.make_canonical(document, people["r"])
    everything = _reader(
        member_of, link_group, people, [Right.VIEW_PENDING, Right.VIEW_ALL_HISTORY], "all"
    )
    with schema_context(migrated_tenant.number):
        events = [e.event for e in entries(everything, document)]
    assert events == ["created", "edit", "freeze", "reviewer_edit", "acceptance", "approval"]


def test_a_return_shows_the_number_it_returned(
    migrated_tenant: Any, cast: Any, link_group: Any, member_of: Any, commit_version: Any
) -> None:
    from review import services
    from review.history import entries

    people = _people(cast, link_group)
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    commit_version(document, people["a"], SECOND, "edit")
    with schema_context(migrated_tenant.number):
        services.return_run(document, people["r"], REASON)
        services.accept(document, people["r"])
    everything = _reader(
        member_of, link_group, people, [Right.VIEW_PENDING, Right.VIEW_ALL_HISTORY], "all"
    )
    with schema_context(migrated_tenant.number):
        shown = [(e.event, e.number) for e in entries(everything, document)]
    assert ("return", "0.0-2") in shown
    assert ("acceptance", "0.1") in shown


def test_a_section_naming_a_passport_commit_does_not_read(
    migrated_tenant: Any, cast: Any, link_group: Any, commit_version: Any
) -> None:
    from django.utils import timezone

    from documents import bundle, gitstore
    from documents.identity import identity_for
    from documents.locks import document_lock
    from editing import numbering
    from review import services

    people = _people(cast, link_group)
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    number = migrated_tenant.number
    with schema_context(number):
        services.accept(document, people["r"])
        repo = gitstore.open_repository(number, document.number)
        with document_lock(number, document.number):
            head = gitstore.head(repo)
            assert head is not None
            now = timezone.now().replace(microsecond=0)
            # An acceptance section naming the previous acceptance's own commit.
            entry = bundle.PassportEntry(
                kind="acceptance", number="0.2", at=now, by=str(people["r"].pk), version=head
            )
            passport = gitstore.read(repo, "passport.md", head).decode()
            gitstore.commit(
                repo,
                {"passport.md": bundle.append_passport(passport, entry).encode()},
                identity_for(people["r"], at=now),
                "Accepted as 0.2",
                gitstore.Kind.ACCEPTANCE,
            )
        with pytest.raises(ValueError):
            numbering.history(document)


def test_the_tab_answers_a_history_that_does_not_read_as_missing(
    migrated_tenant: Any,
    cast: Any,
    link_group: Any,
    commit_version: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from editing import numbering

    people = _people(cast, link_group)
    commit_version(people.document, people["a"], FIRST, "edit")

    def unreadable(document: Any) -> Any:
        raise ValueError("a passport section without its commit")

    monkeypatch.setattr(numbering, "history", unreadable)
    client = signed_in(migrated_tenant, people["r"])
    assert client.get(f"/document/{people.document.number}/history/").status_code == 404


def test_the_boundary_line_stands_above_the_acceptance_it_marks(
    migrated_tenant: Any,
    cast: Any,
    link_group: Any,
    member_of: Any,
    commit_version: Any,
    settings: Any,
) -> None:
    from review import services

    settings.LANGUAGE_CODE = "en"
    people = _people(cast, link_group)
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        services.accept(document, people["r"])
    commit_version(document, people["a"], SECOND, "edit")
    client, _user, membership = member_of("all.synthetic@example.test")
    link_group(document, [Right.VIEW_PENDING, Right.VIEW_ALL_HISTORY], [membership], people["a"])
    page = client.get(f"/document/{document.number}/history/").content.decode()
    boundary = page.index('class="boundary"')
    assert page.index('data-event="edit"') < boundary < page.index('data-event="acceptance"')


def test_a_return_is_listed_within_each_readers_reach(
    migrated_tenant: Any, cast: Any, link_group: Any, member_of: Any, commit_version: Any
) -> None:
    from review import services
    from review.history import entries

    people = _people(cast, link_group)
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        services.accept(document, people["r"])
    commit_version(document, people["a"], SECOND, "edit")
    with schema_context(migrated_tenant.number):
        services.return_run(document, people["r"], REASON)
    everything = _reader(
        member_of, link_group, people, [Right.VIEW_PENDING, Right.VIEW_ALL_HISTORY], "all"
    )
    accepted_only = _reader(
        member_of, link_group, people, [Right.VIEW_ACCEPTED, Right.VIEW_ALL_HISTORY], "acc"
    )
    editions_only = _reader(
        member_of, link_group, people, [Right.VIEW_CANONICAL, Right.VIEW_PREVIOUS_CANONICAL], "ed"
    )
    with schema_context(migrated_tenant.number):
        assert ("return", "0.1-1") in [(e.event, e.number) for e in entries(everything, document)]
        # The return concerns pending work: beyond a reader of accepted text.
        assert "return" not in [e.event for e in entries(accepted_only, document)]
        assert "return" not in [e.event for e in entries(editions_only, document)]
        # *Accept* without a history right: the run's versions alone, no passport entry.
        assert [e.event for e in entries(people["r"], document)] == ["edit"]
