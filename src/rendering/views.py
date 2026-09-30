"""The *View* tab: the text of the version the reader may see (DL-0209), rendered with its clause
numbers, headed by its number and the canonical edition's (DL-0352); beside it the outline of
that text and the attachments that version lists, in the page's side panes (DL-0356)."""

from __future__ import annotations

import logging
from typing import Any, cast

import pygit2
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.http import FileResponse, HttpRequest, HttpResponse, HttpResponseRedirect
from django.http.response import HttpResponseBase
from django.shortcuts import render
from django.utils import timezone
from django.utils.cache import patch_cache_control
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache

from audit.record import record
from documents import bundle, gitstore
from documents.models import Document
from documents.parts import attachments
from editions.visible import visible as visible_to
from identity.models import User, UserPreference
from identity.views.preferences import (
    OUTLINE_WIDTH,
    OUTLINE_WIDTH_MAX,
    OUTLINE_WIDTH_MIN,
    PANEL_WIDTH,
    PANEL_WIDTH_MAX,
    PANEL_WIDTH_MIN,
)
from rendering.outline import outline
from rendering.renderer import labelled, render_tokens
from shell.views import not_found

logger = logging.getLogger(__name__)

# What a document whose repository or rows disagree raises on the way to its text; the reader is
# answered as for a document that does not exist, and the fault is logged for the operator.
UNREADABLE = (pygit2.GitError, LookupError, ObjectDoesNotExist, ValueError)


def view_context(request: HttpRequest, document: Document) -> dict[str, Any] | None:
    """What the tab shows, or `None` when there is nothing the person may be shown."""
    try:
        visible = visible_to(request.user, document)
        if visible is None:
            return None
        tenant = request.tenant  # type: ignore[attr-defined]
        repo = gitstore.open_repository(tenant.number, document.number)
        text = gitstore.read(repo, "document.md", visible.version.commit_sha).decode("utf-8")
        _, body = bundle.parse(text)
    except UNREADABLE:
        logger.exception("a document's text could not be read", extra={"document": document.number})
        return None
    tokens = labelled(body)
    headings = outline(tokens)
    return {
        "version_number": visible.number,
        "version_stance": visible.stance,
        "canonical_number": visible.canonical,
        "attachments": attachments(visible.version),
        "headings": headings,
        "outline_width": _kept(
            request, "outline_width", OUTLINE_WIDTH, OUTLINE_WIDTH_MIN, OUTLINE_WIDTH_MAX
        ),
        "outline_bounds": (OUTLINE_WIDTH_MIN, OUTLINE_WIDTH_MAX),
        "panel_width": _kept(request, "panel_width", PANEL_WIDTH, PANEL_WIDTH_MIN, PANEL_WIDTH_MAX),
        "panel_bounds": (PANEL_WIDTH_MIN, PANEL_WIDTH_MAX),
        "text": mark_safe(render_tokens(tokens)),  # noqa: S308 — raw HTML is off, every value escaped
    }


def _kept(request: HttpRequest, key: str, default: int, least: int, most: int) -> int:
    """The width the person keeps for a pane, or the default."""
    kept = (
        UserPreference.objects.filter(user=cast(User, request.user), key=key)
        .values_list("value", flat=True)
        .first()
    )
    if kept and kept.isdigit() and least <= int(kept) <= most:
        return int(kept)
    return default


# --- export (DL-0172, DL-0193, DL-0241) --------------------------------------------------------


def _offers_and_parts(user: Any, document: Document) -> tuple[list[Any], bool]:
    """The views the person may export, and whether any offered version has attachments."""
    from documents.models import PartIndex, PartKind
    from rendering.export.compose import offers

    offered = offers(user, document)
    parts = PartIndex.objects.filter(
        version__in=[offer.version for offer in offered], kind=PartKind.ATTACHMENT
    ).exists()
    return offered, parts


@never_cache
@login_required
def export(request: HttpRequest, number: int) -> HttpResponse:
    """The export dialog, and the job it asks for: *what*, *format*, *view* and *changes* by the
    person's rights; a request writes the job row, then queues it, then shows its progress."""
    from documents.views import readable_document

    document = readable_document(request, number, methods=("GET", "POST"))
    if document is None:
        return not_found(request)
    try:
        offered, parts = _offers_and_parts(request.user, document)
    except UNREADABLE:
        logger.exception("a document's versions could not be read", extra={"document": number})
        return not_found(request)
    if not offered:
        return not_found(request)
    context: dict[str, Any] = {"document": document, "offers": offered, "parts": parts}
    if request.method == "GET":
        return render(request, "rendering/export.html", context)
    chosen = _chosen(request, offered, parts)
    if isinstance(chosen, str) or _waiting(request, document):
        # One export at a time per person and document: a second waits for the first.
        if not isinstance(chosen, str):
            chosen = _("Your previous export of this document is still being made.")
        context["refusal"] = chosen
        return render(request, "rendering/export.html", context, status=400)
    job = _queued(request, document, chosen)
    if job is None:
        context["refusal"] = _("Your previous export of this document is still being made.")
        return render(request, "rendering/export.html", context, status=400)
    return HttpResponseRedirect(f"/document/{document.number}/export/{job.pk}/")


def _waiting(request: HttpRequest, document: Document) -> bool:
    from documents.reconcile import EXPORT_ABANDONED
    from rendering.models import ExportJob, ExportState

    recent = timezone.now() - EXPORT_ABANDONED
    return ExportJob.objects.filter(
        document=document,
        requested_by=cast(User, request.user),
        state=ExportState.QUEUED,
        created_at__gte=recent,
    ).exists()


def _has_attachments(version: Any) -> bool:
    from documents.models import PartIndex, PartKind

    return PartIndex.objects.filter(version=version, kind=PartKind.ATTACHMENT).exists()


def _chosen(request: HttpRequest, offered: list[Any], parts: bool) -> dict[str, Any] | str:
    """What the form chose, checked against what was offered; a message where it cannot stand."""
    from rendering.models import ExportChanges, ExportFormat

    by_view = {offer.view.value: offer for offer in offered}
    offer = by_view.get(request.POST.get("view", ""))
    fmt = request.POST.get("format", "")
    include_document = request.POST.get("document") == "on"
    include_attachments = parts and request.POST.get("attachments") == "on"
    if offer is None or fmt not in ExportFormat.values:
        return _("Choose a view and a format.")
    if not include_document and not include_attachments:
        return _("Nothing is chosen to export.")
    if include_attachments and not _has_attachments(offer.version):
        if not include_document:
            return _("The chosen version has no attachments: nothing is left to export.")
        return _("The chosen version has no attachments; untick them to export the document.")
    marked = (
        include_document
        and request.POST.get(f"changes-{offer.view.value}") == ExportChanges.MARKED
        and offer.baseline is not None
        and fmt != ExportFormat.MARKDOWN
    )
    return {
        "offer": offer,
        "format": fmt,
        "document": include_document,
        "attachments": include_attachments,
        "changes": ExportChanges.MARKED if marked else ExportChanges.CLEAN,
    }


def _queued(request: HttpRequest, document: Document, chosen: dict[str, Any]) -> Any:
    """The job written, audited, and queued once its row is committed."""
    from django.db import transaction

    from rendering.models import ExportChanges, ExportJob
    from rendering.tasks import render_export

    tenant = request.tenant  # type: ignore[attr-defined]
    offer = chosen["offer"]
    marked = chosen["changes"] == ExportChanges.MARKED
    with transaction.atomic():
        # One export at a time per person and document: the check and the insert under the
        # person's own row, so two requests at once cannot both pass it.
        User.objects.select_for_update().filter(pk=cast(User, request.user).pk).first()
        if _waiting(request, document):
            return None
        job = ExportJob.objects.create(
            document=document,
            version=offer.version,
            include_document=chosen["document"],
            include_attachments=chosen["attachments"],
            format=chosen["format"],
            view=offer.view,
            changes=chosen["changes"],
            baseline_version=offer.baseline if marked else None,
            requested_by=cast(User, request.user),
        )
        record(
            actor=cast(User, request.user),
            action="document.exported",
            obj=document,
            before=None,
            after={
                "number": document.number,
                "export": str(job.pk),
                "view": offer.view.value,
                "format": job.format,
                "changes": job.changes,
                "commit": offer.version.commit_sha,
            },
            tenant=tenant,
        )
        job_id = str(job.pk)
        transaction.on_commit(lambda: render_export.delay(tenant.number, job_id))
    return job


def _own_job(request: HttpRequest, number: int, job_id: str) -> Any:
    """The person's own job on a document they may read, or `None`."""
    from documents.views import readable_document
    from rendering.models import ExportJob

    document = readable_document(request, number)
    if document is None:
        return None
    from rendering.export.compose import still_permitted

    try:
        job = ExportJob.objects.select_related("document", "requested_by").get(
            pk=job_id, document=document, requested_by=cast(User, request.user)
        )
    except (ExportJob.DoesNotExist, ValueError, ValidationError):
        return None
    # A right lost since the job was asked for takes its file with it.
    try:
        return job if still_permitted(job) else None
    except UNREADABLE:
        return None


@never_cache
@login_required
def export_status(request: HttpRequest, number: int, job_id: str) -> HttpResponse:
    """A job's progress: polled while it is queued, the download once done, the reason if it
    failed. Only its requester sees it."""
    from rendering.export.job import artifact

    job = _own_job(request, number, job_id)
    if job is None:
        return not_found(request)
    context = {"document": job.document, "job": job, "file": artifact(job)}
    template = "rendering/export_status.html" if request.htmx else "rendering/export_job.html"  # type: ignore[attr-defined]
    return render(request, template, context)


@never_cache
@login_required
def export_download(request: HttpRequest, number: int, job_id: str) -> HttpResponseBase:
    """The job's file under its name, while it is kept."""
    from rendering.export.job import artifact

    job = _own_job(request, number, job_id)
    path = artifact(job) if job is not None else None
    if path is None:
        return not_found(request)
    response = FileResponse(path.open("rb"), as_attachment=True, filename=path.name)
    response["X-Content-Type-Options"] = "nosniff"
    patch_cache_control(response, private=True)
    return response
