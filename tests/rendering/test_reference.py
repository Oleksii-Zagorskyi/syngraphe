"""The Word reference document, derived from the organisation's stylesheet (DL-0465, ADR-0013):
a fixed mapping of selectors and properties to Word's named styles and the page; what cannot map
listed; nothing of the stylesheet's text copied into the file; the approval's style out of reach.

People and stylesheets are synthetic examples."""

from __future__ import annotations

import io
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import pytest

from access.rights import Right
from tenancy.schemas import schema_context

SHEET = (
    'h1 { font-family: "DejaVu Serif"; font-size: 16pt; color: #1F3864 }\n'
    ".callout-warning { background: #FFF0E0 }\n"
    "@page { size: A4; margin: 20mm }\n"
    "li { letter-spacing: 1px }\n"
    "h2 { letter-spacing: 1pt }\n"
)


def _style(styles: str, identifier: str) -> str:
    found = re.search(
        rf'<w:style\b[^>]*w:styleId="{identifier}"[^>]*>.*?</w:style>', styles, re.DOTALL
    )
    assert found is not None, identifier
    return found.group(0)


def _part(data: bytes, name: str) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as source:
        return source.read(name).decode("utf-8")


@pytest.mark.fast
def test_the_mapping_carries_what_word_can_hold() -> None:
    from rendering.reference import derive

    derived = derive(SHEET)

    heading = derived.styles["Heading1"]
    assert 'w:ascii="DejaVu Serif"' in heading.run["rFonts"]
    assert heading.run["sz"] == '<w:sz w:val="32"/>'
    assert heading.run["color"] == '<w:color w:val="1F3864"/>'
    assert 'w:fill="FFF0E0"' in derived.styles["CalloutWarning"].paragraph["shd"]
    assert derived.section is not None
    assert 'w:w="11906"' in derived.section.paragraph["pgSz"]
    assert 'w:top="1134"' in derived.section.paragraph["pgMar"]
    assert [(u.line, u.selector, u.prop) for u in derived.unmapped] == [
        (4, "li", "letter-spacing"),
        (5, "h2", "letter-spacing"),
    ]


@pytest.mark.fast
def test_the_reference_document_is_derived(tmp_path: Path, monkeypatch: Any) -> None:
    from rendering.export import docx

    default = subprocess.run(  # noqa: S603 — Pandoc's own path and fixed arguments
        [docx._pandoc(), "--print-default-data-file", "reference.docx"],
        capture_output=True,
        check=True,
    ).stdout
    pandoc_styles = _part(default, "word/styles.xml")
    expected = pandoc_styles.replace(
        "</w:styles>",
        "".join(docx._style(n, k, look) for n, (k, look) in docx.STYLES.items()) + "</w:styles>",
    )

    plain = docx.reference("")
    derived = docx.reference(SHEET)

    # With no stylesheet: Pandoc's own styles, the platform's appended, nothing else changed.
    assert _part(plain, "word/styles.xml") == expected
    styles = _part(derived, "word/styles.xml")
    heading = _style(styles, "Heading1")
    assert 'w:ascii="DejaVu Serif"' in heading and '<w:sz w:val="32"/>' in heading
    assert '<w:color w:val="1F3864"/>' in heading
    # Pandoc's own properties of the style kept where the sheet sets nothing.
    assert "<w:keepNext" in heading and "<w:outlineLvl" in heading
    assert 'w:fill="FFF0E0"' in _style(styles, "CalloutWarning")
    section = _part(derived, "word/document.xml")
    assert 'w:w="11906"' in section and 'w:h="16838"' in section
    # Nothing of the sheet's own text reaches the file.
    assert "#1F3864" not in styles and 'DejaVu Serif"' not in styles.replace('="DejaVu Serif"', "")
    # A conversion leaves no derived file behind: its temporary folder, of this test alone,
    # is empty once it has written.
    own = tmp_path / "temporary"
    own.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(own))
    docx.write("<p>A synthetic paragraph.</p>", tmp_path / "out.docx", stylesheet=SHEET + " ")
    assert list(own.iterdir()) == []


@pytest.mark.fast
def test_the_approval_style_is_out_of_reach() -> None:
    from rendering.export import docx

    sheet = "body, p, .title-page { color: #fefefe; font-size: 6pt; text-align: right }\n"
    styles = _part(docx.reference(sheet), "word/styles.xml")

    approval = _style(styles, "TitlePageApproval")
    assert "<w:basedOn" not in approval
    assert '<w:color w:val="000000"/>' in approval and '<w:sz w:val="22"/>' in approval
    assert "FEFEFE" not in approval.upper() and 'w:val="right"' not in approval
    for carried in ("Normal", "BodyText", "TitlePageTitle", "TitlePageDetail"):
        style = _style(styles, carried)
        assert '<w:color w:val="FEFEFE"/>' in style, carried
        assert '<w:sz w:val="12"/>' in style, carried
        assert '<w:jc w:val="right"/>' in style, carried


@pytest.mark.integration
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_an_export_uses_the_derived_reference(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
    settings: Any,
) -> None:
    import pypandoc

    from rendering.models import Stylesheet

    with schema_context(migrated_tenant.number):
        Stylesheet.objects.update(text=SHEET)
    people = edition_cast()
    kit.canonical(migrated_tenant.number, people, commit_version, kit.FIRST)
    client, _ = kit.reader(member_of, link_group, people, [Right.VIEW_CANONICAL], "docx")
    asked = client.post(
        f"/document/{people.document.number}/export/",
        {"document": "on", "format": "docx", "view": "canonical"},
    )
    assert asked.status_code == 302
    job = kit.run_job(migrated_tenant.number, exports[0][1])

    produced = Path(settings.EXPORT_ROOT) / job.artifact_ref
    styles = _part(produced.read_bytes(), "word/styles.xml")
    # Pandoc writes the produced file's XML in its own spacing.
    assert re.search(r'<w:color w:val="1F3864" ?/>', _style(styles, "Heading1"))
    assert "A request for approval" in pypandoc.convert_file(str(produced), "plain", format="docx")


@pytest.mark.integration
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_the_styles_page_lists_what_is_not_carried(
    migrated_tenant: Any, member_of: Any, settings: Any
) -> None:
    import html

    from rendering.models import Stylesheet

    settings.LANGUAGE_CODE = "en"
    admin, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    with schema_context(migrated_tenant.number):
        Stylesheet.objects.update(text=SHEET)

    page = html.unescape(admin.get("/administration/tenant/styles/").content.decode())

    assert "Not carried into Word files" in page
    assert "Line 4: li — letter-spacing" in page
    assert "Line 5: h2 — letter-spacing" in page


@pytest.mark.fast
def test_the_page_keeps_the_footer_first() -> None:
    """The section's children in the order Word's schema gives them: the footer, carrying the
    page number, before the page's size and margins."""
    from rendering.export import docx

    section = _part(
        docx.reference("@page { size: A5 landscape; margin-top: 20mm }\n"), "word/document.xml"
    )

    order = [
        section.index(tag) for tag in ("<w:footerReference", "<w:footnotePr", "<w:pgSz", "<w:pgMar")
    ]
    assert order == sorted(order)
    assert 'w:orient="landscape"' in section


@pytest.mark.fast
def test_pictures_are_fitted_to_the_derived_page(tmp_path: Path, monkeypatch: Any) -> None:
    """A narrower page in the stylesheet narrows the width pictures are fitted to — a turned
    photograph's and a picture's in a table cell, as Pandoc's own fit already is."""
    from rendering.export import docx

    narrow = "@page { size: A5; margin: 12mm }\n"
    assert docx.text_width(narrow) < docx.text_width()
    given: list[int] = []
    real = docx._furnished

    def recorded(produced: Path, target: Path, width: int) -> None:
        given.append(width)
        real(produced, target, width)

    monkeypatch.setattr(docx, "_furnished", recorded)
    docx.write("<p>A synthetic paragraph.</p>", tmp_path / "narrow.docx", stylesheet=narrow)

    assert given == [docx.text_width(narrow)]


@pytest.mark.fast
def test_a_vertical_auto_margin_is_carried_as_none() -> None:
    from rendering.reference import derive

    derived = derive("h1 { margin-top: auto; margin-bottom: auto }\n")

    assert derived.styles["Heading1"].spacing == {"w:before": "0", "w:after": "0"}
    assert derived.unmapped == []


@pytest.mark.fast
def test_a_paragraphs_spacing_never_takes_a_runs() -> None:
    from rendering.reference import Derived, Look, overlay

    style = (
        '<w:styles><w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="h"/>'
        '<w:rPr><w:spacing w:val="20"/></w:rPr></w:style></w:styles>'
    )
    derived = Derived({"Heading1": Look(spacing={"w:before": "240"})}, None, [])

    styles, _document = overlay(style, "<w:document/>", derived)

    assert '<w:pPr><w:spacing w:before="240"/></w:pPr>' in styles
    assert '<w:rPr><w:spacing w:val="20"/></w:rPr>' in styles


@pytest.mark.fast
@pytest.mark.parametrize("margin", ["1mm 20mm", "5mm"])
def test_a_horizontal_margin_is_listed_as_not_carried(margin: str) -> None:
    """Word's paragraph styles take the vertical sides alone; the horizontal ones are named on
    the styles page, never dropped in silence."""
    from rendering.reference import derive

    derived = derive(f"h1 {{ margin: {margin} }}\n")

    assert "w:before" in derived.styles["Heading1"].spacing
    assert [(u.line, u.selector, u.prop) for u in derived.unmapped] == [(1, "h1", "margin")]


@pytest.mark.fast
def test_a_vertical_margin_shorthand_is_carried_whole() -> None:
    from rendering.reference import derive

    derived = derive("h1 { margin: 2mm 0 }\nh2 { margin: 2mm auto }\n")

    assert derived.unmapped == []


@pytest.mark.fast
@pytest.mark.parametrize(
    ("declaration", "drawn"),
    [
        ("border-left: 0 solid #ff0000", False),
        ("border-left: #ff0000", False),
        ("border-left: 2pt", False),
        ("border-left: none", False),
        ("border-left: 2pt solid #ff0000", True),
        ("border-left: solid", True),
    ],
)
def test_a_border_is_drawn_in_word_only_where_css_draws_it(declaration: str, drawn: bool) -> None:
    """A border CSS does not draw — no style, or no width — is none in Word too."""
    from rendering.reference import derive

    derived = derive(f".callout-note {{ {declaration} }}\n")

    border = derived.styles["CalloutNote"].paragraph["pBdr"]
    if drawn:
        assert re.search(r'w:val="single" w:sz="[1-9]', border), border
    else:
        assert 'w:val="none"' in border, border


@pytest.mark.fast
def test_a_marks_words_keep_the_platforms_ink_in_word() -> None:
    """Text coloured like a mark's own shading would vanish inside it: the three marks' styles
    set their ink, as the platform's sheet does for the reading view (DL-0477)."""
    from rendering.export import docx

    sheet = "p { color: #f6d6d6 }\nh1 { color: #dff0d8 }\n"
    styles = _part(docx.reference(sheet), "word/styles.xml")

    for mark in ("Inserted", "Deleted", "FormatChanged"):
        assert '<w:color w:val="222222"/>' in _style(styles, mark), mark
    assert '<w:color w:val="F6D6D6"/>' in _style(styles, "BodyText")
