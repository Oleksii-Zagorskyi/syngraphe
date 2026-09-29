"""The help pages (DL-0171, DL-0195): Markdown files shipped with the application, one set per
language, rendered through the same reading rules as the text; and the page of what the editor
accepts, built when it is asked for — its limits, entities, callout types and every refusal with
its conversion taken from the whitelist specification, so the page cannot fall behind it."""

from __future__ import annotations

from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.safestring import mark_safe
from django.utils.translation import get_language
from django.utils.translation import gettext as _

from editing.diffview import RENDERER
from editing.markdown import Spec, load_spec
from editing.messages import CONSTRUCTS, CONVERSIONS, HELP_PAGES, LABELS, SPAN_NAMES
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
    rows.append((_("Images of the document, on a line of their own"), "![…](images/…)"))
    rows.append((_("Links: to the web, to a mailbox, or to a path in the document"),
                 "[…](https://…), […](mailto:…), […](…)"))  # fmt: skip
    return rows


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
    """The list of help pages."""
    if request.method != "GET":
        return not_found(request)
    return render(request, "editing/help.html", {"pages": HELP_PAGES, "current": None})


@login_required
def page(request: HttpRequest, slug: str) -> HttpResponse:
    """One help page: shipped Markdown, or the page of what the editor accepts."""
    if request.method != "GET" or slug not in HELP_PAGES:
        return not_found(request)
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
