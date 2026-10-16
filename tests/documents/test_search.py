"""Search and the type filter (DL-0197, DL-0236): titles of documents and of their appendices at
the version the searcher reads, never text; the type filter cutting across folders; results
grouped by folder path.

Titles, folders, types, groups and people are synthetic examples; the Cyrillic titles are where
the case folding is the subject."""

from __future__ import annotations

import dataclasses
import re
from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

ROWS = re.compile(r'<tr class="document"[^>]*data-number="(\d+)"')


@pytest.fixture(autouse=True)
def english(settings: Any) -> None:
    settings.LANGUAGE_CODE = "en"


def found(body: str) -> list[int]:
    return [int(n) for n in ROWS.findall(body)]


def headings(body: str) -> list[str]:
    return re.findall(r'<h2 class="folder-path">([^<]+)</h2>', body)


def _folder(migrated_tenant: Any, by: Any, name: str, parent: Any = None) -> Any:
    from documents import folders
    from documents.models import Folder

    with schema_context(migrated_tenant.number):
        return folders.create_folder(parent or Folder.objects.get(number=1), name, by=by)


def _create(migrated_tenant: Any, by: Any, title: str, folder: Any = None) -> Any:
    from documents import services
    from documents.models import DocumentType, Folder
    from identity.models import Language

    Language.objects.get_or_create(code="uk", defaults={"label": "uk", "actor_kind": "system"})
    with schema_context(migrated_tenant.number):
        return services.create_document(
            by,
            title,
            "uk",
            DocumentType.objects.get(code="document"),
            folder or Folder.objects.get(number=1),
        )


def _with_appendices(
    migrated_tenant: Any, document: Any, user: Any, titles: list[str], body: str | None = None
) -> Any:
    """One `reviewer_edit` version listing `titles` as appendices, each committed at
    `appendices/<n>.md` — committed directly, as no form adds appendices yet — with `body` when
    given; its row and caches derived."""
    from documents import bundle, gitstore, services
    from documents.identity import identity_for
    from documents.locks import document_lock

    number = migrated_tenant.number
    with schema_context(number):
        repo = gitstore.open_repository(number, document.number)
        with document_lock(number, document.number):
            head = gitstore.head(repo)
            assert head is not None
            frontmatter, kept = bundle.parse(gitstore.read(repo, "document.md", head).decode())
            body = kept if body is None else body
            listed = [{"number": n, "title": t} for n, t in enumerate(titles, 1)]
            text = bundle.render(dataclasses.replace(frontmatter, appendices=listed), body)
            files = {"document.md": text.encode("utf-8")}
            for n, title in enumerate(titles, 1):
                files[f"appendices/{n}.md"] = f"# {title}\n\nSynthetic appendix text.\n".encode()
            sha = gitstore.commit(
                repo, files, identity_for(user), "Synthetic edit", gitstore.Kind.REVIEWER_EDIT
            )
            return services.derive_version(document, gitstore.commit_at(repo, sha), user)


def _link(migrated_tenant: Any, by: Any, right: Any, membership: Any, *documents: Any) -> None:
    from access.models import AccessGroup, DocumentGroup

    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(
            name=f"Group {right} {membership.pk}", created_by=by, actor_kind="user"
        )
        group.grant(right, by=by)
        group.add_member(membership, by=by)
        for document in documents:
            DocumentGroup.link(document, group, by=by)


def test_titles_match_never_text(migrated_tenant: Any, member_of: Any, repo_root: Any) -> None:
    from access.rights import Right

    client, _, membership = member_of("a.reader@example.test")
    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    a = _folder(migrated_tenant, admin, "A (synthetic example)")
    b = _folder(migrated_tenant, admin, "B (synthetic example)")
    travel = _create(migrated_tenant, admin, "Travel rules (synthetic)", a)
    leave = _create(migrated_tenant, admin, "Leave policy (synthetic)", b)
    texty = _create(migrated_tenant, admin, "Expense guide (synthetic)", b)
    # The third's body says *travel*; only titles are searched.
    _with_appendices(
        migrated_tenant, texty, admin, [], body="# Costs\n\nTravel is booked in advance.\n"
    )
    _link(migrated_tenant, admin, Right.VIEW_PENDING, membership, travel, leave, texty)

    body = client.get("/search/?q=TRAVEL").content.decode()

    assert found(body) == [travel.number]
    assert headings(body) == ["A (synthetic example)"]
    assert "Searched in titles of documents and of their appendices — not in text." in body
    assert 'value="TRAVEL"' in body


def test_appendix_titles_at_the_version_read(
    migrated_tenant: Any, member_of: Any, operator: Any
) -> None:
    from access.models import DocumentGroup
    from access.rights import Right
    from review import services as review

    accepted_reader, _, accepted_membership = member_of("an.accepted.reader@example.test")
    pending_reader, _, pending_membership = member_of("a.pending.reader@example.test")
    document = _create(migrated_tenant, operator.user, "Synthetic travel policy")
    with schema_context(migrated_tenant.number):
        DocumentGroup.link(document, operator.group, by=operator.user)
    _with_appendices(migrated_tenant, document, operator.user, ["Rates"])
    with schema_context(migrated_tenant.number):
        review.accept(document, operator.user)
    _with_appendices(migrated_tenant, document, operator.user, ["Rates", "Draft rates"])
    _link(migrated_tenant, operator.user, Right.VIEW_ACCEPTED, accepted_membership, document)
    _link(migrated_tenant, operator.user, Right.VIEW_PENDING, pending_membership, document)

    assert found(accepted_reader.get("/search/?q=rates").content.decode()) == [document.number]
    assert found(pending_reader.get("/search/?q=rates").content.decode()) == [document.number]
    assert found(accepted_reader.get("/search/?q=draft").content.decode()) == []
    assert found(pending_reader.get("/search/?q=draft").content.decode()) == [document.number]


def test_never_an_unreadable_or_archived_document(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    from access.rights import Right

    member, _, membership = member_of("a.member@example.test")
    admin, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    readable = make_document(title="Synthetic compass", author_only=False)
    unreadable = make_document(title="Synthetic compass", author_only=False)
    archived = make_document(title="Synthetic compass", author_only=False, state="archived")
    _link(migrated_tenant, admin_user, Right.VIEW_PENDING, membership, readable, archived)

    as_member = found(member.get("/search/?q=compass").content.decode())
    as_admin = found(admin.get("/search/?q=compass").content.decode())

    assert as_member == [readable.number]
    assert sorted(as_admin) == sorted([readable.number, unreadable.number])
    assert archived.number not in as_admin


def test_case_is_ignored_in_cyrillic(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    admin, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    upper = make_document(title="ПОЛОЖЕННЯ ПРО ВІДПУСТКИ", author_only=False)
    mixed = make_document(title="Порядок Відряджень", author_only=False)
    porch = make_document(title="Ґанок і їдальня", author_only=False)
    europe = make_document(title="Єдині правила", author_only=False)

    assert found(admin.get("/search/?q=положення").content.decode()) == [upper.number]
    # І/і, Ї/ї, Є/є, Ґ/ґ — the letters Ukrainian adds — each folded both ways.
    assert found(admin.get("/search/?q=відпустки").content.decode()) == [upper.number]
    assert found(admin.get("/search/?q=ВІДРЯДЖЕНЬ").content.decode()) == [mixed.number]
    assert found(admin.get("/search/?q=ґанок").content.decode()) == [porch.number]
    assert found(admin.get("/search/?q=ЇДАЛЬНЯ").content.decode()) == [porch.number]
    assert found(admin.get("/search/?q=єдині").content.decode()) == [europe.number]


def test_the_type_filter_cuts_across_folders(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    from access.rights import Right
    from documents import types

    narrow, _, narrow_membership = member_of("a.narrow.reader@example.test")
    wide, _, wide_membership = member_of("a.wide.reader@example.test")
    admin, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    a = _folder(migrated_tenant, admin_user, "A (synthetic example)")
    b = _folder(migrated_tenant, admin_user, "B (synthetic example)", a)
    with schema_context(migrated_tenant.number):
        policy = types.add_type("policy (synthetic example)", by=admin_user)
    p1 = make_document(title="Synthetic travel", folder=a, document_type=policy, author_only=False)
    p2 = make_document(title="Synthetic leave", folder=b, document_type=policy, author_only=False)
    plain = make_document(title="Synthetic note", author_only=False)
    _link(migrated_tenant, admin_user, Right.VIEW_PENDING, narrow_membership, plain)
    _link(migrated_tenant, admin_user, Right.VIEW_PENDING, wide_membership, p1, p2, plain)

    narrow_list = narrow.get("/folder/1/").content.decode()
    wide_list = wide.get("/folder/1/").content.decode()
    by_type = wide.get(f"/search/?type={policy.code}").content.decode()
    narrowed = wide.get(f"/search/?q=leave&type={policy.code}").content.decode()
    unknown = wide.get("/search/?type=no-such-type").content.decode()

    assert 'name="type"' not in narrow_list
    assert 'name="type"' in wide_list
    options = re.findall(r'<option value="([^"]*)"[^>]*>([^<]*)</option>', wide_list)
    assert options[0] == ("", "All types")
    assert sorted(options[1:]) == sorted([("document", "Документ"), (policy.code, policy.label)])
    assert sorted(found(by_type)) == sorted([p1.number, p2.number])
    assert headings(by_type) == [
        "A (synthetic example)",
        "A (synthetic example) / B (synthetic example)",
    ]
    assert found(narrowed) == [p2.number]
    assert f'<option value="{policy.code}" selected>' in by_type
    assert found(unknown) == [] and "No documents here." in unknown


def test_an_empty_search_returns_to_the_root(migrated_tenant: Any, member_of: Any) -> None:
    client, _, _ = member_of("a.member@example.test")

    for path in ("/search/", "/search/?q=", "/search/?q=%20%20&type="):
        answer = client.get(path)
        assert answer.status_code == 302 and answer["Location"] == "/folder/1/", path
    assert client.post("/search/", {"q": "x"}).status_code == 404


def test_a_long_query_is_cut_and_nothing_found_says_so(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    admin, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    make_document(title="Synthetic", author_only=False)

    body = admin.get("/search/?q=" + "z" * 300).content.decode()

    assert found(body) == [] and "No documents here." in body
    assert 'value="' + "z" * 200 + '"' in body


def test_the_filter_reads_in_a_fixed_number_of_queries(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    """The filter's choices are read in the same number of queries at two documents or five."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from documents import search, types
    from identity.models import User

    _, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    with schema_context(migrated_tenant.number):
        policy = types.add_type("policy (synthetic example)", by=admin_user)
    admin = User.objects.get(pk=admin_user.pk)
    make_document(title="Synthetic one", author_only=False)
    make_document(title="Synthetic two", author_only=False, document_type=policy)

    def cost() -> tuple[int, int]:
        with schema_context(migrated_tenant.number), CaptureQueriesContext(connection) as seen:
            listed = search.filter_types(admin)
        return len(seen.captured_queries), len(listed)

    few = cost()
    for i in range(3):
        make_document(title=f"Synthetic more {i}", author_only=False, document_type=policy)
    many = cost()

    assert few == many and few[1] == 2


def test_a_sort_keeps_the_words_and_the_type(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    from documents import types

    admin, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    with schema_context(migrated_tenant.number):
        policy = types.add_type("policy (synthetic example)", by=admin_user)
    first = make_document(title="Synthetic travel B", document_type=policy, author_only=False)
    second = make_document(title="Synthetic travel A", document_type=policy, author_only=False)
    make_document(title="Synthetic travel C", author_only=False)

    page = admin.get(f"/search/?q=travel&type={policy.code}").content.decode()
    links = re.findall(r'<a class="sort" href="([^"]+)"', page)
    by_number = admin.get("/search/" + links[0].replace("&amp;", "&")).content.decode()

    assert all("q=travel" in link and f"type={policy.code}" in link for link in links)
    assert found(by_number) == [first.number, second.number]


def test_a_nul_character_finds_nothing(migrated_tenant: Any, member_of: Any) -> None:
    client, _, _ = member_of("a.member@example.test")

    for path in ("/search/?q=a%00b", "/search/?type=x%00y", "/search/?q=a&type=%00"):
        answer = client.get(path)
        assert answer.status_code == 200, path
        assert "No documents here." in answer.content.decode(), path


def test_an_unreadable_record_is_left_out_not_a_server_error(
    migrated_tenant: Any, member_of: Any, operator: Any
) -> None:
    """A document found only through an appendix whose record cannot be read is not found; the
    search answers, as the list does."""
    import shutil

    from access.models import DocumentGroup
    from access.rights import Right
    from documents import gitstore

    reader, _, membership = member_of("a.reader@example.test")
    broken = _create(migrated_tenant, operator.user, "Synthetic broken")
    whole = _create(migrated_tenant, operator.user, "Synthetic whole")
    for document in (broken, whole):
        with schema_context(migrated_tenant.number):
            DocumentGroup.link(document, operator.group, by=operator.user)
        _with_appendices(migrated_tenant, document, operator.user, ["Freight rates"])
    _link(migrated_tenant, operator.user, Right.VIEW_PENDING, membership, broken, whole)
    shutil.rmtree(gitstore.repository_path(migrated_tenant.number, broken.number))

    answer = reader.get("/search/?q=freight")

    assert answer.status_code == 200
    assert found(answer.content.decode()) == [whole.number]


def test_a_title_and_an_appendix_matching_find_the_document_once(
    migrated_tenant: Any, member_of: Any, operator: Any
) -> None:
    from access.models import DocumentGroup

    document = _create(migrated_tenant, operator.user, "Synthetic freight policy")
    with schema_context(migrated_tenant.number):
        DocumentGroup.link(document, operator.group, by=operator.user)
    _with_appendices(migrated_tenant, document, operator.user, ["Freight rates"])

    assert found(operator.client.get("/search/?q=freight").content.decode()) == [document.number]


def test_a_member_s_pages_cost_the_same_at_one_document_or_five(
    migrated_tenant: Any, member_of: Any, repo_root: Any
) -> None:
    """The folder and a search by type, with the filter drawn, read in the same number of
    queries whatever the number of documents."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from access.models import AccessGroup, DocumentGroup
    from access.rights import Right
    from documents import types
    from documents.models import Document

    member, _, membership = member_of("a.member@example.test")
    _, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    with schema_context(migrated_tenant.number):
        policy = types.add_type("policy (synthetic example)", by=admin_user)
        group = AccessGroup.objects.create(name="Readers", created_by=admin_user, actor_kind="user")
        group.grant(Right.VIEW_PENDING, by=admin_user)
        group.add_member(membership, by=admin_user)

    def add(title: str, typed: bool) -> None:
        document = _create(migrated_tenant, admin_user, title)
        with schema_context(migrated_tenant.number):
            if typed:
                Document.objects.filter(pk=document.pk).update(document_type=policy)
            DocumentGroup.link(document, group, by=admin_user)

    def cost(path: str) -> int:
        with CaptureQueriesContext(connection) as seen:
            body = member.get(path).content.decode()
        assert 'name="type"' in body
        return len(seen.captured_queries)

    add("Synthetic plain", False)
    add("Synthetic typed 0", True)
    paths = ("/folder/1/", f"/search/?type={policy.code}")
    for path in paths:
        cost(path)  # a warm-up: the first request reads what later ones find cached
    few = [cost(path) for path in paths]
    for i in range(1, 5):
        add(f"Synthetic typed {i}", True)
    many = [cost(path) for path in paths]

    assert few == many


def test_a_hidden_appendix_title_costs_nothing_to_search_for(
    migrated_tenant: Any, member_of: Any, operator: Any
) -> None:
    """A reader of accepted text searching words only a pending appendix holds reads exactly
    what a search for words nothing holds reads: the cost tells of no hidden title."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from access.models import DocumentGroup
    from access.rights import Right
    from review import services as review

    reader, _, membership = member_of("an.accepted.reader@example.test")
    document = _create(migrated_tenant, operator.user, "Synthetic travel policy")
    with schema_context(migrated_tenant.number):
        DocumentGroup.link(document, operator.group, by=operator.user)
    _with_appendices(migrated_tenant, document, operator.user, ["Rates"])
    with schema_context(migrated_tenant.number):
        review.accept(document, operator.user)
    pending = _with_appendices(migrated_tenant, document, operator.user, ["Rates", "Secret rates"])
    # Versions are ordered by commit time to the second; a test commits within one, so the
    # pending version is set apart from the acceptance as editing after it would be.
    with schema_context(migrated_tenant.number):
        from datetime import timedelta

        from django.db.models import F

        from documents.models import Version

        Version.objects.filter(pk=pending.pk).update(
            committed_at=F("committed_at") + timedelta(seconds=2)
        )
    _link(migrated_tenant, operator.user, Right.VIEW_ACCEPTED, membership, document)

    def cost(words: str) -> tuple[int, list[int]]:
        with CaptureQueriesContext(connection) as seen:
            body = reader.get(f"/search/?q={words}").content.decode()
        return len(seen.captured_queries), found(body)

    cost("warm-up")
    hidden, nothing = cost("secret"), cost("secrex")

    assert hidden == nothing
    assert hidden[1] == []


def _later(migrated_tenant: Any, version: Any, seconds: int) -> None:
    """Set `version` apart in time, as editing seconds later would; a test commits within one."""
    from datetime import timedelta

    from django.db.models import F

    from documents.models import Version

    with schema_context(migrated_tenant.number):
        Version.objects.filter(pk=version.pk).update(
            committed_at=F("committed_at") + timedelta(seconds=seconds)
        )


def _accepted_reader_of(
    migrated_tenant: Any, member_of: Any, operator: Any, versions: list[list[str]], accept_at: int
) -> tuple[Any, Any, Any]:
    """A document whose versions list `versions`' appendices in turn, two seconds apart, the
    `accept_at`-th accepted; a member reading accepted text alone. `(client, user, document)`."""
    from access.models import DocumentGroup
    from access.rights import Right
    from review import services as review

    client, user, membership = member_of("an.accepted.reader@example.test")
    document = _create(migrated_tenant, operator.user, "Synthetic travel policy")
    with schema_context(migrated_tenant.number):
        DocumentGroup.link(document, operator.group, by=operator.user)
    for i, titles in enumerate(versions):
        version = _with_appendices(migrated_tenant, document, operator.user, titles)
        _later(migrated_tenant, version, 2 * (i + 1) + (2 if i >= accept_at else 0))
        if i + 1 == accept_at:
            with schema_context(migrated_tenant.number):
                acceptance = review.accept(document, operator.user)
                _later(migrated_tenant, acceptance.version, 2 * (i + 1) + 1)
    _link(migrated_tenant, operator.user, Right.VIEW_ACCEPTED, membership, document)
    return client, user, document


def test_no_appendix_beyond_the_readers_reach_leaves_the_database(
    migrated_tenant: Any, member_of: Any, operator: Any
) -> None:
    """Pending versions after the acceptance hold a title the reader may not read: the database
    returns no candidate for it, so nothing about it reaches the application."""
    from documents import search
    from documents.models import Document

    _, user, document = _accepted_reader_of(
        migrated_tenant,
        member_of,
        operator,
        [["Rates"], ["Rates", "Secret rates"], ["Secret rates"]],
        1,
    )
    with schema_context(migrated_tenant.number):
        allowed = {Document.objects.get(pk=document.pk).pk}
        assert search.appendix_candidates(user, allowed, "secret") == set()
        assert search.appendix_candidates(user, allowed, "rates") == {document.pk}


def test_a_draft_never_accepted_is_beyond_the_readers_reach(
    migrated_tenant: Any, member_of: Any, operator: Any
) -> None:
    """A title a pending version added and a later edit removed, before that later text was
    accepted, was never readable by a reader of accepted text: no candidate, the same cost."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from documents import search

    client, user, document = _accepted_reader_of(
        migrated_tenant, member_of, operator, [["Interim rates"], ["Rates"]], 2
    )
    with schema_context(migrated_tenant.number):
        assert search.appendix_candidates(user, {document.pk}, "interim") == set()
        assert search.appendix_candidates(user, {document.pk}, "rates") == {document.pk}

    def cost(words: str) -> tuple[int, list[int]]:
        with CaptureQueriesContext(connection) as seen:
            body = client.get(f"/search/?q={words}").content.decode()
        return len(seen.captured_queries), found(body)

    cost("warm-up")
    assert cost("interim") == cost("intxrim")
    assert found(client.get("/search/?q=rates").content.decode()) == [
        document.pk and document.number
    ]
