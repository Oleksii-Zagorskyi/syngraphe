"""The help pages (DL-0171, DL-0195): Markdown files shipped with the application, one set per
language, rendered through the same reading rules as the text; and the page of what the editor
accepts, built when it is asked for — its limits, entities, callout types and every refusal with
its conversion taken from the whitelist specification, so the page cannot fall behind it."""

from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.safestring import mark_safe
from django.utils.translation import get_language
from django.utils.translation import gettext as _

from editing.markdown import Spec, load_spec
from editing.messages import CONSTRUCTS, CONVERSIONS, HELP_PAGES, LABELS, SPAN_NAMES
from rendering.renderer import RENDERER
from shell.views import not_found

PAGES = Path(__file__).resolve().parent.parent / "help"
FALLBACK = "en"


def _shipped(slug: str) -> str | None:
    """A shipped page in the interface's language, or in English where it has none."""
    language = (get_language() or FALLBACK).split("-")[0]
    for folder in (language, FALLBACK):
        path = PAGES / folder / f"{slug}.md"
        if path.is_file():
            return path.read_text(encoding="utf-8")
    return None


def accepted(spec: Spec) -> list[tuple[str, str]]:
    """What the editor accepts, and how each is written."""
    rows = [
        (_("Headings, down to level %(depth)s") % {"depth": spec.heading_max_depth},
         "# … " + "#" * spec.heading_max_depth),
        (_("Paragraphs"), _("separated by an empty line")),
        (_("Lists, down to %(depth)s levels") % {"depth": spec.list_max_depth}, "- …, 1. …"),
        (_("Bold, italic"), "**…**, *…*"),
    ]  # fmt: skip
    for kind, takes_id in spec.spans.items():
        if kind == "underline":
            rows.append((_("Underline"), "[…]{.underline}"))
        else:
            name = str(SPAN_NAMES.get(kind, kind))
            written = f"[…]{{.{kind} #…}}" if takes_id else f"[…]{{.{kind}}}"
            rows.append((name, written))
    if spec.quotes:
        rows.append((_("Quotes"), "> …"))
    for kind in spec.callout_types:
        rows.append((str(LABELS.get(kind, kind)), f"> [!{kind}]"))
    tables = _("Tables, not inside another block") if spec.tables_top_level_only else _("Tables")
    rows.append((tables, "| … | … |"))
    folder = _literal_prefix(spec.image_src.pattern)
    images = (
        _("Images of the document, on a line of their own")
        if spec.image_alone
        else _("Images of the document")
    )
    rows.append((images, f"![…]({folder}…)"))
    links = [f"[…]({shown})" for sample, shown in LINK_KINDS if spec.link_schemes.match(sample)]
    rows.append((_("Links"), ", ".join(links)))
    return rows


# One address of each kind a link may take, as it is tested and as the page shows it.
LINK_KINDS = (
    ("https://example.org", "https://…"),
    ("http://example.org", "http://…"),
    ("mailto:someone@example.org", "mailto:…"),
    ("section/part", "…"),
)


def _literal_prefix(pattern: str) -> str:
    """The fixed text a pattern's matches begin with — the image folder of `imageSrc`."""
    match = re.match(r"\^((?:[\w./-]|\\.)*)", pattern)
    return re.sub(r"\\(.)", r"\1", match.group(1)) if match else ""


def refused(spec: Spec) -> list[tuple[str, str]]:
    """What the editor refuses, each once, and what the source view's conversion makes of it."""
    rows: list[tuple[str, str]] = []
    for code, rule in spec.refusals.items():
        row = (str(CONSTRUCTS[code]), str(CONVERSIONS[rule["convert"]]))
        if row not in rows:
            rows.append(row)
    return rows


@login_required
def index(request: HttpRequest) -> HttpResponse:
    """The list of help pages, opened on *Reading a document* — the page every person can use —
    so the index is never an empty page beside its list."""
    if request.method != "GET":
        return not_found(request)
    return page(request, "reading")


@login_required
def page(request: HttpRequest, slug: str) -> HttpResponse:
    """One help page: shipped Markdown, or the page of what the editor accepts."""
    if request.method != "GET" or slug not in HELP_PAGES:
        return not_found(request)
    if settings.HELP_WORK_IN_PROGRESS:
        return _work_in_progress(request)
    context: dict[str, object] = {"pages": HELP_PAGES, "current": slug}
    if slug == "markdown":
        spec = load_spec()
        context |= {"title": HELP_PAGES[slug], "accepted": accepted(spec), "refused": refused(spec)}
    else:
        text = _shipped(slug)
        if text is None:
            return not_found(request)
        context["body"] = mark_safe(RENDERER.render(text))  # noqa: S308 — raw HTML is off
    return render(request, "editing/help.html", context)


def _work_in_progress(request: HttpRequest) -> HttpResponse:
    """The heading and one message in place of every page, until the pages are agreed (DL-0344)."""
    return render(request, "editing/help.html", {"pages": {}, "current": None, "wip": True})
