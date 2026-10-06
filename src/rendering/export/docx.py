"""DOCX by Pandoc (ADR-0013): the same HTML the PDF is made from, the platform's classes mapped to
named Word styles by `styles.lua`, their look carried by a reference document; the footer's page
number rewritten in the produced file, and no header (DL-0182, DL-0362).

The reference document is built from Pandoc's own default, once per process: its eight named
styles and an empty footer are added to it. Pandoc never gates an export: it cannot
fail on a missing resource, so the validator has already refused any reference the document
cannot hold.
"""

from __future__ import annotations

import functools
import io
import subprocess
import tempfile
import zipfile
from pathlib import Path

import pypandoc

from rendering.export import furniture

FILTER = Path(__file__).with_name("styles.lua")
FOOTER = "word/footer1.xml"
RELATIONS = "word/_rels/document.xml.rels"
TYPES = "[Content_Types].xml"
PART = "application/vnd.openxmlformats-officedocument.wordprocessingml"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

# The named styles and their look (the reading view's, `document.css`): character styles for the
# spans, the label and a marked export's changes, paragraph styles for the callouts.
STYLES = {
    "Entity Role": ("character", '<w:shd w:val="clear" w:color="auto" w:fill="E6E6E6"/>'),
    "Entity Action": ("character", '<w:shd w:val="clear" w:color="auto" w:fill="E6E6E6"/>'),
    "Entity Term": ("character", '<w:shd w:val="clear" w:color="auto" w:fill="E6E6E6"/>'),
    "Underline": ("character", '<w:u w:val="single"/>'),
    "Clause Number": ("character", '<w:color w:val="C2C2C2"/><w:sz w:val="18"/>'),
    "Inserted": ("character", '<w:shd w:val="clear" w:color="auto" w:fill="DFF0D8"/>'),
    "Deleted": ("character", '<w:strike/><w:shd w:val="clear" w:color="auto" w:fill="F6D6D6"/>'),
    "Format Changed": ("character", '<w:shd w:val="clear" w:color="auto" w:fill="FFF3C4"/>'),
    "Callout Note": ("paragraph", "F3F6F9"),
    "Callout Warning": ("paragraph", "FBF3E4"),
    "Callout Example": ("paragraph", "F4F4F4"),
}


def _style(name: str, kind: str, look: str) -> str:
    identifier = name.replace(" ", "")
    if kind == "character":
        return (
            f'<w:style w:type="character" w:customStyle="1" w:styleId="{identifier}">'
            f'<w:name w:val="{name}"/><w:rPr>{look}</w:rPr></w:style>'
        )
    return (
        f'<w:style w:type="paragraph" w:customStyle="1" w:styleId="{identifier}">'
        f'<w:name w:val="{name}"/><w:basedOn w:val="BodyText"/><w:pPr>'
        f'<w:shd w:val="clear" w:color="auto" w:fill="{look}"/>'
        '<w:ind w:left="284" w:right="284"/></w:pPr></w:style>'
    )


def _pandoc() -> str:
    return str(pypandoc.get_pandoc_path())


@functools.cache
def reference() -> Path:
    """The reference document: Pandoc's default with the named styles and a footer, and no header
    (DL-0362)."""
    default = subprocess.run(  # noqa: S603 — Pandoc's own path and fixed arguments
        [_pandoc(), "--print-default-data-file", "reference.docx"],
        capture_output=True,
        check=True,
    ).stdout
    source = zipfile.ZipFile(io.BytesIO(default))
    styles = "".join(_style(name, kind, look) for name, (kind, look) in STYLES.items())
    built = io.BytesIO()
    with zipfile.ZipFile(built, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == "word/styles.xml":
                data = data.replace(b"</w:styles>", styles.encode("utf-8") + b"</w:styles>")
            elif item.filename == "word/document.xml":
                references = (
                    f'<w:footerReference xmlns:r="{REL}" w:type="default" r:id="rIdFooter1"/>'
                )
                data = data.replace(b"<w:sectPr>", b"<w:sectPr>" + references.encode("utf-8"))
            elif item.filename == RELATIONS:
                added = f'<Relationship Type="{REL}/footer" Id="rIdFooter1" Target="footer1.xml" />'
                data = data.replace(b"</Relationships>", added.encode() + b"</Relationships>")
            elif item.filename == TYPES:
                added = f'<Override PartName="/{FOOTER}" ContentType="{PART}.footer+xml" />'
                data = data.replace(b"</Types>", added.encode() + b"</Types>")
            target.writestr(item, data)
        target.writestr(FOOTER, furniture.docx_footer())
    path = Path(tempfile.mkdtemp(prefix="syngraphe-docx-")) / "reference.docx"
    path.write_bytes(built.getvalue())
    return path


def _furnished(produced: Path, target: Path) -> None:
    """`produced` copied to `target` with its footer part rewritten."""
    with (
        zipfile.ZipFile(produced) as source,
        zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as out,
    ):
        if FOOTER not in source.namelist():
            raise RuntimeError("the produced document carries no footer to fill")
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == FOOTER:
                data = furniture.docx_footer()
            out.writestr(item, data)


def write(html: str, path: Path) -> None:
    """Convert `html` to DOCX at `path`, its pages numbered at the foot. Nothing is written when a
    step fails."""
    with tempfile.TemporaryDirectory(prefix="syngraphe-docx-") as scratch:
        produced = Path(scratch) / "produced.docx"
        # The scratch folder as the only resource path: nothing outside it is ever embedded.
        arguments = [
            f"--lua-filter={FILTER}",
            f"--reference-doc={reference()}",
            f"--resource-path={scratch}",
        ]
        pypandoc.convert_text(
            html, "docx", format="html", outputfile=str(produced), extra_args=arguments
        )
        partial = path.with_name(path.name + ".part")
        try:
            _furnished(produced, partial)
            partial.replace(path)
        finally:
            partial.unlink(missing_ok=True)
