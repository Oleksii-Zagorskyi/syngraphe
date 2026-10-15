"""The View tab (DL-0352, DL-0356): `/document/M/` shows the version the reader may see, rendered
with its clause numbers, under a header naming its number — *Viewing the 0.1 version*, *Viewing
the 0.1-1 version* — after the page's own gates; `/document/M/info/` stays *Info*. At an edition,
each reader reads their own version under its header; the diff views render through the same
renderer.

The suite renders in `uk`: *View* is *Перегляд*, *Viewing the … version* *Перегляд версії …*.
People, groups and titles are synthetic examples; every text is invented.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from access.rights import Right
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

TOKEN = re.compile(rb'name="csrfmiddlewaretoken" value="[^"]+"')
TITLE = "Procedure for approving requests (synthetic example)"
BODY = (
    "# General provisions\n\n"
    "A request for approval is made in writing.\n"
    "A request is considered within ten days.\n\n"
    "## Time limits\n\n"
    "A copy of the decision goes to the applicant that day.\n"
)
PENDING_SENTENCE = "The register of requests is kept by the officer in charge."


def _commit(tenant: int, document: Any, user: Any, body: str) -> Any:
    """One `reviewer_edit` version holding `body`, its row derived."""
    from documents import bundle, gitstore, services
    from documents.identity import identity_for
    from documents.locks import document_lock

    with schema_context(tenant):
        repo = gitstore.open_repository(tenant, document.number)
        with document_lock(tenant, document.number):
            head = gitstore.head(repo)
            assert head is not None
            frontmatter, _ = bundle.parse(gitstore.read(repo, "document.md", head).decode())
            sha = gitstore.commit(
                repo,
                {"document.md": bundle.render(frontmatter, body).encode("utf-8")},
                identity_for(user),
                "Synthetic edit",
                gitstore.Kind.REVIEWER_EDIT,
            )
            return services.derive_version(document, gitstore.commit_at(repo, sha), user)


@pytest.fixture
def accepted(migrated_tenant: Any, member_of: Any, repo_root: Path) -> Any:
    """A document created by an operator — in a linked group holding *create and edit* and
    *accept* — with one version accepted as `0.1`. `.document`, `.operator`."""
    from access.models import AccessGroup, DocumentGroup
    from documents import services
    from documents.models import DocumentType, Folder
    from identity.models import Language
    from review import services as review

    number = migrated_tenant.number
    _, operator, membership = member_of("operator.synthetic@example.test")
    Language.objects.get_or_create(code="uk", defaults={"label": "uk", "actor_kind": "system"})
    with schema_context(number):
        group = AccessGroup.objects.create(
            name="Operators (synthetic example)", created_by=operator, actor_kind="user"
        )
        group.grant(Right.CREATE_AND_EDIT, by=operator)
        group.grant(Right.ACCEPT, by=operator)
        group.add_member(membership, by=operator)
        document = services.create_document(
            operator,
            TITLE,
            "uk",
            DocumentType.objects.get(code="document"),
            Folder.objects.get(number=1),
        )
        DocumentGroup.link(document, group, by=operator)
    _commit(number, document, operator, BODY)
    with schema_context(number):
        review.accept(document, operator)
    return SimpleNamespace(document=document, operator=operator)


@pytest.fixture
def reader(migrated_tenant: Any, member_of: Any) -> Any:
    """`reader(right, document)`: a client signed in as a member of a new group holding `right`
    alone, linked to `document`."""
    from access.models import AccessGroup, DocumentGroup

    made = iter(range(1, 100))

    def make(right: Right, document: Any) -> Any:
        n = next(made)
        client, _, membership = member_of(f"reader{n}.synthetic@example.test")
        with schema_context(migrated_tenant.number):
            group = AccessGroup.objects.create(
                name=f"Readers {n} (synthetic example)", actor_kind="system"
            )
            group.grant(right, by=None)
            group.add_member(membership, by=None)
            DocumentGroup.link(document, group, by=None)
        return client

    return make


def article(body: str) -> str:
    found = re.search(r'<article class="document-text">(.*?)</article>', body, re.DOTALL)
    assert found is not None, "no document text"
    return found.group(1)


def tab(body: str, label: str) -> str:
    """The opening tag of the tab link whose text is `label`."""
    found = re.search(rf"(<a\b[^>]*>)\s*{label}\s*</a>", body)
    assert found is not None, f"no tab {label}"
    return found.group(1)


def test_accepted_reader_sees_the_view_tab(accepted: Any, reader: Any) -> None:
    document = accepted.document
    client = reader(Right.VIEW_ACCEPTED, document)

    response = client.get(f"/document/{document.number}/")

    assert response.status_code == 200
    body = response.content.decode()
    view = tab(body, "Перегляд")
    assert f'href="/document/{document.number}/"' in view
    assert 'aria-current="page"' in view
    assert 'aria-current="page"' not in tab(body, "Відомості")
    # View comes first in the tab row.
    assert body.index(view) < body.index(tab(body, "Відомості"))
    assert "Перегляд версії 0.1" in body
    text = article(body)
    assert re.search(r'<h1 id="h-1"><span class="num">1</span> General provisions</h1>', text)
    assert re.search(r'<h2 id="h-1\.1"><span class="num">1\.1</span> Time limits</h2>', text)
    # One paragraph, its sentences joined by a space; numbered within its section.
    assert re.search(
        r'<p><span class="num">1-1</span> A request for approval is made in writing\. '
        r"A request is considered within ten days\.</p>",
        text,
    )
    assert re.search(r'<p><span class="num">1\.1-1</span> A copy of the decision', text)


def test_header_then_text_then_the_panels_attachments(accepted: Any, reader: Any) -> None:
    """The attachments stand in the right panel beside the text, not above it (DL-0356)."""
    document = accepted.document
    body = reader(Right.VIEW_ACCEPTED, document).get(f"/document/{document.number}/")
    html = body.content.decode()

    header = html.index("Перегляд версії 0.1")
    text = html.index('<article class="document-text">')
    panel = html.index('<aside class="panel"')
    attachments = html.index('<section class="attachments">')
    assert header < text < panel < attachments


def test_pending_edit_is_not_the_accepted_readers(
    migrated_tenant: Any, accepted: Any, reader: Any
) -> None:
    document = accepted.document
    _commit(migrated_tenant.number, document, accepted.operator, BODY + f"\n{PENDING_SENTENCE}\n")
    accepted_client = reader(Right.VIEW_ACCEPTED, document)
    pending_client = reader(Right.VIEW_PENDING, document)

    as_accepted = accepted_client.get(f"/document/{document.number}/").content.decode()
    as_pending = pending_client.get(f"/document/{document.number}/").content.decode()

    assert re.search(r"Перегляд версії 0\.1(?![-\d])", as_accepted)
    assert PENDING_SENTENCE not in as_accepted
    assert "Перегляд версії 0.1-1" in as_pending
    assert not re.search(r"Перегляд версії 0\.1(?![-\d])", as_pending)
    assert re.search(
        rf'<p><span class="num">1\.1-2</span> {re.escape(PENDING_SENTENCE)}</p>',
        article(as_pending),
    )


def test_the_header_names_the_readers_version_on_every_tab(
    migrated_tenant: Any, accepted: Any, reader: Any
) -> None:
    """The document's header follows the view's rule (DL-0209, `pages.md § Document page`): the
    latest version the reader may see stands after the title, on *View* and on *Info* alike."""
    document = accepted.document
    _commit(migrated_tenant.number, document, accepted.operator, BODY + f"\n{PENDING_SENTENCE}\n")
    accepted_client = reader(Right.VIEW_ACCEPTED, document)
    pending_client = reader(Right.VIEW_PENDING, document)

    def header(client: Any, path: str) -> str:
        found = re.search(r"<h1>(.*?)</h1>", client.get(path).content.decode(), re.S)
        assert found is not None
        return found.group(1)

    for path in (f"/document/{document.number}/", f"/document/{document.number}/info/"):
        assert re.search(r'<span class="version-number">0\.1</span>', header(accepted_client, path))
        assert '<span class="version-number">0.1-1</span>' in header(pending_client, path)
    # The tabs and pages beyond *View* and *Info* share the header, and its version with it.
    assert '<span class="version-number">0.1-1</span>' in header(
        pending_client, f"/document/{document.number}/pending/"
    )
    editor = reader(Right.EDIT, document)
    assert '<span class="version-number">0.1-1</span>' in header(
        editor, f"/document/{document.number}/edit/"
    )


def test_pending_holder_with_nothing_pending_sees_the_accepted_version(
    accepted: Any, reader: Any
) -> None:
    document = accepted.document
    client = reader(Right.VIEW_PENDING, document)

    body = client.get(f"/document/{document.number}/").content.decode()

    assert re.search(r"Перегляд версії 0\.1(?![-\d])", body)


def test_no_edition_not_found(accepted: Any, reader: Any) -> None:
    document = accepted.document
    client = reader(Right.VIEW_CANONICAL, document)

    response = client.get(f"/document/{document.number}/")
    unknown = client.get("/document/9999/")

    assert response.status_code == 404 and unknown.status_code == 404
    assert TOKEN.sub(b"", response.content) == TOKEN.sub(b"", unknown.content)
    assert TITLE not in response.content.decode()


def test_info_stays_info(accepted: Any, reader: Any) -> None:
    document = accepted.document
    client = reader(Right.VIEW_ACCEPTED, document)

    response = client.get(f"/document/{document.number}/info/")

    assert response.status_code == 200
    body = response.content.decode()
    assert 'aria-current="page"' in tab(body, "Відомості")
    assert 'aria-current="page"' not in tab(body, "Перегляд")
    assert 'class="document-text"' not in body


def test_reader_sees_no_editing_tabs(accepted: Any, reader: Any) -> None:
    document = accepted.document
    client = reader(Right.VIEW_ACCEPTED, document)

    for path in (f"/document/{document.number}/", f"/document/{document.number}/info/"):
        body = client.get(path).content.decode()
        for hidden in ("edit/", "pending/", "my-edits/"):
            assert f'href="/document/{document.number}/{hidden}"' not in body, (path, hidden)
        assert 'data-nav="in-edit"' not in body and 'data-nav="in-review"' not in body


# --- by rights, at an edition, and the diff views ----------------------------------------------

FIRST = "# General provisions\n\nA request for approval is made in writing.\n"
SECOND = FIRST + "\nA copy of the decision goes to [the applicant]{.role #applicant} that day.\n"
THIRD = SECOND + "\n> [!note]\n> The register of requests is kept by the officer in charge.\n"


def _at_edition(migrated_tenant: Any, edition_cast: Any, commit_version: Any) -> Any:
    """Edition `1.0` over the first text, `1.1` accepted over the second, `1.1-1` pending."""
    from editions import services as editions
    from review import services as review

    people = edition_cast()
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
        editions.freeze(document, people["p"], "Synthetic reason")
        editions.make_canonical(document, people["p"])
    commit_version(document, people["a"], SECOND, "edit")
    with schema_context(migrated_tenant.number):
        assert review.accept(document, people["r"]).number == "1.1"
    commit_version(document, people["a"], THIRD, "edit")
    return people


def _readers(member_of: Any, link_group: Any, people: Any) -> dict[str, Any]:
    clients = {}
    for name, right in (
        ("pending", Right.VIEW_PENDING),
        ("accepted", Right.VIEW_ACCEPTED),
        ("canonical", Right.VIEW_CANONICAL),
    ):
        client, _, membership = member_of(f"{name}.reader.synthetic@example.test")
        link_group(people.document, [right], [membership], people["a"])
        clients[name] = client
    return clients


def test_view_by_rights(
    migrated_tenant: Any, edition_cast: Any, member_of: Any, link_group: Any, commit_version: Any
) -> None:
    people = _at_edition(migrated_tenant, edition_cast, commit_version)
    readers = _readers(member_of, link_group, people)
    route = f"/document/{people.document.number}/"

    pages = {name: client.get(route).content.decode() for name, client in readers.items()}

    assert "Перегляд версії 1.1-1" in pages["pending"]
    assert "Перегляд версії 1.1" in pages["accepted"] and "1.1-1" not in pages["accepted"]
    assert "Перегляд канонічної версії 1.0" in pages["canonical"]
    for name in ("pending", "accepted"):
        assert "відкрити канонічну версію 1.0" in pages[name], name
    pending, accepted, canonical = (article(pages[n]) for n in ("pending", "accepted", "canonical"))
    assert '<div class="callout callout-note">' in pending
    assert "The register of requests" not in accepted
    assert 'data-id="applicant"' in accepted and "the applicant" not in canonical
    assert re.search(r'<p><span class="num">1-1</span> A request for approval', canonical)


def test_diff_views_use_the_renderer(
    migrated_tenant: Any, edition_cast: Any, member_of: Any, link_group: Any, commit_version: Any
) -> None:
    people = _at_edition(migrated_tenant, edition_cast, commit_version)
    client = people.clients["r"]

    body = client.get(f"/document/{people.document.number}/pending/").content.decode()

    start = body.find('<div class="changes document-text">')
    assert start >= 0, "no changes"
    html = body[start:]
    assert '<div class="callout callout-note">' in html
    assert '<span class="num">1-3</span>' in html
    assert "<ins>The register of requests is kept by the officer in charge.</ins>" in html


def test_info_names_the_canonical_version_and_the_state(
    migrated_tenant: Any, edition_cast: Any, member_of: Any, link_group: Any, commit_version: Any
) -> None:
    """At edition 1.0 with 1.1-1 pending: a holder of *view pending* reads *awaiting review*; a
    reader of canonical text learns of no pending work; both read the canonical version."""
    people = _at_edition(migrated_tenant, edition_cast, commit_version)
    readers = _readers(member_of, link_group, people)
    route = f"/document/{people.document.number}/info/"

    pending = readers["pending"].get(route).content.decode()
    canonical = readers["canonical"].get(route).content.decode()

    assert 'data-state="awaiting_review"' in pending
    assert 'data-state="canonical"' in canonical
    for body in (pending, canonical):
        assert '<dd class="canonical">1.0</dd>' in body


def test_info_names_canonical_when_nothing_is_beyond_it(
    migrated_tenant: Any, edition_cast: Any, member_of: Any, link_group: Any, commit_version: Any
) -> None:
    from editions import services as editions
    from review import services as review

    people = edition_cast()
    commit_version(people.document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(people.document, people["r"])
        editions.freeze(people.document, people["p"], "Synthetic reason")
        editions.make_canonical(people.document, people["p"])
    readers = _readers(member_of, link_group, people)

    body = readers["canonical"].get(f"/document/{people.document.number}/info/").content.decode()

    assert 'data-state="canonical"' in body


def test_the_state_line_says_nothing_of_work_beyond_the_reader(
    migrated_tenant: Any, edition_cast: Any, member_of: Any, link_group: Any, commit_version: Any
) -> None:
    """At an edition with work pending, a reader of canonical text reads *canonical* — what their
    own version is — never an absence that tells them more lies beyond it."""
    people = _at_edition(migrated_tenant, edition_cast, commit_version)
    readers = _readers(member_of, link_group, people)

    canonical = readers["canonical"].get(f"/document/{people.document.number}/info/")
    accepted = readers["accepted"].get(f"/document/{people.document.number}/info/")

    assert 'data-state="canonical"' in canonical.content.decode()
    assert 'data-state="accepted"' in accepted.content.decode()
