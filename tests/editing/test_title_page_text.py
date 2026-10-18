"""The document's own title-page text written in a draft (DL-0476, DL-0483): cleaned, refused
past its rule with what was typed kept, staged as a draft change, read whole by the reviewer, and
printed on the title page. People are synthetic examples; the texts are invented."""

from __future__ import annotations

import html
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


def scene(member_of: Any, new_document: Any, link_group: Any, commit_version: Any) -> Any:
    from access.rights import Right

    _, author, _ = member_of("the.author@example.test")
    client, holder, own = member_of("the.holder@example.test")
    reviewer_client, reviewer, theirs = member_of("the.reviewer@example.test")
    document = new_document(author)
    link_group(document, [Right.EDIT], [own], author)
    link_group(document, [Right.ACCEPT, Right.VIEW_PENDING], [theirs], author)
    commit_version(document, author, BODY)
    assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
    return SimpleNamespace(
        client=client, document=document, reviewer=reviewer, reviewer_client=reviewer_client
    )


def staged(tenant: Any, document: Any) -> dict[str, Any]:
    from editing import holds
    from editing.models import Draft

    with schema_context(tenant.number):
        return dict(Draft.objects.get(hold=holds.open_hold(document)).content["frontmatter"])


def written(people: Any, text: str, *, on: bool = False) -> Any:
    fields = {"title_page_text": text}
    if on:
        fields["title_page"] = "on"
    return people.client.post(f"/document/{people.document.number}/edit/title-page/", fields)


def flat(page: str) -> str:
    import re

    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", page)).split())


def test_the_text_is_cleaned_and_staged(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    from audit.models import AuditEvent

    people = scene(member_of, new_document, link_group, commit_version)

    answer = written(people, "  Register entry: EX-1  \r\nSecond line\n\n")

    assert answer.status_code == 303
    assert staged(migrated_tenant, people.document)["title_page_text"] == (
        "  Register entry: EX-1\nSecond line"
    )
    events = list(AuditEvent.objects.filter(action="frontmatter.staged"))
    assert [e.after["key"] for e in events] == ["title_page_text"]
    written(people, "Code:\n    EX-1")
    assert staged(migrated_tenant, people.document)["title_page_text"] == "Code:\n    EX-1"


@pytest.mark.parametrize(
    "text",
    [
        "x" * 501,
        "\n".join(f"Line {n}" for n in range(9)),
        "Register ‮ entry",
        "Register​ entry",
    ],
    ids=["too-long", "too-many-lines", "a-reordering-mark", "an-invisible-character"],
)
def test_the_texts_rule(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    text: str,
) -> None:
    people = scene(member_of, new_document, link_group, commit_version)

    answer = written(people, text)

    assert answer.status_code == 400
    page = html.unescape(answer.content.decode())
    assert "At most 500 characters and 8 lines, plain text" in page
    assert text.split("\n")[0][:40] in page
    assert staged(migrated_tenant, people.document).get("title_page_text", "") == ""


def test_the_two_joiners_stay(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    """The zero-width non-joiner and joiner some scripts need are kept (DL-0483)."""
    people = scene(member_of, new_document, link_group, commit_version)

    assert written(people, "Register‌entry‍").status_code == 303


def test_the_reviewer_sees_the_text_and_the_export_prints_it(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    from documents import bundle, gitstore
    from rendering.export.compose import _page
    from review import services as review

    people = scene(member_of, new_document, link_group, commit_version)
    written(people, "Register entry: EX-1\nSecond line", on=True)
    n = people.document.number

    finish = flat(people.client.get(f"/document/{n}/edit/finish/").content.decode())
    people.client.post(f"/document/{n}/edit/send/", {"summary": "A title page"})
    pending = flat(people.reviewer_client.get(f"/document/{n}/pending/").content.decode())
    with schema_context(migrated_tenant.number):
        review.accept(people.document, people.reviewer)
        repo = gitstore.open_repository(migrated_tenant.number, n)
        frontmatter = bundle.parse(
            gitstore.read(repo, "document.md", gitstore.head(repo)).decode()
        )[0]
        page = _page(
            SimpleNamespace(document=people.document, view="accepted"),
            frontmatter,
            "<p>The first synthetic sentence.</p>",
            "h",
            "0.1",
        )

    assert "Title page text: Register entry: EX-1 / Second line" in finish
    assert "Title page text: Register entry: EX-1 / Second line" in pending
    assert '<div class="title-page-text"><p>Register entry: EX-1<br>Second line</p></div>' in page

    # Emptied in the next run: listed as removed.
    assert people.client.post(f"/document/{n}/edit/take/").status_code == 200
    written(people, "", on=True)
    people.client.post(f"/document/{n}/edit/send/", {"summary": "No text"})
    assert "Title page text removed" in flat(
        people.reviewer_client.get(f"/document/{n}/pending/").content.decode()
    )


def test_my_edits_read_the_drafts_title_page(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    """Before the run is sent, an export of *my edits* takes the switch and the text from the
    draft, not the head."""
    from documents.models import Version
    from editing import holds
    from rendering.export.compose import _texts
    from rendering.models import ExportAppendices, ExportChanges, ExportView

    people = scene(member_of, new_document, link_group, commit_version)
    written(people, "Register entry: EX-1", on=True)

    with schema_context(migrated_tenant.number):
        job = SimpleNamespace(
            document=people.document,
            version=Version.objects.filter(document=people.document).latest("pk"),
            view=ExportView.MY_EDITS,
            requested_by_id=holds.open_hold(people.document).user_id,
            appendices=ExportAppendices.NONE,
            changes=ExportChanges.CLEAN,
            baseline_version=None,
        )
        frontmatter = _texts(job, migrated_tenant.number).frontmatter

    assert frontmatter.title_page is True
    assert frontmatter.title_page_text == "Register entry: EX-1"


def test_a_refusal_keeps_the_switch_as_set(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    import re

    people = scene(member_of, new_document, link_group, commit_version)

    answer = written(people, "x" * 501, on=True)

    assert answer.status_code == 400
    assert re.search(r'name="title_page"[^>]*checked', answer.content.decode())
    assert staged(migrated_tenant, people.document).get("title_page") is False
