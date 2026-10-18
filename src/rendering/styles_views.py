"""Administration › styles (ST-0046, DL-0230, DL-0464, DL-0465): the organisation's stylesheet,
edited by its administrators and checked at *Apply*; and the stylesheet served to readers of the
organisation's documents, confined to the document's text."""

from __future__ import annotations

from typing import Any, cast

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache

from access.views import administers
from audit.record import record
from documents.views import is_member
from identity.models import User
from identity.naming import person
from rendering.models import Stylesheet
from rendering.stylesheet import FONTS, GENERICS, StyleRefusal, check, digest, served
from shell.views import frame, not_found

PAGE = "/administration/tenant/styles/"


def refusal_text(refusal: StyleRefusal) -> str:
    """One refusal as the styles page shows it, by its line."""
    if refusal.code == "too-large":
        return _("The stylesheet is longer than the platform accepts, 100,000 bytes.")
    sentences = {
        "syntax": _("this cannot be read as CSS."),
        "at-rule": _("@%(subject)s is not allowed; only @page and @media print are."),
        "selector": _(
            "the selector %(subject)s is not allowed: it names something outside the "
            "document's text, or the platform's own marks, or takes a form not allowed."
        ),
        "property": _("%(subject)s is not a property a stylesheet may set."),
        "value": _("the value of %(subject)s is not allowed, or is past its bounds."),
        "fetches": _("%(subject)s fetches from outside the platform."),
        "font": _("the font %(subject)s is not installed."),
    }
    what = sentences.get(refusal.code, refusal.code) % {"subject": refusal.subject}
    return _("Line %(line)s: %(what)s") % {"line": refusal.line, "what": what}


@never_cache
@login_required
def styles(request: HttpRequest) -> HttpResponse:
    """The page; `POST` applies the text in the box when it passes the check, audited as
    `stylesheet.changed` with both texts in full, or draws the page again with every refusal and
    `400`, nothing saved. Empty text returns the organisation to the platform's default."""
    if request.method not in ("GET", "POST") or not administers(request):
        return not_found(request)
    if request.method == "GET":
        return _page(request, Stylesheet.objects.select_related("updated_by").get().text)
    # A browser sends a text box's line breaks as CR LF; the stored text is the typed text.
    text = request.POST.get("text", "").replace("\r\n", "\n")
    refusals = check(text)
    if refusals:
        return _page(request, text, refusals=refusals, status=400)
    with transaction.atomic():
        row = Stylesheet.objects.select_for_update(of=("self",)).get()
        before = {"text": row.text}
        row.text = text
        row.updated_by = cast(User, request.user)
        row.save(update_fields=["text", "updated_by", "updated_at"])
        record(
            actor=cast(User, request.user),
            action="stylesheet.changed",
            obj=row,
            before=before,
            after={"text": text},
            tenant=getattr(request, "tenant", None),
        )
    response = HttpResponse(status=303)
    response["Location"] = PAGE
    return response


def _page(
    request: HttpRequest,
    text: str,
    *,
    refusals: list[StyleRefusal] | None = None,
    status: int = 200,
) -> HttpResponse:
    current = Stylesheet.objects.select_related("updated_by").get()
    context: dict[str, Any] = {
        **frame(request),
        "text": text,
        "refusals": [refusal_text(r) for r in refusals or []],
        "not_carried": _not_carried(current.text if not refusals else ""),
        "fonts": FONTS,
        "generics": GENERICS,
        "changed_by": person(current.updated_by) if current.updated_by_id else "",
        "changed_at": current.updated_at if current.updated_by_id else current.created_at,
        "page_url": PAGE,
    }
    return render(request, "rendering/styles.html", context, status=status)


def _not_carried(text: str) -> list[str]:
    """What the Word files cannot carry of the applied stylesheet, by line (DL-0465)."""
    from rendering.reference import derive

    return [
        _("Line %(line)s: %(selector)s — %(prop)s")
        % {"line": u.line, "selector": u.selector, "prop": u.prop}
        for u in derive(text).unmapped
    ]


def served_view(request: HttpRequest, digest_asked: str) -> HttpResponse:
    """The organisation's stylesheet for its readers, `text/css`; cached for good at the address
    of what it serves, and answered fresh at any other address. Nothing to show to anyone who is
    not a reader of the organisation's documents."""
    if request.method != "GET" or getattr(request, "tenant", None) is None:
        return not_found(request)
    if not request.user.is_authenticated or not is_member(request):
        return not_found(request)
    css = served(Stylesheet.objects.get().text)
    response = HttpResponse(css, content_type="text/css; charset=utf-8")
    response["X-Content-Type-Options"] = "nosniff"
    if digest_asked == digest(css):
        response["Cache-Control"] = "private, max-age=31536000, immutable"
    else:
        response["Cache-Control"] = "private, no-cache"
    return response
