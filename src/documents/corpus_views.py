"""The corpus's pages and acts beyond the list: search and the type filter; the type changed on
the *Info* tab."""

from __future__ import annotations

from typing import cast

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import never_cache

from access.views import administers
from documents import types
from documents.models import DocumentType
from documents.views import readable_document, render_page
from identity.models import User
from shell.views import not_found

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
