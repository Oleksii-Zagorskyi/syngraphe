"""The DOCX export (ADR-0013, DL-0182): the platform's classes as named Word styles, each carried
by the text, the numbering definitions, the footer's page number and no header (DL-0362); a
heading's number set as the heading (DL-0363); the images a version shows embedded, and an
oriented photograph turned as its tag says, fitted to the text (DL-11-003); a marked export's
changed image as its pair, both images embedded.

People, groups and titles are synthetic examples; every text is invented.
"""

from __future__ import annotations

import hashlib
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


def exported_docx(
    tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
    pictures: Any,
    shown: list[Any],
) -> str:
    """A canonical version showing `shown`, exported as DOCX; its `word/document.xml`."""
    from django.conf import settings

    people = edition_cast()
    body = kit.FIRST + "".join(p.paragraph for p in shown)
    pictures.canonical_with(
        tenant.number, people, commit_version, body, {p.path: p.data for p in shown}
    )
    client, _ = kit.reader(member_of, link_group, people, [Right.VIEW_CANONICAL], "word")
    response = client.post(
        f"/document/{people.document.number}/export/",
        {"document": "on", "format": "docx", "view": "canonical"},
    )
    assert response.status_code == 302
    job = kit.run_job(tenant.number, exports[-1][1])
    assert job.state == "done", job.failure_reason
    with zipfile.ZipFile(Path(settings.EXPORT_ROOT) / job.artifact_ref) as docx:
        return docx.read("word/document.xml").decode()


def test_docx_embeds_the_images(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
    pictures: Any,
) -> None:
    shown = [pictures.make(1), pictures.make(2)]
    xml = exported_docx(
        migrated_tenant,
        edition_cast,
        member_of,
        link_group,
        commit_version,
        exports,
        kit,
        pictures,
        shown,
    )
    assert xml.count("<pic:pic") == 2


def laid_out(xml: str) -> list[tuple[int, int]]:
    """Each picture's laid-out box, in EMU: its extent widened or narrowed by its effect extent."""
    extents = [(int(a), int(b)) for a, b in re.findall(r'<wp:extent cx="(\d+)" cy="(\d+)"', xml)]
    effects = re.findall(r'<wp:effectExtent b="(-?\d+)" l="(-?\d+)" r="(-?\d+)" t="(-?\d+)"', xml)
    boxes = []
    for (cx, cy), effect in zip(extents, effects, strict=True):
        bottom, left, right, top = (int(v) for v in effect)
        boxes.append((cx + left + right, cy + top + bottom))
    return boxes


def test_an_oriented_photograph_in_a_docx(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
    pictures: Any,
) -> None:
    """The picture takes its geometry from the JPEG's orientation tag (DL-11-003): a quarter turn,
    its laid-out box taller than wide."""
    photo = pictures.make(3, "jpeg", width=40, height=20, orientation=6)
    xml = exported_docx(
        migrated_tenant,
        edition_cast,
        member_of,
        link_group,
        commit_version,
        exports,
        kit,
        pictures,
        [photo],
    )
    [(width, height)] = laid_out(xml)
    assert height > width
    assert re.search(r'<a:xfrm[^>]*\brot="5400000"', xml)


def image_name(data: bytes, ext: str) -> str:
    return f"images/{hashlib.sha256(data).hexdigest()}.{ext}"


@pytest.mark.parametrize(
    ("orientation", "rotation", "flips"),
    [
        (2, None, ' flipH="1"'),
        (3, "10800000", ""),
        (4, None, ' flipV="1"'),
        (5, "16200000", ' flipH="1"'),
        (6, "5400000", ""),
        (7, "5400000", ' flipH="1"'),
        (8, "16200000", ""),
    ],
)
def test_each_orientation_turns_the_picture(
    orientation: int, rotation: str | None, flips: str, invented_image: Any, tmp_path: Path
) -> None:
    """Each EXIF orientation as Word's own geometry: the turn and the flips on the picture, its
    extent the picture's own size, and a quarter turn's laid-out box changed by the effect extent
    — taller than wide for a picture stored wider than tall."""
    from editing import images
    from rendering.export import docx

    data = images.check(invented_image("jpeg", 40, 20, orientation=orientation)).data
    name = image_name(data, "jpg")
    path = tmp_path / "turned.docx"
    docx.write(f'<p><img src="{name}" alt="A photograph"></p>', path, images={name: data})
    with zipfile.ZipFile(path) as produced:
        xml = produced.read("word/document.xml").decode()
    transform = re.search(r"<a:xfrm([^>]*)>", xml)
    assert transform is not None
    assert (f' rot="{rotation}"' if rotation else "") + flips == transform.group(1)
    [(cx, cy)] = [(int(a), int(b)) for a, b in re.findall(r'<wp:extent cx="(\d+)" cy="(\d+)"', xml)]
    [(ax, ay)] = [(int(a), int(b)) for a, b in re.findall(r'<a:ext cx="(\d+)" cy="(\d+)"', xml)]
    assert (cx, cy) == (ax, ay) and cx > cy
    [(width, height)] = laid_out(xml)
    assert (height > width) == (orientation >= 5)


def test_a_turned_picture_fits_the_text(invented_image: Any, tmp_path: Path) -> None:
    """A quarter-turned picture is laid out as the PDF lays it out: at its size, or the text's
    width where it is wider, never past it."""
    from editing import images
    from rendering.export import docx

    data = images.check(invented_image("jpeg", 2400, 600, orientation=6)).data
    wide = images.check(invented_image("png", 4000, 10)).data
    photo, banner = image_name(data, "jpg"), image_name(wide, "png")
    path = tmp_path / "turned.docx"
    html = f'<p><img src="{photo}" alt="A"></p><p><img src="{banner}" alt="B"></p>'
    docx.write(html, path, images={photo: data, banner: wide})
    with zipfile.ZipFile(path) as produced:
        xml = produced.read("word/document.xml").decode()
    (width, height), (text_width, _) = laid_out(xml)
    assert width == text_width
    assert abs(height / width - 4.0) < 0.01


def test_a_marked_export_carries_both_images(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
    pictures: Any,
    settings: Any,
) -> None:
    """The pair's before side read at the baseline, the image the version no longer holds; no
    full-size copy in a file."""
    people = edition_cast()
    old, new = pictures.make(7), pictures.make(8)
    pictures.canonical_with(
        migrated_tenant.number,
        people,
        commit_version,
        kit.FIRST + old.paragraph,
        {old.path: old.data},
    )
    commit_version(
        people.document,
        people["a"],
        kit.FIRST + new.paragraph,
        "edit",
        files={old.path: None, new.path: new.data},
    )
    client, _ = kit.reader(member_of, link_group, people, [Right.VIEW_PENDING], "marked-word")
    response = client.post(
        f"/document/{people.document.number}/export/",
        {
            "document": "on",
            "format": "docx",
            "view": "pending_edits",
            "changes-pending_edits": "marked",
        },
    )
    assert response.status_code == 302
    job = kit.run_job(migrated_tenant.number, exports[-1][1])
    assert job.state == "done", job.failure_reason
    with zipfile.ZipFile(Path(settings.EXPORT_ROOT) / job.artifact_ref) as docx:
        xml = docx.read("word/document.xml").decode()
    assert xml.count("<pic:pic") == 2
    side_by_side(xml)


def side_by_side(xml: str) -> list[str]:
    """The pair as one row of two cells, each holding one picture and its caption; the cells."""
    rows = re.findall(r"<w:tr\b.*?</w:tr>", xml, re.S)
    [row] = [row for row in rows if "<pic:pic" in row]
    cells = re.findall(r"<w:tc>.*?</w:tc>", row, re.S)
    assert len(cells) == 2
    for cell in cells:
        assert cell.count("<pic:pic") == 1 and 'w:val="ImageCaption"' in cell
    return cells


def test_a_pair_stands_side_by_side_within_its_column(invented_image: Any, tmp_path: Path) -> None:
    """A marked export's pair is two pictures beside each other, as on the page: a row of two
    cells, each picture laid out no wider than its cell; a small one at its own size."""
    from editing import images
    from editing.diffview import render_changes
    from rendering.export import docx
    from rendering.renderer import RenderContext

    wide = images.check(invented_image("png", 4000, 1000)).data
    small = images.check(invented_image("png", 40, 30)).data
    old, new = image_name(wide, "png"), image_name(small, "png")
    context = RenderContext(image_url=str, sides=("0.1", "0.2"), full_size=False)
    html = render_changes(
        f"A sentence.\n\n![A plan]({old})\n".encode(),
        f"A sentence.\n\n![A map]({new})\n".encode(),
        context=context,
    )
    path = tmp_path / "pair.docx"
    docx.write(html, path, images={old: wide, new: small})
    with zipfile.ZipFile(path) as produced:
        xml = produced.read("word/document.xml").decode()

    side_by_side(xml)
    (before, before_height), (after, _) = laid_out(xml)
    assert before <= docx.text_width() // 2
    assert abs(before / before_height - 4.0) < 0.01
    assert after == 40 * docx.EMU_PER_PIXEL


def test_pairs_in_table_cells_fit_their_cells(invented_image: Any, tmp_path: Path) -> None:
    """A table cell's image replaced has its pair inside the cell (DL-11-008): a table within the
    cell's table, each picture fitted to its own cell — in every row, not only the first."""
    from editing import images
    from editing.diffview import render_changes
    from rendering.export import docx
    from rendering.renderer import RenderContext

    data = [images.check(invented_image("png", 4000 + n, 1000)).data for n in range(4)]
    names = [image_name(each, "png") for each in data]
    table = "| Plan | Note |\n| --- | --- |\n| ![A]({}) | A note. |\n| ![B]({}) | Another. |\n"
    context = RenderContext(image_url=str, sides=("0.1", "0.2"), full_size=False)
    html = render_changes(
        table.format(names[0], names[1]).encode(),
        table.format(names[2], names[3]).encode(),
        context=context,
    )
    path = tmp_path / "cells.docx"
    docx.write(html, path, images=dict(zip(names, data, strict=True)))
    with zipfile.ZipFile(path) as produced:
        xml = produced.read("word/document.xml").decode()

    boxes = laid_out(xml)
    assert len(boxes) == 4
    for width, height in boxes:
        assert width <= docx.text_width() // 4
        assert abs(width / height - 4.0) < 0.01


def test_the_title_page_carries_its_styles(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
    settings: Any,
) -> None:
    """A centred title page in Word: the title, each detail and the approval in their *Title
    Page* styles' centred twins, the document's own text one detail with its line break, and a
    page break after."""
    import json

    from documents.models import Document, DocumentTemplate
    from identity.models import Language
    from tenancy.schemas import schema_context

    settings.LANGUAGE_CODE = "en"
    people = edition_cast()
    # The title page's words are the document's language (DL-0502); this one reads English.
    Language.objects.get_or_create(code="en", defaults={"label": "English", "actor_kind": "system"})
    with schema_context(migrated_tenant.number):
        Document.objects.filter(pk=people.document.pk).update(language_id="en")
    layout = {"items": ["title", "number", "text", "approval"], "align": "centre"}
    with schema_context(migrated_tenant.number):
        DocumentTemplate.objects.update(title_page_layout=json.dumps(layout))
    kit.switched(
        migrated_tenant.number,
        people,
        title_page=True,
        title_page_text="Register entry: EX-1 (synthetic)\nSecond line",
    )
    kit.canonical(migrated_tenant.number, people, commit_version, kit.FIRST)
    client, _ = kit.reader(member_of, link_group, people, [Right.VIEW_CANONICAL], "docx")
    response = client.post(
        f"/document/{people.document.number}/export/",
        {"document": "on", "format": "docx", "view": "canonical"},
    )
    assert response.status_code == 302
    job = kit.run_job(migrated_tenant.number, exports[0][1])

    with zipfile.ZipFile(Path(settings.EXPORT_ROOT) / job.artifact_ref) as produced:
        document = produced.read("word/document.xml").decode()
        styles = produced.read("word/styles.xml").decode()
    paragraphs = re.findall(r"<w:p>.*?</w:p>|<w:p .*?</w:p>", document, re.S)
    styled = [
        (re.search(r'w:pStyle w:val="([^"]+)"', p) or [None, None])[1]
        for p in paragraphs
        if "EX-1" in p
        or f"#{people.document.number}<" in p
        or people.document.title in p
        or "Approved" in p
    ]
    assert styled[:3] == [
        "TitlePageTitleCentred",
        "TitlePageDetailCentred",
        "TitlePageDetailCentred",
    ]
    assert styled[-1] == "TitlePageApprovalCentred"
    text = next(p for p in paragraphs if "EX-1" in p)
    assert re.search(r"<w:br ?/>", text) and "Second line" in text
    approval = document.index("TitlePageApprovalCentred")
    assert '<w:br w:type="page"/>' in document[approval:]
    for style in (
        "TitlePageTitle",
        "TitlePageDetail",
        "TitlePageApproval",
        "TitlePageTitleCentred",
        "TitlePageDetailCentred",
        "TitlePageApprovalCentred",
    ):
        assert f'w:styleId="{style}"' in styles, style
