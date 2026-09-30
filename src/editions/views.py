"""The acts of editions on the document page: *Freeze* (ST-0038) and *Make canonical* (ST-0039),
the second confirmed with the edition's number first. Each answers as an address that does not
exist to anyone who may not perform it, and lands on the document page with a notice."""

from __future__ import annotations

import logging
from typing import cast

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache

from access.rights import Right, rights_on
from documents.locks import LockTimeout
from documents.models import Document, DocumentState
from editions import services
from editions.models import REASON_MAX
from identity.models import User
from review.services import RecordIncomplete
from shell.views import not_found

logger = logging.getLogger(__name__)

REFUSALS = {
    "already_frozen": lambda: _("The document is already frozen."),
    "held": lambda: _("The document is held; freeze it once it is released."),
    "reason_invalid": lambda: (
        _("The reason is one line of at most %(count)s characters.") % {"count": REASON_MAX}
    ),
}
CANONICAL_REFUSALS = {
    "not_frozen": lambda: _("Freeze the document first."),
    "nothing_accepted": lambda: _("Nothing new has been accepted to make canonical."),
    # Never the pending number: an approver may not see pending edits (DL-0234).
    "unaccepted_changes": lambda: _("Changes are waiting for review; they must be accepted first."),
    "distinct_approver": lambda: _(
        "You accepted a run this edition would carry; another approver makes it canonical."
    ),
    "accepted_changed": lambda: _(
        "What is accepted changed while you were confirming — check it again."
    ),
}


def _incomplete() -> str:
    return _("The document's record is incomplete; it cannot be changed until it is repaired.")


def canonical_reason(code: str) -> str:
    """What a refusal of *make canonical* says to a holder of the right."""
    return CANONICAL_REFUSALS[code]() if code in CANONICAL_REFUSALS else ""


def _document(
    request: HttpRequest, number: int, right: Right, methods: tuple[str, ...] = ("POST",)
) -> Document | None:
    """The request's organisation's active document `number`, when the person holds `right` on
    it; `None` otherwise, a missing document costing what a forbidden one does."""
    if getattr(request, "tenant", None) is None or request.method not in methods:
        return None
    document = Document.objects.filter(number=number, state=DocumentState.ACTIVE).first()
    if document is None or right not in rights_on(request.user, document):
        return None
    return document


@never_cache
@login_required
def freeze(request: HttpRequest, number: int) -> HttpResponse:
    """POST: freeze the document with the reason given, if any."""
    document = _document(request, number, Right.FREEZE)
    if document is None:
        return not_found(request)
    page = HttpResponseRedirect(f"/document/{document.number}/")
    try:
        services.freeze(document, cast(User, request.user), request.POST.get("reason", ""))
    except services.FreezeRefused as refused:
        if refused.reason not in REFUSALS:
            return not_found(request)
        messages.error(request, REFUSALS[refused.reason]())
        return page
    except LockTimeout:
        messages.error(request, _("The document is busy. Try again in a moment."))
        return page
    except RecordIncomplete:
        messages.error(request, _incomplete())
        return page
    messages.success(request, _("Frozen."))
    return page


def _confirmation(
    request: HttpRequest, document: Document, user: User, error: str = "", status: int = 200
) -> HttpResponse:
    """The confirmation: the accepted version that becomes the edition, by its number, the
    edition's number, and the version's commit, which the act checks (as DL-0333 does for
    accepting)."""
    from documents import gitstore
    from documents.holds import held_by
    from editing.holds import tenant_number
    from review.services import passport_at

    target = services.canonical_target(document)
    assert target is not None
    repo = gitstore.open_repository(tenant_number(), document.number)
    head = gitstore.head(repo)
    context = {
        "document": document,
        "tab": "",
        "can_edit": Right.EDIT in rights_on(user, document),
        "holding": held_by(document, user),
        "accepted": target[1],
        "confirmed": target[0].commit_sha,
        "number": services.next_edition(passport_at(repo, head) if head else []),
        "error": error,
    }
    return render(request, "editions/make_canonical.html", context, status=status)


@never_cache
@login_required
def make_canonical(request: HttpRequest, number: int) -> HttpResponse:
    """GET: the confirmation, naming the accepted version and the edition's number. POST: the
    act, on the version the confirmation named."""
    from rendering.views import UNREADABLE

    document = _document(request, number, Right.MAKE_CANONICAL, ("GET", "POST"))
    if document is None:
        return not_found(request)
    user = cast(User, request.user)
    page = HttpResponseRedirect(f"/document/{document.number}/")
    try:
        if request.method == "GET":
            refused = services.canonical_refusal(document, user)
            if refused is not None and refused not in CANONICAL_REFUSALS:
                return not_found(request)
            if refused is not None:
                messages.error(request, canonical_reason(refused))
                return page
            if not services.edition_number_agrees(document):
                # A stopped approval, or a tag in the way: the page would name an edition that
                # cannot be made; the act settles or refuses under the lock.
                messages.error(request, _incomplete())
                return page
            return _confirmation(request, document, user)
        try:
            edition = services.make_canonical(
                document, user, confirmed=request.POST.get("confirmed", "")
            )
        except services.CanonicalRefused as refused:
            if refused.reason not in CANONICAL_REFUSALS:
                return not_found(request)
            if refused.reason == "accepted_changed":
                return _confirmation(request, document, user, canonical_reason(refused.reason), 409)
            messages.error(request, canonical_reason(refused.reason))
            return page
    except LockTimeout:
        messages.error(request, _("The document is busy. Try again in a moment."))
        return page
    except (RecordIncomplete, *UNREADABLE):
        logger.exception("an edition's record could not be read", extra={"document": number})
        messages.error(request, _incomplete())
        return page
    messages.success(request, _("Made canonical as %(number)s.") % {"number": edition.number})
    return page
