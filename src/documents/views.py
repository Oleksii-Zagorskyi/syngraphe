"""The documents' pages."""

from __future__ import annotations

import logging
import uuid
from typing import Any, cast

from django.contrib.auth.decorators import login_required
from django.db.models.functions import Collate
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.views.decorators.cache import never_cache

from access.models import DocumentGroup
from access.rights import Right, can_create, readable, rights_on
from documents.forms import CreateForm
from documents.holds import held_by
from documents.models import ROOT_FOLDER, Document, DocumentState, PartIndex, PartKind, Version
from documents.services import CreationStopped, create_document
from identity.models import User
from shell.views import not_found

logger = logging.getLogger(__name__)


@login_required
def create(request: HttpRequest) -> HttpResponse:
    """The create dialog; a valid POST creates the document and redirects to its address."""
    tenant = getattr(request, "tenant", None)
    if (
        request.method not in ("GET", "POST")
        or tenant is None
        or not can_create(request.user, tenant)
    ):
        return not_found(request)
    organisation = tenant.name
    if request.method == "POST":
        form = CreateForm(request.POST, organisation=organisation)
        if form.is_valid():
            try:
                document = create_document(
                    cast(User, request.user),
                    form.cleaned_data["title"],
                    form.cleaned_data["language"].code,
                    form.cleaned_data["document_type"],
                    form.cleaned_data["folder"],
                )
            except CreationStopped as stopped:
                # The row is kept and the reconciler finishes it; the person keeps what they typed.
                logger.exception("a creation stopped", extra={"document": stopped.number})
                context = {"form": form, "stopped": stopped.number}
                return render(request, "documents/create.html", context, status=503)
            return HttpResponseRedirect(f"/document/{document.number}/")
        return render(request, "documents/create.html", {"form": form}, status=400)
    return render(request, "documents/create.html", {"form": CreateForm(organisation=organisation)})


def _member(request: HttpRequest) -> bool:
    """Someone the resolved organisation's documents are for: an active member, or a platform
    administrator exercising the role (DL-0308)."""
    return getattr(request, "membership", None) is not None or bool(
        getattr(request.user, "acts_as_platform_admin", False)
    )


def _parts(documents: list[Document]) -> dict[Any, set[str]]:
    """The kinds of part each document's latest version lists; the newest version is the one
    committed last, the row written last where two share a second."""
    latest: dict[Any, Any] = {}
    for document_id, version_id in (
        Version.objects.filter(document__in=documents)
        .order_by("document_id", "-committed_at", "-created_at")
        .values_list("document_id", "id")
    ):
        latest.setdefault(document_id, version_id)
    kinds: dict[Any, set[str]] = {pk: set() for pk in latest}
    by_version = {version: document for document, version in latest.items()}
    for version_id, kind in PartIndex.objects.filter(version_id__in=by_version).values_list(
        "version_id", "kind"
    ):
        kinds[by_version[version_id]].add(kind)
    return kinds


@never_cache
@login_required
def folder(request: HttpRequest, number: int) -> HttpResponse:
    """A folder's documents the person may open, by title; the root alone until folders exist."""
    tenant = getattr(request, "tenant", None)
    if request.method != "GET" or tenant is None or number != ROOT_FOLDER or not _member(request):
        return not_found(request)
    documents = list(
        Document.objects.filter(folder__number=number, state=DocumentState.ACTIVE)
        .select_related("document_type")
        .order_by(Collate("title", "uk-x-icu"), "number")
    )
    allowed = readable(request.user, [d.pk for d in documents])
    shown = [d for d in documents if d.pk in allowed]
    parts = _parts(shown)
    rows = [
        {
            "document": document,
            "appendices": PartKind.APPENDIX in parts.get(document.pk, set()),
            "attachments": PartKind.ATTACHMENT in parts.get(document.pk, set()),
        }
        for document in shown
    ]
    context = {"rows": rows, "can_create": can_create(request.user, tenant)}
    return render(request, "documents/list.html", context)


# Looked up in place of a missing number, so a missing document costs what a forbidden one does.
ABSENT = uuid.UUID(int=0)


@never_cache
@login_required
def page(request: HttpRequest, number: int) -> HttpResponse:
    """The document page's *Info* tab, under the header every tab shares (DL-0208)."""
    tenant = getattr(request, "tenant", None)
    if tenant is None or request.method != "GET" or not _member(request):
        return not_found(request)
    document = (
        Document.objects.filter(number=number, state=DocumentState.ACTIVE)
        .select_related("document_type", "folder", "language", "created_by")
        .first()
    )
    allowed = readable(request.user, [document.pk if document is not None else ABSENT])
    if document is None or document.pk not in allowed:
        return not_found(request)
    membership = getattr(request, "membership", None)
    administrator = bool(getattr(request.user, "acts_as_platform_admin", False)) or bool(
        membership and membership.is_tenant_admin
    )
    creator = document.created_by
    # A reader learns who created the document by name; an address only an administrator sees.
    shown = ""
    if creator is not None:
        shown = creator.display_name or (creator.email if administrator else "")
    linked = (
        sorted(
            link.group.name
            for link in DocumentGroup.objects.filter(document=document).select_related("group")
        )
        if administrator
        else []
    )
    context = {
        "document": document,
        "administrator": administrator,
        "creator": shown,
        "linked": linked,
        "can_edit": Right.EDIT in rights_on(request.user, document),
        "holding": held_by(document, request.user),
        "tab": "info",
    }
    return render(request, "documents/page.html", context)
