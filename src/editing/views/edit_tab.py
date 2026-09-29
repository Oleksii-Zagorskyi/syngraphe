"""The *Edit* tab: the editor's mount point for the holder, *held* for anyone else with *edit*,
and nothing for a reader without it. Loading the tab changes nothing; the editor takes the hold
with a POST as it mounts (DL-0319) — at once only when the tab was opened from the application
itself or typed in, and otherwise on a *Start editing* the person presses (DL-0325)."""

from __future__ import annotations

from typing import cast

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache

from access.rights import Right, rights_on_many
from documents.locks import LockTimeout
from documents.models import Document, DocumentState
from documents.views import ABSENT
from editing import holds, messages
from identity.models import User
from shell.views import not_found


def editable(request: HttpRequest, number: int) -> Document | None:
    """The active document `number` of the request's organisation, when the person holds *edit*
    on it; `None` otherwise. A missing document costs what a forbidden one does (ADR-0008)."""
    if getattr(request, "tenant", None) is None:
        return None
    document = Document.objects.filter(number=number, state=DocumentState.ACTIVE).first()
    rights = rights_on_many(request.user, [document.pk if document is not None else ABSENT])
    if document is None or Right.EDIT not in rights.get(document.pk, frozenset()):
        return None
    return document


@never_cache
@login_required
def page(request: HttpRequest, number: int) -> HttpResponse:
    """The tab: the mount point, told whether to take the hold at once or wait to be asked."""
    document = editable(request, number)
    if document is None or request.method != "GET":
        return not_found(request)
    from editing.views.capture import settings_for_the_editor as capture_settings

    hold = holds.open_hold(document)
    # The browser's own word for where the navigation came from; a request without it is treated
    # as coming from elsewhere.
    own = request.headers.get("Sec-Fetch-Site") in ("same-origin", "none")
    holding = hold is not None and hold.user_id == request.user.pk
    context = {
        "document": document,
        "can_edit": True,
        "holding": holding,
        "take_on_mount": own or holding,
        "tab": "edit",
        "words": {**messages.for_the_editor(), "capture": capture_settings()},
    }
    if hold is not None and hold.user_id != request.user.pk:
        return render(request, "editing/held_by_other.html", context)
    return render(request, "editing/edit_tab.html", context)


@never_cache
@login_required
def take(request: HttpRequest, number: int) -> HttpResponse:
    """Take the hold, or keep the one the person already has; `409` while someone else holds,
    `503` while the document's lock stays busy."""
    document = editable(request, number)
    if document is None or request.method != "POST":
        return not_found(request)
    try:
        holds.take(document, cast(User, request.user))
    except holds.NotEditable:
        return not_found(request)
    except holds.HeldByOther:
        return JsonResponse({"held": True}, status=409)
    except LockTimeout:
        return JsonResponse({"busy": True}, status=503)
    return JsonResponse({"held": False})
