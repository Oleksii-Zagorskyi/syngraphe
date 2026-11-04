"""The appendix page (DL-0443, DL-0444): the document's frame for one appendix of the version its
reader may see — its own outline, its numbers from 1 with nothing in front, the read-only panel, the
document's path in appendix mode (DL-0522) and no document action; an appendix that version does not
list costs what a missing one does. Titles and people are synthetic examples; text is invented
English."""

from __future__ import annotations

import re
from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

BODY = "# Purpose\n\nThe first synthetic sentence.\n"
TITLE = "Approval matrix (example)"
APPENDIX = (
    "# Approval matrix\n\nThe first appendix sentence.\n\n## Thresholds\n\n"
    "A request below the threshold is approved by the head of unit.\n"
)


def committed(commit_version: Any, document: Any, user: Any, text: str = APPENDIX) -> Any:
    return commit_version(
        document,
        user,
        BODY,
        files={"appendices/2.md": text.encode()},
        appendices=[{"number": 2, "title": TITLE}],
    )


def shown(tenant: Any, user: Any, document: Any) -> str:
    from editions.visible import visible

    with schema_context(tenant.number):
        found = visible(user, document)
        assert found is not None
        return str(found.number)


def test_the_appendix_page(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    settings: Any,
) -> None:
    from access.rights import Right

    settings.LANGUAGE_CODE = "en"
    _, author, _ = member_of("the.author@example.test")
    reader_client, reader, reading = member_of("the.reader@example.test")
    admin_client, _, _ = member_of("the.admin@example.test", is_tenant_admin=True)
    holder_client, holder, holding = member_of("the.holder@example.test")
    document = new_document(author, "Synthetic leave rules")
    link_group(document, [Right.VIEW_PENDING], [reading], author)
    link_group(document, [Right.EDIT, Right.VIEW_PENDING], [holding], author)
    committed(commit_version, document, author)
    holder_client.post(f"/document/{document.number}/edit/take/")
    number = shown(migrated_tenant, reader, document)
    m = document.number

    for client in (reader_client, admin_client, holder_client):
        answer = client.get(f"/document/{m}/appendix/2/")
        assert answer.status_code == 200
        html = answer.content.decode()
        heading = re.search(r"<h1>.*?</h1>", html, re.S)
        assert heading
        # The appendix after its document, then the version; the state tags follow.
        before_tags = heading.group(0).split('<span class="tag"', 1)[0]
        title = re.sub(r"<[^>]+>", "", before_tags)
        assert " ".join(title.split()) == f"#{m} Synthetic leave rules › {TITLE} {number}"
        assert f'<a href="/document/{m}/">' in heading.group(0)
        text = html[html.index('class="document-text"') :]
        assert re.search(r">1</span>\s*Approval matrix", text) or "1 Approval matrix" in (
            re.sub(r"<[^>]+>", " ", text)
        )
        flat = " ".join(re.sub(r"<[^>]+>", " ", text).split())
        assert "1.1 Thresholds" in flat
        assert "1-1" in flat and "1.1-1" in flat
        assert 'id="outline-pane"' in html
        # No document act on an appendix's page (DL-0207); the icons are the document's (DL-0443).
        above = html[: html.index('class="document-text"')]
        for absent in ("/copy/", "/archive/", 'data-command="approve"', 'data-command="freeze"'):
            assert absent not in above, absent
        assert '<details class="more">' not in above and 'data-command="review"' not in above
        # Export starts on the latest view the reader may export (DL-0529).
        assert f'<a class="icon-btn" href="/document/{m}/export/?view=latest"' in above
        assert 'class="tabs"' not in html
    # The document's path for the appendix: the latest opens the appendix, outlined; the run's
    # arc stays the document's; the reader has no editor to open.
    reader_page = reader_client.get(f"/document/{m}/appendix/2/").content.decode()
    path = re.search(r'<nav class="path".*?</nav>', reader_page, re.S)
    assert path
    assert (
        f'<a class="go" href="/document/{m}/appendix/2/" data-go="latest" aria-current="location">'
    ) in path.group(0)
    assert f'href="/document/{m}/pending/"' in path.group(0)
    assert f"/document/{m}/appendix/2/edit/" not in path.group(0)
    # The holder's draft opens the appendix's editor.
    holder_page = holder_client.get(f"/document/{m}/appendix/2/").content.decode()
    assert f'href="/document/{m}/appendix/2/edit/" data-go="draft"' in holder_page


def test_unlisted_appendices_are_missing(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
) -> None:
    from access.rights import Right
    from editing import holds, parts

    client, author, own = member_of("the.author@example.test")
    stranger_client, _, _ = member_of("a.stranger@example.test")
    document = new_document(author)
    link_group(document, [Right.EDIT, Right.CREATE_APPENDIX, Right.VIEW_PENDING], [own], author)
    committed(commit_version, document, author)
    with schema_context(migrated_tenant.number):
        holds.take(document, author)
        parts.create_appendix(document, author, title="Only in the draft (example)")
    m = document.number
    for asker, path in (
        (client, f"/document/{m}/appendix/5/"),
        (client, f"/document/{m}/appendix/3/"),
        (stranger_client, f"/document/{m}/appendix/2/"),
    ):
        answer = asker.get(path)
        # The uniform body: what the same person is answered for a document that does not exist.
        uniform = asker.get("/document/99999/").content
        assert answer.status_code == 404
        assert re.sub(rb'value="[^"]*"', b"", answer.content) == re.sub(
            rb'value="[^"]*"', b"", uniform
        )


def test_the_view_panel_lists_appendices(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any, settings: Any
) -> None:
    settings.LANGUAGE_CODE = "en"
    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    committed(commit_version, document, author)
    html = client.get(f"/document/{document.number}/").content.decode()
    panel = html[html.index('id="panel"') :]
    assert f'<a href="/document/{document.number}/appendix/2/">{TITLE}</a>' in panel
    assert panel.index(TITLE) < panel.index("Attachments")


def test_mentions_in_an_appendix_are_filtered(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    """ASR-16, DL-0437: a mention of a document the reader may open is a link; one of an archived
    document its plain words, as the View tab renders the body's."""
    from documents import archive

    client, author, _ = member_of("the.author@example.test")
    _, admin, _ = member_of("the.admin@example.test", is_tenant_admin=True)
    document = new_document(author)
    open_ = new_document(author, "Synthetic travel rules")
    gone = new_document(author, "Synthetic procurement rules")
    with schema_context(migrated_tenant.number):
        archive.archive(gone, admin)
    committed(
        commit_version,
        document,
        author,
        "# Approval matrix\n\n"
        f"See [the travel rules]{{.document #{open_.number}}} "
        f"and [the purchasing rules]{{.document #{gone.number}}}.\n",
    )
    html = client.get(f"/document/{document.number}/appendix/2/").content.decode()
    text = html[html.index('class="document-text"') :]
    assert f'href="/document/{open_.number}/"' in text
    assert f'href="/document/{gone.number}/"' not in text
    assert "the purchasing rules" in text


def test_the_appendix_carries_the_documents_path(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    settings: Any,
) -> None:
    """An appendix listed at the canonical version and at the latest: each point opens the
    appendix at its version, and the one act is *Edit*, to the appendix's editor — no approval,
    no toggle, no review, no administrator's menu, whoever reads it (DL-0207, DL-0522)."""
    from access.rights import Right
    from editions import services as editions
    from review import services as review

    settings.LANGUAGE_CODE = "en"
    _, author, _ = member_of("path.author@example.test")
    editor_client, _, editing = member_of("path.editor@example.test")
    reviewer_client, reviewer, reviewing = member_of("path.reviewer@example.test")
    document = new_document(author, "Synthetic travel rules")
    link_group(document, [Right.EDIT, Right.VIEW_PENDING], [editing], author)
    link_group(document, [Right.ACCEPT, Right.FREEZE, Right.MAKE_CANONICAL], [reviewing], author)
    committed(commit_version, document, author)
    with schema_context(migrated_tenant.number):
        review.accept(document, reviewer)
        editions.make_canonical(document, reviewer)
    committed(commit_version, document, author, APPENDIX + "\nA later appendix sentence.\n")
    m = document.number

    for client in (editor_client, reviewer_client):
        page = client.get(f"/document/{m}/appendix/2/").content.decode()
        path = re.search(r'<nav class="path".*?</nav>', page, re.S)
        assert path
        drawn = path.group(0)
        # Each point that lists the appendix opens it at that version.
        assert f'href="/document/{m}/version/1.0/appendix/2/" data-go="canonical"' in drawn
        assert f'href="/document/{m}/appendix/2/" data-go="latest"' in drawn
        commands = re.findall(r'data-command="([^"]+)"', drawn)
        assert commands == ["edit"], commands
        assert f'href="/document/{m}/appendix/2/edit/" data-command="edit"' in drawn
        above = page[: page.index('class="document-text"')]
        assert '<details class="more">' not in above
        for absent in ("approve", "freeze", "unfreeze", "review"):
            assert f'data-command="{absent}"' not in above, absent
