"""An undo at its edges (ST-0037, ADR-0015, DL-0233, DL-0243, DL-0329, DL-0380): a second undo into
the same draft never types a line in twice, and the same one twice is refused; a refused undo
leaves nobody holding the document; a reversal that changes no text is nothing to undo; an undo
the draft could not hold is refused; a kept draft disables the controls with its reason; every
input the route does not admit answers as missing; a record that does not read, too.

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

BASE = "# General provisions\n\nAn application is made in writing.\nIt is signed.\nIt is dated.\n"
A_DELETES = "# General provisions\n\nAn application is made in writing.\nIt is dated.\n"
B_ELSEWHERE = A_DELETES + "\nA paragraph of author B.\n"
A_ADDS = B_ELSEWHERE + "\nA paragraph of author A.\n"


def _with_an_edit(tenant: int, document: Any) -> None:
    """The open hold's draft given an edit: a hold with no edits keeps nothing when it ends."""
    from editing.models import Draft

    with schema_context(tenant):
        draft = Draft.objects.get(hold__document=document, hold__released_at__isnull=True)
        body = draft.content["document.md"] + "\nAn invented sentence kept in the draft.\n"
        draft.content = {**draft.content, "document.md": body}
        draft.save()


def signed_in(tenant: Any, user: Any) -> Client:
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(user)
    session = client.session
    session["tenant_number"] = tenant.number
    session.save()
    return client


def _run(migrated_tenant: Any, cast: Any, commit_version: Any) -> Any:
    from review import services

    people = cast(editors=("a", "b"), reviewers=("r",))
    document = people.document
    commit_version(document, people["a"], BASE, "edit")
    with schema_context(migrated_tenant.number):
        services.accept(document, people["r"])
    people.deletes = commit_version(document, people["a"], A_DELETES, "edit")
    commit_version(document, people["b"], B_ELSEWHERE, "edit")
    people.adds = commit_version(document, people["a"], A_ADDS, "edit")
    return people


def _body(document: Any) -> str:
    from editing.models import Draft

    draft = Draft.objects.get(hold__document=document, hold__released_at__isnull=True)
    return str(draft.content["document.md"])


def test_a_version_then_its_author_types_nothing_twice(
    migrated_tenant: Any, cast: Any, commit_version: Any
) -> None:
    from review import undo

    people = _run(migrated_tenant, cast, commit_version)
    document = people.document
    with schema_context(migrated_tenant.number):
        undo.apply(document, people["r"], version=people.deletes)
        assert _body(document) == BASE + "\nA paragraph of author B.\n\nA paragraph of author A.\n"
        undo.apply(document, people["r"], author=people["a"])
        assert _body(document) == BASE + "\nA paragraph of author B.\n"
        assert _body(document).count("It is signed.") == 1


def test_the_same_undo_twice_is_refused(
    migrated_tenant: Any, cast: Any, commit_version: Any
) -> None:
    from review import undo

    people = _run(migrated_tenant, cast, commit_version)
    document = people.document
    with schema_context(migrated_tenant.number):
        undo.apply(document, people["r"], version=people.deletes)
        once = _body(document)
        with pytest.raises(undo.UndoRefused) as refused:
            undo.apply(document, people["r"], version=people.deletes)
        assert refused.value.reason == "nothing_to_undo"
        assert _body(document) == once


def test_a_refused_undo_leaves_nobody_holding_the_document(
    migrated_tenant: Any, cast: Any, commit_version: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from editing.models import Hold
    from review import undo

    people = _run(migrated_tenant, cast, commit_version)

    def refused(*args: Any, **kwargs: Any) -> Any:
        raise undo.UndoRefused("nothing_to_undo")

    monkeypatch.setattr(undo, "plan", refused)
    with schema_context(migrated_tenant.number):
        with pytest.raises(undo.UndoRefused):
            undo.apply(people.document, people["r"], author=people["a"])
        assert not Hold.objects.filter(document=people.document).exists()


def test_an_undo_the_draft_could_not_hold_is_refused(
    migrated_tenant: Any, cast: Any, commit_version: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    import dataclasses

    from editing.markdown import load_spec
    from editing.models import Hold
    from review import undo

    people = _run(migrated_tenant, cast, commit_version)
    small = dataclasses.replace(load_spec(), max_bytes=40)
    monkeypatch.setattr(undo, "load_spec", lambda: small)
    with schema_context(migrated_tenant.number):
        with pytest.raises(undo.UndoRefused) as refused:
            undo.apply(people.document, people["r"], version=people.deletes)
        assert refused.value.reason == "too_large"
        assert not Hold.objects.filter(document=people.document).exists()


def test_a_version_changing_no_text_is_nothing_to_undo(
    migrated_tenant: Any, cast: Any, commit_version: Any
) -> None:
    from documents import bundle, gitstore, services
    from documents.identity import identity_for
    from documents.locks import document_lock
    from editing.models import Hold
    from review import undo

    people = _run(migrated_tenant, cast, commit_version)
    document = people.document
    number = migrated_tenant.number
    with schema_context(number):
        repo = gitstore.open_repository(number, document.number)
        with document_lock(number, document.number):
            head = gitstore.head(repo)
            assert head is not None
            frontmatter, body = bundle.parse(gitstore.read(repo, "document.md", head).decode())
            frontmatter.title = "A renamed synthetic document"
            sha = gitstore.commit(
                repo,
                {"document.md": bundle.render(frontmatter, body).encode()},
                identity_for(people["b"]),
                "Synthetic rename",
                gitstore.Kind.EDIT,
            )
            renamed = services.derive_version(document, gitstore.commit_at(repo, sha), people["b"])
        with pytest.raises(undo.UndoRefused) as refused:
            undo.apply(document, people["r"], version=renamed)
        assert refused.value.reason == "nothing_to_undo"
        assert not Hold.objects.filter(document=document).exists()


def test_a_kept_draft_disables_the_controls(
    migrated_tenant: Any, cast: Any, commit_version: Any, settings: Any
) -> None:
    from documents.locks import document_lock
    from editing import holds
    from editing.models import ReleaseKind
    from review import undo

    settings.LANGUAGE_CODE = "en"
    people = _run(migrated_tenant, cast, commit_version)
    document = people.document
    with schema_context(migrated_tenant.number):
        hold = holds.take(document, people["r"])
    _with_an_edit(migrated_tenant.number, document)
    with schema_context(migrated_tenant.number):
        with document_lock(migrated_tenant.number, document.number):
            from django.db import transaction

            with transaction.atomic():
                holds.release(hold, ReleaseKind.INACTIVITY)
        assert undo.refusal(document, people["r"], author=people["a"]) == "draft_kept"
    tab = signed_in(migrated_tenant, people["r"]).get(f"/document/{document.number}/pending/")
    page = tab.content.decode()
    assert "take the document back" in page
    assert 'data-command="undo-version"' not in page


@pytest.mark.parametrize(
    "posted",
    [
        {"version": "9.9"},
        {"author": "not-an-identifier"},
        {"author": "00000000-0000-0000-0000-000000000000"},
        {"author": "the reviewer"},
        {},
    ],
)
def test_what_the_route_does_not_admit_is_missing(
    migrated_tenant: Any, cast: Any, commit_version: Any, posted: dict[str, str]
) -> None:
    from editing.models import Draft

    people = _run(migrated_tenant, cast, commit_version)
    document = people.document
    if posted.get("author") == "the reviewer":
        # A person of the organisation who wrote nothing in the run.
        posted = {"author": str(people["r"].pk)}
    client = signed_in(migrated_tenant, people["r"])
    answer = client.post(f"/document/{document.number}/history/undo/", posted)
    assert answer.status_code == 404, posted
    assert client.get(f"/document/{document.number}/history/undo/").status_code == 404
    with schema_context(migrated_tenant.number):
        assert not Draft.objects.filter(hold__document=document).exists()


def test_a_version_outside_the_run_is_nothing_to_undo(
    migrated_tenant: Any, cast: Any, commit_version: Any, settings: Any
) -> None:
    from editing.models import Draft

    settings.LANGUAGE_CODE = "en"
    people = _run(migrated_tenant, cast, commit_version)
    document = people.document
    client = signed_in(migrated_tenant, people["r"])
    # The accepted base: a version the reviewer may open, and none of the run.
    answer = client.post(f"/document/{document.number}/history/undo/", {"version": "0.1"})
    assert answer.status_code == 302
    assert answer["Location"] == f"/document/{document.number}/pending/"
    with schema_context(migrated_tenant.number):
        assert not Draft.objects.filter(hold__document=document).exists()


def test_an_editor_without_accept_has_no_control(
    migrated_tenant: Any, cast: Any, commit_version: Any, link_group: Any
) -> None:
    from access.rights import Right

    people = _run(migrated_tenant, cast, commit_version)
    document = people.document
    link_group(document, [Right.VIEW_ALL_HISTORY], [people.memberships["b"]], people["a"])
    page = signed_in(migrated_tenant, people["b"]).get(f"/document/{document.number}/history/")
    assert page.status_code == 200
    assert "history/undo/" not in page.content.decode()


def test_a_record_that_does_not_read_answers_as_missing(
    migrated_tenant: Any, cast: Any, commit_version: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from editing import numbering

    people = _run(migrated_tenant, cast, commit_version)

    def unreadable(document: Any) -> Any:
        raise ValueError("a passport section without its commit")

    monkeypatch.setattr(numbering, "history", unreadable)
    client = signed_in(migrated_tenant, people["r"])
    answer = client.post(f"/document/{people.document.number}/history/undo/", {"version": "0.1-1"})
    assert answer.status_code == 404
