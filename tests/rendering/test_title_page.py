"""The title page (DL-0164, DL-0360, DL-0462, DL-0475, DL-0476): the details the organisation's
layout chooses, in its order and alignment, the approval line always among them; off the canonical
view and before the first edition the approval details left out; the document's own text printed
as plain text.

People, types and texts are synthetic examples."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from access.rights import Right
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

CENTRED = json.dumps({"items": ["number", "title", "type", "approval"], "align": "centre"})


@pytest.fixture(autouse=True)
def english(settings: Any) -> None:
    # The details' words are read in English; the catalogue test reads them in `uk`.
    settings.LANGUAGE_CODE = "en"


@pytest.mark.fast
@pytest.mark.parametrize(
    ("stored", "expected", "warned"),
    [
        ("", "default", False),
        (CENTRED, "centred", False),
        (json.dumps({"items": ["number", "title"], "align": "left"}), "default", True),
        ("not a layout", "default", True),
        # Nested past the interpreter's depth: written by no page, read without failing an export.
        ("[" * 100_000, "default", True),
        (json.dumps({"items": {"approval": 1}, "align": "left"}), "default", True),
    ],
    ids=[
        "empty",
        "centred",
        "without-the-approval",
        "unreadable",
        "nested-too-deep",
        "items-not-a-list",
    ],
)
def test_a_stored_layout_reads_or_falls_back(
    stored: str, expected: str, warned: bool, caplog: Any
) -> None:
    from rendering.title_page import DEFAULT, Layout, layout_of

    with caplog.at_level(logging.WARNING, logger="rendering.title_page"):
        layout = layout_of(stored)

    wanted = {
        "default": DEFAULT,
        "centred": Layout(("number", "title", "type", "approval"), "centre"),
    }
    assert layout == wanted[expected]
    assert bool(caplog.records) is warned


@pytest.mark.fast
def test_a_layout_is_written_as_it_is_read() -> None:
    from rendering.title_page import DEFAULT, Layout, dump, layout_of

    centred = Layout(("text", "approval", "edition"), "centre")

    assert dump(DEFAULT) == ""
    assert layout_of(dump(centred)) == centred


def _approved(migrated_tenant: Any, edition_cast: Any, commit_version: Any, kit: Any) -> Any:
    """A document of an invented type whose edition 1.0 a named approver made canonical."""
    from documents.models import Document, DocumentType

    people = edition_cast()
    people["p"].display_name = "An Approver (synthetic)"
    people["p"].save(update_fields=["display_name"])
    with schema_context(migrated_tenant.number):
        kind = DocumentType.objects.create(
            code="type-synthetic", label="Procedure (synthetic example)", actor_kind="system"
        )
        Document.objects.filter(pk=people.document.pk).update(document_type=kind)
        people.document.refresh_from_db()
    kit.canonical(migrated_tenant.number, people, commit_version, kit.FIRST)
    return people


def _facts(people: Any, view: str, number: str, text: str = "") -> Any:
    from rendering.title_page import facts_for

    job = SimpleNamespace(document=people.document, view=view)
    return facts_for(job, "Synthetic policy", number, text)


def test_the_layout_orders_and_aligns_the_details(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any, kit: Any
) -> None:
    from rendering.title_page import html, layout_of

    people = _approved(migrated_tenant, edition_cast, commit_version, kit)
    with schema_context(migrated_tenant.number):
        page = html(_facts(people, "canonical", "1.0"), layout_of(CENTRED))

    assert page.startswith('<section class="title-page align-centre">')
    order = [
        page.index(f"#{people.document.number}"),
        page.index("Synthetic policy"),
        page.index("Type: Procedure (synthetic example)"),
        page.index("Approved: An Approver (synthetic)"),
    ]
    assert order == sorted(order)
    assert "@" not in page


def test_the_approval_line_is_always_there(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any, kit: Any, new_document: Any
) -> None:
    from rendering.title_page import Layout, html

    every = Layout(
        ("title", "number", "type", "edition", "approver", "approval_date", "approval"), "left"
    )
    people = _approved(migrated_tenant, edition_cast, commit_version, kit)
    unapproved = new_document(people["a"])
    with schema_context(migrated_tenant.number):
        canonical = html(_facts(people, "canonical", "1.0"), every)
        pending = html(_facts(people, "pending_edits", "1.0-1"), every)
        never = html(_facts(SimpleNamespace(document=unapproved), "pending_edits", "0.0-1"), every)

    assert "Edition 1.0" in canonical
    assert "Approved by: An Approver (synthetic)" in canonical
    assert "Approval date:" in canonical
    assert "Approved: An Approver (synthetic)" in canonical
    # Off the canonical view: the edition the text departs from, and nothing that reads as approval.
    assert "Edition 1.0" in pending
    assert "Approved by" not in pending and "Approval date" not in pending
    assert "Not approved — pending edits to edition 1.0" in pending
    # Before the first edition: none of the three.
    assert "Edition" not in never and "Approved by" not in never and "Approval date" not in never
    assert "Not yet approved" in never


def test_the_documents_own_text_is_plain() -> None:
    from rendering.title_page import Layout, TitleFacts, html

    facts = TitleFacts(
        title="Synthetic policy",
        number="#7",
        type_label="",
        edition=None,
        approver=None,
        approval_date=None,
        text="Register entry: EX-1\n<b>x</b>",
        approval="Not yet approved",
    )
    layout = Layout(("title", "text", "approval"), "left")

    page = html(facts, layout)
    empty = html(TitleFacts(**{**facts.__dict__, "text": ""}), layout)

    assert (
        '<div class="title-page-text"><p>Register entry: EX-1<br>&lt;b&gt;x&lt;/b&gt;</p></div>'
        in page
    )
    assert "title-page-text" not in empty
    # A text that is nothing once cleaned draws nothing.
    blank = html(TitleFacts(**{**facts.__dict__, "text": "\n  \n"}), layout)
    assert "title-page-text" not in blank
    # A line's leading spaces, kept when it was written, stay visible where it is printed.
    indented = html(TitleFacts(**{**facts.__dict__, "text": "Code:\n    EX-1  a b"}), layout)
    assert "<br>\u00a0\u00a0\u00a0\u00a0EX-1  a b</p>" in indented


def test_the_pdf_prints_the_configured_title_page(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
    settings: Any,
) -> None:
    from pypdf import PdfReader

    from documents.models import DocumentTemplate

    people = edition_cast()
    with schema_context(migrated_tenant.number):
        DocumentTemplate.objects.update(title_page_layout=CENTRED)
    kit.switched(migrated_tenant.number, people, title_page=True)
    kit.canonical(migrated_tenant.number, people, commit_version, kit.FIRST)
    client, _ = kit.reader(member_of, link_group, people, [Right.VIEW_CANONICAL], "pdf")
    response = client.post(
        f"/document/{people.document.number}/export/",
        {"document": "on", "format": "pdf", "view": "canonical"},
    )
    assert response.status_code == 302
    job = kit.run_job(migrated_tenant.number, exports[0][1])

    pages = PdfReader(str(Path(settings.EXPORT_ROOT) / job.artifact_ref)).pages
    first = pages[0].extract_text()
    lines = [line.strip() for line in first.splitlines() if line.strip()]
    assert lines[0] == f"#{people.document.number}"
    assert lines[1] == people.document.title
    assert lines[2].startswith("Type: ")
    assert lines[3].startswith("Approved: ")
    assert "A request for approval is made in writing." in pages[1].extract_text()
