"""The corpus's pages and acts beyond the list: search and the type filter; the type changed on
the *Info* tab; archiving and restoring a document; copying one."""

from __future__ import annotations

import logging
from typing import cast

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import never_cache

from access.views import administers
from documents import types
from documents.forms import CopyForm
from documents.models import DocumentType
from documents.views import readable_document, render_page
from identity.models import User
from shell.views import not_found

logger = logging.getLogger(__name__)

# What each refusal of a type change tells the administrator on the *Info* tab.
TYPE_CHANGE_REFUSALS = {
    "retired": _("A retired type cannot be given to a document."),
    "unchanged": _("The document already has this type."),
    "archived": _("This document is archived — restore it first."),
}


@never_cache
@login_required
def change_type(request: HttpRequest, number: int) -> HttpResponse:
    """`POST` the type `document_type` (a code): back to the *Info* tab; `404` for anyone but an
    administrator, or a document the page's gate refuses; the tab with the refusal and `400`."""
    if not administers(request):
        return not_found(request)
    document = readable_document(request, number, methods=("POST",))
    if document is None:
        return not_found(request)
    kind = DocumentType.objects.filter(code=request.POST.get("document_type", "")).first()
    if kind is None:
        return render_page(request, document, "info", error=str(_("No such type.")), status=400)
    try:
        types.change_type(document, kind, cast(User, request.user))
    except types.TypeRefused as refused:
        if refused.reason == "not_allowed":
            return not_found(request)
        if refused.reason == "gone":
            return render_page(request, document, "info", error=str(_("No such type.")), status=400)
        error = TYPE_CHANGE_REFUSALS[refused.reason]
        return render_page(request, document, "info", error=str(error), status=400)
    return HttpResponseRedirect(f"/document/{document.number}/info/")


@never_cache
@login_required
def search(request: HttpRequest) -> HttpResponse:
    """`GET /search/?q=…&type=…`: the documents found, grouped by folder path, the tree beside them
    cut to their folders, sorted within each group (DL-0197, DL-0207); with neither, the root."""
    from documents import search as finding
    from documents.tree import Tree
    from documents.views import _grouped, _pane, _rows, _sorted, _sorting, is_member

    tenant = getattr(request, "tenant", None)
    if request.method != "GET" or tenant is None or not is_member(request):
        return not_found(request)
    words = finding.query(request.GET.get("q", ""))
    type_code = finding.query(request.GET.get("type", "")) or None
    if not words and type_code is None:
        return HttpResponseRedirect("/folder/1/")
    found = _sorted(request, finding.find(request.user, words, type_code))
    listed = _rows(request.user, found, administrator=administers(request))
    tree = Tree(tenant.name, {d.folder.number for d in found})
    context = {
        **listed,
        **_pane(request, tree, open_all=True),
        **_sorting(request, {"q": words, "type": type_code or ""}),
        "groups": _grouped(listed["rows"], tree),
        "words": words,
        "type_code": type_code or "",
        "types": finding.filter_types(request.user),
    }
    return render(request, "documents/search.html", context)


@never_cache
@login_required
def archive(request: HttpRequest, number: int) -> HttpResponse:
    """`POST`: archive the document — back to its page, which an administrator still reaches."""
    return _archive_act(request, number, restoring=False)


@never_cache
@login_required
def restore(request: HttpRequest, number: int) -> HttpResponse:
    """`POST`: restore the archived document — back to its page."""
    return _archive_act(request, number, restoring=True)


def _archive_act(request: HttpRequest, number: int, *, restoring: bool) -> HttpResponse:
    from documents import archive as archiving
    from documents.locks import LockTimeout
    from review.services import RecordIncomplete

    if not administers(request):
        return not_found(request)
    document = readable_document(request, number, methods=("POST",))
    if document is None:
        return not_found(request)
    page = HttpResponseRedirect(f"/document/{document.number}/")
    act = archiving.restore if restoring else archiving.archive
    try:
        act(document, cast(User, request.user))
    except archiving.ArchiveRefused:
        return not_found(request)
    except LockTimeout:
        messages.error(request, _("The document is busy. Try again in a moment."))
        return page
    except RecordIncomplete:
        messages.error(
            request,
            _("The document's record is incomplete; it cannot be changed until it is repaired."),
        )
        return page
    messages.success(request, _("Restored.") if restoring else _("Archived."))
    return page


# What each refusal of a copy tells the copier in the dialog; `not_allowed` and `archived` answer
# *nothing to show* instead.
COPY_REFUSALS = {
    "changed": _("The version changed since the dialog showed it. Check it and copy again."),
    "unreadable": _("This version cannot be read, so it cannot be copied."),
    "no_such_appendix": _("An appendix chosen is no longer in this version. Choose again."),
}


@never_cache
@login_required
def copy(request: HttpRequest, number: int) -> HttpResponse:
    """The copy dialog, its record read through `_copy`: a source whose record cannot be read
    answers *nothing to show*, logged for the operator, as every page of a document does."""
    from rendering.views import UNREADABLE

    try:
        return _copy(request, number)
    except UNREADABLE:
        logger.exception("a copy's source could not be read", extra={"document": number})
        return not_found(request)


def _copy(request: HttpRequest, number: int) -> HttpResponse:
    """The copy dialog (`pages.md § Create or copy a document`): `GET`, its fields —
    `?version=<view>` choosing the version whose appendices it lists; `POST`, the copy, then its
    page. `404` for anyone but a holder of *create and edit* reading the active source with a
    version to offer; `409` when the version moved, `503` when the copy stopped, the form kept."""
    from access.rights import can_create
    from documents import copying
    from documents.locks import LockTimeout
    from documents.services import ChoiceGone
    from documents.views import CHOICE_GONE
    from review.services import RecordIncomplete

    tenant = getattr(request, "tenant", None)
    source = readable_document(request, number, methods=("GET", "POST"))
    if (
        tenant is None
        or source is None
        or source.state != "active"
        or not can_create(request.user, tenant)
    ):
        return not_found(request)
    choices = copying.offered(cast(User, request.user), source)
    if not choices:
        return not_found(request)
    seen = {
        "organisation": tenant.name,
        "user": request.user,
        "administrator": administers(request),
        "source": source,
    }

    def dialog(form: CopyForm, view: str, *, error: str = "", status: int = 200) -> HttpResponse:
        chosen = copying.default_offer(choices, view)
        listed = copying.listed_appendices(source, chosen)
        posted = set(request.POST.getlist("appendix")) if request.method == "POST" else set()
        context = {
            "form": form,
            "source": source,
            "offers": choices,
            "chosen": chosen,
            "appendices": listed,
            # Every appendix by default: a copy starts as the version it copies.
            "mode": request.POST.get("appendices", "all") if request.method == "POST" else "all",
            # Matched as text against the numbers listed: a posted value is never converted here.
            "ticked": {part for part, _ in listed if str(part) in posted},
            "error": error,
        }
        return render(request, "documents/copy.html", context, status=status)

    if request.method == "GET":
        return dialog(CopyForm(**seen), request.GET.get("version", ""))
    form = CopyForm(request.POST, **seen)
    posted_view = str(request.POST.get("version", "")).partition(":")[0]
    if not form.is_valid():
        return dialog(form, posted_view, status=400)
    data = form.cleaned_data
    try:
        document = copying.copy_document(
            cast(User, request.user),
            source,
            title=data["title"],
            document_type=data["document_type"],
            folder=data["folder"],
            view=data["view"],
            number=data["number"],
            appendices=data["appendices"],
        )
    except copying.CopyRefused as refused:
        if refused.reason in ("not_allowed", "archived"):
            return not_found(request)
        # The offers as they stand now, the posted stance still chosen where it is offered.
        choices[:] = copying.offered(cast(User, request.user), source)
        if not choices:
            return not_found(request)
        status = 409 if refused.reason == "changed" else 400
        return dialog(form, posted_view, error=str(COPY_REFUSALS[refused.reason]), status=status)
    except ChoiceGone as gone:
        form.add_error(gone.field, str(CHOICE_GONE[gone.field]))
        return dialog(form, posted_view, status=400)
    except LockTimeout:
        error = str(_("The document is busy. Try again in a moment."))
        return dialog(form, posted_view, error=error, status=503)
    except RecordIncomplete:
        error = str(
            _("The document's record is incomplete; it cannot be changed until it is repaired.")
        )
        return dialog(form, posted_view, error=error, status=503)
    except copying.CopyStopped as stopped:
        logger.exception("a copy stopped", extra={"document": stopped.number})
        error = str(_("The copy was not finished, and nothing of it can be seen. Copy again."))
        return dialog(form, posted_view, error=error, status=503)
    return HttpResponseRedirect(f"/document/{document.number}/")
