"""The commit of a draft writes every path the draft stages beside `document.md` — the declared
`entities.yaml`, the images the texts reference, the attachments' operations, the appendices — in
one commit (ADR-0005, DL-0175, DL-0439, DL-0440). Invented English; people are synthetic examples;
image bytes are placeholders, since the commit reads no image's content."""

from __future__ import annotations

import hashlib
from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

BODY = "The first synthetic sentence.\n\nThe second synthetic sentence.\n"
APPENDIX = [{"number": 1, "title": "Synthetic appendix"}]


def name(data: bytes) -> str:
    return f"images/{hashlib.sha256(data).hexdigest()}.png"


def picture(data: bytes, words: str = "A synthetic plan") -> str:
    return f"![{words}]({name(data)})\n"


def held(client: Any, tenant: Any, document: Any) -> tuple[Any, Any]:
    from editing.models import Draft, Hold

    client.post(f"/document/{document.number}/edit/take/")
    with schema_context(tenant.number):
        hold = Hold.objects.get(document=document, released_at__isnull=True)
        return hold, Draft.objects.get(hold=hold)


def write(tenant: Any, draft: Any, **content: Any) -> None:
    with schema_context(tenant.number):
        draft.refresh_from_db()
        draft.content = {**draft.content, **content}
        draft.save()


def stage(
    tenant: Any, draft: Any, kind: str, path: str, operation: str, data: bytes | None
) -> None:
    from django.utils import timezone

    from editing.models import DraftFile

    with schema_context(tenant.number):
        DraftFile.objects.create(
            draft_id=draft.pk,
            kind=kind,
            path=path,
            operation=operation,
            content=data,
            file_name=path.rsplit("/", 1)[-1],
            sha256=hashlib.sha256(data).hexdigest() if data is not None else "",
            at=timezone.now(),
        )


def repository(tenant: Any, document: Any) -> Any:
    from documents import gitstore

    return gitstore.open_repository(tenant.number, document.number)


def present(repo: Any, path: str, sha: str) -> bool:
    from documents import gitstore

    try:
        gitstore.read(repo, path, sha)
    except KeyError:
        return False
    return True


def test_one_commit_writes_every_staged_path(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    commit_version: Any,
    queued_authorship: list[Any],
) -> None:
    from documents import gitstore
    from editing import services

    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    before = commit_version(document, author, BODY, files={"attachments/1": b"an old attachment"})
    hold, draft = held(client, migrated_tenant, document)
    kept, dropped = b"a synthetic image kept", b"a synthetic image dropped"
    appendix = "# Synthetic appendix\n\nAn appendix sentence.\n"
    write(
        migrated_tenant,
        draft,
        **{
            "document.md": BODY + "\n" + picture(kept),
            "appendices/1.md": appendix,
            "frontmatter": {**draft.content["frontmatter"], "appendices": APPENDIX},
        },
    )
    stage(migrated_tenant, draft, "image", name(kept), "add", kept)
    stage(migrated_tenant, draft, "image", name(dropped), "add", dropped)
    stage(migrated_tenant, draft, "attachment", "attachments/2", "add", b"a new attachment")
    stage(migrated_tenant, draft, "attachment", "attachments/1", "remove", None)

    with schema_context(migrated_tenant.number):
        version = services.commit_draft(hold, author, "Files and an appendix")
        repo = repository(migrated_tenant, document)
        head = gitstore.head(repo)
        assert version.commit_sha == head
        assert [str(p.id) for p in gitstore.commit_at(repo, head).parents] == [before.commit_sha]
        assert gitstore.read(repo, name(kept), head) == kept
        assert not present(repo, name(dropped), head)
        assert gitstore.read(repo, "attachments/2", head) == b"a new attachment"
        assert not present(repo, "attachments/1", head)
        assert gitstore.read(repo, "appendices/1.md", head).decode() == appendix
        assert picture(kept) in gitstore.read(repo, "document.md", head).decode()
        assert gitstore.listing(repo, "images", head) == [name(kept).removeprefix("images/")]


def test_an_unreferenced_image_leaves_the_tree(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    commit_version: Any,
    queued_authorship: list[Any],
) -> None:
    from documents import gitstore
    from editing import services

    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    body_image, appendix_image = b"an image of the body", b"an image of the appendix"
    commit_version(
        document,
        author,
        BODY + "\n" + picture(body_image),
        files={
            name(body_image): body_image,
            name(appendix_image): appendix_image,
            "appendices/1.md": "An appendix sentence.\n\n" + picture(appendix_image),
        },
        appendices=APPENDIX,
    )
    hold, draft = held(client, migrated_tenant, document)
    write(migrated_tenant, draft, **{"document.md": BODY})

    with schema_context(migrated_tenant.number):
        version = services.commit_draft(hold, author, "The body's image removed")
        repo = repository(migrated_tenant, document)
        assert not present(repo, name(body_image), version.commit_sha)
        assert gitstore.read(repo, name(appendix_image), version.commit_sha) == appendix_image


def test_nothing_changed_counts_files_and_entities(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    commit_version: Any,
    queued_authorship: list[Any],
) -> None:
    from documents import entities, gitstore
    from editing import services

    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    image = b"an image the head holds"
    commit_version(
        document,
        author,
        BODY + "\n" + picture(image),
        files={name(image): image, "attachments/1": b"an attachment the head holds"},
    )
    declared = entities.dump([entities.Declared("role", "approver", "the approver")])

    hold, draft = held(client, migrated_tenant, document)
    write(migrated_tenant, draft, **{"entities.yaml": declared})
    with schema_context(migrated_tenant.number):
        first = services.commit_draft(hold, author, "An entity declared")
        repo = repository(migrated_tenant, document)
        assert gitstore.read(repo, "entities.yaml", first.commit_sha).decode() == declared

    hold, draft = held(client, migrated_tenant, document)
    stage(migrated_tenant, draft, "attachment", "attachments/2", "add", b"a new attachment")
    with schema_context(migrated_tenant.number):
        second = services.commit_draft(hold, author, "An attachment added")
        assert gitstore.read(repo, "attachments/2", second.commit_sha) == b"a new attachment"

    hold, draft = held(client, migrated_tenant, document)
    stage(migrated_tenant, draft, "image", name(image), "add", image)
    stage(
        migrated_tenant,
        draft,
        "attachment",
        "attachments/1",
        "add",
        b"an attachment the head holds",
    )
    stage(migrated_tenant, draft, "attachment", "attachments/9", "remove", None)
    with schema_context(migrated_tenant.number), pytest.raises(services.NothingChanged):
        services.commit_draft(hold, author, "Nothing new")
    with schema_context(migrated_tenant.number):
        assert gitstore.head(repo) == second.commit_sha


def test_a_missing_image_is_refused_by_its_file_and_line(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    commit_version: Any,
    queued_authorship: list[Any],
    settings: Any,
) -> None:
    from documents import gitstore
    from editing import services

    settings.LANGUAGE_CODE = "en"
    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    commit_version(document, author, BODY, appendices=[{"number": 2, "title": "Synthetic"}])
    hold, draft = held(client, migrated_tenant, document)
    in_body, in_appendix = b"an image nobody uploaded", b"another image nobody uploaded"
    write(
        migrated_tenant,
        draft,
        **{
            "document.md": BODY + "\n" + picture(in_body),
            "appendices/2.md": "An appendix sentence.\n\n" + picture(in_appendix),
        },
    )
    expected = [
        services.MissingImage(5, "image-missing", "document.md"),
        services.MissingImage(3, "image-missing", "appendices/2.md"),
    ]
    with schema_context(migrated_tenant.number):
        repo = repository(migrated_tenant, document)
        head = gitstore.head(repo)
        for act in (
            lambda: services.finish(hold),
            lambda: services.my_edits(hold),
            lambda: services.commit_draft(hold, author, "Missing images"),
        ):
            with pytest.raises(services.MissingImages) as refused:
                act()
            assert refused.value.refusals == expected
        assert gitstore.head(repo) == head

    page = client.get(f"/document/{document.number}/edit/finish/").content.decode()
    assert "line 5: an image the document does not hold" in page
    # An appendix is named by its title, and a missing image is not refused text (DL-11-004).
    assert "appendix «Synthetic», line 3: an image the document does not hold" in page
    assert "The draft refers to an image the document does not hold" in page
    assert "text the editor does not accept" not in page


def test_undeclared_spans_are_declared_at_commit(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    commit_version: Any,
    queued_authorship: list[Any],
) -> None:
    from documents import entities, gitstore
    from editing import services

    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    commit_version(document, author, BODY, appendices=APPENDIX)
    hold, draft = held(client, migrated_tenant, document)
    write(
        migrated_tenant,
        draft,
        **{
            "document.md": (
                "The request goes to [the approver]{.role #approver}.\n"
                "[The approving officer]{.role #approver} signs it.\n\n"
                "[The clerk]{.role} files it.\n"
            ),
            "appendices/1.md": "[The auditor]{.role #auditor} reads it.\n",
        },
    )

    with schema_context(migrated_tenant.number):
        version = services.commit_draft(hold, author, "Roles marked")
        repo = repository(migrated_tenant, document)
        declared = gitstore.read(repo, "entities.yaml", version.commit_sha).decode()
    assert entities.parse(declared) == [
        entities.Declared("role", "approver", "the approver"),
        entities.Declared("role", "auditor", "The auditor"),
    ]


@pytest.mark.parametrize(
    "row",
    [
        ("attachment", "document.md", "remove", None),
        ("attachment", "appendices/1.md", "add", b"an appendix from a row"),
        ("attachment", "images/" + "c" * 64 + ".png", "add", b"bytes past the checks"),
        ("image", "images/x.svg", "add", b"<svg/>"),
        ("image", "images/" + "d" * 64 + ".png", "add", b"bytes whose hash is not the name"),
    ],
)
def test_a_staged_row_outside_its_place_is_refused(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    commit_version: Any,
    queued_authorship: list[Any],
    row: tuple[str, str, str, bytes | None],
) -> None:
    """The commit writes an attachment only under `attachments/` and an image only at the name
    its content's hash gives (DL-0439); any other row is a fault, and nothing is committed."""
    from documents import gitstore
    from editing import services

    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    commit_version(document, author, BODY)
    hold, draft = held(client, migrated_tenant, document)
    kind, path, operation, data = row
    if kind == "image":
        write(migrated_tenant, draft, **{"document.md": BODY + f"\n![A synthetic plan]({path})\n"})
    stage(migrated_tenant, draft, kind, path, operation, data)
    with schema_context(migrated_tenant.number):
        repo = repository(migrated_tenant, document)
        head = gitstore.head(repo)
        with pytest.raises(ValueError):
            services.commit_draft(hold, author, "A row out of place")
        assert gitstore.head(repo) == head


def test_declarations_over_the_cap_are_refused(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    commit_version: Any,
    queued_authorship: list[Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The declared `entities.yaml` is held to the size the body is held to: a commit that would
    write more is refused as too large, as the body is."""
    from documents import entities
    from editing import services

    monkeypatch.setattr(entities, "MAX_BYTES", 200)
    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    commit_version(document, author, BODY)
    hold, draft = held(client, migrated_tenant, document)
    marked = "".join(f"[Role {n}]{{.role #role-{n}}} acts.\n" for n in range(8))
    write(migrated_tenant, draft, **{"document.md": marked})
    with schema_context(migrated_tenant.number), pytest.raises(services.DraftRefused) as refused:
        services.commit_draft(hold, author, "Many roles")
    assert [r.code for r in refused.value.refusals] == ["too-large"]
