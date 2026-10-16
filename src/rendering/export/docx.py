"""DOCX by Pandoc (ADR-0013): the same HTML the PDF is made from, the platform's classes mapped to
named Word styles by `styles.lua`, their look carried by a reference document; in the produced
file the footer's page number rewritten, no header (DL-0182, DL-0362), and an oriented
photograph's picture turned as its tag says (DL-11-003).

The reference document is built from Pandoc's own default, once per process: its eight named
styles and an empty footer are added to it. Pandoc never gates an export: it cannot fail on a
missing resource, so nothing it is given may be missing — the validator refuses a remote
reference, and the export job reads every image before Pandoc runs.
"""

from __future__ import annotations

import functools
import io
import re
import subprocess
import tempfile
import zipfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

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


DOCUMENT = "word/document.xml"
# Each EXIF orientation as `(degrees clockwise, flipH, flipV)`; Word flips a picture before it
# turns it.
TURNS = {
    2: (0, True, False),
    3: (180, False, False),
    4: (0, False, True),
    5: (270, True, False),
    6: (90, False, False),
    7: (90, True, False),
    8: (270, False, False),
}
DRAWING = re.compile(r"<w:drawing>.*?</w:drawing>", re.DOTALL)
EMBED = re.compile(r'r:embed="([^"]+)"')
EXTENT = re.compile(r'<wp:extent cx="(\d+)" cy="(\d+)"')
GRAPHIC_EXTENT = re.compile(r'<a:ext cx="(\d+)" cy="(\d+)"')
EFFECT = re.compile(r"<wp:effectExtent[^>]*/>")
RELATION = re.compile(r'<Relationship\b[^>]*\bId="([^"]+)"[^>]*\bTarget="([^"]+)"')
# Pandoc's size for a picture without a resolution of its own: 72 dots an inch, in EMU a pixel.
EMU_PER_PIXEL = 12700


@functools.cache
def text_width() -> int:
    """The widest a picture is laid out, in EMU: what Pandoc gives one far wider than the page."""
    from PIL import Image

    with tempfile.TemporaryDirectory(prefix="syngraphe-docx-") as scratch:
        Image.new("L", (8000, 4)).save(Path(scratch) / "wide.png")
        produced = Path(scratch) / "wide.docx"
        pypandoc.convert_text(
            '<p><img src="wide.png" alt=""></p>',
            "docx",
            format="html",
            outputfile=str(produced),
            extra_args=[f"--reference-doc={reference()}", f"--resource-path={scratch}"],
        )
        with zipfile.ZipFile(produced) as source:
            found = EXTENT.search(source.read(DOCUMENT).decode("utf-8"))
    if found is None:
        raise RuntimeError("Pandoc laid out no picture")
    return int(found.group(1))


def _turned(text: str, data: bytes, turn: tuple[int, bool, bool]) -> str:
    """One drawing of `data` given its turn as Word writes one: the picture's own size in both
    its extents, the turn and the flips on its transform, and a quarter turn's laid-out box —
    widened or narrowed by the effect extent — fitted to the text as the PDF fits it."""
    from editing.images import size

    degrees, flip_h, flip_v = turn
    width, height = size(data)
    produced = EXTENT.search(text)
    per_pixel: float = EMU_PER_PIXEL
    if produced is not None and int(produced.group(1)) < text_width():
        per_pixel = int(produced.group(1)) / width
    quarter = degrees in (90, 270)
    # The width the picture is laid out at: a quarter-turned picture is as wide as it is tall.
    laid = (height if quarter else width) * per_pixel
    scale = min(laid, text_width()) / laid
    cx, cy = round(width * per_pixel * scale), round(height * per_pixel * scale)
    across, down = (cy - cx, cx - cy) if quarter else (0, 0)
    left, top = across // 2, down // 2
    effect = f'<wp:effectExtent b="{down - top}" l="{left}" r="{across - left}" t="{top}" />'
    text = EXTENT.sub(f'<wp:extent cx="{cx}" cy="{cy}"', text, 1)
    text = GRAPHIC_EXTENT.sub(f'<a:ext cx="{cx}" cy="{cy}"', text, 1)
    text = EFFECT.sub(effect, text, 1)
    attributes = "".join(
        [
            f' rot="{degrees * 60000}"' if degrees else "",
            ' flipH="1"' if flip_h else "",
            ' flipV="1"' if flip_v else "",
        ]
    )
    return text.replace("<a:xfrm>", f"<a:xfrm{attributes}>", 1)


def _oriented(source: zipfile.ZipFile, document: str) -> str:
    """`document`'s pictures of an oriented JPEG (DL-0472) given their orientation as Word's own
    geometry, so a photograph stands as the reading view and the PDF stand it (DL-11-003); nothing
    is decoded."""
    from editing.images import orientation

    relations = source.read(RELATIONS).decode("utf-8")
    turned: dict[str, tuple[bytes, tuple[int, bool, bool]]] = {}
    for identifier, target in RELATION.findall(relations):
        part = str(PurePosixPath("word") / target)
        if part in source.namelist():
            data = source.read(part)
            found = orientation(data)
            if found in TURNS:
                turned[identifier] = (data, TURNS[found])

    def turn(drawing: re.Match[str]) -> str:
        embed = EMBED.search(drawing.group(0))
        if embed is None or embed.group(1) not in turned:
            return drawing.group(0)
        data, how = turned[embed.group(1)]
        return _turned(drawing.group(0), data, how)

    return DRAWING.sub(turn, document)


def _furnished(produced: Path, target: Path) -> None:
    """`produced` copied to `target` with its footer part rewritten and its oriented pictures
    turned."""
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
            elif item.filename == DOCUMENT and RELATIONS in source.namelist():
                data = _oriented(source, data.decode("utf-8")).encode("utf-8")
            out.writestr(item, data)


def write(html: str, path: Path, *, images: Mapping[str, bytes] | None = None) -> None:
    """Convert `html` to DOCX at `path`, its pages numbered at the foot, `images` — each by the path
    the HTML names it by — embedded. Nothing is written when a step fails."""
    from documents.images import is_image_path

    with tempfile.TemporaryDirectory(prefix="syngraphe-docx-") as scratch:
        for name, data in (images or {}).items():
            # Only the platform's own image names, so nothing is written outside the scratch.
            if not is_image_path(name):
                raise ValueError(f"not an image of the document: {name!r}")
            target = Path(scratch) / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
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
