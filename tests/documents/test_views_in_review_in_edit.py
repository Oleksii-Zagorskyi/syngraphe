"""*In review* and *In edit* (DL-0194, DL-0197, ST-0013, ST-0014): views of their own, grouped by
folder — the documents awaiting review that the person may accept, and those they may edit with
versions beyond the latest edition; the shell's links drawn only for a person who holds the right
on some document, disabled when the view is empty.

People, groups and texts are synthetic examples."""

from __future__ import annotations

import importlib.util
import re
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest
from django.test import Client

from access.rights import Right
from documents import gitstore
from tenancy.schemas import schema_context

_spec = importlib.util.spec_from_file_location(
    "views_review_fixtures", Path(__file__).resolve().parents[1] / "review" / "conftest.py"
)
assert _spec is not None and _spec.loader is not None
_review = importlib.util.module_from_spec(_spec)
# Registered before it runs: its dataclass looks its own module up by name.
sys.modules[_spec.name] = _review
_spec.loader.exec_module(_review)
new_document = _review.new_document
link_group = _review.link_group
commit_version = _review.commit_version

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

BODY = "# Conditions\n\nThe first synthetic sentence.\n"
LISTED = re.compile(r'class="document" data-number="(\d+)"')


def listed(body: str) -> list[int]:
    return [int(n) for n in LISTED.findall(body)]


def test_in_review_lists_pending_runs_the_person_may_accept(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    from review import services

    client, reviewer, membership = member_of("the.reviewer@example.test")
    pending = new_document(reviewer, "Synthetic document under review")
    accepted = new_document(reviewer, "Synthetic accepted document")
    for document in (pending, accepted):
        link_group(document, [Right.ACCEPT], [membership], reviewer)
        commit_version(document, reviewer, BODY, "edit")
    with schema_context(migrated_tenant.number):
        services.accept(accepted, reviewer)

    body = client.get("/in-review/").content.decode()
    assert listed(body) == [pending.number]
    assert 'data-state="awaiting_review"' in body
    assert 'class="folder-group"' in body


def test_a_frozen_document_with_a_pending_run_is_in_review(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    """A freeze does not stop accepting (DL-0351): the run waiting through it is listed."""
    from editions import services as editions

    client, reviewer, membership = member_of("the.reviewer@example.test")
    document = new_document(reviewer)
    link_group(document, [Right.ACCEPT, Right.FREEZE], [membership], reviewer)
    commit_version(document, reviewer, BODY, "edit")
    with schema_context(migrated_tenant.number):
        editions.freeze(document, reviewer, "Synthetic reason")

    body = client.get("/in-review/").content.decode()
    assert listed(body) == [document.number]
    assert 'data-state="frozen"' in body and 'data-state="awaiting_review"' in body
    link = re.search(r'<a [^>]*data-nav="in-review"[^>]*>', body)
    assert link is not None and 'href="/in-review/"' in link.group(0)


def test_in_review_needs_accept(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    client, viewer, viewer_membership = member_of("the.viewer@example.test")
    _, author, author_membership = member_of("the.author@example.test")
    document = new_document(author)
    link_group(document, [Right.ACCEPT], [author_membership], author)
    link_group(document, [Right.VIEW_PENDING], [viewer_membership], author)
    commit_version(document, author, BODY, "edit")

    assert client.get("/in-review/").status_code == 404, "no accept anywhere, no view"


def test_in_review_lists_only_the_documents_the_person_may_accept(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    """*accept* on one document opens the view; a document where the person holds *view pending*
    alone stays out of it, though it awaits review."""
    client, reviewer, membership = member_of("the.reviewer@example.test")
    _, author, author_membership = member_of("the.author@example.test")
    mine = new_document(author, "Synthetic document to accept")
    theirs = new_document(author, "Synthetic document to view only")
    link_group(mine, [Right.ACCEPT], [membership, author_membership], author)
    link_group(theirs, [Right.ACCEPT], [author_membership], author)
    link_group(theirs, [Right.VIEW_PENDING], [membership], author)
    for document in (mine, theirs):
        commit_version(document, author, BODY, "edit")

    assert listed(client.get("/in-review/").content.decode()) == [mine.number]


def test_an_editors_empty_in_edit_draws_its_link_disabled(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    """At its edition with nothing since, a document leaves *In edit* empty: the link is drawn,
    with no address."""
    from editions import services as editions
    from review import services

    client, editor, membership = member_of("the.editor@example.test")
    document = new_document(editor)
    link_group(document, [Right.ACCEPT, Right.FREEZE, Right.MAKE_CANONICAL], [membership], editor)
    commit_version(document, editor, BODY, "edit")
    with schema_context(migrated_tenant.number):
        services.accept(document, editor)
        editions.freeze(document, editor, "Synthetic reason")
        editions.make_canonical(document, editor)

    page = client.get("/folder/1/").content.decode()
    link = re.search(r'<a [^>]*data-nav="in-edit"[^>]*>', page)
    assert link is not None
    assert 'aria-disabled="true"' in link.group(0) and "href=" not in link.group(0)
    assert listed(client.get("/in-edit/").content.decode()) == []


def test_in_edit_lists_versions_after_the_edition(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    from editions import services as editions
    from review import services

    client, editor, membership = member_of("the.editor@example.test")
    still = new_document(editor, "Synthetic document without changes")
    moved = new_document(editor, "Synthetic document with changes")
    for document in (still, moved):
        link_group(
            document, [Right.ACCEPT, Right.FREEZE, Right.MAKE_CANONICAL], [membership], editor
        )
        commit_version(document, editor, BODY, "edit")
        with schema_context(migrated_tenant.number):
            services.accept(document, editor)
            editions.freeze(document, editor, "Synthetic reason")
            editions.make_canonical(document, editor)
    commit_version(moved, editor, BODY + "\nThe second synthetic sentence.\n", "edit")

    assert listed(client.get("/in-edit/").content.decode()) == [moved.number]


def test_links_drawn_only_for_holders_of_the_right(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    editor_client, editor, editor_membership = member_of("the.editor@example.test")
    reader_client, _, reader_membership = member_of("the.reader@example.test")
    document = new_document(editor)
    link_group(document, [Right.EDIT], [editor_membership], editor)
    link_group(document, [Right.VIEW_ACCEPTED], [reader_membership], editor)

    editor_page = editor_client.get("/folder/1/").content.decode()
    # A document with no edition yet counts as beyond it, so *In edit* is open.
    assert re.search(r'<a [^>]*href="/in-edit/"', editor_page)
    assert 'href="/in-review/"' not in editor_page and 'data-nav="in-review"' not in editor_page
    assert listed(editor_client.get("/in-edit/").content.decode()) == [document.number]
    reader_page = reader_client.get("/folder/1/").content.decode()
    assert 'data-nav="in-edit"' not in reader_page and 'data-nav="in-review"' not in reader_page


def test_the_author_of_an_author_only_document_has_in_edit(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    """The author's own reach holds *edit* as a group's does (ADR-0007), with no group at all."""
    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)

    page = client.get("/folder/1/").content.decode()
    assert re.search(r'<a [^>]*href="/in-edit/"', page)
    assert 'data-nav="in-review"' not in page
    assert listed(client.get("/in-edit/").content.decode()) == [document.number]


def test_an_empty_view_draws_its_link_disabled(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    client, reviewer, membership = member_of("the.reviewer@example.test")
    document = new_document(reviewer)
    link_group(document, [Right.ACCEPT], [membership], reviewer)

    page = client.get("/folder/1/").content.decode()
    link = re.search(r'<a [^>]*data-nav="in-review"[^>]*>', page)
    assert link is not None
    assert 'aria-disabled="true"' in link.group(0) and "href=" not in link.group(0)


def _closed(client: Any) -> None:
    """Neither view answers — the uniform refusal — and a shell page offers neither link."""
    missing = client.get("/folder/999/").content
    for view in ("/in-review/", "/in-edit/"):
        refused = client.get(view)
        assert refused.status_code == 404, view
        assert re.sub(rb'name="csrfmiddlewaretoken" value="[^"]*"', b"", refused.content) == re.sub(
            rb'name="csrfmiddlewaretoken" value="[^"]*"', b"", missing
        ), view
    page = client.get("/help/").content.decode()
    assert 'data-nav="in-edit"' not in page and 'data-nav="in-review"' not in page


def test_closed_without_a_tenant_or_the_right(
    member_of: Any, signed_in_without_tenant: Any
) -> None:
    client, _, _ = member_of("a.member@example.test")
    alone = signed_in_without_tenant("no.tenant@example.test")

    _closed(client)
    missing = alone.get("/folder/999/").content
    for view in ("/in-review/", "/in-edit/"):
        refused = alone.get(view)
        assert refused.status_code == 404, view
        assert re.sub(rb'name="csrfmiddlewaretoken" value="[^"]*"', b"", refused.content) == re.sub(
            rb'name="csrfmiddlewaretoken" value="[^"]*"', b"", missing
        ), view


def test_closed_to_administrators_without_groups(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    """Administration reads documents; it holds neither *edit* nor *accept* on them."""
    from identity.models import User

    _, author, membership = member_of("the.author@example.test")
    document = new_document(author)
    link_group(document, [Right.ACCEPT], [membership], author)
    commit_version(document, author, BODY, "edit")
    tenant_admin, _, _ = member_of("the.admin@example.test", is_tenant_admin=True)
    operator = Client(headers={"host": "127.0.0.1"})
    operator.force_login(
        User.objects.create_user(
            "the.operator@example.test", "test-only-not-a-password", is_platform_admin=True
        )
    )
    session = operator.session
    session["tenant_number"] = migrated_tenant.number
    session.save()

    _closed(tenant_admin)
    _closed(operator)


@pytest.mark.parametrize("standing", ["blocked", "self_blocked"])
def test_closed_to_a_person_not_in_good_standing(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    standing: str,
) -> None:
    """A blocked membership, or a self-blocked person, reaches nothing (DL-0308)."""
    client, reviewer, membership = member_of("the.reviewer@example.test")
    document = new_document(reviewer)
    link_group(document, [Right.ACCEPT], [membership], reviewer)
    commit_version(document, reviewer, BODY, "edit")
    if standing == "blocked":
        membership.change("state", "blocked", by=None)
    else:
        reviewer.self_blocked = True
        reviewer.save()

    _closed(client)


def test_closed_to_a_member_of_another_organisation(
    migrated_tenant: Any,
    member_of: Any,
    make_tenant_schema: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
) -> None:
    from access.models import GroupMember
    from identity.models import Membership, User

    _, author, membership = member_of("the.author@example.test")
    document = new_document(author)
    group = link_group(document, [Right.ACCEPT], [membership], author)
    commit_version(document, author, BODY, "edit")
    elsewhere = make_tenant_schema("Another synthetic organisation")
    stranger = User.objects.create_user("a.stranger@example.test", "test-only-not-a-password")
    theirs = Membership.objects.create(tenant=elsewhere, user=stranger, actor_kind="system")
    with schema_context(migrated_tenant.number):
        # A row no act writes: a member of another organisation in this one's group.
        GroupMember.objects.create(group=group, membership=theirs, actor_kind="system")
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(stranger)
    session = client.session
    session["tenant_number"] = migrated_tenant.number
    session.save()

    _closed(client)


def test_closed_where_the_right_reaches_only_an_archived_document(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    """A group grants nothing on an archived document (DL-0233), so it offers no view."""
    from documents.models import Document

    client, editor, membership = member_of("the.editor@example.test")
    document = new_document(editor)
    link_group(document, [Right.ACCEPT], [membership], editor)
    commit_version(document, editor, BODY, "edit")
    with schema_context(migrated_tenant.number):
        Document.objects.filter(pk=document.pk).update(state="archived")

    _closed(client)


def test_an_unreadable_repository_fails_no_page(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    """The menu and the views leave out a document whose record cannot be read, and log it."""
    client, reviewer, membership = member_of("the.reviewer@example.test")
    broken = new_document(reviewer, "Synthetic damaged document")
    whole = new_document(reviewer, "Synthetic whole document")
    for document in (broken, whole):
        link_group(document, [Right.ACCEPT], [membership], reviewer)
        commit_version(document, reviewer, BODY, "edit")
    shutil.rmtree(gitstore.repository_path(migrated_tenant.number, broken.number))

    for page, status in (("/help/", 200), ("/folder/1/", 200), ("/document/999/", 404)):
        assert client.get(page).status_code == status, page
    for view in ("/in-review/", "/in-edit/"):
        response = client.get(view)
        assert response.status_code == 200, view
        assert broken.number not in listed(response.content.decode()), view


def _pending_for(
    email: str, count: int, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> Any:
    client, person, membership = member_of(email)
    for n in range(count):
        document = new_document(person, f"Synthetic procedure {email} {n}")
        link_group(document, [Right.ACCEPT], [membership], person)
        commit_version(document, person, BODY, "edit")
    return client


def _cost(client: Any, path: str, monkeypatch: pytest.MonkeyPatch) -> tuple[int, int]:
    """The database queries and repository opens of one request."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    opened = []
    real = gitstore.open_repository

    def counting(*args: Any) -> Any:
        opened.append(args)
        return real(*args)

    with monkeypatch.context() as patched:
        patched.setattr(gitstore, "open_repository", counting)
        with CaptureQueriesContext(connection) as queries:
            assert client.get(path).status_code == 200, path
    return len(queries.captured_queries), len(opened)


def test_the_menu_costs_the_same_at_one_document_or_five(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every page draws the menu, which stops at the first document each view would list; the
    views themselves cost the folder list's cost plus a fixed amount."""
    one = _pending_for("one@example.test", 1, member_of, new_document, link_group, commit_version)
    five = _pending_for("five@example.test", 5, member_of, new_document, link_group, commit_version)
    for client in (one, five):
        client.get("/help/")  # the host and session caches filled before anything is counted

    assert _cost(one, "/help/", monkeypatch) == _cost(five, "/help/", monkeypatch)
    for view in ("/in-review/", "/in-edit/"):
        added = [
            _cost(client, view, monkeypatch)[0] - _cost(client, "/folder/1/", monkeypatch)[0]
            for client in (one, five)
        ]
        assert added[0] == added[1], (view, added)


def test_a_view_is_read_once_on_its_own_page(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The view's own answer draws its menu link; the menu does not read it again."""
    from documents import views

    client = _pending_for(
        "the.reviewer@example.test", 1, member_of, new_document, link_group, commit_version
    )
    calls: list[str] = []
    for name in ("in_review_documents", "in_edit_documents", "any_in_review", "any_in_edit"):
        real = getattr(views, name)
        monkeypatch.setattr(
            views, name, lambda *a, _real=real, _name=name: calls.append(_name) or _real(*a)
        )

    client.get("/in-review/")
    assert calls == ["in_review_documents", "any_in_edit"]
    calls.clear()
    client.get("/in-edit/")
    assert calls == ["in_edit_documents", "any_in_review"]


def test_catalogue_covers_the_views_and_their_links(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    settings: Any,
) -> None:
    spec = importlib.util.spec_from_file_location(
        "views_catalogue", Path(__file__).resolve().parents[1] / "review" / "test_catalogue.py"
    )
    assert spec is not None and spec.loader is not None
    review = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(review)

    settings.LANGUAGE_CODE = "uk"
    client, reviewer, membership = member_of("the.reviewer@example.test")
    document = new_document(reviewer)
    link_group(document, [Right.ACCEPT], [membership], reviewer)
    commit_version(document, reviewer, BODY, "edit")
    ids = review.message_ids(review.CATALOGUE.read_text(encoding="utf-8"))
    for view in ("/in-review/", "/in-edit/"):
        response = client.get(view)
        assert response.status_code == 200, view
        shown = review.text_of(response.content.decode())
        leaked = [message for message in ids if message in shown]
        assert leaked == [], (view, leaked)


# Epic 10
def test_groups_are_headed_by_full_path(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    """Runs in *A / B* and the root: groups headed by the organisation's name, then *A / B*; the
    pane cut to the folders holding them."""
    from documents import folders
    from documents.models import Document, Folder

    client, reviewer, membership = member_of("the.reviewer@example.test")
    _, author, author_membership = member_of("the.author@example.test")
    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    with schema_context(migrated_tenant.number):
        root = Folder.objects.get(number=1)
        a = folders.create_folder(root, "A (synthetic example)", by=admin)
        b = folders.create_folder(a, "B (synthetic example)", by=admin)
        folders.create_folder(root, "Elsewhere (synthetic example)", by=admin)
    deep = new_document(author, "Synthetic deep")
    rooted = new_document(author, "Synthetic rooted")
    with schema_context(migrated_tenant.number):
        Document.objects.filter(pk=deep.pk).update(folder=b)
    for document in (deep, rooted):
        link_group(document, [Right.ACCEPT], [membership, author_membership], author)
        commit_version(document, author, BODY, "edit")

    body = client.get("/in-review/").content.decode()

    headings = re.findall(r'<h2 class="folder-path">([^<]+)</h2>', body)
    assert headings == [migrated_tenant.name, "A (synthetic example) / B (synthetic example)"]
    pane = body.split('class="folder-tree"', 1)[1].split("</nav>", 1)[0]
    assert "Elsewhere" not in pane and "B (synthetic example)" in pane
    assert listed(body) == [rooted.number, deep.number]


def test_groups_follow_their_paths_alphabetically_and_the_cut_tree_is_open(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    """Groups in `uk-x-icu` path order, component by component (the collation is the subject);
    the pane beside a view opens every folder it holds."""
    from documents import folders
    from documents.models import Document, Folder

    client, _, membership = member_of("the.reviewer@example.test")
    _, author, author_membership = member_of("the.author@example.test")
    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    with schema_context(migrated_tenant.number):
        root = Folder.objects.get(number=1)
        ye = folders.create_folder(root, "Євро", by=admin)
        be = folders.create_folder(root, "Бета", by=admin)
        inner = folders.create_folder(be, "Явка", by=admin)
        orange = folders.create_folder(be, "апельсин", by=admin)
    placed = []
    for folder in (ye, inner, orange, be):
        document = new_document(author, f"Synthetic in {folder.name}")
        with schema_context(migrated_tenant.number):
            Document.objects.filter(pk=document.pk).update(folder=folder)
        link_group(document, [Right.ACCEPT], [membership, author_membership], author)
        commit_version(document, author, BODY, "edit")
        placed.append(document)

    body = client.get("/in-review/").content.decode()

    headings = re.findall(r'<h2 class="folder-path">([^<]+)</h2>', body)
    assert headings == ["Бета", "Бета / апельсин", "Бета / Явка", "Євро"]
    pane = body.split('class="folder-tree"', 1)[1].split("</nav>", 1)[0]
    assert 'class="shut"' not in pane
