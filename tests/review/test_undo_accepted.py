"""An undo through to its acceptance (ST-0037, ADR-0014, ADR-0015, DL-0380, DL-0427): the places
left for the reviewer show both wordings; *accept as* commits the reviewer's version and tells the
undone author which lines went; *create version* leaves it pending; the act is audited; while an
undo waits in a draft the run is not accepted around it; a stopped commit is settled before the
undo; a record that does not read, or a busy document, answers as such.

People, groups and texts are synthetic examples; every text is invented.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.test import Client

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

BASE = "# General provisions\n\nAn application is made in writing.\nIt is signed.\n"
A_FIRST = BASE + "A first sentence of author A.\nA second sentence of author A.\n"
B_BUILT = BASE + "A first sentence of author A.\nAuthor B reworded the second sentence.\n"
A_LATER = B_BUILT + "\nA later paragraph of author A.\n"
REASON = "Synthetic reason for the example"


def signed_in(tenant: Any, user: Any) -> Client:
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(user)
    session = client.session
    session["tenant_number"] = tenant.number
    session.save()
    return client


def _run(migrated_tenant: Any, cast: Any, commit_version: Any) -> Any:
    from review import services

    people = cast(editors=("a", "b"), reviewers=("r", "s"))
    document = people.document
    commit_version(document, people["a"], BASE, "edit")
    with schema_context(migrated_tenant.number):
        services.accept(document, people["r"])
    people.first = commit_version(document, people["a"], A_FIRST, "edit")
    people.built = commit_version(document, people["b"], B_BUILT, "edit")
    people.later = commit_version(document, people["a"], A_LATER, "edit")
    return people


def _draft(document: Any) -> Any:
    from editing.models import Draft

    return Draft.objects.get(hold__document=document, hold__released_at__isnull=True)


def test_a_listed_place_shows_both_wordings(
    migrated_tenant: Any, cast: Any, commit_version: Any, settings: Any
) -> None:
    from audit.models import AuditEvent
    from review import undo

    settings.LANGUAGE_CODE = "en"
    people = _run(migrated_tenant, cast, commit_version)
    document = people.document
    with schema_context(migrated_tenant.number):
        undo.apply(document, people["r"], author=people["a"])
        (place,) = _draft(document).content["undo"]["listed"]
        assert place["wrote"] == "A second sentence of author A."
        assert place["after"] == "Author B reworded the second sentence."
        event = AuditEvent.objects.get(action="document.undo_applied")
        assert event.actor_id == people["r"].pk
        assert event.after["author"] == str(people["a"].pk)
    page = signed_in(migrated_tenant, people["r"]).get(f"/document/{document.number}/edit/")
    body = page.content.decode()
    assert "A second sentence of author A." in body
    assert "Author B reworded the second sentence." in body


def test_accept_as_after_an_undo_tells_the_undone_author_what_went(
    migrated_tenant: Any, cast: Any, commit_version: Any, repository: Any
) -> None:
    from editing.models import Hold
    from review import services, undo
    from review.models import CorrectionLine

    people = _run(migrated_tenant, cast, commit_version)
    document = people.document
    with schema_context(migrated_tenant.number):
        hold = undo.apply(document, people["r"], author=people["a"])
        services.accept_as(Hold.objects.get(pk=hold.pk), people["r"], "Synthetic undo")
        lines = CorrectionLine.objects.filter(notice__author=people["a"])
        assert {line.author_version_id for line in lines} >= {people.first.pk, people.later.pk}
    assert repository.kinds(document)[-2:] == ["reviewer_edit", "acceptance"]


def test_create_version_after_an_undo_leaves_it_pending(
    migrated_tenant: Any, cast: Any, commit_version: Any, repository: Any
) -> None:
    from editing import services as editing
    from editing.models import Hold
    from review import services, undo

    people = _run(migrated_tenant, cast, commit_version)
    document = people.document
    with schema_context(migrated_tenant.number):
        hold = undo.apply(document, people["r"], author=people["a"])
        editing.commit_draft(Hold.objects.get(pk=hold.pk), people["r"], "Synthetic undo")
        assert repository.kinds(document)[-1] == "reviewer_edit"
        assert services.run(document)[-1].kind == "reviewer_edit"


def test_the_run_is_not_accepted_around_a_waiting_undo(
    migrated_tenant: Any, cast: Any, commit_version: Any, settings: Any
) -> None:
    from editing.models import Hold
    from review import services, undo

    settings.LANGUAGE_CODE = "en"
    people = _run(migrated_tenant, cast, commit_version)
    document = people.document
    with schema_context(migrated_tenant.number):
        hold = undo.apply(document, people["r"], author=people["a"])
        for reviewer in (people["s"], people["r"]):
            with pytest.raises(services.AcceptRefused) as refused:
                services.accept(document, reviewer)
            assert refused.value.reason == "undo_waits"
    pending = signed_in(migrated_tenant, people["s"]).get(f"/document/{document.number}/pending/")
    body = pending.content.decode()
    assert f'href="/document/{document.number}/pending/accept/"' not in body
    assert "undo" in body.lower()
    # Its own reviewer accepts through *accept as*, the undo with it.
    with schema_context(migrated_tenant.number):
        services.accept_as(Hold.objects.get(pk=hold.pk), people["r"], "Synthetic undo")


def test_a_stopped_commit_is_settled_before_the_undo(
    migrated_tenant: Any, cast: Any, commit_version: Any
) -> None:
    from review import services, undo
    from review.models import Return

    people = _run(migrated_tenant, cast, commit_version)
    document = people.document
    with schema_context(migrated_tenant.number):
        with pytest.raises(services.InjectedFault):
            services.return_run(document, people["s"], REASON, fault_at=1)
        undo.apply(document, people["r"], author=people["a"])
        assert Return.objects.filter(version__document=document).count() == 1


def test_a_walk_that_fails_answers_as_missing(
    migrated_tenant: Any, cast: Any, commit_version: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from editing import authorship
    from editing.models import Hold
    from review import undo

    people = _run(migrated_tenant, cast, commit_version)

    def failing(*args: Any, **kwargs: Any) -> Any:
        raise authorship.AuthorshipError("git timed out")

    monkeypatch.setattr(undo, "prepare", failing)
    client = signed_in(migrated_tenant, people["r"])
    answer = client.post(f"/document/{people.document.number}/history/undo/", {"version": "0.1-1"})
    assert answer.status_code == 404
    with schema_context(migrated_tenant.number):
        assert not Hold.objects.filter(document=people.document).exists()


def test_a_busy_document_says_so(
    migrated_tenant: Any,
    cast: Any,
    commit_version: Any,
    settings: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from documents.locks import LockTimeout
    from review import services, undo

    settings.LANGUAGE_CODE = "en"
    people = _run(migrated_tenant, cast, commit_version)
    n = people.document.number
    client = signed_in(migrated_tenant, people["r"])

    def busy(*args: Any, **kwargs: Any) -> Any:
        raise LockTimeout(n)

    def incomplete(*args: Any, **kwargs: Any) -> Any:
        raise services.RecordIncomplete("a commit the rows do not know")

    for name, fault, words in (("apply", busy, "busy"), ("apply", incomplete, "incomplete")):
        monkeypatch.setattr(undo, name, fault)
        answer = client.post(f"/document/{n}/history/undo/", {"version": "0.1-1"}, follow=True)
        assert words in answer.content.decode(), words
    for fault, words in ((busy, "busy"), (incomplete, "incomplete")):
        monkeypatch.setattr(services, "return_run", fault)
        last = people.later.commit_sha
        answer = client.post(
            f"/document/{n}/pending/return/", {"reason": REASON, "confirmed": last}, follow=True
        )
        assert words in answer.content.decode(), words


def test_a_second_undo_keeps_the_places_the_first_left(
    migrated_tenant: Any, cast: Any, commit_version: Any
) -> None:
    """A place the reviewer's draft had changed, listed by the first undo, is still listed after a
    second undo of a version elsewhere in the text; the first stays refused as done."""
    from editing import holds
    from editing.models import Draft
    from review import services, undo

    start = "# General provisions\n\nThe first sentence stands.\nA middle sentence stands.\n"
    base = start + "The last sentence stands.\n"
    people = cast(editors=("a", "b"), reviewers=("r",))
    document = people.document
    commit_version(document, people["a"], base, "edit")
    with schema_context(migrated_tenant.number):
        services.accept(document, people["r"])
    by_a = base.replace("The first sentence stands.", "Author A rewrote the first sentence.")
    first = commit_version(document, people["a"], by_a, "edit")
    by_b = by_a.replace("The last sentence stands.", "Author B rewrote the last sentence.")
    second = commit_version(document, people["b"], by_b, "edit")
    own = "The reviewer's own first sentence."
    with schema_context(migrated_tenant.number):
        hold = holds.take(document, people["r"])
        draft = Draft.objects.get(hold=hold)
        body = draft.content[holds.BODY]
        draft.content = {
            **draft.content,
            holds.BODY: body.replace("Author A rewrote the first sentence.", own),
        }
        draft.save()
        undo.apply(document, people["r"], version=first)
        (kept,) = [p for p in _draft(document).content["undo"]["listed"] if own in p["after"]]
        undo.apply(document, people["r"], version=second)
        after = _draft(document).content
        assert own in after[holds.BODY]
        assert "The last sentence stands." in after[holds.BODY]
        assert kept in after["undo"]["listed"]
        assert undo.refusal(document, people["r"], version=first) == "nothing_to_undo"


def test_the_reviewer_holding_the_undo_is_told_in_the_second_person(
    migrated_tenant: Any, cast: Any, commit_version: Any, settings: Any
) -> None:
    """The reviewer whose own draft holds the undo reads that it waits in *their* draft; another
    reviewer reads it under the holder's name."""
    import re

    from identity.models import User
    from review import undo

    settings.LANGUAGE_CODE = "en"
    people = _run(migrated_tenant, cast, commit_version)
    document = people.document
    User.objects.filter(pk=people["r"].pk).update(display_name="Synthetic Reviewer R")
    with schema_context(migrated_tenant.number):
        undo.apply(document, people["r"], author=people["a"])

    def said(user: Any) -> str:
        page = signed_in(migrated_tenant, user).get(f"/document/{document.number}/pending/")
        return " ".join(re.sub(r"<[^>]+>", " ", page.content.decode()).split())

    assert (
        "An undo of these edits waits in your draft: the run is accepted when you finish it with "
        "“Accept as”."
    ) in said(people["r"])
    assert "waits in Synthetic Reviewer R’s draft" in said(people["s"])
