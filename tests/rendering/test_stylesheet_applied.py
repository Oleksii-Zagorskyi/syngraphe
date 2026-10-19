"""Where the organisation's stylesheet applies (DL-0464, DL-0465; ADR-0013): confined to the
document's text on every read-only page that draws it, never in the editor, served from the
platform's own address at the digest of what it serves; read by no page without document text;
and, once a rule has tightened past a stored row, reaching no one.

People, texts and stylesheets are synthetic examples."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from access.rights import Right
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

LINK = re.compile(r'href="(/document-styles/([0-9a-f]{16})\.css)"')
SRC = Path(__file__).resolve().parents[2] / "src"


@pytest.mark.fast
def test_the_browser_gets_it_confined_and_exports_as_written() -> None:
    from rendering.stylesheet import for_export, scoped_for_browser

    text = (
        "body { color: #123 } h1, .document-text h2 { color: red } "
        "@page { margin: 20mm } @media print { p { color: blue } }"
    )

    browser = scoped_for_browser(text)
    export = for_export(text)

    assert ".document-text {color: #123}" in browser
    assert ".document-text h1, .document-text h2 {color: red}" in browser
    assert "@media print { .document-text p {color: blue} }" in browser
    assert "@page" not in browser
    assert ":root body, :root .document-text {color: #123}" in export
    # A leading `.document-text` takes both forms, as `body` does: the default sets the text's
    # font on `.document-text` itself.
    assert ":root h1, :root body h2, :root .document-text h2 {color: red}" in export
    assert "@page {margin: 20mm}" in export
    assert "@media print { :root p {color: blue} }" in export


def _apply(migrated_tenant: Any, text: str) -> None:
    from rendering.models import Stylesheet

    with schema_context(migrated_tenant.number):
        Stylesheet.objects.update(text=text)


def _document(migrated_tenant: Any, edition_cast: Any, commit_version: Any, kit: Any) -> Any:
    """An edition 1.0, then a pending edit 1.0-1."""
    people = edition_cast()
    kit.canonical(migrated_tenant.number, people, commit_version, kit.FIRST)
    commit_version(people.document, people["a"], kit.SECOND, "edit")
    return people


def test_read_only_renderings_link_it_and_the_editors_do_not(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    kit: Any,
) -> None:
    _apply(migrated_tenant, "h1 { color: #123456 }")
    people = _document(migrated_tenant, edition_cast, commit_version, kit)
    n = people.document.number
    reader, _ = kit.reader(
        member_of,
        link_group,
        people,
        [Right.VIEW_CANONICAL, Right.VIEW_ACCEPTED, Right.VIEW_PENDING, Right.VIEW_ALL_HISTORY],
        "reader",
    )

    for page in (
        f"/document/{n}/",
        f"/document/{n}/pending/",
        f"/document/{n}/version/1.0/",
        f"/document/{n}/compare/?from=1.0&to=1.0-1",
    ):
        answer = reader.get(page)
        assert answer.status_code == 200, page
        assert LINK.search(answer.content.decode()), page
    editing = people.clients["a"].get(f"/document/{n}/edit/")
    assert editing.status_code == 200
    assert not LINK.search(editing.content.decode())
    # The pages the scenario does not open fill or empty the block the same way.
    templates = SRC / "rendering" / "templates" / "rendering"
    for filled in (
        templates / "appendix.html",
        templates / "compare_appendix.html",
        templates / "compare_documents.html",
        SRC / "review" / "templates" / "review" / "notice.html",
    ):
        assert "{% block document_styles %}{% organisation_stylesheet %}" in filled.read_text()
    emptied = SRC / "editing" / "templates" / "editing" / "appendix_edit.html"
    assert "{% block document_styles %}{% endblock %}" in emptied.read_text()


def test_the_appendix_page_links_it_and_its_edit_tab_does_not(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    kit: Any,
) -> None:
    """The appendix's own reading page and its editor, asked for as a reader and the person
    editing ask for them."""
    from editions import services as editions
    from review import services as review

    _apply(migrated_tenant, "h1 { color: #123456 }")
    people = edition_cast()
    commit_version(
        people.document,
        people["a"],
        kit.FIRST,
        "edit",
        files={"appendices/1.md": b"# Synthetic appendix\n\nIts one sentence.\n"},
        appendices=[{"number": 1, "title": "A synthetic appendix"}],
    )
    with schema_context(migrated_tenant.number):
        review.accept(people.document, people["r"])
        editions.freeze(people.document, people["p"], "Synthetic reason")
        editions.make_canonical(people.document, people["p"])
    n = people.document.number
    reader, _ = kit.reader(member_of, link_group, people, [Right.VIEW_CANONICAL], "reader")

    reading = reader.get(f"/document/{n}/appendix/1/")
    editor = people.clients["a"]
    assert editor.post(f"/document/{n}/edit/take/").status_code == 200
    editing = editor.get(f"/document/{n}/appendix/1/edit/")

    assert reading.status_code == 200 and LINK.search(reading.content.decode())
    assert editing.status_code == 200 and not LINK.search(editing.content.decode())


def test_the_served_stylesheet(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    kit: Any,
    make_tenant_schema: Any,
    monkeypatch: Any,
) -> None:
    from django.test import Client

    from identity.models import Membership, User
    from rendering import stylesheet

    _apply(migrated_tenant, "h1 { color: #123456 }")
    people = _document(migrated_tenant, edition_cast, commit_version, kit)
    reader, _ = kit.reader(member_of, link_group, people, [Right.VIEW_CANONICAL], "reader")
    found = LINK.search(reader.get(f"/document/{people.document.number}/").content.decode())
    assert found is not None
    address, digest = found.groups()

    served = reader.get(address)
    stale = reader.get("/document-styles/0000000000000000.css")
    other = make_tenant_schema("Another organisation (synthetic)")
    stranger = User.objects.create_user("a.stranger@example.test", "test-only-not-a-password")
    Membership.objects.create(tenant=other, user=stranger, actor_kind="system")
    elsewhere = Client(headers={"host": "127.0.0.1"})
    elsewhere.force_login(stranger)
    session = elsewhere.session
    session["tenant_number"] = other.number
    session.save()

    assert served.status_code == 200
    assert served["Content-Type"] == "text/css; charset=utf-8"
    assert served["X-Content-Type-Options"] == "nosniff"
    assert "immutable" in served["Cache-Control"]
    body = served.content.decode()
    assert ".document-text h1 {color: #123456}" in body and body.endswith(stylesheet.GUARD)
    assert stale.status_code == 200 and "no-cache" in stale["Cache-Control"]
    # Another organisation's member is answered in their own organisation: none of this one's.
    theirs = elsewhere.get(address)
    assert theirs.status_code == 200 and "#123456" not in theirs.content.decode()
    nobody = Client(headers={"host": "127.0.0.1"})
    nobody.force_login(User.objects.create_user("no.one@example.test", "test-only-not-a-password"))
    assert nobody.get(address).status_code == 404
    # A release that changes what is served changes the address; the row is the same.
    monkeypatch.setattr(stylesheet, "GUARD", stylesheet.GUARD + "/* changed */\n")
    again = LINK.search(reader.get(f"/document/{people.document.number}/").content.decode())
    assert again is not None and again.group(2) != digest


def test_pages_without_document_text_never_read_it(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    kit: Any,
    signed_in_without_tenant: Any,
) -> None:
    people = _document(migrated_tenant, edition_cast, commit_version, kit)
    reader, _ = kit.reader(member_of, link_group, people, [Right.VIEW_CANONICAL], "reader")
    platform = signed_in_without_tenant("p.admin@example.test", is_platform_admin=True)

    with CaptureQueriesContext(connection) as unrelated:
        assert platform.get("/administration/").status_code == 200
        assert reader.get("/folder/1/").status_code == 200
    with CaptureQueriesContext(connection) as viewed:
        assert reader.get(f"/document/{people.document.number}/").status_code == 200

    assert not [q for q in unrelated.captured_queries if "rendering_stylesheet" in q["sql"]]
    assert len([q for q in viewed.captured_queries if "rendering_stylesheet" in q["sql"]]) == 1


def test_a_row_that_no_longer_passes_reaches_no_one(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
    settings: Any,
    monkeypatch: Any,
) -> None:
    from rendering import stylesheet
    from rendering.export import pdf

    settings.LANGUAGE_CODE = "en"
    # Written outside the page, as no administrator's *Apply* could.
    _apply(migrated_tenant, "p { display: none }")
    people = _document(migrated_tenant, edition_cast, commit_version, kit)
    reader, _ = kit.reader(member_of, link_group, people, [Right.VIEW_CANONICAL], "reader")
    given: list[list[str]] = []
    real = pdf.write

    def recorded(html: str, path: Path, **kwargs: Any) -> None:
        given.append(list(kwargs["stylesheets"]))
        real(html, path, **kwargs)

    monkeypatch.setattr(pdf, "write", recorded)
    from rendering.export import docx

    words: list[str] = []
    real_docx = docx.write

    def recorded_docx(html: str, path: Path, **kwargs: Any) -> None:
        words.append(kwargs.get("stylesheet", ""))
        real_docx(html, path, **kwargs)

    monkeypatch.setattr(docx, "write", recorded_docx)
    n = people.document.number
    page = reader.get(f"/document/{n}/").content.decode()
    served = reader.get("/document-styles/0000000000000000.css").content.decode()
    info = reader.get(f"/document/{n}/info/").content.decode()
    asked = reader.post(
        f"/document/{n}/export/", {"document": "on", "format": "pdf", "view": "canonical"}
    )
    assert asked.status_code == 302
    kit.run_job(migrated_tenant.number, exports[0][1])

    assert not LINK.search(page)
    assert served == stylesheet.GUARD
    assert "The platform's default" in info
    (sheets,) = given
    assert "display" not in sheets[2] and sheets[2].strip() == ""
    # The Word file as with no stylesheet: the default's reference document.
    asked = reader.post(
        f"/document/{n}/export/", {"document": "on", "format": "docx", "view": "canonical"}
    )
    assert asked.status_code == 302
    done = kit.run_job(migrated_tenant.number, exports[-1][1])
    assert done.state == "done", done.failure_reason
    assert words and docx.reference(stylesheet.applied(words[0])) == docx.reference("")


def test_the_info_tab_says_the_title_page_and_the_style(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    kit: Any,
    settings: Any,
) -> None:
    """*Title page* for the version the reader is shown (DL-0463), *Style* for the organisation
    (DL-0465)."""
    settings.LANGUAGE_CODE = "en"
    people = edition_cast()
    kit.switched(migrated_tenant.number, people, title_page=True)
    kit.canonical(migrated_tenant.number, people, commit_version, kit.FIRST)
    reader, _ = kit.reader(member_of, link_group, people, [Right.VIEW_CANONICAL], "reader")
    info = f"/document/{people.document.number}/info/"

    before = reader.get(info).content.decode()
    _apply(migrated_tenant, "h1 { color: #123456 }")
    after = reader.get(info).content.decode()

    assert '<dd class="title-page-shown">Yes</dd>' in before
    assert '<dd class="style">The platform\'s default</dd>' in before
    assert '<dd class="style">The organisation\'s stylesheet</dd>' in after


@pytest.mark.fast
def test_a_stored_text_is_checked_once(monkeypatch: Any) -> None:
    """Every reader goes through `applied`, and a page asks it more than once: the stored text's
    verdict and its served form are worked out once a process, not per request."""
    from rendering import stylesheet

    calls: list[str] = []
    real = stylesheet.check

    def counted(text: str) -> list[Any]:
        calls.append(text)
        return real(text)

    monkeypatch.setattr(stylesheet, "check", counted)
    text = "h1 { color: #654321 }  /* a stored text of this test alone */\n"

    for _ in range(3):
        assert stylesheet.applied(text) == text
        assert stylesheet.served(text).endswith(stylesheet.GUARD)

    assert calls == [text]
