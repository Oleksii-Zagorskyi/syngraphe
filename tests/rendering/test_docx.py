"""The DOCX export (ADR-0013, DL-0182): the platform's classes as named Word styles, each carried
by the text, the numbering definitions, the footer's page number and no header (DL-0362); a
heading's number set as the heading (DL-0363).

People, groups and titles are synthetic examples; every text is invented.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any

import pytest

from access.rights import Right

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

STYLES = (
    "EntityRole",
    "EntityAction",
    "EntityTerm",
    "Underline",
    "ClauseNumber",
    "CalloutNote",
    "CalloutWarning",
    "CalloutExample",
)


def test_docx_named_styles_and_furniture(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
    settings: Any,
) -> None:
    sample = (kit.FIXTURES / "conformance.md").read_text(encoding="utf-8")
    people = edition_cast()
    kit.canonical(migrated_tenant.number, people, commit_version, sample)
    client, _ = kit.reader(member_of, link_group, people, [Right.VIEW_CANONICAL], "docx")

    response = client.post(
        f"/document/{people.document.number}/export/",
        {"document": "on", "format": "docx", "view": "canonical"},
    )
    assert response.status_code == 302
    job = kit.run_job(migrated_tenant.number, exports[0][1])

    assert job.state == "done", job.failure_reason
    with zipfile.ZipFile(Path(settings.EXPORT_ROOT) / job.artifact_ref) as docx:
        styles = docx.read("word/styles.xml").decode()
        document = docx.read("word/document.xml").decode()
        numbering = docx.read("word/numbering.xml").decode()
        names = docx.namelist()
        footer = docx.read("word/footer1.xml").decode()
    for style in STYLES:
        assert f'w:styleId="{style}"' in styles, style
        assert f'w:val="{style}"' in document, style
    assert len(re.findall(r"<w:abstractNum ", numbering)) == 3
    assert not any(name.startswith("word/header") for name in names)
    assert "headerReference" not in document
    # Nor does the header's text open the body as a title paragraph, from the page's `<title>`.
    assert not re.search(r'<w:pStyle w:val="Title"\s*/>', document)
    assert "— " + "канонічна" not in re.sub(r"<[^>]+>", "", document)
    assert "PAGE" in footer
    # A heading's number takes the heading's look, never the clause number's (DL-0363).
    paragraphs = re.findall(r"<w:p>.*?</w:p>", document, re.S)
    headings = [p for p in paragraphs if re.search(r'<w:pStyle w:val="Heading\d"\s*/>', p)]
    assert headings
    for heading in headings:
        assert 'w:val="ClauseNumber"' not in heading


def test_a_marked_docx_carries_its_changes_in_styles_of_their_own(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
    settings: Any,
) -> None:
    """An insertion, a deletion and a change of formatting each take a named style of its own,
    never the look of an underlined or struck-out word; the formatting change shows by its colour
    alone."""
    people = edition_cast()
    kit.canonical(migrated_tenant.number, people, commit_version, kit.SECOND)
    changed = (
        kit.SECOND.replace("made in writing", "made in **writing**").replace(
            "\nA copy of the decision goes to the applicant that day.\n", ""
        )
        + "\nThe register of requests is kept by the officer in charge.\n"
    )
    commit_version(people.document, people["a"], changed, "edit")
    client, _ = kit.reader(member_of, link_group, people, [Right.VIEW_PENDING], "marks")
    response = client.post(
        f"/document/{people.document.number}/export/",
        {"document": "on", "format": "docx", "view": "pending_edits",
         "changes-pending_edits": "marked"},
    )  # fmt: skip
    assert response.status_code == 302
    job = kit.run_job(migrated_tenant.number, exports[0][1])

    assert job.state == "done", job.failure_reason
    with zipfile.ZipFile(Path(settings.EXPORT_ROOT) / job.artifact_ref) as docx:
        body = docx.read("word/document.xml").decode()
        styles = docx.read("word/styles.xml").decode()
    assert 'w:val="C2C2C2"' in styles
    for style in ("Inserted", "Deleted", "FormatChanged"):
        assert f'w:styleId="{style}"' in styles, style
        assert re.search(rf'<w:rStyle w:val="{style}"\s*/>', body), style
    assert not re.search(r'<w:rStyle w:val="Underline"\s*/>', body)
    # The formatting change is marked by its colour alone (DL-0363).
    assert "лише форматування" not in body
