"""The corpus's sections of Administration (`pages.md § Administration`): the organisation's
document types; an administrator's alone, every other person answered as for a missing page."""

from __future__ import annotations

from typing import Any, cast

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.db.models.functions import Collate
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import never_cache

from access.views import administers
from documents import types
from documents.models import Document, DocumentType
from identity.models import User
from shell.views import frame, not_found

TYPES_PAGE = "/administration/tenant/document-types/"

# What each refusal of a type's act tells the administrator.
TYPE_REFUSALS = {
    "label_invalid": _("A label is one line of text, at most 100 characters."),
    "label_taken": _("Another type already has this label, perhaps in different capitals."),
    "in_use": _("This type is in use: it can be retired, not deleted."),
    "retired": _("This type is retired."),
    "seeded": _(
        "The type every organisation starts with is kept for documents the platform loads or "
        "recovers: it can be renamed or retired, not deleted."
    ),
    "last_type": _("The organisation's last type not retired can be neither retired nor deleted."),
}
LAST_TYPE = _("the organisation's last type not retired")


@never_cache
@login_required
def document_types(request: HttpRequest) -> HttpResponse:
    """The organisation's types, each with the number of documents carrying it; `POST` with `act`
    — `add`, `rename`, `retire`, `delete` — and `code`, back to the page, or the page again with
    the refusal and `400`."""
    if request.method not in ("GET", "POST") or not administers(request):
        return not_found(request)
    if request.method == "GET":
        return _types_page(request)
    act = request.POST.get("act", "")
    by = cast(User, request.user)
    label = request.POST.get("label", "")
    try:
        if act == "add":
            types.add_type(label, by)
            return HttpResponseRedirect(TYPES_PAGE)
        kind = DocumentType.objects.filter(code=request.POST.get("code", "")).first()
        if kind is None or act not in ("rename", "retire", "delete"):
            return not_found(request)
        if act == "rename":
            types.rename_type(kind, label, by)
        elif act == "retire":
            types.retire_type(kind, by)
        else:
            types.delete_type(kind, by)
    except types.TypeRefused as refused:
        if refused.reason in ("gone", "not_allowed"):
            return not_found(request)
        # What was typed stays in the field it was typed in, for the administrator to correct.
        attempt = {"act": act, "code": request.POST.get("code", ""), "label": label}
        return _types_page(
            request, error=str(TYPE_REFUSALS[refused.reason]), attempt=attempt, status=400
        )
    return HttpResponseRedirect(TYPES_PAGE)


def _types_page(
    request: HttpRequest,
    *,
    error: str = "",
    attempt: dict[str, str] | None = None,
    status: int = 200,
) -> HttpResponse:
    listed = list(DocumentType.objects.order_by(Collate("label", "uk-x-icu"), "code"))
    # Every document row counts, in any state, as the delete's refusal counts it.
    carried = dict(Document.objects.values_list("document_type").annotate(n=Count("id")).order_by())
    unretired = sum(1 for kind in listed if kind.retired_at is None)
    rows: list[dict[str, Any]] = [
        {
            "kind": kind,
            "documents": carried.get(kind.pk, 0),
            "deletable": types.deletable(kind, carried.get(kind.pk, 0)),
            "last": kind.retired_at is None and unretired == 1,
        }
        for kind in listed
    ]
    context = {
        **frame(request),
        "rows": rows,
        "error": error,
        "attempt": attempt or {},
        "last_type": LAST_TYPE,
        "page_url": TYPES_PAGE,
    }
    return render(request, "documents/document_types.html", context, status=status)
