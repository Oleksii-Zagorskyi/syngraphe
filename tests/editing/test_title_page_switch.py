"""The title page switched in a draft (DL-0463, DL-0168): the holder's change of the frontmatter,
staged, listed among the run's changes, committed with the run, seen by the reviewer, kept by an
undo as a title is. People are synthetic examples; the text is invented."""

from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

BODY = "# Purpose\n\nThe first synthetic sentence.\n"


@pytest.fixture(autouse=True)
def english(settings: Any) -> None:
    settings.LANGUAGE_CODE = "en"


def scene(
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    linked: Any = None,
    rights: Any = None,
) -> Any:
    """A document with its title page off, held by an editor; a reviewer holding *accept*;
    `linked(document, author)` called before the hold, a document's groups being fixed while
    it is held."""
    from access.rights import Right

    _, author, _ = member_of("the.author@example.test")
    client, holder, own = member_of("the.holder@example.test")
    reviewer_client, reviewer, theirs = member_of("the.reviewer@example.test")
    document = new_document(author)
    link_group(document, rights or [Right.EDIT], [own], author)
    link_group(document, [Right.ACCEPT, Right.VIEW_PENDING], [theirs], author)
    commit_version(document, author, BODY)
    if linked is not None:
        linked(document, author)
    assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
    return SimpleNamespace(
        client=client,
        holder=holder,
        document=document,
        reviewer=reviewer,
        reviewer_client=reviewer_client,
    )


def flat(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def draft_frontmatter(tenant: Any, document: Any) -> dict[str, Any]:
    from editing import holds
    from editing.models import Draft

    with schema_context(tenant.number):
        return dict(Draft.objects.get(hold=holds.open_hold(document)).content["frontmatter"])


def head_frontmatter(tenant: Any, document: Any) -> Any:
    from documents import bundle, gitstore

    repo = gitstore.open_repository(tenant.number, document.number)
    head = gitstore.head(repo)
    assert head is not None
    return bundle.parse(gitstore.read(repo, "document.md", head).decode())[0]


def switch(people: Any, on: bool, text: str = "") -> Any:
    fields = {"title_page_text": text}
    if on:
        fields["title_page"] = "on"
    return people.client.post(f"/document/{people.document.number}/edit/title-page/", fields)


def test_the_switch_is_a_draft_change(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    from audit.models import AuditEvent

    people = scene(member_of, new_document, link_group, commit_version)

    answer = switch(people, True)

    assert answer.status_code == 303
    assert draft_frontmatter(migrated_tenant, people.document)["title_page"] is True
    assert head_frontmatter(migrated_tenant, people.document).title_page is False
    (event,) = AuditEvent.objects.filter(action="frontmatter.staged")
    assert event.after["key"] == "title_page" and event.after["value"] is True
    tab = people.client.get(f"/document/{people.document.number}/edit/").content.decode()
    assert re.search(r'name="title_page"[^>]*checked', tab)


def test_a_switch_alone_is_a_version(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    people = scene(member_of, new_document, link_group, commit_version)
    switch(people, True)
    n = people.document.number

    for path in (f"/document/{n}/my-edits/", f"/document/{n}/edit/finish/"):
        assert "Title page switched on" in flat(people.client.get(path).content.decode()), path
    sent = people.client.post(f"/document/{n}/edit/send/", {"summary": "A title page"})

    assert sent.status_code == 302
    assert head_frontmatter(migrated_tenant, people.document).title_page is True


def test_the_reviewer_sees_it_and_the_export_follows(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    canonical_pdf: Any,
) -> None:
    from access.rights import Right
    from review import services as review

    approver_client, approver, approvers = member_of("the.approver@example.test")

    def linked(document: Any, author: Any) -> None:
        rights = [Right.FREEZE, Right.MAKE_CANONICAL, Right.VIEW_CANONICAL]
        link_group(document, rights, [approvers], author)

    people = scene(member_of, new_document, link_group, commit_version, linked)
    switch(people, True)
    n = people.document.number
    people.client.post(f"/document/{n}/edit/send/", {"summary": "A title page"})

    pending = flat(people.reviewer_client.get(f"/document/{n}/pending/").content.decode())
    with schema_context(migrated_tenant.number):
        review.accept(people.document, people.reviewer)
    info = people.reviewer_client.get(f"/document/{n}/info/").content.decode()
    pages = canonical_pdf(people.document, approver_client, approver)

    assert "Title page switched on" in pending
    assert '<dd class="title-page-shown">Yes</dd>' in info
    # The canonical PDF opens with the title page; the text starts on the next.
    assert "The first synthetic sentence." not in pages[0]
    assert people.document.title in pages[0]
    assert "Approved:" in pages[0] and "edition 1.0" in pages[0]
    assert any("The first synthetic sentence." in page for page in pages[1:])


def test_refusals(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    from access.rights import Right
    from documents.models import Document

    reader, _, theirs = member_of("a.reader@example.test")
    other, _, own = member_of("another.editor@example.test")

    def linked(document: Any, author: Any) -> None:
        link_group(document, [Right.VIEW_ACCEPTED], [theirs], author)
        link_group(document, [Right.EDIT], [own], author)

    people = scene(member_of, new_document, link_group, commit_version, linked)
    n = people.document.number

    def posted(client: Any, fields: dict[str, str]) -> Any:
        return client.post(f"/document/{n}/edit/title-page/", fields, follow=True)

    not_an_editor = reader.post(f"/document/{n}/edit/title-page/", {"title_page": "on"})
    while_held = posted(other, {"title_page": "on"})
    # Nothing asked to change, and a text past the rule: the hold is still what refuses.
    unchanged = posted(other, {"title_page_text": ""})
    too_long = posted(other, {"title_page_text": "x" * 501})

    assert not_an_editor.status_code == 404
    for answer in (while_held, unchanged, too_long):
        assert answer.status_code == 200
        assert "You are not editing this document now" in flat(answer.content.decode())
    assert draft_frontmatter(migrated_tenant, people.document)["title_page"] is False
    with schema_context(migrated_tenant.number):
        assert Document.objects.get(pk=people.document.pk).state == "active"


def test_a_reservation_refuses_another(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    from access.rights import Right
    from audit.models import AuditEvent

    other, _, own = member_of("another.editor@example.test")
    people = scene(
        member_of,
        new_document,
        link_group,
        commit_version,
        lambda document, author: link_group(document, [Right.EDIT], [own], author),
        [Right.EDIT, Right.RESERVE_FOR_EDITING],
    )
    n = people.document.number
    assert people.client.post(f"/document/{n}/edit/reserve/").status_code == 302
    people.client.post(f"/document/{n}/edit/close/")

    answer = other.post(f"/document/{n}/edit/title-page/", {"title_page": "on"}, follow=True)

    assert "You are not editing this document now" in flat(answer.content.decode())
    assert not AuditEvent.objects.filter(action="frontmatter.staged").exists()


def test_an_undo_keeps_the_switch(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    from editing import holds
    from editing.models import Draft
    from review import undo

    people = scene(member_of, new_document, link_group, commit_version)
    switch(people, True)
    # And a sentence changed in the same run, which the undo takes back.
    with schema_context(migrated_tenant.number):
        draft = Draft.objects.get(hold=holds.open_hold(people.document))
        draft.content = {
            **draft.content,
            "document.md": "# Purpose\n\nThe first synthetic sentence, revised.\n",
        }
        draft.save()
    n = people.document.number
    people.client.post(f"/document/{n}/edit/send/", {"summary": "A title page"})

    with schema_context(migrated_tenant.number):
        undo.apply(people.document, people.reviewer, author=people.holder)
        draft = Draft.objects.get(hold=holds.open_hold(people.document))
        assert draft.content["frontmatter"]["title_page"] is True
        assert {"before": "", "after": "", "frontmatter": "kept"} in draft.content["undo"]["listed"]


def test_a_draft_older_than_the_text_lists_no_change(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    """A draft whose frontmatter predates the title-page text — no such key in it — reads as the
    head's empty text: nothing listed, nothing to send."""
    from editing import holds
    from editing.models import Draft

    people = scene(member_of, new_document, link_group, commit_version)
    with schema_context(migrated_tenant.number):
        draft = Draft.objects.get(hold=holds.open_hold(people.document))
        frontmatter = dict(draft.content["frontmatter"])
        frontmatter.pop("title_page_text", None)
        draft.content = {**draft.content, "frontmatter": frontmatter}
        draft.save()
    n = people.document.number

    from documents.models import Version

    finish = flat(people.client.get(f"/document/{n}/edit/finish/").content.decode())
    with schema_context(migrated_tenant.number):
        before = Version.objects.filter(document=people.document).count()
    people.client.post(f"/document/{n}/edit/send/", {"summary": "Nothing"})

    assert "Title page text" not in finish
    with schema_context(migrated_tenant.number):
        assert Version.objects.filter(document=people.document).count() == before
