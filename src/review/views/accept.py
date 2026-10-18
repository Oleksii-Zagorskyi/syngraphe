"""*Accept the run* (ST-0036, DL-0090): the confirmation naming the versions accepted and the
number that results, then the act. The confirmation carries the last version it named, and a run
that grew since is refused and shown again (DL-0333). Afterwards the document page, with the
number the acceptance gave (DL-0332)."""

from __future__ import annotations

from typing import Any, cast

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache

from access.rights import Right, rights_on
from documents.holds import held_by
from documents.locks import LockTimeout
from documents.models import Document
from editing import numbering
from identity.models import User
from identity.naming import person
from review import services
from review.views.pending import readable_pending
from shell.views import not_found


def reason(document: Document, user: User, code: str) -> str:
    """What a refusal says to a holder of *accept*; the reservation names its holder (DL-0226)."""
    if code == "reserved":
        from editing.models import Hold
        from review.state import reserved_since

        hold = Hold.objects.filter(
            document=document, released_at__isnull=True, reserved_at__isnull=False
        ).first()
        if hold is None or hold.reserved_at is None:
            return ""
        return _("Reserved for editing by %(name)s since %(date)s.") % {
            "name": person(hold.user),
            "date": reserved_since(hold.reserved_at),
        }
    if code == "undo_waits":
        from review.services import undo_waiting

        hold = undo_waiting(document)
        return _(
            "An undo of these edits waits in %(name)s’s draft: the run is accepted when they "
            "finish it with “Accept as”."
        ) % {"name": person(hold.user) if hold is not None else ""}
    if code == "revert_waits":
        from review.services import revert_waiting

        hold = revert_waiting(document)
        return _(
            "A revert of parts waits in %(name)s’s draft: the run is accepted when they finish "
            "it with “Accept as”."
        ) % {"name": person(hold.user) if hold is not None else ""}
    return {
        "no_reviewer": _("No reviewer is assigned to this document."),
        "nothing_to_accept": _("Nothing awaits review."),
        "not_a_reviewer": _("You may not accept this document."),
        "run_changed": _("The run changed while you were confirming — check it again."),
    }.get(code, "")


def _confirmation(
    request: HttpRequest, document: Document, error: str = "", status: int = 200
) -> HttpResponse:
    pending = services.run(document)
    accepted = numbering.accepted(document)
    context: dict[str, Any] = {
        "document": document,
        "tab": "pending",
        "can_edit": Right.EDIT in rights_on(request.user, document),
        "holding": held_by(document, request.user),
        "run": [
            {"number": f"{accepted}-{n}", "summary": v.summary, "author": person(v.author)}
            for n, v in enumerate(pending, 1)
        ],
        "confirmed": pending[-1].commit_sha if pending else "",
        "number": numbering.next_accepted(document),
        "error": error,
    }
    return render(request, "review/accept_confirm.html", context, status=status)


@never_cache
@login_required
def accept(request: HttpRequest, number: int) -> HttpResponse:
    """GET: the confirmation. POST: the acceptance of the run it named."""
    document = readable_pending(request, number)
    if (
        document is None
        or request.method not in ("GET", "POST")
        or Right.ACCEPT not in rights_on(request.user, document)
    ):
        return not_found(request)
    user = cast(User, request.user)
    pending_tab = HttpResponseRedirect(f"/document/{document.number}/pending/")
    if request.method == "GET":
        refused = services.refusal(document, user)
        if refused is not None:
            messages.error(request, reason(document, user, refused))
            return pending_tab
        return _confirmation(request, document)
    try:
        acceptance = services.accept(document, user, confirmed=request.POST.get("confirmed", ""))
    except services.AcceptRefused as refused:
        if refused.reason == "run_changed":
            return _confirmation(request, document, reason(document, user, refused.reason), 409)
        messages.error(request, reason(document, user, refused.reason))
        return pending_tab
    except LockTimeout:
        messages.error(request, _("The document is busy. Try again in a moment."))
        return pending_tab
    except services.RecordIncomplete:
        messages.error(
            request,
            _("The document's record is incomplete; it cannot be changed until it is repaired."),
        )
        return pending_tab
    messages.success(request, _("Accepted as %(number)s.") % {"number": acceptance.number})
    return HttpResponseRedirect(f"/document/{document.number}/")
