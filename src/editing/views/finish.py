"""Finishing an editing session (DL-0222, DL-0261): the screen with *my edits*, the summary and the
number the version will carry; the choices — *send for review* for a holder of *edit* alone,
*accept as N.M* and *create version N.M-X* for a holder of *accept* (ADR-0016) — each of which
commits it; *discard my edits*, from the screen and from the edit tab (DL-0237); and the *My edits*
tab."""

from __future__ import annotations

from typing import Any, cast

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache

from access.rights import Right, rights_on
from documents.locks import LockTimeout
from documents.models import Document
from editing import holds, numbering, services, summary
from editing.messages import for_the_editor as messages_for_the_editor
from editing.models import Hold, ReleaseKind
from editing.views.edit_tab import editable
from identity.models import User
from review.services import RecordIncomplete
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


def _run(document: Document) -> list[dict[str, str]]:
    """The versions *accept as* accepts besides the holder's own, named as the confirmation names
    them (DL-0333)."""
    from identity.naming import person
    from review.services import run

    accepted = numbering.accepted(document)
    return [
        {"number": f"{accepted}-{n}", "summary": v.summary, "author": person(v.author)}
        for n, v in enumerate(run(document), 1)
    ]


def _reviewer(request: HttpRequest, document: Document) -> bool:
    return Right.ACCEPT in rights_on(request.user, document)


# What each holder may choose on the screen: the holder of *accept* never *sends*, the holder of
# *edit* alone never accepts (DL-0222).
CHOICES = {True: ("accept", "create"), False: ("send",)}


def _screen(
    request: HttpRequest, document: Document, finishing: services.Finishing, **more: Any
) -> HttpResponse:
    status = more.pop("status", 200)
    reviewer = _reviewer(request, document)
    from documents import gitstore

    context = _context(
        document,
        "edit",
        head=gitstore.head(gitstore.open_repository(holds.tenant_number(), document.number)),
        changes=mark_safe(finishing.changes),  # noqa: S308 — built from escaped text alone
        summary=more.pop("summary", finishing.summary),
        number=finishing.number,
        accept_number=numbering.next_accepted(document) if reviewer else "",
        run=_run(document) if reviewer else [],
        reviewer=reviewer,
        summary_max=summary.SUMMARY_MAX,
        # The discard's box says a reservation ends with the draft (DL-0237).
        reserved=_reserved(document),
        **more,
    )
    return render(request, "editing/finish.html", context, status=status)


def _reserved(document: Document) -> bool:
    hold = holds.open_hold(document)
    return hold is not None and hold.reserved_at is not None


def _waiting(request: HttpRequest, document: Document, reason: str = "") -> HttpResponse:
    context = _context(
        document,
        "edit",
        reason=reason
        or _("Finishing waits until the other tabs editing this document are closed."),
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
    """The screen's choice: *send for review* or *create version* commits the version, *accept
    as* commits it and accepts the run in one act; the holder is taken to the document page with
    the number the version waits as, or the acceptance gave (DL-0322, DL-0332)."""
    if request.method != "POST":
        return not_found(request)
    found = _holders(request, number)
    if found is None:
        return _just_sent(request, number) or not_found(request)
    document, hold = found
    choice = request.POST.get("choice", "send")
    if choice not in CHOICES[_reviewer(request, document)]:
        return not_found(request)
    message = request.POST.get("summary", "")
    user = cast(User, request.user)
    try:
        if choice == "accept":
            from review.services import AcceptRefused, accept_as
            from review.views.accept import reason

            try:
                acceptance = accept_as(
                    hold, user, message, confirmed=request.POST.get("head") or None
                )
            except AcceptRefused as refused:
                accepted = (
                    _accepted_as(document, refused.committed)
                    if refused.committed is not None
                    else None
                )
                if accepted is not None:
                    messages.success(request, _("Accepted as %(number)s.") % {"number": accepted})
                    return HttpResponseRedirect(f"/document/{document.number}/")
                if refused.committed is not None:
                    # The version stands and waits; the acceptance did not happen.
                    messages.success(
                        request,
                        _("Version created — it waits as %(number)s.")
                        % {"number": numbering.latest(document)},
                    )
                    messages.error(request, reason(document, user, refused.reason))
                    return HttpResponseRedirect(f"/document/{document.number}/")
                return _screen_or_wait(
                    request,
                    document,
                    hold,
                    summary=message,
                    error=reason(document, user, refused.reason),
                    status=409,
                )
            messages.success(request, _("Accepted as %(number)s.") % {"number": acceptance.number})
            return HttpResponseRedirect(f"/document/{document.number}/")
        version = services.commit_draft(hold, user, message)
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
    except (LockTimeout, RecordIncomplete) as stopped:
        context = _context(
            document,
            "edit",
            reason=_("The document is busy. Try again in a moment.")
            if isinstance(stopped, LockTimeout)
            else _(
                "The document's record is incomplete; it cannot be changed until it is repaired."
            ),
        )
        return render(request, "editing/finish_waits.html", context, status=503)
    except holds.NotEditable:
        return _just_sent(request, number) or not_found(request)
    except holds.Frozen as frozen:
        said = (
            _("Frozen — “%(reason)s” — until it is unfrozen or made canonical.")
            % {"reason": frozen.reason}
            if frozen.reason
            else _("Frozen — until it is unfrozen or made canonical.")
        )
        context = _context(document, "edit", reason=said)
        return render(request, "editing/finish_waits.html", context, status=409)
    accepted = _accepted_as(document, version)
    if accepted is not None:
        # A finish resumed after someone accepted the version it had committed.
        messages.success(request, _("Accepted as %(number)s.") % {"number": accepted})
        return HttpResponseRedirect(f"/document/{document.number}/")
    notice = (
        _("Version created — it waits as %(number)s.")
        if choice == "create"
        else _("Sent for review — the version waits as %(number)s.")
    )
    messages.success(request, notice % {"number": numbering.latest(document)})
    return HttpResponseRedirect(f"/document/{document.number}/")


def _accepted_as(document: Document, version: Any) -> str | None:
    """The number of the acceptance that already covers `version`, or `None` while it waits."""
    from review.services import latest_acceptance, run

    acceptance = latest_acceptance(document)
    if acceptance is None or any(v.pk == version.pk for v in run(document)):
        return None
    return acceptance.number


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


@never_cache
@login_required
def discard(request: HttpRequest, number: int) -> HttpResponse:
    """*Discard my edits* (DL-0237): the draft thrown away, the hold released, to the document
    page; `409` while an editor is open. A person who may edit but no longer holds — a second
    click, a hold released meanwhile — goes back to the edit tab, which says what stands; `404`
    for anyone else."""
    if request.method != "POST":
        return not_found(request)
    found = _holders(request, number)
    if found is None:
        document = editable(request, number)
        held_it = (
            document is not None
            and Hold.objects.filter(document=document, user_id=cast(User, request.user).pk).exists()
        )
        return HttpResponseRedirect(f"/document/{number}/edit/") if held_it else not_found(request)
    document, hold = found
    try:
        kept = services.discard(hold, cast(User, request.user))
    except services.EditorsOpen:
        return _waiting(
            request,
            document,
            _("Discarding waits until the other tabs editing this document are closed."),
        )
    except holds.NotEditable:
        return HttpResponseRedirect(f"/document/{number}/edit/")
    except LockTimeout:
        reason = _("The document is busy. Try again in a moment.")
        return render(
            request,
            "editing/finish_waits.html",
            _context(document, "edit", reason=reason),
            status=503,
        )
    if kept is not None:
        messages.success(
            request,
            _(
                "Your later edits were discarded; the version you had already made stands and "
                "awaits review."
            ),
        )
    else:
        messages.success(request, _("Your edits were discarded."))
    return HttpResponseRedirect(f"/document/{number}/")
