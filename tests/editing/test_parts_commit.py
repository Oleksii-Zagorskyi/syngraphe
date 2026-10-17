"""A draft's parts committed with its text (ADR-0005, DL-0168, DL-0175): the lists, each
appendix held to its rules and normalised, the staged files, a part-only session, the rights
decided again at the commit, a stopped part-only finish, and the frontmatter kinds another app may
register (DL-0463). Every title, file name and person is a synthetic example; text is invented
English and file bytes are placeholders."""

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
FORM = b"a synthetic spreadsheet"


def held(tenant: Any, document: Any, user: Any) -> tuple[Any, Any]:
    from editing import holds
    from editing.models import Draft

    with schema_context(tenant.number):
        hold = holds.take(document, user)
        return hold, Draft.objects.get(hold=hold)


def write(tenant: Any, draft: Any, **content: Any) -> None:
    with schema_context(tenant.number):
        draft.refresh_from_db()
        draft.content = {**draft.content, **content}
        draft.save()


def tree(tenant: Any, document: Any) -> tuple[Any, str]:
    from documents import gitstore

    repo = gitstore.open_repository(tenant.number, document.number)
    head = gitstore.head(repo)
    assert head is not None
    return repo, head


def read(tenant: Any, document: Any, path: str) -> bytes | None:
    from documents import gitstore

    repo, head = tree(tenant, document)
    try:
        return gitstore.read(repo, path, head)
    except KeyError:
        return None


def frontmatter(tenant: Any, document: Any) -> Any:
    from documents import bundle

    text = read(tenant, document, "document.md")
    assert text is not None
    return bundle.parse(text.decode("utf-8"))[0]


def holder_of(member_of: Any, new_document: Any, link_group: Any, *rights: Any) -> Any:
    """A document created by an author, and a holder of *edit* and `rights` through a group."""
    from access.rights import Right

    _, author, _ = member_of("the.author@example.test")
    _, holder, own = member_of("the.holder@example.test")
    document = new_document(author)
    group = link_group(document, [Right.EDIT, *rights], [own], author)
    return document, holder, author, group


def test_parts_are_committed_with_the_text(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    queued_authorship: list[Any],
) -> None:
    from access.rights import Right
    from documents.parts import lists_at
    from editing import parts, services

    document, holder, *_ = holder_of(
        member_of, new_document, link_group, Right.CREATE_APPENDIX, Right.UPLOAD_ATTACHMENT
    )
    hold, draft = held(migrated_tenant, document, holder)
    with schema_context(migrated_tenant.number):
        appendix = parts.create_appendix(document, holder, title="Appendix one (example)")
        form = parts.upload_attachment(
            document, holder, title="Form (example)", file_name="form.xlsx", data=FORM
        )
        parts.rename_attachment(document, holder, form, title="Request form (example)")
    typed = "# Appendix one (example)\n\nThe first appendix sentence. The second one follows.\n"
    write(migrated_tenant, draft, **{parts.appendix_key(appendix): typed})

    with schema_context(migrated_tenant.number):
        version = services.commit_draft(hold, holder, "Parts added")
        listed = frontmatter(migrated_tenant, document)
        assert listed.appendices == [{"number": appendix, "title": "Appendix one (example)"}]
        assert listed.attachments == [
            {
                "number": form,
                "title": "Request form (example)",
                "file_name": "form.xlsx",
                "sha256": hashlib.sha256(FORM).hexdigest(),
                "bytes": len(FORM),
            }
        ]
        # Normalised as the body is: one sentence a line.
        assert read(migrated_tenant, document, f"appendices/{appendix}.md") == (
            b"# Appendix one (example)\n\nThe first appendix sentence.\nThe second one follows.\n"
        )
        assert read(migrated_tenant, document, f"attachments/{form}") == FORM
        assert lists_at(version) == (listed.appendices, listed.attachments)


def test_a_reorder_alone_is_a_change(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    queued_authorship: list[Any],
) -> None:
    from documents.models import Version
    from editing import parts, services

    document, holder, author, _ = holder_of(member_of, new_document, link_group)
    entries = [
        {
            "number": n,
            "title": f"Form {n} (example)",
            "file_name": f"form-{n}.txt",
            "sha256": hashlib.sha256(FORM + bytes([n])).hexdigest(),
            "bytes": len(FORM) + 1,
        }
        for n in (1, 2)
    ]
    before = commit_version(
        document,
        author,
        BODY,
        files={f"attachments/{n}": FORM + bytes([n]) for n in (1, 2)},
        attachments=entries,
    )
    hold, _ = held(migrated_tenant, document, holder)
    with schema_context(migrated_tenant.number):
        parts.reorder_attachments(document, holder, [2, 1])
        assert services.finish(hold).number
        version = services.commit_draft(hold, holder, "Forms reordered")
        assert version.commit_sha != before.commit_sha
        assert Version.objects.filter(document=document).count() == 3
        assert [e["number"] for e in frontmatter(migrated_tenant, document).attachments] == [2, 1]
    assert read(migrated_tenant, document, "document.md").decode().endswith(BODY)  # type: ignore[union-attr]


def test_a_deleted_appendix_leaves_the_tree(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    queued_authorship: list[Any],
) -> None:
    from access.rights import Right
    from editing import parts, services

    document, holder, author, _ = holder_of(
        member_of, new_document, link_group, Right.DELETE_APPENDIX
    )
    commit_version(
        document,
        author,
        BODY,
        files={"appendices/1.md": b"# Appendix one (example)\n"},
        appendices=[{"number": 1, "title": "Appendix one (example)"}],
    )
    hold, _ = held(migrated_tenant, document, holder)
    with schema_context(migrated_tenant.number):
        parts.delete_appendix(document, holder, 1)
        services.commit_draft(hold, holder, "Appendix deleted")
        assert read(migrated_tenant, document, "appendices/1.md") is None
        assert frontmatter(migrated_tenant, document).appendices == []


def test_a_right_lost_since_staging_refuses_the_commit(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    queued_authorship: list[Any],
) -> None:
    from access.rights import Right
    from editing import parts, services
    from editing.models import Draft

    document, holder, author, group = holder_of(
        member_of, new_document, link_group, Right.UPLOAD_ATTACHMENT
    )
    hold, draft = held(migrated_tenant, document, holder)
    with schema_context(migrated_tenant.number):
        parts.upload_attachment(
            document, holder, title="Budget model (example)", file_name="budget.xlsx", data=FORM
        )
        group.revoke(Right.UPLOAD_ATTACHMENT, by=author)
        _, head = tree(migrated_tenant, document)
        with pytest.raises(services.PartRightLost) as lost:
            services.commit_draft(hold, holder, "An upload")
        assert lost.value.parts == ["Budget model (example)"]
        assert tree(migrated_tenant, document)[1] == head
        assert Draft.objects.filter(pk=draft.pk).exists()


@pytest.mark.parametrize(
    "text, refusal",
    [
        ("A sentence before the heading.\n\n# Appendix one (example)\n", "heading"),
        ("# Appendix one (example)\n\n# A second heading\n", "heading"),
        ("# Appendix one (example)\n\n<div>Raw markup.</div>\n", "construct"),
        ("# Appendix one (example)\n\n" + "A synthetic sentence. " * 18_200 + "\n", "too-large"),
    ],
)
def test_each_appendix_is_held_to_the_rules(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    text: str,
    refusal: str,
) -> None:
    from editing import services

    document, holder, author, _ = holder_of(member_of, new_document, link_group)
    commit_version(
        document,
        author,
        BODY,
        files={"appendices/1.md": b"# Appendix one (example)\n"},
        appendices=[{"number": 1, "title": "Appendix one (example)"}],
    )
    hold, draft = held(migrated_tenant, document, holder)
    write(migrated_tenant, draft, **{"appendices/1.md": text})
    if refusal == "too-large":
        assert len(text.encode()) > 400_000

    with schema_context(migrated_tenant.number):
        for act in (
            lambda: services.finish(hold),
            lambda: services.commit_draft(hold, holder, "Refused"),
        ):
            if refusal == "heading":
                with pytest.raises(services.AppendixHeading) as heading:
                    act()
                assert heading.value.title == "Appendix one (example)"
            else:
                with pytest.raises(services.DraftRefused) as refused:
                    act()
                assert refused.value.appendix == "Appendix one (example)"
                codes = [r.code for r in refused.value.refusals]
                assert ("too-large" in codes) == (refusal == "too-large")


def test_a_stopped_part_only_finish_is_recognised(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    queued_authorship: list[Any],
) -> None:
    from access.rights import Right
    from documents.models import Version
    from editing import holds, numbering, parts, services

    document, holder, *_ = holder_of(member_of, new_document, link_group, Right.UPLOAD_ATTACHMENT)
    hold, _ = held(migrated_tenant, document, holder)
    with schema_context(migrated_tenant.number):
        parts.upload_attachment(
            document, holder, title="Form (example)", file_name="form.txt", data=FORM
        )
        with pytest.raises(services.InjectedFault):
            services.commit_draft(hold, holder, "A form", fault_at=1)
        _, stopped = tree(migrated_tenant, document)
        offered = services.finish(hold).number
        version = services.commit_draft(hold, holder, "A form")
        assert version.commit_sha == stopped == tree(migrated_tenant, document)[1]
        assert offered == numbering.number_of(document, version)
        assert Version.objects.filter(document=document, commit_sha=stopped).count() == 1
        assert holds.open_hold(document) is None


def test_a_registered_frontmatter_key_is_a_draft_change(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    frontmatter_kinds: dict[str, Any],
    queued_authorship: list[Any],
) -> None:
    from audit.models import AuditEvent
    from editing import parts, services

    parts.register_frontmatter_kind(
        parts.FrontmatterKind(
            "title_page",
            lambda value: isinstance(value, bool),
            lambda older, newer: "title page on" if newer else "title page off",
        )
    )
    document, holder, *_ = holder_of(member_of, new_document, link_group)
    hold, draft = held(migrated_tenant, document, holder)
    with schema_context(migrated_tenant.number):
        parts.stage_frontmatter(document, holder, "title_page", True)
        draft.refresh_from_db()
        assert draft.content["frontmatter"]["title_page"] is True
        with pytest.raises(parts.PartRefused) as unknown:
            parts.stage_frontmatter(document, holder, "language", "en")
        assert unknown.value.reason == "unknown_key"
        with pytest.raises(parts.PartRefused) as bad:
            parts.stage_frontmatter(document, holder, "title_page", "yes")
        assert bad.value.reason == "bad_value"
        services.commit_draft(hold, holder, "A title page")
        assert frontmatter(migrated_tenant, document).title_page is True
    staged = AuditEvent.objects.get(action="frontmatter.staged")
    assert staged.after == {"number": document.number, "key": "title_page", "value": True}
    with pytest.raises(ValueError):
        parts.register_frontmatter_kind(
            parts.FrontmatterKind("appendices", lambda value: True, lambda o, n: "")
        )
    assert list(frontmatter_kinds) == ["title_page"]


def test_an_appendixs_images_are_the_documents(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    queued_authorship: list[Any],
) -> None:
    from django.utils import timezone

    from editing import services
    from editing.models import DraftFile

    document, holder, author, _ = holder_of(member_of, new_document, link_group)
    listed = [
        {"number": 1, "title": "Appendix one (example)"},
        {"number": 2, "title": "Appendix two (example)"},
    ]
    commit_version(
        document,
        author,
        BODY,
        files={
            "appendices/1.md": b"# Appendix one (example)\n",
            "appendices/2.md": b"# Appendix two (example)\n",
        },
        appendices=listed,
    )
    image = b"a synthetic picture"
    path = f"images/{hashlib.sha256(image).hexdigest()}.png"
    hold, draft = held(migrated_tenant, document, holder)
    with schema_context(migrated_tenant.number):
        DraftFile.objects.create(
            draft=draft,
            kind="image",
            path=path,
            operation="add",
            content=image,
            file_name="plan.png",
            sha256=hashlib.sha256(image).hexdigest(),
            at=timezone.now(),
        )
    missing = f"images/{'e' * 64}.png"
    write(
        migrated_tenant,
        draft,
        **{
            "appendices/1.md": f"# Appendix one (example)\n\n![A missing plan]({missing})\n",
            "appendices/2.md": f"# Appendix two (example)\n\n![A plan]({path})\n",
        },
    )
    with schema_context(migrated_tenant.number):
        _, head = tree(migrated_tenant, document)
        with pytest.raises(services.MissingImages) as refused:
            services.commit_draft(hold, holder, "Images")
        assert refused.value.refusals == [
            services.MissingImage(3, "image-missing", "appendices/1.md")
        ]
        assert tree(migrated_tenant, document)[1] == head
    write(migrated_tenant, draft, **{"appendices/1.md": "# Appendix one (example)\n"})
    with schema_context(migrated_tenant.number):
        services.commit_draft(hold, holder, "Images")
        assert read(migrated_tenant, document, path) == image


def test_only_known_keys_and_listed_appendices_are_written(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    frontmatter_kinds: dict[str, Any],
    queued_authorship: list[Any],
) -> None:
    from editing import parts, services

    with pytest.raises(ValueError):
        parts.register_frontmatter_kind(
            parts.FrontmatterKind("colour", lambda value: True, lambda o, n: "")
        )
    document, holder, *_ = holder_of(member_of, new_document, link_group)
    hold, draft = held(migrated_tenant, document, holder)
    write(
        migrated_tenant,
        draft,
        **{"document.md": BODY, "appendices/9.md": "# Not listed (example)\n"},
    )
    with schema_context(migrated_tenant.number):
        services.commit_draft(hold, holder, "A body")
        assert read(migrated_tenant, document, "appendices/9.md") is None


@pytest.mark.parametrize("same", [True, False])
def test_a_revert_is_exempt_only_for_what_it_staged(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    queued_authorship: list[Any],
    same: bool,
) -> None:
    """A revert's inverse needs *accept* alone at the commit (DL-0446) — the file it staged, and
    no other: a later replacement of the same part needs its own right."""
    from django.db import transaction

    from access.rights import Right
    from editing import parts, services
    from editing.models import Draft

    document, reviewer, author, _ = holder_of(member_of, new_document, link_group, Right.ACCEPT)
    before, after = b"the base's synthetic form", b"the run's synthetic form"

    def entry(data: bytes) -> dict[str, Any]:
        return {
            "number": 2,
            "title": "Form (example)",
            "file_name": "form.txt",
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
        }

    commit_version(
        document, author, BODY, files={"attachments/2": before}, attachments=[entry(before)]
    )
    commit_version(
        document, author, BODY, files={"attachments/2": after}, attachments=[entry(after)]
    )
    hold, draft = held(migrated_tenant, document, reviewer)
    staged = before if same else b"a third synthetic form"
    with schema_context(migrated_tenant.number), transaction.atomic():
        locked = Draft.objects.select_for_update().get(pk=draft.pk)
        parts.apply_to_draft(
            locked, "replace_attachment", number=2, file_name="form.txt", data=staged
        )
        locked.content = {
            **locked.content,
            "revert": [
                {
                    "part": "attachment:2",
                    "change": "replaced",
                    "head": tree(migrated_tenant, document)[1],
                    "staged": entry(before),
                }
            ],
        }
        locked.save()
    with schema_context(migrated_tenant.number):
        if same:
            services.commit_draft(hold, reviewer, "Reverted")
            assert read(migrated_tenant, document, "attachments/2") == before
        else:
            with pytest.raises(services.PartRightLost):
                services.commit_draft(hold, reviewer, "Reverted")


def test_a_listed_appendix_without_its_file_is_named(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
) -> None:
    """A head listing an appendix whose file is gone — the reconciler's `part_missing` — reads as
    the empty text, which the appendix's rules name, never an error page."""
    from editing import services

    document, holder, author, _ = holder_of(member_of, new_document, link_group)
    commit_version(
        document, author, BODY, appendices=[{"number": 1, "title": "Appendix one (example)"}]
    )
    hold, _ = held(migrated_tenant, document, holder)
    with schema_context(migrated_tenant.number), pytest.raises(services.AppendixHeading):
        services.finish(hold)
