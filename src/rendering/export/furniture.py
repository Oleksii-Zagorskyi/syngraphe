"""Page furniture (DL-0182, DL-0362): the footer numbers the page, and no page carries a header —
the title, the version and the stance stand on the title page and in the file's name. In PDF the
number is a page margin box; in DOCX Pandoc takes a footer only from the reference document, so
the produced file's footer part is rewritten after it. `header_text` still names the export, as
its HTML title and its PDF's title.
"""

from __future__ import annotations

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


def pdf_css() -> str:
    """A4 pages, the page number at the foot and nothing at the head (DL-0362), a narrow left
    margin beside the gutter (DL-0363); the title page and the attachment list each on a page of
    their own, and each embedded appendix starting one."""
    return (
        "@page { size: A4; margin: 18mm 18mm 20mm 10mm;"
        " @bottom-center { content: counter(page); font: 9pt 'DejaVu Sans', sans-serif;"
        " color: #555; } }"
        # The title page and the attachment list each stand on a page of their own.
        " .title-page { break-after: page; } .attachment-list { break-before: page; }"
        " .appendix { break-before: page; }"
        # On paper a change of formatting is marked by its colour; its words are the screen's.
        " .document-text .format-changed::after { content: none; }"
    )


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
