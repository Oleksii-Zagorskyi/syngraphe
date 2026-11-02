"""Administration › styles (ST-0046, DL-0230, DL-0464, DL-0465): the organisation's stylesheet,
edited by its administrators and checked at *Apply*; and the stylesheet served to readers of the
organisation's documents, confined to the document's text."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, cast

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import FileResponse, HttpRequest, HttpResponse
from django.http.response import HttpResponseBase
from django.shortcuts import render
from django.utils import timezone, translation
from django.utils.cache import patch_cache_control
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache

from access.views import administers
from audit.record import record
from documents.views import is_member
from identity.models import User
from rendering.models import ExportFormat, ExportState, SampleExport, Stylesheet
from rendering.stylesheet import FONTS, GENERICS, StyleRefusal, check, digest, served
from shell.views import frame, not_found

logger = logging.getLogger(__name__)

PAGE = "/administration/tenant/styles/"
# A queued sample older than this was never taken: it counts as failed (DL-0466). The `render`
# queue is shared with the exports, each up to its hard limit.
STALE = timedelta(minutes=30)


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
        text = Stylesheet.objects.select_related("updated_by").get().text
        shown = _shown_sample(request)
        # Back from asking for a sample: the box as it was typed, so what was tried is what
        # *Apply* applies (DL-0466); someone else's sample leaves one's own box alone.
        if shown is not None and shown["sample"].requested_by_id == request.user.pk:
            text = shown["sample"].stylesheet
        return _page(request, text)
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
    refused: str = "",
) -> HttpResponse:
    current = Stylesheet.objects.select_related("updated_by").get()
    context: dict[str, Any] = {
        **frame(request),
        "text": text,
        "refusals": [refusal_text(r) for r in refusals or []],
        "not_carried": _not_carried(current.text if not refusals else ""),
        "fonts": FONTS,
        "generics": GENERICS,
        # By address, as every administration page names a person (DL-0434).
        "changed_by": current.updated_by.email if current.updated_by is not None else "",
        "changed_at": current.updated_at if current.updated_by_id else current.created_at,
        "page_url": PAGE,
        "refused": refused,
        "sample": _shown_sample(request),
    }
    return render(request, "rendering/styles.html", context, status=status)


def _shown_sample(request: HttpRequest) -> dict[str, Any] | None:
    """The sample `?sample=` names, with its file while it is kept."""
    from rendering.export.job import artifact

    asked = request.GET.get("sample", "")
    try:
        sample = SampleExport.objects.filter(pk=asked).first() if asked else None
    except (ValueError, ValidationError):
        sample = None
    return {"sample": sample, "file": artifact(sample)} if sample is not None else None


@never_cache
@login_required
def sample(request: HttpRequest) -> HttpResponse:
    """*Export a sample PDF* or *Word file* of the text in the box, never applied (DL-0466):
    checked first; one at a time per organisation, no request waiting behind a render; the row
    written and audited before it is queued, and failed — never reported queued — when the queue
    refuses it."""
    from rendering.tasks import render_sample

    if request.method != "POST" or not administers(request):
        return not_found(request)
    fmt = request.POST.get("format", "")
    text = request.POST.get("text", "").replace("\r\n", "\n")
    if fmt not in (ExportFormat.PDF, ExportFormat.DOCX):
        return _page(request, text, status=400, refused=_("Choose a PDF or a Word file."))
    refusals = check(text)
    if refusals:
        return _page(request, text, refusals=refusals, status=400)
    tenant = getattr(request, "tenant", None)
    assert tenant is not None
    with transaction.atomic():
        Stylesheet.objects.select_for_update(of=("self",)).get()
        busy = _busy()
        if not busy:
            made = _queued_sample(request, fmt, text, tenant)
    # Drawn once the transaction has ended: no lock is held while a page renders.
    if busy:
        return _page(request, text, status=409, refused=_("A sample is being made; wait for it."))
    try:
        render_sample.delay(tenant.number, str(made.pk))
    except Exception as error:
        logger.exception("a sample could not be queued", extra={"sample": str(made.pk)})
        made.state = ExportState.FAILED
        made.failure_reason = _("The sample could not be queued (%(error)s).") % {
            "error": error.__class__.__name__
        }
        made.save(update_fields=["state", "failure_reason"])
    response = HttpResponse(status=303)
    response["Location"] = f"{PAGE}?sample={made.pk}"
    return response


def _unheld(ids: list[Any]) -> set[Any]:
    """Which of `ids` are still queued and held by nobody — the locking read, which never
    waits."""
    return set(
        SampleExport.objects.select_for_update(of=("self",), skip_locked=True)
        .filter(pk__in=ids, state=ExportState.QUEUED)
        .values_list("pk", flat=True)
    )


def _busy() -> bool:
    """Whether a sample is being made, under the stylesheet row's lock. The queued samples read
    twice, neither read waiting: one the plain read finds and the locking read skips is held — by
    the worker rendering it, or finished meanwhile. A queued, unheld one asked longer ago than
    `STALE` was never taken: failed, if it is still queued."""
    queued = list(SampleExport.objects.filter(state=ExportState.QUEUED))
    free = _unheld([waiting.pk for waiting in queued])
    now = timezone.now()
    for waiting in queued:
        if waiting.pk in free:
            if waiting.created_at > now - STALE:
                return True
            SampleExport.objects.filter(pk=waiting.pk, state=ExportState.QUEUED).update(
                state=ExportState.FAILED, failure_reason=_("The sample was not made in time.")
            )
        elif SampleExport.objects.filter(pk=waiting.pk, state=ExportState.QUEUED).exists():
            return True
    return False


def _queued_sample(request: HttpRequest, fmt: str, text: str, tenant: Any) -> SampleExport:
    """The sample's row, written and audited before it is queued."""
    made = SampleExport.objects.create(
        format=fmt,
        stylesheet=text,
        language=translation.get_language() or "",
        requested_by=cast(User, request.user),
    )
    record(
        actor=cast(User, request.user),
        action="stylesheet.sample_requested",
        obj=made,
        before=None,
        after={"format": fmt, "language": made.language},
        tenant=tenant,
    )
    return made


def _sample(request: HttpRequest, sample_id: Any) -> SampleExport | None:
    if not administers(request):
        return None
    return SampleExport.objects.filter(pk=sample_id).first()


@never_cache
@login_required
def sample_status(request: HttpRequest, sample_id: Any) -> HttpResponse:
    """A sample's progress, polled while it is queued, for any administrator of the organisation:
    the sample holds nothing of its documents."""
    from rendering.export.job import artifact

    made = _sample(request, sample_id)
    if made is None:
        return not_found(request)
    context = {"sample": made, "file": artifact(made)}
    return render(request, "rendering/sample_status.html", context)


@never_cache
@login_required
def sample_download(request: HttpRequest, sample_id: Any) -> HttpResponseBase:
    """The sample's file while it is kept."""
    from rendering.export.job import artifact
    from rendering.views import DOWNLOAD_TYPES

    made = _sample(request, sample_id)
    path = artifact(made) if made is not None else None
    if path is None:
        return not_found(request)
    response = FileResponse(
        path.open("rb"),
        as_attachment=True,
        filename=path.name,
        content_type=DOWNLOAD_TYPES.get(path.suffix, "application/octet-stream"),
    )
    response["X-Content-Type-Options"] = "nosniff"
    patch_cache_control(response, private=True)
    return response


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
