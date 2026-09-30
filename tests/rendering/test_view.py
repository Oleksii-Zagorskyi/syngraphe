"""The View tab (DL-0349, DL-0352): `/document/M/` shows the version the reader may see, rendered
with its clause numbers, under a header naming its number — *Viewing the 0.1 version*, *Viewing
the 0.1-1 version* — after the page's own gates; `/document/M/info/` stays *Info*.

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
TITLE = "Порядок погодження заяв (синтетичний приклад)"
BODY = (
    "# Загальні положення\n\n"
    "Заяву на погодження подають письмово.\n"
    "Строк розгляду заяви становить десять днів.\n\n"
    "## Строки\n\n"
    "Копію рішення надсилають заявникові того ж дня.\n"
)
PENDING_SENTENCE = "Реєстр заяв веде відповідальний виконавець."


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
                "Синтетична правка",
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
            name="Оператори (синтетичний приклад)", created_by=operator, actor_kind="user"
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
                name=f"Читачі {n} (синтетичний приклад)", actor_kind="system"
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
    assert re.search(r'<h1><span class="num">1</span> Загальні положення</h1>', text)
    assert re.search(r'<h2><span class="num">1\.1</span> Строки</h2>', text)
    # One paragraph, its sentences joined by a space; numbered within its section.
    assert re.search(
        r'<p><span class="num">1-1</span> Заяву на погодження подають письмово\. '
        r"Строк розгляду заяви становить десять днів\.</p>",
        text,
    )
    assert re.search(r'<p><span class="num">1\.1-1</span> Копію рішення', text)


def test_header_then_attachments_then_text(accepted: Any, reader: Any) -> None:
    document = accepted.document
    body = reader(Right.VIEW_ACCEPTED, document).get(f"/document/{document.number}/")
    html = body.content.decode()

    header = html.index("Перегляд версії 0.1")
    attachments = html.index('<section class="attachments">')
    text = html.index('<article class="document-text">')
    assert header < attachments < text


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


def test_pending_holder_with_nothing_pending_sees_the_accepted_version(
    accepted: Any, reader: Any
) -> None:
    document = accepted.document
    client = reader(Right.VIEW_PENDING, document)

    body = client.get(f"/document/{document.number}/").content.decode()

    assert re.search(r"Перегляд версії 0\.1(?![-\d])", body)


def test_view_canonical_alone_answers_as_missing(accepted: Any, reader: Any) -> None:
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
