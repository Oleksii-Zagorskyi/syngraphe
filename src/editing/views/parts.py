"""The parts panel of the edit tab (DL-0442): the draft's appendices and attachments, each control
drawn to a person who holds its right; the forms that stage each operation in the holder's draft,
each answering with the edit tab again and a refusal, if any, said there; and the draft's
attachment downloaded by the person whose draft it is (T-15).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, cast

import pygit2
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest, HttpResponseRedirect
from django.template.defaultfilters import filesizeformat
from django.utils.cache import patch_cache_control
from django.utils.http import content_disposition_header
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.cache import never_cache

from access.rights import LABELS, Right, rights_on_many
from audit.record import record
from documents import bundle, gitstore
from documents.locks import LockTimeout
from documents.models import Document
from editing import holds, parts
from editing.models import Draft
from editing.views.edit_tab import editable
from identity.models import User
from shell.views import not_found

ORDER = re.compile(r"[1-9][0-9]{0,9}(,[1-9][0-9]{0,9})*")

# One message per reason a part operation is refused.
REFUSALS = {
    "not_holding": gettext_lazy(
        "You are not editing this document now; open it for editing to change its parts."
    ),
    "not_editable": gettext_lazy("This document cannot be edited now."),
    "frozen": gettext_lazy("Frozen — until it is unfrozen or made canonical."),
    "bad_title": gettext_lazy("A title is one line of text, at most 500 characters."),
    "bad_file_name": gettext_lazy(
        "This file’s name cannot be kept: it must be one line, without slashes, and must not "
        "begin with a dot."
    ),
    "no_such_part": gettext_lazy("That part is no longer in your draft."),
    "editor_open": gettext_lazy("An editor is open on this appendix; close it first."),
    "bad_order": gettext_lazy("The order no longer matches your draft; reload the page."),
    "record_incomplete": gettext_lazy(
        "The document's record is incomplete; it cannot be changed until it is repaired."
    ),
}


def _said(refused: parts.PartRefused) -> str:
    if refused.reason == "no_right":
        return _("You do not hold the right to %(right)s.") % {
            "right": LABELS[refused.detail["right"]]
        }
    if refused.reason == "too_large":
        return _("%(name)s is %(size)s; this organisation’s limit is %(limit)s.") % {
            "name": refused.detail["file_name"],
            "size": filesizeformat(refused.detail["size"]),
            "limit": filesizeformat(refused.detail["limit"]),
        }
    return str(REFUSALS[refused.reason])


def _back(document: Document) -> HttpResponse:
    response = HttpResponseRedirect(f"/document/{document.number}/edit/")
    # The form's post is done; the tab is fetched anew.
    response.status_code = 303
    return response


def _staged(
    request: HttpRequest, number: int, act: Callable[[Document, User], object]
) -> HttpResponse:
    """`act` on the document for the person, under the parts services' own locks; the edit tab
    again, with the refusal said there."""
    document = editable(request, number)
    if document is None or request.method != "POST":
        return not_found(request)
    try:
        act(document, cast(User, request.user))
    except parts.PartRefused as refused:
        messages.error(request, _said(refused))
    except LockTimeout:
        messages.error(request, _("The document is busy. Try again in a moment."))
    return _back(document)


class Malformed(Exception):
    """A post without a field its form always sends, or with a value no form sends."""


def _field(request: HttpRequest, name: str) -> str:
    value = request.POST.get(name)
    if value is None:
        raise Malformed(name)
    return value


def _order(request: HttpRequest) -> list[int]:
    value = _field(request, "order")
    if not ORDER.fullmatch(value):
        raise Malformed("order")
    return [int(n) for n in value.split(",")]


def _file(request: HttpRequest) -> Any:
    files = request.FILES.getlist("file")
    if len(files) != 1:
        raise Malformed("file")
    return files[0]


def _bytes(upload: Any) -> bytes:
    return bytes(upload.read())


def _uploaded(
    request: HttpRequest, number: int, act: Callable[[Document, User, str, bytes], object]
) -> HttpResponse:
    """A form that carries a file: the person and the file's declared size decided before a byte
    of it is read, so a refused upload never fills the worker's memory."""
    upload = _file(request)
    document = editable(request, number)
    if document is None or request.method != "POST":
        return not_found(request)
    name = upload.name or ""
    limit = parts.upload_limit()
    if upload.size is None or upload.size > limit:
        size = upload.size or 0
        messages.error(
            request, _said(parts.PartRefused("too_large", file_name=name, size=size, limit=limit))
        )
        return _back(document)
    data = _bytes(upload)
    return _staged(request, number, lambda d, u: act(d, u, name, data))


def _form(view: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
    """A panel form's view: never cached, signed in, and `400` for a malformed post."""

    @never_cache
    @login_required
    def answer(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        try:
            return view(request, *args, **kwargs)
        except Malformed:
            if request.method != "POST" or editable(request, kwargs["number"]) is None:
                return not_found(request)
            return HttpResponseBadRequest()

    answer.__doc__ = view.__doc__
    answer.__name__ = view.__name__
    return answer


@_form
def create_appendix(request: HttpRequest, number: int) -> HttpResponse:
    title = _field(request, "title")
    return _staged(request, number, lambda d, u: parts.create_appendix(d, u, title=title))


@_form
def rename_appendix(request: HttpRequest, number: int, part: int) -> HttpResponse:
    title = _field(request, "title")
    return _staged(request, number, lambda d, u: parts.rename_appendix(d, u, part, title=title))


@_form
def delete_appendix(request: HttpRequest, number: int, part: int) -> HttpResponse:
    return _staged(request, number, lambda d, u: parts.delete_appendix(d, u, part))


@_form
def reorder_appendices(request: HttpRequest, number: int) -> HttpResponse:
    order = _order(request)
    return _staged(request, number, lambda d, u: parts.reorder_appendices(d, u, order))


@_form
def upload_attachment(request: HttpRequest, number: int) -> HttpResponse:
    title = _field(request, "title")
    return _uploaded(
        request,
        number,
        lambda d, u, name, data: parts.upload_attachment(
            d, u, title=title, file_name=name, data=data
        ),
    )


@_form
def replace_attachment(request: HttpRequest, number: int, part: int) -> HttpResponse:
    return _uploaded(
        request,
        number,
        lambda d, u, name, data: parts.replace_attachment(d, u, part, file_name=name, data=data),
    )


@_form
def rename_attachment(request: HttpRequest, number: int, part: int) -> HttpResponse:
    title = _field(request, "title")
    return _staged(request, number, lambda d, u: parts.rename_attachment(d, u, part, title=title))


@_form
def delete_attachment(request: HttpRequest, number: int, part: int) -> HttpResponse:
    return _staged(request, number, lambda d, u: parts.delete_attachment(d, u, part))


@_form
def reorder_attachments(request: HttpRequest, number: int) -> HttpResponse:
    order = _order(request)
    return _staged(request, number, lambda d, u: parts.reorder_attachments(d, u, order))


@never_cache
@login_required
def attachment(request: HttpRequest, number: int, part: int) -> HttpResponse:
    """The draft's attachment `part` — staged in it, or as the draft's base holds it — to the
    person whose draft it is: the holder, or the owner of a draft kept from their ended hold
    (DL-0225). Served as T-15 says, audited; anything else costs what a missing one does."""
    document = editable(request, number)
    if document is None or request.method != "GET":
        return not_found(request)
    user = cast(User, request.user)
    hold = holds.open_hold(document)
    kept = hold is None or hold.user_id != user.pk
    draft = (
        holds.preserved_draft(document, user) if kept else Draft.objects.filter(hold=hold).first()
    )
    if draft is None:
        return not_found(request)
    try:
        found, data = parts.draft_attachment(draft, part)
    except (KeyError, ValueError, pygit2.GitError):
        # Unlisted, or bytes that are not the listed ones (logged by the parts service).
        return not_found(request)
    response = HttpResponse(data, content_type="application/octet-stream")
    response["Content-Disposition"] = content_disposition_header(
        as_attachment=True, filename=str(found["file_name"])
    )
    response["X-Content-Type-Options"] = "nosniff"
    patch_cache_control(response, private=True)
    record(
        actor=user,
        action="attachment.downloaded",
        obj=document,
        before=None,
        after={
            "number": document.number,
            "attachment": part,
            "staged": True,
            **({"kept": True} if kept else {}),
        },
        tenant=request.tenant,  # type: ignore[attr-defined]
    )
    return response


def _swapped(numbers: list[int], at: int, by: int) -> str | None:
    other = at + by
    if not 0 <= other < len(numbers):
        return None
    order = list(numbers)
    order[at], order[other] = order[other], order[at]
    return ",".join(map(str, order))


def panel(document: Document, user: Any, hold: Any) -> dict[str, Any]:
    """What the panel draws: the draft's lists for its holder — the head's for a tab drawn before
    the hold, the draft starting as the head — each part with the controls the person's rights
    allow; a part the draft itself added is withdrawn with the right that added it (DL-0473)."""
    repo = gitstore.open_repository(holds.tenant_number(), document.number)
    head = gitstore.head(repo)
    current, _ = (
        bundle.parse(gitstore.read(repo, holds.BODY, head).decode("utf-8"))
        if head
        else (
            None,
            "",
        )
    )
    head_numbers = {
        "appendices": {int(e["number"]) for e in current.appendices} if current else set(),
        "attachments": {int(e["number"]) for e in current.attachments} if current else set(),
    }
    draft = Draft.objects.filter(hold=hold).first() if hold is not None else None
    if draft is not None:
        listed = parts.draft_parts(draft)
        appendices, attachments = listed.appendices, listed.attachments
    else:
        appendices = [dict(e) for e in current.appendices] if current else []
        attachments = [dict(e, staged=False) for e in current.attachments] if current else []
    rights = rights_on_many(user, [document.pk]).get(document.pk, frozenset())

    def drawn(entries: list[dict[str, Any]], kind: str, add: Right, delete: Right) -> None:
        numbers = [int(e["number"]) for e in entries]
        for at, item in enumerate(entries):
            added = item["number"] not in head_numbers[kind]
            item["draft_only"] = added
            item["can_delete"] = (add if added else delete) in rights
            item["up"] = _swapped(numbers, at, -1)
            item["down"] = _swapped(numbers, at, 1)

    drawn(appendices, "appendices", Right.CREATE_APPENDIX, Right.DELETE_APPENDIX)
    drawn(attachments, "attachments", Right.UPLOAD_ATTACHMENT, Right.DELETE_ATTACHMENT)
    return {
        "appendices": appendices,
        "attachments": attachments,
        "can_create_appendix": Right.CREATE_APPENDIX in rights,
        "can_upload": Right.UPLOAD_ATTACHMENT in rights,
        "can_replace": Right.REPLACE_ATTACHMENT in rights,
    }
