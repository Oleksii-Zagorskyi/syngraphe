"""The DOCX export (ADR-0013, DL-0182): the platform's classes as named Word styles, each carried
by the text, the numbering definitions, and the header and footer filled.

People, groups and titles are synthetic examples; every text is invented.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any

import pytest

from access.rights import Right
from tenancy.schemas import schema_context

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
    from rendering.export import compose
    from rendering.models import ExportView

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
        header = docx.read("word/header1.xml").decode()
        footer = docx.read("word/footer1.xml").decode()
    for style in STYLES:
        assert f'w:styleId="{style}"' in styles, style
        assert f'w:val="{style}"' in document, style
    assert len(re.findall(r"<w:abstractNum ", numbering)) == 3
    with schema_context(migrated_tenant.number):
        stance = compose.stance(ExportView.CANONICAL)
    assert people.document.title in header and "1.0" in header and stance in header
    assert "PAGE" in footer


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
    never the look of an underlined or struck-out word; the formatting change carries its label."""
    people = edition_cast()
    kit.canonical(migrated_tenant.number, people, commit_version, kit.SECOND)
    changed = (
        kit.SECOND.replace("подають письмово", "подають **письмово**").replace(
            "\nКопію рішення надсилають заявникові того ж дня.\n", ""
        )
        + "\nРеєстр заяв веде відповідальний виконавець.\n"
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
    for style in ("Inserted", "Deleted", "FormatChanged", "ChangeLabel"):
        assert f'w:styleId="{style}"' in styles, style
        assert re.search(rf'<w:rStyle w:val="{style}"\s*/>', body), style
    assert not re.search(r'<w:rStyle w:val="Underline"\s*/>', body)
    assert "лише форматування" in body
