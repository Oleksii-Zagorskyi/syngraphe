"""Copying a document (ST-0067, DL-0451, DL-0455, DL-0268): the copy's one `created` commit holds
a version of the source the copier may see — its text, the chosen appendices renumbered from 1,
the language and title page, the images it references and its entities, never an attachment — and
its source is recorded before any repository exists.

Titles, appendices, files, groups and people are synthetic examples."""

from __future__ import annotations

import dataclasses
import hashlib
import html
import re
from types import SimpleNamespace
from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

IMAGE = b"\x89PNG synthetic image bytes"
IMAGE_PATH = f"images/{hashlib.sha256(IMAGE).hexdigest()}.png"
# An image only the appendix *Rates* shows; the copies take *Forms* alone, so it stays behind.
RATES_IMAGE = b"\x89PNG synthetic rate table bytes"
RATES_IMAGE_PATH = f"images/{hashlib.sha256(RATES_IMAGE).hexdigest()}.png"
RATES = (
    "# Rates\n\nSynthetic rates: [the synthetic rate]{.term #synthetic-rate}.\n\n"
    f"![A synthetic rate table]({RATES_IMAGE_PATH})\n"
)
FORMS = "# Forms\n\nSynthetic forms: [the synthetic form]{.term #synthetic-form}.\n"
# The source's declarations: the body marks the role, *Forms* the form; nothing marks the unused
# term, the role's key under another kind, or — once *Rates* is left behind — the rate.
ENTITIES = (
    b"- kind: role\n  key: synthetic-head\n  label: Synthetic head of unit\n"
    b"- kind: action\n  key: synthetic-head\n  label: Synthetic head's action\n"
    b"- kind: term\n  key: synthetic-unused\n  label: Synthetic unused term\n"
    b"- kind: term\n  key: synthetic-rate\n  label: Synthetic rate\n"
    b"- kind: term\n  key: synthetic-form\n  label: Synthetic form\n"
)
MARKED = (
    b"- kind: role\n  key: synthetic-head\n  label: Synthetic head of unit\n"
    b"- kind: term\n  key: synthetic-form\n  label: Synthetic form\n"
)
SCHEME = b"synthetic attachment bytes\n"


def _body(words: str) -> str:
    return (
        f"# Terms\n\n{words}\n\n[The synthetic head]{{.role #synthetic-head}} approves it; "
        "[an unnamed clerk]{.role} records it.\n\n"
        f"![A synthetic picture]({IMAGE_PATH})\n"
    )


def _commit(
    migrated_tenant: Any,
    document: Any,
    user: Any,
    body: str,
    *,
    appendices: list[tuple[str, str]] | None = None,
    attachments: bool = False,
    files: dict[str, bytes] | None = None,
    title_page: bool | None = None,
) -> Any:
    """A `reviewer_edit` version of `document` with `body`; `appendices` replace the listed ones,
    `attachments` lists the one attachment, `files` added as they stand. The row derived."""
    from documents import bundle, gitstore, services
    from documents.identity import identity_for
    from documents.locks import document_lock

    number = migrated_tenant.number
    with schema_context(number):
        repo = gitstore.open_repository(number, document.number)
        with document_lock(number, document.number):
            head = gitstore.head(repo)
            assert head is not None
            frontmatter, _ = bundle.parse(gitstore.read(repo, "document.md", head).decode())
            written = dict(files or {})
            if appendices is not None:
                listed = [{"number": n, "title": t} for n, (t, _) in enumerate(appendices, 1)]
                frontmatter = dataclasses.replace(frontmatter, appendices=listed)
                for n, (_, text) in enumerate(appendices, 1):
                    written[f"appendices/{n}.md"] = text.encode()
            if title_page is not None:
                frontmatter = dataclasses.replace(frontmatter, title_page=title_page)
            if attachments:
                entry = {
                    "number": 1,
                    "title": "Synthetic scheme",
                    "file_name": "scheme.txt",
                    "sha256": hashlib.sha256(SCHEME).hexdigest(),
                    "bytes": len(SCHEME),
                }
                frontmatter = dataclasses.replace(frontmatter, attachments=[entry])
                written["attachments/1"] = SCHEME
            written["document.md"] = bundle.render(frontmatter, body).encode()
            sha = gitstore.commit(
                repo, written, identity_for(user), "Synthetic edit", gitstore.Kind.REVIEWER_EDIT
            )
            return services.derive_version(document, gitstore.commit_at(repo, sha), user)


@pytest.fixture
def source(migrated_tenant: Any, member_of: Any, repo_root: Any) -> SimpleNamespace:
    """A document with an edition `1.0`, an acceptance `1.1` and a pending `1.1-2`: two
    appendices, an attachment, an image its text references and a list of entities. Its author is
    an administrator holding every right through *Operators*."""
    from access.models import AccessGroup, DocumentGroup
    from access.rights import Right
    from documents import services
    from documents.models import DocumentType, Folder
    from editions import services as editions
    from identity.models import Language
    from review import services as review

    Language.objects.get_or_create(code="uk", defaults={"label": "uk", "actor_kind": "system"})
    client, user, membership = member_of("the.operator@example.test", is_tenant_admin=True)
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(
            name="Operators (synthetic example)", created_by=user, actor_kind="user"
        )
        for right in Right:
            group.grant(right, by=user)
        group.add_member(membership, by=user)
        document = services.create_document(
            user,
            "Synthetic travel policy",
            "uk",
            DocumentType.objects.get(code="document"),
            Folder.objects.get(number=1),
        )
        DocumentGroup.link(document, group, by=user)
    appendices = [
        ("Rates", RATES),
        ("Forms", FORMS),
    ]
    _commit(
        migrated_tenant,
        document,
        user,
        _body("The first synthetic text."),
        appendices=appendices,
        attachments=True,
        files={IMAGE_PATH: IMAGE, RATES_IMAGE_PATH: RATES_IMAGE, "entities.yaml": ENTITIES},
        title_page=True,
    )
    with schema_context(migrated_tenant.number):
        review.accept(document, user)
        editions.freeze(document, user, "Synthetic reason")
        editions.make_canonical(document, user)
    _commit(migrated_tenant, document, user, _body("The accepted synthetic text."))
    with schema_context(migrated_tenant.number):
        review.accept(document, user)
    _commit(migrated_tenant, document, user, _body("The pending synthetic text, first."))
    _commit(migrated_tenant, document, user, _body("The pending synthetic text, second."))
    return SimpleNamespace(client=client, user=user, group=group, document=document)


def _copy(migrated_tenant: Any, source: Any, view: str, number: str, **kwargs: Any) -> Any:
    from documents import copying
    from documents.models import DocumentType, Folder

    with schema_context(migrated_tenant.number):
        return copying.copy_document(
            source.user,
            source.document,
            title=kwargs.pop("title", "Synthetic copy"),
            document_type=DocumentType.objects.get(code="document"),
            folder=Folder.objects.get(number=1),
            view=view,
            number=number,
            appendices=kwargs.pop("appendices", None),
            **kwargs,
        )


def test_the_first_commit_is_the_chosen_version(migrated_tenant: Any, source: Any) -> None:
    from documents import bundle, entities, gitstore
    from documents.models import Version

    copy = _copy(migrated_tenant, source, "accepted", "1.1", appendices=[2])

    repo = gitstore.open_repository(migrated_tenant.number, copy.number)
    history = list(gitstore.history(repo))
    assert len(history) == 1 and gitstore.kind_of(history[0].message) is gitstore.Kind.CREATED
    assert history[0].author.name == str(source.user.pk)
    head = str(history[0].id)
    frontmatter, body = bundle.parse(gitstore.read(repo, "document.md", head).decode())
    assert "The accepted synthetic text." in body
    assert frontmatter.title == "Synthetic copy" and frontmatter.language == "uk"
    # The source's title page switched on, against the template's default.
    assert frontmatter.title_page is True
    assert frontmatter.appendices == [{"number": 1, "title": "Forms"}]
    assert frontmatter.attachments == []
    assert gitstore.read(repo, "appendices/1.md", head) == FORMS.encode()
    assert gitstore.read(repo, IMAGE_PATH, head) == IMAGE
    # The declarations the copied text marks, by kind and key; the unmarked one left behind.
    carried = gitstore.read(repo, "entities.yaml", head).decode()
    assert entities.parse(carried) == entities.parse(MARKED.decode())
    for absent in ("attachments/1", "appendices/2.md", RATES_IMAGE_PATH):
        with pytest.raises(KeyError):
            gitstore.read(repo, absent, head)
    with schema_context(migrated_tenant.number):
        assert list(Version.objects.filter(document=copy).values_list("kind", flat=True)) == [
            "created"
        ]


def test_the_source_is_recorded_and_administrators_told(
    migrated_tenant: Any, member_of: Any, source: Any
) -> None:
    from audit.models import AuditEvent
    from documents.models import Document, Version
    from notifications.models import Notification

    _, other_admin, _ = member_of("another.admin@example.test", is_tenant_admin=True)
    with schema_context(migrated_tenant.number):
        accepted = Version.objects.filter(document=source.document, kind="reviewer_edit").order_by(
            "committed_at"
        )[1]

    copy = _copy(migrated_tenant, source, "accepted", "1.1", appendices=[2])

    with schema_context(migrated_tenant.number):
        copy = Document.objects.get(pk=copy.pk)
        told = list(Notification.objects.filter(event="document_copied"))
    assert copy.author_only and copy.copied_from_id == source.document.pk
    copied = AuditEvent.objects.get(action="document.copied")
    assert copied.object_type == "document" and copied.object_id == copy.pk
    assert copied.after == {
        "number": copy.number,
        "source_number": source.document.number,
        "source_version": "1.1",
        "source_commit": accepted.commit_sha,
        "appendices": [2],
    }
    created = AuditEvent.objects.get(action="document.created", object_id=copy.pk)
    assert created.after["copied_from"] == source.document.number
    assert copied.at <= created.at
    assert [n.user_id for n in told] == [other_admin.pk]
    assert told[0].document_id == copy.pk


def test_only_versions_the_copier_may_see(
    migrated_tenant: Any, member_of: Any, source: Any, settings: Any
) -> None:
    from access.models import AccessGroup, DocumentGroup
    from access.rights import Right

    settings.LANGUAGE_CODE = "en"
    reader, user, membership = member_of("a.reader@example.test")
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(
            name="Readers", created_by=source.user, actor_kind="user"
        )
        group.grant(Right.VIEW_ACCEPTED, by=source.user)
        group.add_member(membership, by=source.user)
        DocumentGroup.link(source.document, group, by=source.user)
        creators = AccessGroup.objects.create(
            name="Creators", created_by=source.user, actor_kind="user"
        )
        creators.grant(Right.CREATE_AND_EDIT, by=source.user)
        creators.add_member(membership, by=source.user)

    dialog = html.unescape(reader.get(f"/document/{source.document.number}/copy/").content.decode())

    offered = re.findall(
        r'<input type="radio" name="version" value="([a-z_]+):([0-9.-]+)"([^>]*)>', dialog
    )
    assert [(view, number) for view, number, _ in offered] == [
        ("accepted", "1.1"),
        ("canonical", "1.0"),
    ]
    assert "checked" in offered[0][2]
    assert "Attachments are not copied." in dialog


def test_a_source_that_moved_is_refused(migrated_tenant: Any, source: Any, settings: Any) -> None:
    from documents.models import Document

    settings.LANGUAGE_CODE = "en"
    client = source.client
    dialog = client.get(f"/document/{source.document.number}/copy/").content.decode()
    assert 'value="pending_edits:1.1-2" checked' in dialog
    _commit(
        migrated_tenant, source.document, source.user, _body("The pending synthetic text, third.")
    )
    with schema_context(migrated_tenant.number):
        before = Document.objects.count()

    answer = client.post(
        f"/document/{source.document.number}/copy/",
        {
            "title": "Synthetic copy",
            "document_type": "document",
            "folder": "1",
            "version": "pending_edits:1.1-2",
            "appendices": "none",
        },
    )

    body = html.unescape(answer.content.decode())
    assert answer.status_code == 409
    assert "The version changed since the dialog showed it" in body
    assert 'value="pending_edits:1.1-3" checked' in body
    with schema_context(migrated_tenant.number):
        assert Document.objects.count() == before


def test_refusals(migrated_tenant: Any, member_of: Any, source: Any, settings: Any) -> None:
    from access.models import AccessGroup, DocumentGroup
    from access.rights import Right
    from documents import archive, copying
    from documents.models import DocumentType, Folder

    settings.LANGUAGE_CODE = "en"
    reader, _, membership = member_of("a.reader@example.test")
    stranger, _, stranger_membership = member_of("a.stranger@example.test")
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(
            name="Readers", created_by=source.user, actor_kind="user"
        )
        group.grant(Right.VIEW_PENDING, by=source.user)
        group.add_member(membership, by=source.user)
        DocumentGroup.link(source.document, group, by=source.user)
        creators = AccessGroup.objects.create(
            name="Creators", created_by=source.user, actor_kind="user"
        )
        creators.grant(Right.CREATE_AND_EDIT, by=source.user)
        creators.add_member(stranger_membership, by=source.user)

    # A reader without *create and edit*; a creator who may not read the source.
    assert reader.get(f"/document/{source.document.number}/copy/").status_code == 404
    assert stranger.get(f"/document/{source.document.number}/copy/").status_code == 404
    # The document's page offers no copy: copying starts from the list (DL-0520).
    page = source.client.get(f"/document/{source.document.number}/").content.decode()
    assert f'href="/document/{source.document.number}/copy/"' not in page

    with schema_context(migrated_tenant.number):
        archive.archive(source.document, source.user)
        source.document.refresh_from_db()
        with pytest.raises(copying.CopyRefused) as refused:
            copying.copy_document(
                source.user,
                source.document,
                title="Synthetic copy",
                document_type=DocumentType.objects.get(code="document"),
                folder=Folder.objects.get(number=1),
                view="accepted",
                number="1.1",
                appendices=[],
            )
        assert refused.value.reason == "archived"
    archived_page = html.unescape(
        source.client.get(f"/document/{source.document.number}/").content.decode()
    )
    assert source.client.get(f"/document/{source.document.number}/copy/").status_code == 404
    assert f'href="/document/{source.document.number}/copy/"' not in archived_page


def test_administrators_read_the_source_on_info(
    migrated_tenant: Any, member_of: Any, source: Any, settings: Any
) -> None:
    from access.models import AccessGroup, DocumentGroup
    from access.rights import Right

    settings.LANGUAGE_CODE = "en"
    source.user.display_name = "Synthetic Copier"
    source.user.save()
    copy = _copy(migrated_tenant, source, "accepted", "1.1", appendices=[])
    reader, _, membership = member_of("a.reader@example.test")
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(
            name="Readers", created_by=source.user, actor_kind="user"
        )
        group.grant(Right.VIEW_PENDING, by=source.user)
        group.add_member(membership, by=source.user)
        DocumentGroup.link(copy, group, by=source.user)
    from audit.models import AuditEvent

    commit = AuditEvent.objects.get(action="document.copied").after["source_commit"]

    as_admin = html.unescape(source.client.get(f"/document/{copy.number}/info/").content.decode())
    as_reader = reader.get(f"/document/{copy.number}/info/").content.decode()

    assert "Copied from" in as_admin and "Copied from" not in as_reader
    copied = as_admin.split("Copied from", 1)[1].split("</dd>", 1)[0]
    assert f'href="/document/{source.document.number}/"' in copied
    assert "1.1" in copied and commit[:12] in copied and commit[:13] not in copied
    assert "Synthetic Copier" in copied
    # The date of the copy, in the display timezone, as the tab writes its dates.
    from zoneinfo import ZoneInfo

    from django.utils import formats, translation

    at = AuditEvent.objects.get(action="document.copied").at
    with translation.override("en"):
        day = formats.date_format(at.astimezone(ZoneInfo(settings.DISPLAY_TIMEZONE)), "j E Y")
    assert f"{day}, by Synthetic Copier" in copied


@pytest.mark.parametrize(
    "appendix", ["²", "9" * 5000, "invalid"], ids=["superscript", "past-digit-limit", "letters"]
)
def test_a_malformed_appendix_is_refused_as_input(
    migrated_tenant: Any, source: Any, settings: Any, appendix: str
) -> None:
    """A chosen appendix that is no number answers the dialog again with `400`, nothing written —
    a superscript digit and a number past the interpreter's digit limit included."""
    from documents.models import Document

    settings.LANGUAGE_CODE = "en"
    with schema_context(migrated_tenant.number):
        before = Document.objects.count()

    answer = source.client.post(
        f"/document/{source.document.number}/copy/",
        {
            "title": "Synthetic copy",
            "document_type": "document",
            "folder": "1",
            "version": "pending_edits:1.1-2",
            "appendices": "chosen",
            "appendix": appendix,
        },
    )

    assert answer.status_code == 400
    assert "Choose the appendices to copy." in html.unescape(answer.content.decode())
    with schema_context(migrated_tenant.number):
        assert Document.objects.count() == before


def test_an_unreadable_source_is_nothing_to_show(
    migrated_tenant: Any, source: Any, settings: Any, caplog: Any
) -> None:
    """A source whose repository cannot be read: the dialog and the copy answer *nothing to show*,
    logged for the operator, never a server error; nothing written. The same source read again
    once its repository is back."""
    from documents import gitstore
    from documents.models import Document

    settings.LANGUAGE_CODE = "en"
    client = source.client
    client.raise_request_exception = False
    number = source.document.number
    path = gitstore.repository_path(migrated_tenant.number, number)
    with schema_context(migrated_tenant.number):
        before = Document.objects.count()
    parked = path.with_name(path.name + ".parked")
    path.rename(parked)
    try:
        dialog = client.get(f"/document/{number}/copy/")
        posted = client.post(
            f"/document/{number}/copy/",
            {
                "title": "Synthetic copy",
                "document_type": "document",
                "folder": "1",
                "version": "pending_edits:1.1-2",
                "appendices": "none",
            },
        )
    finally:
        parked.rename(path)

    assert dialog.status_code == 404 and posted.status_code == 404
    assert "could not be read" in caplog.text
    with schema_context(migrated_tenant.number):
        assert Document.objects.count() == before
    assert client.get(f"/document/{number}/copy/").status_code == 200


def test_a_source_whose_declarations_do_not_read_is_refused(
    migrated_tenant: Any, source: Any, settings: Any
) -> None:
    """A source version whose `entities.yaml` does not read cannot be copied: the dialog again,
    *cannot be read*, nothing written — never a server error."""
    from documents.models import Document

    settings.LANGUAGE_CODE = "en"
    _commit(
        migrated_tenant,
        source.document,
        source.user,
        _body("The pending synthetic text, broken."),
        files={"entities.yaml": b"- kind: [not a declaration\n"},
    )
    with schema_context(migrated_tenant.number):
        before = Document.objects.count()

    answer = source.client.post(
        f"/document/{source.document.number}/copy/",
        {
            "title": "Synthetic copy",
            "document_type": "document",
            "folder": "1",
            "version": "pending_edits:1.1-3",
            "appendices": "none",
        },
    )

    assert answer.status_code == 400
    assert "This version cannot be read, so it cannot be copied." in html.unescape(
        answer.content.decode()
    )
    with schema_context(migrated_tenant.number):
        assert Document.objects.count() == before


def test_a_copy_carries_the_title_page_text_of_the_version_copied(
    migrated_tenant: Any, member_of: Any, repo_root: Any, tmp_path: Any
) -> None:
    """DL-0478: the copy's first tree holds the title-page text as it stood at the version copied,
    not the head's, and the copy's exports print it on its title page."""
    import zipfile

    from pypdf import PdfReader

    from access.models import AccessGroup, DocumentGroup
    from access.rights import Right
    from documents import bundle, gitstore, services
    from documents.locks import document_lock
    from documents.models import DocumentType, Folder
    from editions import services as editions
    from identity.models import Language
    from rendering.export import compose, docx, furniture, job, pdf
    from review import services as review

    Language.objects.get_or_create(code="uk", defaults={"label": "uk", "actor_kind": "system"})
    _, user, membership = member_of("the.copier@example.test", is_tenant_admin=True)
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(
            name="Copiers (synthetic example)", created_by=user, actor_kind="user"
        )
        for right in Right:
            group.grant(right, by=user)
        group.add_member(membership, by=user)
        kind, root = DocumentType.objects.get(code="document"), Folder.objects.get(number=1)
        document = services.create_document(user, "Synthetic register policy", "uk", kind, root)
        DocumentGroup.link(document, group, by=user)

    def with_text(text: str, body: str) -> None:
        number = migrated_tenant.number
        with schema_context(number):
            repo = gitstore.open_repository(number, document.number)
            with document_lock(number, document.number):
                head = gitstore.head(repo)
                assert head is not None
                frontmatter, _ = bundle.parse(gitstore.read(repo, "document.md", head).decode())
                changed = dataclasses.replace(frontmatter, title_page=True, title_page_text=text)
                from documents.identity import identity_for

                sha = gitstore.commit(
                    repo,
                    {"document.md": bundle.render(changed, body).encode()},
                    identity_for(user),
                    "Synthetic edit",
                    gitstore.Kind.REVIEWER_EDIT,
                )
                services.derive_version(document, gitstore.commit_at(repo, sha), user)

    with_text("Register entry: EX-1 (synthetic)", "# Terms\n\nThe first synthetic text.\n")
    with schema_context(migrated_tenant.number):
        review.accept(document, user)
        editions.freeze(document, user, "Synthetic reason")
        editions.make_canonical(document, user)
    with_text("Register entry: EX-2 (synthetic)", "# Terms\n\nThe later synthetic text.\n")

    copy = _copy(migrated_tenant, SimpleNamespace(user=user, document=document), "canonical", "1.0")

    repo = gitstore.open_repository(migrated_tenant.number, copy.number)
    head = str(next(gitstore.history(repo)).id)
    frontmatter, body = bundle.parse(gitstore.read(repo, "document.md", head).decode())
    assert frontmatter.title_page_text == "Register entry: EX-1 (synthetic)"
    with schema_context(migrated_tenant.number):
        shown = SimpleNamespace(document=copy, view="accepted")
        page = compose._page(shown, frontmatter, "<p>The first synthetic text.</p>", "h", "0.0")
        pdf.write(
            page,
            tmp_path / "copy.pdf",
            stylesheets=[job.STYLESHEET.read_text(encoding="utf-8"), furniture.pdf_css()],
            read_image=lambda path: b"",
        )
        docx.write(page, tmp_path / "copy.docx")
    first = PdfReader(str(tmp_path / "copy.pdf")).pages[0].extract_text()
    assert "Register entry: EX-1 (synthetic)" in first
    with zipfile.ZipFile(tmp_path / "copy.docx") as produced:
        words = produced.read("word/document.xml").decode()
    assert "Register entry: EX-1 (synthetic)" in words and "EX-2" not in words


def _listed(migrated_tenant: Any, source: Any, count: int, right: Any) -> tuple[Any, list[Any]]:
    """`count` more documents in the root folder and a group holding `right` linked to each."""
    from access.models import AccessGroup, DocumentGroup
    from documents import services
    from documents.models import Document, DocumentType, Folder

    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(
            name=f"List readers {Document.objects.count()} (synthetic example)",
            created_by=source.user,
            actor_kind="user",
        )
        group.grant(right, by=source.user)
        made = []
        for n in range(count):
            document = services.create_document(
                source.user,
                f"Synthetic listed document {n}",
                "uk",
                DocumentType.objects.get(code="document"),
                Folder.objects.get(number=1),
            )
            DocumentGroup.link(document, group, by=source.user)
            made.append(document)
    return group, made


def _joined(migrated_tenant: Any, source: Any, membership: Any, *groups: Any) -> None:
    with schema_context(migrated_tenant.number):
        for group in groups:
            group.add_member(membership, by=source.user)


def test_copy_on_the_list(
    migrated_tenant: Any,
    member_of: Any,
    source: Any,
    settings: Any,
    django_assert_num_queries: Any,
) -> None:
    """⧉ on a row whose document has a version the reader may see, to a holder of *create and
    edit*; none on a row whose record cannot be read, which shows no version; no column for a
    reader who may not create (DL-0520). The offer is read once per list, never per row."""
    from access.models import AccessGroup
    from access.rights import Right
    from documents import gitstore

    settings.LANGUAGE_CODE = "en"
    readable, (seen,) = _listed(migrated_tenant, source, 1, Right.VIEW_PENDING)
    blind, (unseen,) = _listed(migrated_tenant, source, 1, Right.VIEW_PENDING)
    creator, _, creating = member_of("list.creator@example.test")
    reader, _, reading = member_of("list.reader@example.test")
    with schema_context(migrated_tenant.number):
        creators = AccessGroup.objects.create(
            name="List creators (synthetic example)", created_by=source.user, actor_kind="user"
        )
        creators.grant(Right.CREATE_AND_EDIT, by=source.user)
    _joined(migrated_tenant, source, creating, creators, readable, blind)
    _joined(migrated_tenant, source, reading, readable, blind)

    # Its repository away: listed, its versions unread, nothing to copy.
    path = gitstore.repository_path(migrated_tenant.number, unseen.number)
    parked = path.with_name(path.name + ".parked")
    path.rename(parked)
    try:
        page = creator.get("/folder/1/").content.decode()
    finally:
        parked.rename(path)
    rows = dict(re.findall(r'<tr class="document" data-number="(\d+)">(.*?)</tr>', page, re.S))
    cell = rows[str(seen.number)].split('<td class="copy">', 1)[1]
    assert f'<a class="icon" href="/document/{seen.number}/copy/"' in cell
    assert str(unseen.number) in rows and "/copy/" not in rows[str(unseen.number)]
    assert '<th class="copy">' in page

    listed = reader.get("/folder/1/").content.decode()
    assert "/copy/" not in listed and '<th class="copy">' not in listed

    # Ten copyable rows cost what one does.
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as one:
        creator.get("/folder/1/")
    more, _ = _listed(migrated_tenant, source, 9, Right.VIEW_PENDING)
    _joined(migrated_tenant, source, creating, more)
    with django_assert_num_queries(len(one.captured_queries)):
        ten = creator.get("/folder/1/").content.decode()
    # The nine new rows, the first, and the second now its repository is back.
    assert ten.count("/copy/") == 11


def test_no_copy_on_the_page(migrated_tenant: Any, source: Any, settings: Any) -> None:
    """The document's page offers neither copying nor comparing with another document: both
    start from the list (DL-0520)."""
    settings.LANGUAGE_CODE = "en"
    number = source.document.number
    page = html.unescape(source.client.get(f"/document/{number}/").content.decode())
    assert f"/document/{number}/copy/" not in page
    assert "with=" not in page and "Compare with another document" not in page
    assert "Copy" not in re.sub(r"<[^>]*>", " ", page)
