"""The run's parts on *Pending edits* (DL-0168, ASR-04): the body's changes, then each appendix
whose text the run changed, then the parts changed in the run with each attachment's files at the
base and the head, and a *Parts:* line on each version that changed one; *show author* attributes
appendix lines. Titles and people are synthetic examples; text is invented English."""

from __future__ import annotations

import hashlib
import re
from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

BODY = "# Purpose\n\nThe first synthetic sentence.\n"
FORM = b"a synthetic form"


def entry(number: int, data: bytes, title: str = "Request form (example)") -> dict[str, Any]:
    return {
        "number": number,
        "title": title,
        "file_name": f"form-{number}.xlsx",
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }


def flat(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def reviewer(member_of: Any, link_group: Any, document: Any, by: Any) -> Any:
    from access.rights import Right

    client, _, membership = member_of("the.reviewer@example.test")
    link_group(document, [Right.ACCEPT, Right.VIEW_PENDING], [membership], by)
    return client


def number_of(tenant: Any, document: Any, sha: str) -> str:
    from documents.models import Version
    from editing import numbering

    with schema_context(tenant.number):
        return numbering.number_of(document, Version.objects.get(document=document, commit_sha=sha))


def test_pending_lists_the_runs_parts(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    accepted_directly: Any,
    settings: Any,
) -> None:
    settings.LANGUAGE_CODE = "en"
    _, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    client = reviewer(member_of, link_group, document, author)
    commit_version(
        document,
        author,
        BODY,
        files={"appendices/1.md": b"# One\n\nThe appendix sentence.\n", "attachments/2": FORM},
        appendices=[{"number": 1, "title": "Appendix one (example)"}],
        attachments=[entry(2, FORM)],
    )
    base = accepted_directly(document, author)
    first = commit_version(
        document,
        author,
        BODY,
        files={"appendices/1.md": b"# One\n\nThe appendix sentence, revised.\n"},
    )
    second = commit_version(
        document,
        author,
        BODY,
        files={"attachments/2": b"new bytes", "appendices/3.md": b"# Three\n\nNew text.\n"},
        appendices=[
            {"number": 1, "title": "Appendix one (example)"},
            {"number": 3, "title": "Appendix three (example)"},
        ],
        attachments=[entry(2, b"new bytes")],
    )
    m = document.number
    html = client.get(f"/document/{m}/pending/").content.decode()
    text = flat(html)
    blocks = flat(html[html.index('class="appendix-changes"') :])
    assert blocks.index("Appendix one (example)") < blocks.index("Appendix three (example)")
    assert "📎 Request form (example) replaced" in text
    old = number_of(migrated_tenant, document, base.version.commit_sha)
    new = number_of(migrated_tenant, document, second.commit_sha)
    assert f'href="/document/{m}/version/{old}/attachment/2/"' in html
    assert f'href="/document/{m}/version/{new}/attachment/2/"' in html
    assert f'href="/document/{m}/appendix/3/"' in html
    runs = re.findall(r'<li data-number="([^"]+)">(.*?)</li>', html, re.S)
    lines = {number: "Parts:" in body for number, body in runs}
    assert lines == {
        number_of(migrated_tenant, document, first.commit_sha): False,
        new: True,
    }


def test_rename_and_reorder_rows(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    accepted_directly: Any,
    settings: Any,
) -> None:
    settings.LANGUAGE_CODE = "en"
    _, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    client = reviewer(member_of, link_group, document, author)
    two = [entry(1, FORM, "First (example)"), entry(2, FORM, "Second (example)")]
    commit_version(
        document,
        author,
        BODY,
        files={"appendices/1.md": b"# One\n", "attachments/1": FORM, "attachments/2": FORM},
        appendices=[{"number": 1, "title": "Older title (example)"}],
        attachments=two,
    )
    accepted_directly(document, author)
    commit_version(
        document,
        author,
        BODY,
        appendices=[{"number": 1, "title": "Newer title (example)"}],
        attachments=list(reversed(two)),
    )
    text = flat(client.get(f"/document/{document.number}/pending/").content.decode())
    assert "▤ Newer title (example) renamed from “Older title (example)”" in text
    assert "Attachments reordered" in text


def test_appendix_lines_are_attributed(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    accepted_directly: Any,
) -> None:
    from identity.models import User

    _, author, _ = member_of("the.author@example.test")
    _, second, _ = member_of("the.second@example.test")
    User.objects.filter(pk=author.pk).update(display_name="Author A")
    User.objects.filter(pk=second.pk).update(display_name="Author B")
    author.refresh_from_db()
    second.refresh_from_db()
    document = new_document(author)
    client = reviewer(member_of, link_group, document, author)
    commit_version(
        document,
        author,
        BODY,
        files={"appendices/1.md": b"# One\n\nThe base sentence.\n"},
        appendices=[{"number": 1, "title": "Appendix one (example)"}],
    )
    accepted_directly(document, author)
    commit_version(
        document,
        author,
        BODY,
        files={"appendices/1.md": b"# One\n\nThe base sentence.\n\nA's sentence.\n"},
    )
    commit_version(
        document,
        second,
        BODY,
        files={
            "appendices/1.md": b"# One\n\nThe base sentence.\n\nA's sentence.\n\nB's sentence.\n"
        },
    )
    client.post("/preferences/show-author/", {"show_author": "on"})
    html = client.get(f"/document/{document.number}/pending/").content.decode()
    appendix = html[html.index("Appendix one (example)") :]
    assert re.search(r'data-author="Author A"[^>]*><ins>A&#x27;s sentence', appendix) or re.search(
        r"data-author=\"Author A\"[^>]*><ins>A's sentence", appendix
    )
    assert re.search(r'data-author="Author B"[^>]*><ins>B', appendix)


def test_a_registered_frontmatter_kind_is_listed(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    accepted_directly: Any,
    frontmatter_kinds: dict[str, Any],
    settings: Any,
) -> None:
    """A kind another app registers is drawn in its own words, with no change here."""
    from access.rights import Right
    from editing import parts

    settings.LANGUAGE_CODE = "en"
    parts.register_frontmatter_kind(
        parts.FrontmatterKind(
            "title_page",
            lambda value: isinstance(value, bool),
            lambda older, newer: "Synthetic title page switched",
        )
    )
    _, author, _ = member_of("the.author@example.test")
    editor_client, editor, own = member_of("the.editor@example.test")
    document = new_document(author)
    client = reviewer(member_of, link_group, document, author)
    link_group(document, [Right.EDIT], [own], author)
    commit_version(document, author, BODY)
    accepted_directly(document, author)
    with schema_context(migrated_tenant.number):
        from documents import gitstore
        from editing import holds

        repo = gitstore.open_repository(migrated_tenant.number, document.number)
        frontmatter, body = holds.split(
            gitstore.read(repo, "document.md", gitstore.head(repo)).decode()
        )
    frontmatter["title_page"] = True
    commit_version(
        document, author, body, files={"document.md": holds.join(frontmatter, body).encode()}
    )
    assert "Synthetic title page switched" in flat(
        client.get(f"/document/{document.number}/pending/").content.decode()
    )
    editor_client.post(f"/document/{document.number}/edit/take/")
    with schema_context(migrated_tenant.number):
        parts.stage_frontmatter(document, editor, "title_page", False)
    assert "Synthetic title page switched" in flat(
        editor_client.get(f"/document/{document.number}/edit/finish/").content.decode()
    )


def test_an_underived_head_draws_no_new_file(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    accepted_directly: Any,
    settings: Any,
) -> None:
    """A finish stopped after its commit leaves the head without its version row: the run's
    attachment is still listed as replaced, and *new* is not drawn to the version before."""
    from access.rights import Right
    from editing import holds, parts, services

    settings.LANGUAGE_CODE = "en"
    _, author, _ = member_of("the.author@example.test")
    editor_client, editor, own = member_of("the.editor@example.test")
    document = new_document(author)
    client = reviewer(member_of, link_group, document, author)
    link_group(document, [Right.EDIT, Right.REPLACE_ATTACHMENT], [own], author)
    commit_version(
        document, author, BODY, files={"attachments/2": FORM}, attachments=[entry(2, FORM)]
    )
    accepted_directly(document, author)
    with schema_context(migrated_tenant.number):
        hold = holds.take(document, editor)
        parts.replace_attachment(document, editor, 2, file_name="form-2.xlsx", data=b"newer")
        with pytest.raises(services.InjectedFault):
            services.commit_draft(hold, editor, "A new form", fault_at=1)
    html = client.get(f"/document/{document.number}/pending/").content.decode()
    table = html[html.index('class="part-changes"') :]
    assert "📎 Request form (example) replaced" in flat(table)
    links = re.findall(r'<a href="([^"]+)">([^<]+)</a>', table.split("</table>")[0])
    assert [label for _, label in links] == ["old"]


def test_mentions_in_the_runs_appendices_are_filtered(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    accepted_directly: Any,
) -> None:
    """ASR-16 on an appendix's changes: a mention of a document the reader may not reach is its
    words alone."""
    _, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    hidden = new_document(author, "Synthetic hidden rules")
    client = reviewer(member_of, link_group, document, author)
    commit_version(
        document,
        author,
        BODY,
        files={"appendices/1.md": b"# One\n\nA sentence.\n"},
        appendices=[{"number": 1, "title": "Appendix one (example)"}],
    )
    accepted_directly(document, author)
    mention = f"# One\n\nA sentence, see [the hidden rules]{{.document #{hidden.number}}}.\n"
    commit_version(document, author, BODY, files={"appendices/1.md": mention.encode()})
    html = client.get(f"/document/{document.number}/pending/").content.decode()
    block = html[html.index('class="appendix-changes"') :]
    assert "the hidden rules" in block
    assert f'href="/document/{hidden.number}/"' not in block
