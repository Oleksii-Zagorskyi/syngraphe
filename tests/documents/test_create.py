"""Creating a document: the one write across both stores, in order, with every crash state the
reconciler repairs (DL-0111, DL-0268, ADR-0007, ADR-0008).

Group names and people are synthetic examples."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]


@pytest.fixture
def author(migrated_tenant: Any, member_of: Any) -> Any:
    """A member of a group holding `create and edit`, signed in; `(client, user)`."""
    from access.models import AccessGroup
    from access.rights import Right
    from identity.models import Language

    Language.objects.get_or_create(code="uk", defaults={"label": "uk", "actor_kind": "system"})
    client, user, membership = member_of("an.author@example.test")
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(name="Authors", actor_kind="system")
        group.grant(Right.CREATE_AND_EDIT, by=None)
        group.add_member(membership, by=None)
    return client, user


def _form(migrated_tenant: Any) -> dict[str, str]:
    from documents.models import DocumentType, Folder

    with schema_context(migrated_tenant.number):
        document_type = DocumentType.objects.get(code="document")
        folder = Folder.objects.get(number=1)
    return {
        "title": "Synthetic example",
        "language": "uk",
        "document_type": str(document_type.id),
        "folder": str(folder.id),
    }


def test_create_document_end_to_end(migrated_tenant: Any, author: Any, repo_root: Path) -> None:
    from audit.models import AuditEvent
    from documents import gitstore
    from documents.gitstore import Kind
    from documents.models import Document, Version

    client, user = author

    response = client.post("/document/new/", _form(migrated_tenant))

    with schema_context(migrated_tenant.number):
        document = Document.objects.get()
        versions = list(Version.objects.filter(document=document))
    assert response.status_code == 302
    assert response["Location"] == f"/document/{document.number}/"
    assert (document.state, document.author_only, document.created_by_id) == (
        "active",
        True,
        user.id,
    )
    repo = gitstore.open_repository(migrated_tenant.number, document.number)
    assert (
        Path(repo.path).resolve()
        == (
            repo_root / f"tenant-{migrated_tenant.number}" / f"document-{document.number}"
        ).resolve()
    )
    history = list(gitstore.history(repo))
    assert len(history) == 1
    assert gitstore.kind_of(history[0].message) is Kind.CREATED
    assert history[0].author.name == str(user.id)
    assert [(v.commit_sha, v.kind, v.author_id) for v in versions] == [
        (str(history[0].id), "created", user.id)
    ]
    events = AuditEvent.objects.filter(action="document.created")
    assert [(e.tenant_id, e.actor_id, e.after["number"]) for e in events] == [
        (migrated_tenant.id, user.id, document.number)
    ]


def test_created_commit_holds_the_initial_tree(
    migrated_tenant: Any, author: Any, repo_root: Path
) -> None:
    from documents import bundle, gitstore
    from documents.models import Document, DocumentTemplate

    client, _ = author
    with schema_context(migrated_tenant.number):
        DocumentTemplate.objects.update(
            outline="# Purpose\nThe first sentence. The second sentence.\n"
        )
    client.post("/document/new/", _form(migrated_tenant))

    with schema_context(migrated_tenant.number):
        document = Document.objects.get()
    repo = gitstore.open_repository(migrated_tenant.number, document.number)
    sha = str(next(gitstore.history(repo)).id)
    frontmatter, body = bundle.parse(gitstore.read(repo, "document.md", sha).decode())
    assert (frontmatter.title, frontmatter.language, frontmatter.title_page) == (
        "Synthetic example",
        "uk",
        False,
    )
    assert (frontmatter.appendices, frontmatter.attachments) == ([], [])
    # The outline in normal form for the document's language, each sentence on a line of its own.
    assert body == "# Purpose\n\nThe first sentence.\nThe second sentence.\n"
    assert gitstore.read(repo, "passport.md", sha).decode() == bundle.passport_header(
        migrated_tenant.number, document.number
    )
    assert gitstore.read(repo, "entities.yaml", sha) == b"[]\n"


def test_numbers_never_reused(migrated_tenant: Any, author: Any, repo_root: Path) -> None:
    from documents import services
    from documents.models import Document, DocumentType, Folder

    _, user = author
    with schema_context(migrated_tenant.number):
        kind = DocumentType.objects.get(code="document")
        root = Folder.objects.get(number=1)
        first = services.create_document(user, "First", "uk", kind, root)
        second = services.create_document(user, "Second", "uk", kind, root)
        with pytest.raises(services.InjectedFault):
            services.create_document(user, "Third", "uk", kind, root, fault_at=1)
        fourth = services.create_document(user, "Fourth", "uk", kind, root)
        numbers = list(Document.objects.order_by("number").values_list("number", "state"))

    assert second.number == first.number + 1
    assert fourth.number == first.number + 3
    assert numbers == [
        (first.number, "active"),
        (first.number + 1, "active"),
        (first.number + 2, "creating"),
        (first.number + 3, "active"),
    ]


def test_create_needs_the_right(migrated_tenant: Any, member_of: Any, repo_root: Path) -> None:
    from documents.models import Document

    client, _, _ = member_of("a.reader@example.test")

    assert client.get("/document/new/").status_code == 404
    assert client.post("/document/new/", _form(migrated_tenant)).status_code == 404
    with schema_context(migrated_tenant.number):
        assert not Document.objects.exists()


def test_the_form_refuses_what_it_cannot_take(
    migrated_tenant: Any, author: Any, repo_root: Path
) -> None:
    from documents.models import Document

    client, _ = author
    form = _form(migrated_tenant)

    from documents.models import DocumentType, Folder, next_folder_number

    with schema_context(migrated_tenant.number):
        retired = DocumentType.objects.create(
            code="old", label="old", retired_at="2026-01-01T00:00:00Z", actor_kind="system"
        )
        other_folder = Folder.objects.create(
            number=next_folder_number(),
            parent=Folder.objects.get(number=1),
            name="Sub",
            actor_kind="system",
        )
    bads = (
        {"title": "   "},
        {"title": "x" * 501},
        {"title": "a\x7fb"},
        {"title": "a\nb"},
        {"language": "xx"},
        {"document_type": "not-a-uuid"},
        {"document_type": str(retired.id)},
        {"folder": str(other_folder.id)},
    )
    for bad in bads:
        response = client.post("/document/new/", {**form, **bad})
        assert response.status_code == 400, bad
    with schema_context(migrated_tenant.number):
        assert not Document.objects.exists()


def test_the_dialog_renders(migrated_tenant: Any, author: Any, repo_root: Path) -> None:
    from identity.models import Language

    client, _ = author
    Language.objects.update_or_create(
        code="uk", defaults={"label": "Українська", "actor_kind": "system"}
    )
    Language.objects.update_or_create(
        code="en", defaults={"label": "English", "actor_kind": "system"}
    )

    response = client.get("/document/new/")

    assert response.status_code == 200
    body = response.content.decode()
    assert 'name="title"' in body
    assert 'value="uk"' in body
    # Language and type are named in words, as the Info tab names them, never by their codes.
    from documents.models import DocumentType
    from tenancy.schemas import schema_context

    with schema_context(migrated_tenant.number):
        kind = DocumentType.objects.get(code="document")
        language = Language.objects.get(code="uk")
        options = re.findall(r"<option[^>]*>([^<]*)</option>", body)
    assert language.label in options and "uk" not in options and "en" not in options
    assert kind.label in options and "document" not in options
    # The installation's language preselected while an organisation has none of its own
    # (DL-0512): the suite's is Ukrainian.
    assert re.search(r'<option value="uk" selected>', body)


@pytest.mark.parametrize(("installation", "offered"), [("en", "en"), ("de", "en")])
def test_the_installations_language_is_offered_first(
    migrated_tenant: Any, author: Any, settings: Any, installation: str, offered: str
) -> None:
    """The create form offers the installation's language first (DL-0512), never the person's
    interface language; a code no language row has falls to English."""
    from identity.models import Language

    client, _ = author
    for code, label in (("uk", "Українська"), ("en", "English")):
        Language.objects.update_or_create(
            code=code, defaults={"label": label, "actor_kind": "system"}
        )
    settings.LANGUAGE_CODE = installation

    body = client.get("/document/new/").content.decode()

    assert re.search(rf'<option value="{offered}" selected>', body)


def test_the_dialog_offers_the_folders_the_person_sees(
    migrated_tenant: Any, author: Any, member_of: Any, make_document: Any
) -> None:
    """The folder choice is the person's visible folders by path, the root first; a posted
    folder they may not see is refused as an unknown one (DL-0206)."""
    from access.models import AccessGroup, DocumentGroup
    from access.rights import Right
    from documents import folders
    from documents.models import Document, Folder
    from identity.models import Membership

    client, user = author
    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    with schema_context(migrated_tenant.number):
        root = Folder.objects.get(number=1)
        seen = folders.create_folder(root, "Seen (synthetic example)", by=admin)
        inner = folders.create_folder(seen, "Inner (synthetic example)", by=admin)
        hidden = folders.create_folder(root, "Hidden (synthetic example)", by=admin)
    readable = make_document(title="Synthetic readable", folder=inner, author_only=False)
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(name="Readers", actor_kind="system")
        group.grant(Right.VIEW_ACCEPTED, by=None)
        group.add_member(Membership.objects.get(user=user), by=None)
        DocumentGroup.link(readable, group, by=admin)
    form = _form(migrated_tenant)

    body = client.get("/document/new/").content.decode()
    refused = client.post("/document/new/", {**form, "folder": str(hidden.id)})

    options = re.findall(r'<option value="([^"]+)"[^>]*>([^<]*)</option>', body)
    folder_options = [
        label
        for value, label in options
        if value in {str(root.id), str(seen.id), str(inner.id), str(hidden.id)}
    ]
    assert folder_options == [
        migrated_tenant.name,
        "Seen (synthetic example)",
        "Seen (synthetic example) / Inner (synthetic example)",
    ]
    assert refused.status_code == 400
    with schema_context(migrated_tenant.number):
        assert not Document.objects.filter(title="Synthetic example").exists()


def test_crash_states_are_the_documented_ones(
    migrated_tenant: Any, author: Any, repo_root: Path
) -> None:
    from audit.models import AuditEvent
    from documents import gitstore, services
    from documents.models import Document, DocumentType, Folder, HeadingIndex, Version

    _, user = author
    states = {}
    with schema_context(migrated_tenant.number):
        kind = DocumentType.objects.get(code="document")
        root = Folder.objects.get(number=1)
        for step in (1, 2, 3, 4):
            with pytest.raises(services.InjectedFault):
                services.create_document(user, f"Step {step}", "uk", kind, root, fault_at=step)
            document = Document.objects.get(title=f"Step {step}")
            path = gitstore.repository_path(migrated_tenant.number, document.number)
            commits = (
                len(list(gitstore.history(gitstore.open_repository(*_numbers(document)))))
                if path.exists()
                else None
            )
            states[step] = (
                document.state,
                path.exists(),
                commits,
                Version.objects.filter(document=document).count(),
                HeadingIndex.objects.filter(document=document).count(),
            )

    assert states == {
        1: ("creating", False, None, 0, 0),
        2: ("creating", True, 0, 0, 0),
        3: ("creating", True, 1, 0, 0),
        4: ("creating", True, 1, 1, 1),
    }
    assert not AuditEvent.objects.filter(action="document.created").exists()


def test_a_step_that_fails_leaves_a_documented_state(
    migrated_tenant: Any, author: Any, repo_root: Path, monkeypatch: Any
) -> None:
    from documents import caches, services
    from documents.models import Document, Version

    client, _ = author

    def broken(*args: Any, **kwargs: Any) -> None:
        raise OSError("the disk is full")

    monkeypatch.setattr(caches, "rebuild", broken)
    response = client.post("/document/new/", _form(migrated_tenant))

    with schema_context(migrated_tenant.number):
        document = Document.objects.get()
        assert document.state == "creating"
        assert not Version.objects.exists()
    assert response.status_code == 503
    body = response.content.decode()
    alert = re.search(r'role="alert">([^<]*)<', body)
    assert alert and str(document.number) in alert.group(1)
    assert 'value="Synthetic example"' in body
    assert services.CreationStopped


def _numbers(document: Any) -> tuple[int, int]:
    from django.db import connection

    from tenancy.schemas import current_tenant

    tenant = current_tenant(connection)
    assert tenant is not None
    return tenant, document.number
