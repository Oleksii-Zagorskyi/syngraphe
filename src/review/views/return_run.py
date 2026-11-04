"""*Return without accepting* (ST-0052, DL-0114, DL-0424): the confirmation naming the versions
returned, with the reason the act is defined by, then the act. As for an acceptance, the
confirmation carries the last version it named, and a run that grew since is refused and shown
again. Afterwards the pending tab, where the run stays."""

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
from documents.path import frame
from editing import numbering
from editing.reservations import ReasonRefused
from editing.summary import first_line
from identity.models import User
from identity.naming import person
from review import services
from review.views.accept import reason as accept_reason
from review.views.pending import readable_pending
from shell.views import not_found


def reason(document: Document, user: User, code: str) -> str:
    """What a refusal says to a holder of *accept*, in the acceptance's words where they are the
    same."""
    return {
        "nothing_to_return": _("Nothing awaits review."),
        "not_a_reviewer": _("You may not return this document's edits."),
        "already_returned": _("The run is already returned; nothing was sent since."),
    }.get(code) or accept_reason(document, user, code)


def _confirmation(
    request: HttpRequest,
    document: Document,
    *,
    error: str = "",
    typed: str = "",
    status: int = 200,
) -> HttpResponse:
    pending = services.run(document)
    accepted = numbering.accepted(document)
    context: dict[str, Any] = {
        "document": document,
        "frame": frame(request, document, here="review"),
        "tab": "pending",
        "can_edit": Right.EDIT in rights_on(request.user, document),
        "holding": held_by(document, request.user),
        "run": [
            {
                "number": f"{accepted}-{n}",
                "summary": first_line(v.summary),
                "author": person(v.author),
            }
            for n, v in enumerate(pending, 1)
        ],
        # The run as listed: a confirmation always names the versions its page shows.
        "confirmed": pending[-1].commit_sha if pending else "",
        "error": error,
        "typed": typed,
    }
    return render(request, "review/return_confirm.html", context, status=status)


@never_cache
@login_required
def return_run(request: HttpRequest, number: int) -> HttpResponse:
    """GET: the confirmation, with the reason. POST: the return of the run it named."""
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
        refused = services.return_refusal(document, user)
        if refused is not None:
            messages.error(request, reason(document, user, refused))
            return pending_tab
        return _confirmation(request, document)
    typed = request.POST.get("reason", "")
    confirmed = request.POST.get("confirmed", "")
    try:
        services.return_run(document, user, typed, confirmed=confirmed)
    except ReasonRefused:
        from editions.models import REASON_MAX

        # DL-0378's one rule for every reason a person types, in its one sentence.
        rule = _(
            "The reason is required: one line of at most %(most)s characters, without control "
            "characters."
        ) % {"most": REASON_MAX}
        return _confirmation(request, document, error=rule, typed=typed, status=400)
    except services.ReturnRefused as refused:
        if refused.reason == "run_changed":
            return _confirmation(
                request,
                document,
                error=reason(document, user, refused.reason),
                typed=typed,
                status=409,
            )
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
    messages.success(request, _("Returned to its authors without accepting."))
    return pending_tab
