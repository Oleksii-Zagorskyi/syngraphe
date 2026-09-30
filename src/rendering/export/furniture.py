"""Page furniture (DL-0182): the header names the document, its version and the stance the export
shows; the footer numbers the page. In PDF it is the page's margin boxes; in DOCX Pandoc takes
headers and footers only from the reference document, so the produced file's header and footer
parts are rewritten after it.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def header_text(title: str, version: str, stance: str) -> str:
    """`Title 2.0 — canonical version`; before any number, the title and the stance alone."""
    named = f"{title} {version}" if version else title
    # No control character reaches a page's margin or a Word part, which refuses them.
    return "".join(c for c in f"{named} — {stance}" if c >= " " and c != "\x7f")


def _css_string(text: str) -> str:
    """`text` as a CSS string: quoted, its backslashes, quotes and line breaks escaped."""
    escaped = "".join(f"\\{ord(c):x} " if c in '\\"\n\r' or ord(c) < 0x20 else c for c in text)
    return f'"{escaped}"'


def pdf_css(header: str) -> str:
    """A4 pages, the header across the top and the page number at the foot; the title page and
    the attachment list each on a page of their own."""
    return (
        "@page { size: A4; margin: 22mm 18mm 20mm 18mm;"
        f" @top-center {{ content: {_css_string(header)}; font: 9pt 'DejaVu Sans', sans-serif;"
        " color: #555; }"
        " @bottom-center { content: counter(page); font: 9pt 'DejaVu Sans', sans-serif;"
        " color: #555; } }"
        # The title page and the attachment list each stand on a page of their own.
        " .title-page { break-after: page; } .attachment-list { break-before: page; }"
    )


def docx_header(header: str) -> bytes:
    """`word/header1.xml` holding the header's text."""
    return (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:hdr xmlns:w="{W}">'
        '<w:p><w:pPr><w:pStyle w:val="Header"/><w:jc w:val="center"/></w:pPr>'
        f'<w:r><w:t xml:space="preserve">{escape(header)}</w:t></w:r></w:p></w:hdr>'
    ).encode()


def docx_footer() -> bytes:
    """`word/footer1.xml` holding the page-number field."""
    return (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:ftr xmlns:w="{W}">'
        '<w:p><w:pPr><w:pStyle w:val="Footer"/><w:jc w:val="center"/></w:pPr>'
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        '<w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>1</w:t></w:r>'
        '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p></w:ftr>'
    ).encode()
