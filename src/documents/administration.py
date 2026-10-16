"""The corpus's sections of Administration (`pages.md § Administration`): the organisation's
folders and document types; an administrator's alone, every other person answered as for a
missing page."""

from __future__ import annotations

from typing import Any, cast

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.db.models.functions import Collate
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext
from django.views.decorators.cache import never_cache

from access.views import administers
from documents import folders as acts
from documents import types
from documents.models import Document, DocumentState, DocumentType, Folder
from documents.tree import Tree
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


FOLDERS_PAGE = "/administration/tenant/folders/"

# What each refusal of a folder's act tells the administrator; `not_empty` names what it holds.
FOLDER_REFUSALS = {
    "name_invalid": _("A folder's name is one line of text, at most 200 characters."),
    "name_taken": _("Another folder here already has this name, perhaps in different capitals."),
    "root": _("The folder named after the organisation cannot be renamed or deleted."),
    "archived": _("An archived document cannot be moved: restore it first."),
    "same_folder": _("These documents are already in that folder."),
    "not_in_folder": _("Choose documents of this folder to move."),
}
NOT_EMPTY = _("Only an empty folder can be deleted.")


def _holding(name: str, documents: int, folders: int) -> str:
    """Why a folder's *Delete* is disabled: *Human resources holds 3 documents and 2 folders.*,
    naming only what it holds."""
    counted = {
        "name": name,
        "documents": ngettext("%(count)s document", "%(count)s documents", documents)
        % {"count": documents},
        "folders": ngettext("%(count)s folder", "%(count)s folders", folders) % {"count": folders},
    }
    if documents and folders:
        return str(_("%(name)s holds %(documents)s and %(folders)s.")) % counted
    if documents:
        return str(_("%(name)s holds %(documents)s.")) % counted
    return str(_("%(name)s holds %(folders)s.")) % counted


# A folder number is a positive integer column; more digits than it holds name no folder.
NUMBER_DIGITS = 10


def _number(request: HttpRequest, key: str) -> int | None:
    value = request.POST.get(key) if request.method == "POST" else request.GET.get(key)
    if value is None or not value.isascii() or not value.isdigit() or len(value) > NUMBER_DIGITS:
        return None
    return int(value)


@never_cache
@login_required
def folders(request: HttpRequest) -> HttpResponse:
    """The whole tree, each folder with its counts, and the chosen folder's documents — the root
    unless `?folder=<n>` names another."""
    if request.method != "GET" or not administers(request):
        return not_found(request)
    number = _number(request, "folder") if "folder" in request.GET else 1
    chosen = Folder.objects.filter(number=number).first() if number else None
    if chosen is None:
        return not_found(request)
    return _folders_page(request, chosen)


def _folders_page(
    request: HttpRequest,
    chosen: Folder,
    *,
    error: str = "",
    attempt: dict[str, str] | None = None,
    status: int = 200,
) -> HttpResponse:
    tenant = getattr(request, "tenant", None)
    tree = Tree(tenant.name if tenant is not None else "")
    direct = dict(Document.objects.values_list("folder").annotate(n=Count("id")).order_by())
    subfolders = dict(
        Folder.objects.filter(parent__isnull=False)
        .values_list("parent")
        .annotate(n=Count("id"))
        .order_by()
    )
    rows = [
        {
            "node": node,
            "documents": direct.get(node.folder.pk, 0),
            "folders": subfolders.get(node.folder.pk, 0),
        }
        for node in tree.flat()
    ]
    documents = list(
        Document.objects.filter(folder=chosen)
        .exclude(state=DocumentState.CREATING)
        .order_by(Collate("title", "uk-x-icu"), "number")
    )
    name = tree.path_of(chosen)
    holds = (direct.get(chosen.pk, 0), subfolders.get(chosen.pk, 0))
    context = {
        **frame(request),
        "rows": rows,
        "chosen": chosen,
        "chosen_name": name,
        "is_root": chosen.number == 1,
        "empty": holds == (0, 0),
        "holding": _holding(chosen.name or name, *holds),
        "documents": documents,
        "error": error,
        "attempt": attempt or {},
        "page_url": FOLDERS_PAGE,
    }
    return render(request, "documents/folders.html", context, status=status)


def _refused(
    request: HttpRequest, chosen: Folder, refused: acts.FolderRefused, attempt: dict[str, str]
) -> HttpResponse:
    if refused.reason in ("gone", "not_allowed"):
        return not_found(request)
    if refused.reason == "not_empty":
        error = f"{NOT_EMPTY} {_holding(chosen.name, refused.documents, refused.folders)}"
    else:
        error = str(FOLDER_REFUSALS[refused.reason])
    return _folders_page(request, chosen, error=error, attempt=attempt, status=400)


def _chosen(number: int) -> HttpResponseRedirect:
    return HttpResponseRedirect(f"{FOLDERS_PAGE}?folder={number}")


@never_cache
@login_required
def folder_new(request: HttpRequest) -> HttpResponse:
    """`POST` `parent` and `name`: a folder inside the parent, then the page with it chosen."""
    if request.method != "POST" or not administers(request):
        return not_found(request)
    parent = Folder.objects.filter(number=_number(request, "parent") or 0).first()
    if parent is None:
        return not_found(request)
    name = request.POST.get("name", "")
    try:
        folder = acts.create_folder(parent, name, cast(User, request.user))
    except acts.FolderRefused as refused:
        return _refused(request, parent, refused, {"act": "new", "name": name})
    return _chosen(folder.number)


@never_cache
@login_required
def folder_rename(request: HttpRequest, number: int) -> HttpResponse:
    if request.method != "POST" or not administers(request):
        return not_found(request)
    folder = Folder.objects.filter(number=number).first()
    if folder is None:
        return not_found(request)
    name = request.POST.get("name", "")
    try:
        acts.rename_folder(folder, name, cast(User, request.user))
    except acts.FolderRefused as refused:
        return _refused(request, folder, refused, {"act": "rename", "name": name})
    return _chosen(folder.number)


@never_cache
@login_required
def folder_delete(request: HttpRequest, number: int) -> HttpResponse:
    if request.method != "POST" or not administers(request):
        return not_found(request)
    folder = Folder.objects.filter(number=number).first()
    if folder is None:
        return not_found(request)
    try:
        acts.delete_folder(folder, cast(User, request.user))
    except acts.FolderRefused as refused:
        return _refused(request, folder, refused, {})
    parent = Folder.objects.filter(pk=folder.parent_id).first() if folder.parent_id else None
    return _chosen(parent.number if parent is not None else 1)


@never_cache
@login_required
def folder_move(request: HttpRequest, number: int) -> HttpResponse:
    """*Move documents…*: the folder's active documents to tick and the target by path; `POST`
    `document` (repeated numbers) and `to`. Nothing ticked, or a number not among them, refuses
    the whole move, nothing moved."""
    if request.method not in ("GET", "POST") or not administers(request):
        return not_found(request)
    folder = Folder.objects.filter(number=number).first()
    if folder is None:
        return not_found(request)
    active = list(
        Document.objects.filter(folder=folder, state=DocumentState.ACTIVE).order_by(
            Collate("title", "uk-x-icu"), "number"
        )
    )
    if request.method == "GET":
        return _move_page(request, folder, active)
    ticked = request.POST.getlist("document")
    by_number = {str(d.number): d for d in active}
    target = Folder.objects.filter(number=_number(request, "to") or 0).first()
    if target is None:
        return not_found(request)
    if not ticked or any(n not in by_number for n in ticked):
        error = str(_("Choose documents of this folder to move."))
        return _move_page(request, folder, active, error=error, status=400)
    try:
        acts.move_documents(
            [by_number[n] for n in ticked], target, cast(User, request.user), source=folder
        )
    except acts.FolderRefused as refused:
        if refused.reason in ("gone", "not_allowed"):
            return not_found(request)
        error = str(FOLDER_REFUSALS[refused.reason])
        return _move_page(request, folder, active, error=error, status=400)
    return _chosen(target.number)


def _move_page(
    request: HttpRequest,
    folder: Folder,
    active: list[Document],
    *,
    error: str = "",
    status: int = 200,
) -> HttpResponse:
    tenant = getattr(request, "tenant", None)
    tree = Tree(tenant.name if tenant is not None else "")
    targets = [
        {"folder": node.folder, "path": tree.path_of(node.folder)}
        for node in tree.flat()
        if node.folder.pk != folder.pk
    ]
    context = {
        **frame(request),
        "folder": folder,
        "path": tree.path_of(folder),
        "documents": active,
        "targets": targets,
        "ticked": set(request.POST.getlist("document")) if request.method == "POST" else set(),
        # A refused move keeps the destination it was given.
        "chosen_target": _number(request, "to") if request.method == "POST" else None,
        "error": error,
        "page_url": FOLDERS_PAGE,
    }
    return render(request, "documents/folders_move.html", context, status=status)
