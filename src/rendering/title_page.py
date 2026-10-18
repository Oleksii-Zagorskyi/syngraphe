"""The export's title page (DL-0164, DL-0360, DL-0462, DL-0475, DL-0476): generated from the
document's details, laid out as the organisation's template chooses — which details, in which
order, aligned how — with the approval line always among them and never reading as approval of a
text that is not approved."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from html import escape
from typing import Any, Literal

from django.utils import formats, timezone
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)

# The details a layout may show, `text` the document's own title-page text; the approval line is
# no choice, only its place.
DETAILS = ("title", "number", "type", "edition", "approver", "approval_date", "text")
APPROVAL = "approval"
ALIGNMENTS = ("left", "centre")


@dataclass(frozen=True)
class Layout:
    items: tuple[str, ...]
    align: Literal["left", "centre"]


# DL-0360's form, with the document's own text after its number where it has one.
DEFAULT = Layout(("title", "number", "text", APPROVAL), "left")


def layout_of(text: str) -> Layout:
    """The stored layout; `DEFAULT` for none, and for one that does not read — logged, never
    failing the export."""
    if not text:
        return DEFAULT
    try:
        data = json.loads(text)
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            raise ValueError("not a layout")
        items = tuple(data["items"])
        align = data["align"]
        known = all(item in (*DETAILS, APPROVAL) for item in items)
        if (
            set(data) != {"items", "align"}
            or not known
            or len(set(items)) != len(items)
            or items.count(APPROVAL) != 1
            or align not in ALIGNMENTS
        ):
            raise ValueError("not a layout")
    except (ValueError, TypeError, KeyError, RecursionError):
        logger.warning("the title page's stored layout does not read; the default form is used")
        return DEFAULT
    return Layout(items, align)


def dump(layout: Layout) -> str:
    """The stored form: empty for `DEFAULT`."""
    if layout == DEFAULT:
        return ""
    return json.dumps({"items": list(layout.items), "align": layout.align})


@dataclass(frozen=True)
class TitleFacts:
    """What a title page may say, already in words; `None` for a detail with nothing to show."""

    title: str
    number: str
    type_label: str
    edition: str | None
    approver: str | None
    approval_date: str | None
    text: str
    approval: str


def facts_for(job: Any, title: str, number: str, text: str = "") -> TitleFacts:
    """The facts of `job`'s document as the exported version `number` stands: the edition from the
    number's major (DL-0183), the approver and the date on the canonical view alone (DL-0475), the
    approval line as DL-0360 words it."""
    from zoneinfo import ZoneInfo

    from django.conf import settings

    from editions.models import Edition
    from identity.naming import person
    from rendering.export.compose import stance
    from rendering.models import ExportView

    # `N.M` and `N.M-X` stand on edition `N.0`, so a job run after a newer edition still names
    # the one it exports.
    major = int(number.split(".", 1)[0])
    edition = (
        Edition.objects.filter(version__document=job.document, number=f"{major}.0")
        .select_related("approved_by")
        .first()
        if major
        else None
    )
    approver = date = None
    if edition is None:
        approval = _("Not yet approved")
    elif job.view == ExportView.CANONICAL:
        approved_at = timezone.localtime(edition.approved_at, ZoneInfo(settings.DISPLAY_TIMEZONE))
        approver = person(edition.approved_by)
        date = formats.date_format(approved_at, "j E Y")
        approval = _("Approved: %(name)s, %(date)s; edition %(number)s") % {
            "name": approver,
            "date": date,
            "number": edition.number,
        }
    else:
        approval = _("Not approved — %(stance)s to edition %(number)s") % {
            "stance": stance(job.view),
            "number": edition.number,
        }
    kind = getattr(job.document, "document_type", None)
    return TitleFacts(
        title=title,
        number=f"#{job.document.number}",
        type_label=str(kind.label) if kind is not None else "",
        edition=edition.number if edition is not None else None,
        approver=approver,
        approval_date=date,
        text=text,
        approval=approval,
    )


def _detail(css: str, words: str) -> str:
    # A paragraph inside the classed block, so Pandoc keeps the class for the Word style.
    return f'<div class="{css}"><p>{escape(words)}</p></div>'


def html(facts: TitleFacts, layout: Layout) -> str:
    """The title page as the export's HTML: each shown item in the layout's order, an item with
    nothing to show left out with its element. The document's text is plain — escaped, its line
    breaks kept — never read as Markdown or HTML (ASR-19)."""
    from documents.bundle import clean_title_page_text

    # Cleaned again where it is drawn: a text written by hand into `document.md` may not be.
    text = clean_title_page_text(facts.text)
    drawn: dict[str, str | None] = {
        "title": f'<h1 class="document-title">{escape(facts.title)}</h1>',
        "number": _detail("document-number", facts.number),
        "type": (
            _detail("document-type", _("Type: %(type)s") % {"type": facts.type_label})
            if facts.type_label
            else None
        ),
        "edition": (
            _detail("document-edition", _("Edition %(number)s") % {"number": facts.edition})
            if facts.edition
            else None
        ),
        "approver": (
            _detail("approver", _("Approved by: %(name)s") % {"name": facts.approver})
            if facts.approver
            else None
        ),
        "approval_date": (
            _detail("approval-date", _("Approval date: %(date)s") % {"date": facts.approval_date})
            if facts.approval_date
            else None
        ),
        "text": (
            '<div class="title-page-text"><p>'
            + "<br>".join(escape(line) for line in text.split("\n"))
            + "</p></div>"
            if text
            else None
        ),
        APPROVAL: _detail("approval", facts.approval),
    }
    shown = "".join(part for item in layout.items if (part := drawn.get(item)))
    return f'<section class="title-page align-{layout.align}">{shown}</section>'
