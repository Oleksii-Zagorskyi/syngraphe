"""*Revert* on a row of *Parts changed in the run* (ST-0063, DL-0446): a holder of *accept* posts
the part, the change and the head the page showed; the inverse is staged in their draft, which
opens on the edit tab. Anything not of the forms the page draws answers as missing."""

from __future__ import annotations

from typing import cast

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache

from access.rights import Right, rights_on
from documents.locks import LockTimeout
from identity.models import User
from review import revert, services
from review.views.pending import readable_pending
from shell.views import not_found


def reason(document: object, user: User, code: str) -> str:
    """What a refused revert says to a holder of *accept*."""
    from review.views.undo import reason as undo_reason

    return {
        "run_changed": _("The run changed since the page was drawn — check it again."),
        "nothing_to_revert": _("Nothing of this is left to revert."),
        "changed_in_draft": _(
            "Your draft has already changed this part: settle it in your draft first."
        ),
        "editor_open": _("An editor is open on this appendix; close it first."),
        "not_a_reviewer": _("You may not revert parts of this document."),
    }.get(code) or undo_reason(document, user, code)


def _back(number: int) -> HttpResponse:
    response = HttpResponseRedirect(f"/document/{number}/pending/")
    response.status_code = 303
    return response


@never_cache
@login_required
def revert_view(request: HttpRequest, number: int) -> HttpResponse:
    """POST `part`, `change` and `head`: the row's inverse in the reviewer's draft, and the edit
    tab; a refusal said on the pending tab."""
    document = readable_pending(request, number)
    part, change, head = (request.POST.get(name, "") for name in ("part", "change", "head"))
    if (
        document is None
        or request.method != "POST"
        or Right.ACCEPT not in rights_on(request.user, document)
        or not revert.well_formed(part, change, head)
    ):
        return not_found(request)
    user = cast(User, request.user)
    try:
        revert.apply(document, user, part=part, change=change, head=head)
    except revert.RevertRefused as refused:
        messages.error(request, reason(document, user, refused.reason))
        return _back(document.number)
    except LockTimeout:
        messages.error(request, _("The document is busy. Try again in a moment."))
        return _back(document.number)
    except services.RecordIncomplete:
        messages.error(
            request,
            _("The document's record is incomplete; it cannot be changed until it is repaired."),
        )
        return _back(document.number)
    response = HttpResponseRedirect(f"/document/{document.number}/edit/")
    response.status_code = 303
    return response
