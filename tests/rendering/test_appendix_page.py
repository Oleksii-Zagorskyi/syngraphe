"""The appendix page (DL-0443, DL-0444): the document's frame for one appendix of the version its
reader may see — its own outline, its numbers from 1 with nothing in front, the read-only panel,
the tabs of DL-0443 and no document action; an appendix that version does not list costs what a
missing one does. Titles and people are synthetic examples; text is invented English."""

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
        title = re.sub(r"<[^>]+>", "", heading.group(0))
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
        for absent in ("/export/", "/copy/", "/archive/", "Freeze", "Make canonical", "More ▾"):
            assert absent not in html[: html.index('class="document-text"')], absent
        tabs = re.search(r'<nav class="tabs">.*?</nav>', html, re.S)
        assert tabs
    reader_tabs = re.search(
        r'<nav class="tabs">.*?</nav>',
        reader_client.get(f"/document/{m}/appendix/2/").content.decode(),
        re.S,
    )
    assert reader_tabs
    links = re.findall(r'<a href="([^"]+)"[^>]*>([^<]+)</a>', reader_tabs.group(0))
    assert links[0] == (f"/document/{m}/appendix/2/", "View")
    assert (f"/document/{m}/pending/", "Pending edits") in links
    assert f"/document/{m}/appendix/2/edit/" not in [href for href, _ in links]
    assert "aria-current" not in reader_tabs.group(0).split("Pending edits")[0].split("View")[1]
    holder_tabs = re.search(
        r'<nav class="tabs">.*?</nav>',
        holder_client.get(f"/document/{m}/appendix/2/").content.decode(),
        re.S,
    )
    assert holder_tabs and f'href="/document/{m}/appendix/2/edit/"' in holder_tabs.group(0)


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
