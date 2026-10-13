"""The documents' pages."""

from __future__ import annotations

import logging
import uuid
from typing import Any, cast

from django.contrib.auth.decorators import login_required
from django.db.models.functions import Collate
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.utils.cache import patch_cache_control
from django.utils.http import content_disposition_header
from django.utils.translation import pgettext_lazy
from django.views.decorators.cache import never_cache

from access.models import DocumentGroup
from access.rights import (
    BEYOND_CANONICAL,
    Right,
    can_create,
    holds_anywhere,
    readable,
    rights_on,
    rights_on_many,
)
from audit.record import record
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


def is_member(request: HttpRequest) -> bool:
    """Someone the resolved organisation's documents are for: an active member, or a platform
    administrator exercising the role (DL-0308)."""
    return getattr(request, "membership", None) is not None or bool(
        getattr(request.user, "acts_as_platform_admin", False)
    )


def _parts(versions: dict[Any, Version]) -> dict[Any, set[str]]:
    """The kinds of part each document's shown version lists, in one query: the version the row's
    numbers name, so every cell of a row describes the same text (DL-0209)."""
    by_version = {version.pk: document for document, version in versions.items()}
    kinds: dict[Any, set[str]] = {pk: set() for pk in versions}
    for version_id, kind in PartIndex.objects.filter(version_id__in=by_version).values_list(
        "version_id", "kind"
    ):
        kinds[by_version[version_id]].add(kind)
    return kinds


def _versions(user: Any, documents: list[Document]) -> dict[Any, Any]:
    """What each listed document shows `user`, from `editions.visible`; a document whose record
    cannot be read shows nothing of it and is logged, never failing the list."""
    from editions.visible import visible_many
    from rendering.views import UNREADABLE

    try:
        return visible_many(user, documents)
    except UNREADABLE:
        logger.exception("a list's versions could not be read, document by document")
    shown: dict[Any, Any] = {}
    for document in documents:
        try:
            shown |= visible_many(user, [document])
        except UNREADABLE:
            logger.exception(
                "a document's version could not be read", extra={"document": document.number}
            )
            shown[document.pk] = None
    return shown


def _canonical(seen: Any) -> str:
    """The *Canonical* cell: the latest edition's number (DL-0208)."""
    return (seen.canonical or "") if seen is not None else ""


def _latest(seen: Any) -> str:
    """The *Latest* cell: the number of the latest version beyond the edition the person may
    see, empty when what they see is the edition (DL-0209)."""
    return seen.number if seen is not None and seen.stance != "canonical" else ""


@never_cache
@login_required
def folder(request: HttpRequest, number: int) -> HttpResponse:
    """A folder's documents the person may open, by title; the root alone until folders exist."""
    tenant = getattr(request, "tenant", None)
    if request.method != "GET" or tenant is None or number != ROOT_FOLDER or not is_member(request):
        return not_found(request)
    documents = list(
        Document.objects.filter(folder__number=number, state=DocumentState.ACTIVE)
        .select_related("document_type")
        .order_by(Collate("title", "uk-x-icu"), "number")
    )
    allowed = readable(request.user, [d.pk for d in documents])
    shown = [d for d in documents if d.pk in allowed]
    context = {**_rows(request.user, shown), "can_create": can_create(request.user, tenant)}
    return render(request, "documents/list.html", context)


def _rows(user: Any, shown: list[Document], seen: Any = None) -> dict[str, Any]:
    """A list's rows — the numbers, the parts and the state tags of each document — and whether
    the *Latest* column is drawn; shared by the folder and the two views."""
    seen = _versions(user, shown) if seen is None else seen
    parts = _parts({pk: s.version for pk, s in seen.items() if s is not None})
    # The state tags after the title, each to those it concerns (DL-0233, DL-0351).
    from review.state import LABELS, tags

    shown_tags = tags(user, shown)
    rows = [
        {
            "document": document,
            "canonical": _canonical(seen.get(document.pk)),
            "latest": _latest(seen.get(document.pk)),
            "appendices": PartKind.APPENDIX in parts.get(document.pk, set()),
            "attachments": PartKind.ATTACHMENT in parts.get(document.pk, set()),
            "tags": [
                {"state": tag, "label": LABELS[tag]} for tag in shown_tags.get(document.pk, [])
            ],
        }
        for document in shown
    ]
    # Drawn only for someone who may see beyond canonical text on a listed document (DL-0233).
    beyond = rights_on_many(user, [d.pk for d in shown])
    return {
        "rows": rows,
        "latest_column": any(held & BEYOND_CANONICAL for held in beyond.values()),
    }


def _active_documents() -> list[Document]:
    return list(
        Document.objects.filter(state=DocumentState.ACTIVE)
        .select_related("document_type", "folder")
        .order_by(Collate("title", "uk-x-icu"), "number")
    )


def _holding(user: Any, right: Right) -> list[Document]:
    documents = _active_documents()
    rights = rights_on_many(user, [d.pk for d in documents])
    return [d for d in documents if right in rights.get(d.pk, frozenset())]


def in_review_documents(user: Any) -> list[Document]:
    """The documents awaiting review that `user` may accept (DL-0197), frozen ones included: the
    list's own tags decide, so a freeze hides no run (DL-0351) and an unreadable record is left
    out and logged."""
    from review.state import State, tags

    mine = _holding(user, Right.ACCEPT)
    shown = tags(user, mine)
    return [d for d in mine if State.AWAITING_REVIEW in shown[d.pk]]


def in_edit_documents(user: Any) -> tuple[list[Document], dict[Any, Any]]:
    """The documents `user` may edit whose text they read lies beyond the latest edition, and
    what each shows them (DL-0197)."""
    mine = _holding(user, Right.EDIT)
    seen = _versions(user, mine)
    beyond = [d for d in mine if seen.get(d.pk) is not None and seen[d.pk].stance != "canonical"]
    return beyond, seen


def any_in_review(user: Any) -> bool:
    """Whether *In review* lists anything for `user`, stopping at the first document: what the
    menu draws on every page."""
    from review.state import any_awaiting

    return any_awaiting(_holding(user, Right.ACCEPT))


def any_in_edit(user: Any) -> bool:
    """Whether *In edit* lists anything for `user`, stopping at the first document. *edit*
    implies *view pending*, so the text read is the latest content version."""
    from editions.visible import any_beyond_edition

    return any_beyond_edition(_holding(user, Right.EDIT))


def _view(request: HttpRequest, right: Right) -> HttpResponse | None:
    if (
        request.method != "GET"
        or getattr(request, "tenant", None) is None
        or not is_member(request)
        or not holds_anywhere(request.user, right)
    ):
        return not_found(request)
    return None


def _grouped(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The rows under one heading per folder: the root alone until folders exist, when the
    groups take their folder's path as heading and its alphabetical order (DL-0207)."""
    groups: dict[Any, dict[str, Any]] = {}
    for row in rows:
        folder = row["document"].folder
        groups.setdefault(folder.pk, {"folder": folder, "rows": []})["rows"].append(row)
    return sorted(groups.values(), key=lambda group: group["folder"].number)


@never_cache
@login_required
def in_review(request: HttpRequest) -> HttpResponse:
    """*In review*: the documents awaiting review the person may accept, by folder."""
    refused = _view(request, Right.ACCEPT)
    if refused is not None:
        return refused
    documents = in_review_documents(request.user)
    # The menu draws its link from this answer rather than reading the view again.
    cast(Any, request).views_found = {"in_review": bool(documents)}
    listed = _rows(request.user, documents)
    context = {**listed, "groups": _grouped(listed["rows"]), "view": "in-review"}
    return render(request, "documents/view_list.html", context)


@never_cache
@login_required
def in_edit(request: HttpRequest) -> HttpResponse:
    """*In edit*: the documents the person may edit with versions beyond the latest edition."""
    refused = _view(request, Right.EDIT)
    if refused is not None:
        return refused
    documents, seen = in_edit_documents(request.user)
    cast(Any, request).views_found = {"in_edit": bool(documents)}
    listed = _rows(request.user, documents, seen)
    context = {**listed, "groups": _grouped(listed["rows"]), "view": "in-edit"}
    return render(request, "documents/view_list.html", context)


# Looked up in place of a missing number, so a missing document costs what a forbidden one does.
ABSENT = uuid.UUID(int=0)
# The *Info* tab's name for each derived state, by the state's value (`review.state.State`).
INFO_STATES = {
    "frozen": pgettext_lazy("document state", "frozen"),
    "canonical": pgettext_lazy("document state", "canonical"),
    "accepted": pgettext_lazy("document state", "accepted"),
    "awaiting_review": pgettext_lazy("document state", "awaiting review"),
    "no_reviewer_assigned": pgettext_lazy("document state", "no reviewer assigned"),
}


def readable_document(
    request: HttpRequest, number: int, *, methods: tuple[str, ...] = ("GET",)
) -> Document | None:
    """The document page's gates, in their order: an organisation, the method, a member, the
    document active and readable. `None` wherever the answer is *nothing to show*."""
    tenant = getattr(request, "tenant", None)
    if tenant is None or request.method not in methods or not is_member(request):
        return None
    document = (
        Document.objects.filter(number=number, state=DocumentState.ACTIVE)
        .select_related("document_type", "folder", "language", "created_by")
        .first()
    )
    allowed = readable(request.user, [document.pk if document is not None else ABSENT])
    if document is None or document.pk not in allowed:
        return None
    return document


@never_cache
@login_required
def page(request: HttpRequest, number: int, tab: str = "view") -> HttpResponse:
    """The document page: the *View* tab by default, *Info* at its own address, under the header
    every tab shares (DL-0208)."""
    document = readable_document(request, number)
    if document is None:
        return not_found(request)
    context: dict[str, Any] = {
        "document": document,
        "can_edit": Right.EDIT in rights_on(request.user, document),
        "holding": held_by(document, request.user),
        "tab": tab,
    }
    if tab == "view":
        from rendering.views import view_context

        shown = view_context(request, document)
        if shown is None:
            return not_found(request)
        context |= shown
        return render(request, "documents/page.html", context)
    membership = getattr(request, "membership", None)
    administrator = bool(getattr(request.user, "acts_as_platform_admin", False)) or bool(
        membership and membership.is_tenant_admin
    )
    creator = document.created_by
    # A reader learns who created the document by name; an address only an administrator sees.
    shown_name = ""
    if creator is not None:
        shown_name = creator.display_name or (creator.email if administrator else "")
    linked = (
        sorted(
            link.group.name
            for link in DocumentGroup.objects.filter(document=document).select_related("group")
        )
        if administrator
        else []
    )
    context |= {"administrator": administrator, "creator": shown_name, "linked": linked}
    context |= _state_line(request, document)
    return render(request, "documents/page.html", context)


def _state_line(request: HttpRequest, document: Document) -> dict[str, Any]:
    """The *Info* tab's canonical version and state (DL-0351): the document's one derived state to
    a holder of *view pending*; to any other reader, what their own version is — *frozen*,
    *canonical* or *accepted* — so the line never tells them of work beyond it (DL-0209)."""
    from editions.models import open_freeze
    from editions.visible import visible
    from rendering.views import UNREADABLE
    from review.state import State, states

    try:
        seen = visible(request.user, document)
        state = states([document])[document.pk]
    except UNREADABLE:
        # A record that cannot be read costs the line, never the page; logged for the operator.
        logger.exception(
            "a document's state could not be read", extra={"document": document.number}
        )
        return {"canonical_number": None, "state": None, "state_label": ""}
    rights = rights_on(request.user, document)
    if Right.VIEW_PENDING not in rights and state not in (State.NEW, State.FROZEN, State.CANONICAL):
        # What the reader's own version is, never an absence that tells them more lies beyond it.
        if open_freeze(document) is not None:
            state = State.FROZEN
        elif seen is not None and seen.stance == "canonical":
            state = State.CANONICAL
        else:
            state = State.ACCEPTED
    shown = state in (State.FROZEN, State.CANONICAL, State.ACCEPTED) or Right.VIEW_PENDING in rights
    return {
        "canonical_number": seen.canonical if seen is not None else None,
        "state": state if shown else None,
        "state_label": INFO_STATES.get(state, "") if shown else "",
    }


@never_cache
@login_required
def attachment(request: HttpRequest, number: int, part: int) -> HttpResponse:
    """One attachment of the version the reader may see, as a download under its original name,
    never opened by the platform (DL-0342, T-15). Whatever may not be served costs what a missing
    document costs."""
    from documents.parts import read_attachment
    from editions.visible import latest_visible
    from rendering.views import UNREADABLE

    document = readable_document(request, number)
    if document is None:
        return not_found(request)
    tenant = request.tenant  # type: ignore[attr-defined]
    try:
        version = latest_visible(request.user, document)
        if version is None:
            return not_found(request)
        found, data = read_attachment(tenant.number, document, version, part)
    except UNREADABLE:
        # An unlisted number or a hash mismatch (logged by the parts service), or a repository
        # that disagrees with its rows: each costs what a missing document costs.
        return not_found(request)
    response = HttpResponse(data, content_type="application/octet-stream")
    response["Content-Disposition"] = content_disposition_header(
        as_attachment=True, filename=found.file_name
    )
    response["X-Content-Type-Options"] = "nosniff"
    patch_cache_control(response, private=True)
    record(
        actor=cast(User, request.user),
        action="attachment.downloaded",
        obj=document,
        before=None,
        after={"number": document.number, "attachment": part, "commit": version.commit_sha},
        tenant=tenant,
    )
    return response
