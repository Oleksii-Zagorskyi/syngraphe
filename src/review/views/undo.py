"""*Undo this edit* and *undo all of this author's edits* (ST-0037, ADR-0015, DL-0243): a holder
of *accept* posts from the review page's panel (DL-0522); the reversal is typed into their
draft, which opens on the edit tab with what is left for their hand listed above the editor
(DL-0380). The version is named by its number within the reviewer's ceiling, the author by
their identifier among the run's own authors; anything else answers as missing."""

from __future__ import annotations

import logging
from typing import cast

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache

from access.rights import Right, rights_on
from documents.locks import LockTimeout
from editing import authorship
from identity.models import User
from rendering.views import UNREADABLE
from review import services, undo
from review.views.pending import readable_pending
from shell.views import not_found

logger = logging.getLogger(__name__)


def reason(document: object, user: User, code: str) -> str:
    """What a refused undo says to a holder of *accept*."""
    from review.views.accept import reason as accept_reason

    return {
        "held": _("This document is held: someone is editing it."),
        "draft_kept": _(
            "Your editing of this document was ended, and your draft was kept: take the document "
            "back or discard the draft first."
        ),
        "too_large": _("The undo would make your draft larger than the platform accepts."),
        "nothing_to_undo": _("Nothing of this is left to undo."),
        "not_a_reviewer": _("You may not undo edits of this document."),
    }.get(code) or accept_reason(document, user, code)  # type: ignore[arg-type]


@never_cache
@login_required
def undo_view(request: HttpRequest, number: int) -> HttpResponse:
    """POST `version` — a version's number — or `author` — a person's identifier — and the run's
    versions they name are undone into the reviewer's draft."""
    document = readable_pending(request, number)
    if (
        document is None
        or request.method != "POST"
        or Right.ACCEPT not in rights_on(request.user, document)
    ):
        return not_found(request)
    user = cast(User, request.user)
    # A refusal goes back to the review page, where the undo stands (DL-0522).
    review_page = HttpResponseRedirect(f"/document/{document.number}/pending/")
    version = author = None
    try:
        if request.POST.get("version"):
            from review.history import ceiling

            version = ceiling(user, document).version(request.POST["version"])
            if version is None:
                return not_found(request)
        else:
            # Among the run's own authors: an identifier names nobody else here.
            wanted = request.POST.get("author", "")
            author = next(
                (v.author for v in services.run(document) if str(v.author_id) == wanted), None
            )
            if author is None:
                return not_found(request)
    except UNREADABLE:
        logger.exception("a document's history could not be read", extra={"document": number})
        return not_found(request)
    try:
        undo.apply(document, user, version=version, author=author)
    except undo.UndoRefused as refused:
        messages.error(request, reason(document, user, refused.reason))
        return review_page
    except LockTimeout:
        messages.error(request, _("The document is busy. Try again in a moment."))
        return review_page
    except (*UNREADABLE, authorship.AuthorshipError):
        logger.exception("a document's history could not be read", extra={"document": number})
        return not_found(request)
    except services.RecordIncomplete:
        messages.error(
            request,
            _("The document's record is incomplete; it cannot be changed until it is repaired."),
        )
        return review_page
    return HttpResponseRedirect(f"/document/{document.number}/edit/")
