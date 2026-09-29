"""Finishing an editing session (DL-0222, DL-0261): the screen with *my edits*, the summary and the
number the version will carry; *send for review*, which commits it; and the *My edits* tab."""

from __future__ import annotations

from typing import Any, cast

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache

from documents.locks import LockTimeout
from documents.models import Document
from editing import holds, numbering, services, summary
from editing.messages import for_the_editor as messages_for_the_editor
from editing.models import Hold, ReleaseKind
from editing.views.edit_tab import editable
from identity.models import User
from shell.views import not_found


def _holders(request: HttpRequest, number: int) -> tuple[Document, Hold] | None:
    """The document and the person's own open hold on it; `None` for anyone else."""
    document = editable(request, number)
    if document is None:
        return None
    hold = holds.open_hold(document)
    if hold is None or hold.user_id != request.user.pk:
        return None
    return document, hold


def _context(document: Document, tab: str, **more: Any) -> dict[str, Any]:
    return {"document": document, "can_edit": True, "holding": True, "tab": tab, **more}


def _screen(
    request: HttpRequest, document: Document, finishing: services.Finishing, **more: Any
) -> HttpResponse:
    status = more.pop("status", 200)
    context = _context(
        document,
        "edit",
        changes=mark_safe(finishing.changes),  # noqa: S308 — built from escaped text alone
        summary=more.pop("summary", finishing.summary),
        number=finishing.number,
        summary_max=summary.SUMMARY_MAX,
        **more,
    )
    return render(request, "editing/finish.html", context, status=status)


def _waiting(request: HttpRequest, document: Document) -> HttpResponse:
    context = _context(
        document,
        "edit",
        reason=_("Finishing waits until the other tabs editing this document are closed."),
    )
    return render(request, "editing/finish_waits.html", context, status=409)


def _refused(
    request: HttpRequest, document: Document, refused: services.DraftRefused
) -> HttpResponse:
    """The draft holds text the editor does not accept: each line named, the way back to the
    source view where it is corrected."""
    words = messages_for_the_editor()
    lines = [
        words["notices"]["line"] % {"line": r.line, "construct": words["constructs"][r.code]}
        for r in refused.refusals
    ]
    context = _context(
        document,
        "edit",
        reason=_("The draft holds text the editor does not accept; correct it in the editor."),
        refusals=lines,
    )
    return render(request, "editing/finish_waits.html", context, status=409)


def _screen_or_wait(
    request: HttpRequest, document: Document, hold: Hold, **more: Any
) -> HttpResponse:
    """The finishing screen again, with what `more` says; or what stands in its way."""
    try:
        finishing = services.finish(hold)
    except services.EditorsOpen:
        return _waiting(request, document)
    except services.DraftRefused as refused:
        return _refused(request, document, refused)
    return _screen(request, document, finishing, **more)


@never_cache
@login_required
def finish(request: HttpRequest, number: int) -> HttpResponse:
    """The finishing screen: the holder's changes, the drafted summary, the number to come."""
    found = _holders(request, number)
    if found is None or request.method != "GET":
        return not_found(request)
    document, hold = found
    return _screen_or_wait(request, document, hold)


def _just_sent(request: HttpRequest, number: int) -> HttpResponse | None:
    """A second *send for review* after the first committed — a double click: the document page,
    where the first one's notice is."""
    document = editable(request, number)
    if document is None:
        return None
    user = cast(User, request.user)
    last = Hold.objects.filter(document=document, user=user).order_by("-acquired_at").first()
    if last is None or last.release_kind != ReleaseKind.FINISHED:
        return None
    return HttpResponseRedirect(f"/document/{document.number}/")


@never_cache
@login_required
def send(request: HttpRequest, number: int) -> HttpResponse:
    """*Send for review*: the version committed, the holder taken to the document page with the
    number it waits as (DL-0322)."""
    if request.method != "POST":
        return not_found(request)
    found = _holders(request, number)
    if found is None:
        return _just_sent(request, number) or not_found(request)
    document, hold = found
    message = request.POST.get("summary", "")
    try:
        services.commit_draft(hold, cast(User, request.user), message)
    except services.InvalidSummary as refused:
        return _screen_or_wait(
            request, document, hold, summary=message, error=str(refused), status=400
        )
    except services.NothingChanged:
        return _screen_or_wait(
            request,
            document,
            hold,
            summary=message,
            error=_("Nothing changed: there is no version to send."),
            status=400,
        )
    except services.EditorsOpen:
        return _waiting(request, document)
    except services.DraftRefused as refused:
        return _refused(request, document, refused)
    except LockTimeout:
        context = _context(
            document, "edit", reason=_("The document is busy. Try again in a moment.")
        )
        return render(request, "editing/finish_waits.html", context, status=503)
    except holds.NotEditable:
        return _just_sent(request, number) or not_found(request)
    messages.success(
        request,
        _("Sent for review — the version waits as %(number)s.")
        % {"number": numbering.latest(document)},
    )
    return HttpResponseRedirect(f"/document/{document.number}/")


@never_cache
@login_required
def my_edits(request: HttpRequest, number: int) -> HttpResponse:
    """The holder's draft: the whole document, its changes marked in place."""
    found = _holders(request, number)
    if found is None or request.method != "GET":
        return not_found(request)
    document, hold = found
    try:
        _, changes = services.my_edits(hold)
    except services.DraftRefused as refused:
        return _refused(request, document, refused)
    # Built from escaped text alone, as the finishing screen's changes are.
    context = _context(document, "my-edits", changes=mark_safe(changes))  # noqa: S308
    return render(request, "editing/my_edits.html", context)
