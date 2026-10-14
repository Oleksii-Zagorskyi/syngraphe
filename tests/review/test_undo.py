"""Undoing a contribution (ST-0037, ADR-0015, DL-0243, DL-0380, DL-0422): *undo all of this
author's edits* and *undo this edit* type the reversal into the reviewer's own draft — the clean
lines reverted, the built-on ones left and listed beside the text, never in it; a line the draft
already changed is built on too; nothing is removed from history; finishing with *accept as*
discloses the removed lines to their author; an undo is refused while reserved, while someone else
holds the document, or with nothing to undo, and its controls say why; an open editor of the draft
is told it is stale.

People, groups and texts are synthetic examples; every text is invented.
"""

from __future__ import annotations

import json
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


def signed_in(tenant: Any, user: Any) -> Client:
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(user)
    session = client.session
    session["tenant_number"] = tenant.number
    session.save()
    return client


def _run(migrated_tenant: Any, cast: Any, commit_version: Any) -> Any:
    """The base accepted, then A, B, A — B's version built on A's second sentence."""
    from review import services

    people = cast(editors=("a", "b"), reviewers=("r",))
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


def test_undo_an_authors_contribution(
    migrated_tenant: Any, cast: Any, commit_version: Any, repository: Any
) -> None:
    from review import undo

    people = _run(migrated_tenant, cast, commit_version)
    document = people.document
    kinds = repository.kinds(document)
    with schema_context(migrated_tenant.number):
        undo.apply(document, people["r"], author=people["a"])
        draft = _draft(document)
        assert draft.hold.user_id == people["r"].pk
        assert draft.content["document.md"] == BASE + "Author B reworded the second sentence.\n"
        listed = draft.content["undo"]["listed"]
        assert [entry["after"] for entry in listed] == ["Author B reworded the second sentence."]
        assert draft.content["undo"]["author"] == str(people["a"].pk)
    # Nothing is removed from history, nothing committed.
    assert repository.kinds(document) == kinds


def test_undo_one_version(
    migrated_tenant: Any, cast: Any, commit_version: Any, repository: Any
) -> None:
    from review import undo

    people = _run(migrated_tenant, cast, commit_version)
    document = people.document
    with schema_context(migrated_tenant.number):
        undo.apply(document, people["r"], version=people.first)
        draft = _draft(document)
        assert draft.content["document.md"] == (
            BASE + "Author B reworded the second sentence.\n\nA later paragraph of author A.\n"
        )
        assert [e["after"] for e in draft.content["undo"]["listed"]] == [
            "Author B reworded the second sentence."
        ]
        assert draft.content["undo"]["version"] == people.first.commit_sha


def test_an_edited_draft_is_built_on(migrated_tenant: Any, cast: Any, commit_version: Any) -> None:
    from editing import holds
    from review import undo

    people = _run(migrated_tenant, cast, commit_version)
    document = people.document
    with schema_context(migrated_tenant.number):
        hold = holds.take(document, people["r"])
        draft = _draft(document)
        edited = draft.content["document.md"].replace(
            "A first sentence of author A.", "The reviewer's own first sentence."
        )
        draft.content = {**draft.content, "document.md": edited}
        draft.save()
        assert undo.apply(document, people["r"], author=people["a"]).pk == hold.pk
        after = _draft(document).content
        # A's untouched line reverted; the line the reviewer had edited kept, and listed.
        assert after["document.md"] == (
            BASE + "The reviewer's own first sentence.\nAuthor B reworded the second sentence.\n"
        )
        afters = [e["after"] for e in after["undo"]["listed"]]
        assert "The reviewer's own first sentence." in afters
        assert "Author B reworded the second sentence." in afters


def test_refusals(
    migrated_tenant: Any, cast: Any, commit_version: Any, link_group: Any, settings: Any
) -> None:
    from access.rights import Right
    from editing import holds, reservations
    from review import services, undo

    settings.LANGUAGE_CODE = "en"
    people = _run(migrated_tenant, cast, commit_version)
    document = people.document
    link_group(document, [Right.RESERVE_FOR_EDITING], [people.memberships["b"]], people["a"])
    client = signed_in(migrated_tenant, people["r"])
    with schema_context(migrated_tenant.number):
        held = holds.take(document, people["b"])
        with pytest.raises(undo.UndoRefused) as refused:
            undo.apply(document, people["r"], author=people["a"])
        assert refused.value.reason == "held"
    tab = client.get(f"/document/{document.number}/history/").content.decode()
    assert "disabled" in tab and "is editing" in tab
    with schema_context(migrated_tenant.number):
        reservations.reserve(held, people["b"])
        with pytest.raises(undo.UndoRefused) as refused:
            undo.apply(document, people["r"], version=people.first)
        assert refused.value.reason == "reserved"
    tab = client.get(f"/document/{document.number}/history/").content.decode()
    assert "Reserved for editing" in tab
    answer = client.post(
        f"/document/{document.number}/history/undo/",
        {"version": "0.1-1"},
        follow=True,
    )
    assert "Reserved for editing" in answer.content.decode()
    # An empty run: nothing to undo.
    other = cast(editors=("c",), reviewers=("s",))
    with schema_context(migrated_tenant.number):
        with pytest.raises(undo.UndoRefused) as refused:
            undo.apply(other.document, other["s"], author=other["c"])
        assert refused.value.reason == "nothing_to_undo"
        assert services.run(other.document) == []


def test_the_route_and_the_controls(
    migrated_tenant: Any, cast: Any, commit_version: Any, settings: Any
) -> None:
    settings.LANGUAGE_CODE = "en"
    people = _run(migrated_tenant, cast, commit_version)
    document = people.document
    n = document.number
    client = signed_in(migrated_tenant, people["r"])
    tab = client.get(f"/document/{n}/history/").content.decode()
    assert f'action="/document/{n}/history/undo/"' in tab
    assert "Undo this edit" in tab and "Undo all of" in tab
    # An editor without *accept* finds the route missing.
    editor = signed_in(migrated_tenant, people["b"])
    assert editor.post(f"/document/{n}/history/undo/", {"version": "0.1-1"}).status_code == 404
    answer = client.post(f"/document/{n}/history/undo/", {"version": "0.1-1"})
    assert answer.status_code == 302 and answer["Location"] == f"/document/{n}/edit/"
    edit_tab = client.get(f"/document/{n}/edit/").content.decode()
    assert 'class="undo-listed"' in edit_tab
    assert "Author B reworded the second sentence." in edit_tab
    # By author, named by their identifier.
    again = client.post(f"/document/{n}/history/undo/", {"author": str(people["a"].pk)})
    assert again.status_code == 302 and again["Location"] == f"/document/{n}/edit/"
    with schema_context(migrated_tenant.number):
        assert _draft(document).content["document.md"] == (
            BASE + "Author B reworded the second sentence.\n"
        )


def test_an_undone_author_is_notified_at_the_acceptance(
    migrated_tenant: Any, cast: Any, commit_version: Any
) -> None:
    from editing.models import Hold
    from review import services, undo
    from review.models import CorrectionNotice

    people = _run(migrated_tenant, cast, commit_version)
    document = people.document
    with schema_context(migrated_tenant.number):
        hold = undo.apply(document, people["r"], author=people["a"])
        services.accept_as(Hold.objects.get(pk=hold.pk), people["r"], "Synthetic undo")
        assert CorrectionNotice.objects.filter(author=people["a"]).exists()
        assert not _draft_exists(document)


def _draft_exists(document: Any) -> bool:
    from editing.models import Draft

    return Draft.objects.filter(hold__document=document, hold__released_at__isnull=True).exists()


def test_an_undo_makes_an_open_editor_stale(
    migrated_tenant: Any, cast: Any, commit_version: Any
) -> None:
    from review import undo

    people = _run(migrated_tenant, cast, commit_version)
    document = people.document
    client = signed_in(migrated_tenant, people["r"])
    client.post(f"/document/{document.number}/edit/take/")
    loaded = client.post(f"/document/{document.number}/edit/load/").json()
    with schema_context(migrated_tenant.number):
        undo.apply(document, people["r"], author=people["a"])
    answer = client.post(
        f"/document/{document.number}/edit/capture/",
        data=json.dumps(
            {
                "editor": loaded["editor"],
                "base_hash": loaded["base_hash"],
                "body": loaded["body"] + "\nTyped in the open editor.\n",
            }
        ),
        content_type="application/json",
    )
    assert answer.status_code == 409 and answer.json().get("stale") is True


def test_the_undo_needs_its_csrf_token(
    migrated_tenant: Any, cast: Any, commit_version: Any, repository: Any
) -> None:
    from editing.models import Draft

    people = _run(migrated_tenant, cast, commit_version)
    document = people.document
    strict = Client(enforce_csrf_checks=True, headers={"host": "127.0.0.1"})
    strict.force_login(people["r"])
    session = strict.session
    session["tenant_number"] = migrated_tenant.number
    session.save()
    answer = strict.post(f"/document/{document.number}/history/undo/", {"version": "0.1-1"})
    assert answer.status_code == 403
    with schema_context(migrated_tenant.number):
        assert not Draft.objects.filter(hold__document=document).exists()
