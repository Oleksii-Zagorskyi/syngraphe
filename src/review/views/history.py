"""The *History* tab (ST-0032, DL-0197, DL-0251): the document's versions and events within the
reader's ceiling, newest first, each version opening as a historical page in a new window."""

from __future__ import annotations

import logging
from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.translation import pgettext_lazy
from django.views.decorators.cache import never_cache

from access.rights import Right, rights_on
from documents.holds import held_by
from documents.path import frame
from documents.views import readable_document
from identity.naming import person
from rendering.views import UNREADABLE
from review.history import entries, has_tab
from shell.views import not_found

logger = logging.getLogger(__name__)

# The words a history entry reads, by its event (DL-0197, `pages.md § The tabs`).
EVENTS = {
    "created": pgettext_lazy("history event", "created"),
    "edit": pgettext_lazy("history event", "edit"),
    "reviewer_edit": pgettext_lazy("history event", "a reviewer's version"),
    "acceptance": pgettext_lazy("history event", "acceptance"),
    "return": pgettext_lazy("history event", "return"),
    "approval": pgettext_lazy("history event", "made canonical"),
    "freeze": pgettext_lazy("history event", "freeze"),
    "unfreeze": pgettext_lazy("history event", "unfreeze"),
}


def _rows(found: list[Any]) -> list[dict[str, Any]]:
    """History's rows, newest first. The *accepted* line stands above the newest entry concerning
    the latest accepted version — its acceptance or its edition — so all that lies above the line
    is work not yet accepted. History lists and opens; the undo stands on the review page
    (DL-0522)."""
    accepted = next((entry.target for entry in found if entry.boundary), None)
    newest = [entry for entry in reversed(found)]
    line = next((i for i, entry in enumerate(newest) if accepted and entry.target == accepted), -1)
    rows = []
    for i, entry in enumerate(newest):
        rows.append(
            {
                "number": entry.number,
                "event": EVENTS[entry.event],
                "code": entry.event,
                "who": person(entry.actor),
                "at": entry.at,
                "opens": entry.version is not None,
                "boundary": i == line,
            }
        )
    return rows


@never_cache
@login_required
def page(request: HttpRequest, number: int) -> HttpResponse:
    """The tab, to a holder of a history right or *accept*; *Nothing to show here* otherwise."""
    document = readable_document(request, number)
    if document is None:
        return not_found(request)
    rights = rights_on(request.user, document)
    if not has_tab(rights):
        return not_found(request)
    try:
        found = entries(request.user, document)
    except UNREADABLE:
        logger.exception("a document's history could not be read", extra={"document": number})
        return not_found(request)
    context = {
        "document": document,
        "frame": frame(request, document, here="history"),
        "tab": "history",
        "can_edit": Right.EDIT in rights,
        "holding": held_by(document, request.user),
        "rows": _rows(found),
        "editions_only": Right.VIEW_PREVIOUS_CANONICAL in rights
        and Right.VIEW_ALL_HISTORY not in rights
        and Right.ACCEPT not in rights,
        "run_only": Right.ACCEPT in rights
        and not rights & {Right.VIEW_ALL_HISTORY, Right.VIEW_PREVIOUS_CANONICAL},
    }
    return render(request, "review/history.html", context)
