"""Reservations for editing (ADR-0009): the holder's reserve and cancel from the edit tab, and
*My reservations*; the kept draft's take-back and discard; and the administrator's *End the
reservation* page and Administration › reservations."""

from __future__ import annotations

from typing import cast

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache

from access.rights import Right, holds_anywhere
from documents.locks import LockTimeout
from documents.views import is_member
from editing import holds, reservations
from editing.models import Hold
from editing.views.edit_tab import editable
from identity.models import User
from shell.views import not_found


def _tab(number: int) -> HttpResponseRedirect:
    return HttpResponseRedirect(f"/document/{number}/edit/")


def _refused(request: HttpRequest, number: int, why: str, status: int) -> HttpResponse:
    """A form's refusal as a page with its reason and the way back, never a bare answer."""
    return render(request, "editing/refused.html", {"number": number, "why": why}, status=status)


def _own_hold(request: HttpRequest, number: int) -> Hold | None:
    """The person's open hold on document `number`, for a POST; `None` otherwise."""
    document = editable(request, number)
    if document is None or request.method != "POST":
        return None
    hold = holds.open_hold(document)
    return hold if hold is not None and hold.user_id == request.user.pk else None


@never_cache
@login_required
def reserve(request: HttpRequest, number: int) -> HttpResponse:
    """Reserve the person's hold: back to the tab; `409` while frozen or already reserved — the
    control is drawn disabled then; `404` for anyone but a holder with the right."""
    hold = _own_hold(request, number)
    if hold is None:
        return not_found(request)
    try:
        reservations.reserve(hold, cast(User, request.user))
    except reservations.ReservationRefused as refused:
        if refused.reason == "not_allowed":
            return not_found(request)
        if refused.reason == "frozen":
            return _refused(request, number, "frozen", 409)
        # Reserved already — a second click — or released meanwhile: the tab says which.
        return _tab(number)
    except LockTimeout:
        return _refused(request, number, "busy", 503)
    return _tab(number)


@never_cache
@login_required
def cancel(request: HttpRequest, number: int) -> HttpResponse:
    """Cancel the person's reservation: back to the tab; `404` for anyone else, or with none."""
    hold = _own_hold(request, number)
    if hold is None:
        return not_found(request)
    try:
        reservations.cancel_reservation(hold, cast(User, request.user))
    except reservations.ReservationRefused as refused:
        if refused.reason == "not_allowed":
            return not_found(request)
        return _tab(number)
    except LockTimeout:
        return _refused(request, number, "busy", 503)
    return _tab(number)


@never_cache
@login_required
def my_reservations(request: HttpRequest) -> HttpResponse:
    """The person's reserved documents in this organisation, with the date each began (DL-0241):
    for a holder of *reserve for editing* on some document, the menu's entry drawn for them."""
    if (
        request.method != "GET"
        or getattr(request, "tenant", None) is None
        or not is_member(request)
        or not holds_anywhere(request.user, Right.RESERVE_FOR_EDITING)
    ):
        return not_found(request)
    reserved = (
        Hold.objects.filter(
            user_id=cast(User, request.user).pk,
            released_at__isnull=True,
            reserved_at__isnull=False,
        )
        .select_related("document")
        .order_by("reserved_at", "document__number")
    )
    return render(request, "editing/my_reservations.html", {"reserved": list(reserved)})


@never_cache
@login_required
def take_back(request: HttpRequest, number: int) -> HttpResponse:
    """Take the document back with the person's kept draft, while nobody has committed since —
    read under the lock (DL-0318); back to the tab either way, which shows the draft read-only
    when the head moved meanwhile. `404` without a kept draft."""
    document = editable(request, number)
    if document is None or request.method != "POST":
        return not_found(request)
    if holds.preserved_draft(document, request.user) is None:
        return not_found(request)
    try:
        holds.take(document, cast(User, request.user), take_back=True)
    except (
        holds.DraftPreserved,
        holds.NothingKept,
        holds.HeldByOther,
        holds.Frozen,
        holds.NotEditable,
    ):
        # The tab shows what stands now: the draft read-only, or nothing kept.
        pass
    except LockTimeout:
        return _refused(request, number, "busy", 503)
    return _tab(number)


@never_cache
@login_required
def discard_draft(request: HttpRequest, number: int) -> HttpResponse:
    """Throw the person's kept draft away (DL-0381); back to the tab, which then opens as usual.
    `404` without a kept draft."""
    from editing.services import discard_preserved

    document = editable(request, number)
    if document is None or request.method != "POST":
        return not_found(request)
    kept = holds.preserved_draft(document, request.user)
    if kept is None:
        return not_found(request)
    try:
        discard_preserved(kept, cast(User, request.user))
    except LockTimeout:
        return _refused(request, number, "busy", 503)
    return _tab(number)


def _reserved_hold(request: HttpRequest, number: int) -> Hold | None:
    """The open reserved hold on document `number`, for an administrator of the organisation."""
    from access.views import administers
    from documents.models import Document, DocumentState

    if not administers(request):
        return None
    document = Document.objects.filter(number=number, state=DocumentState.ACTIVE).first()
    if document is None:
        return None
    hold = holds.open_hold(document)
    return hold if hold is not None and hold.reserved_at is not None else None


@never_cache
@login_required
def end(request: HttpRequest, number: int) -> HttpResponse:
    """*End the reservation* (DL-0214, DL-0415): the page naming the reservation, with the reason,
    and its POST — to the document page once ended; the page again with the rule for a refused
    reason; `409` when the reservation the page named is no longer the one open, so a newer one is
    never ended with a reason written about another. `404` for anyone but an administrator, on a
    hold not reserved, or for its own holder, who cancels it instead."""
    from editions.models import REASON_MAX
    from identity.naming import person

    if request.method not in ("GET", "POST"):
        return not_found(request)
    hold = _reserved_hold(request, number)
    if hold is None or hold.user_id == request.user.pk:
        return not_found(request)
    context = {
        "hold": hold,
        "document": hold.document,
        "holder": person(hold.user),
        "reason": "",
        "reason_max": REASON_MAX,
    }
    if request.method == "POST":
        reason = request.POST.get("reason", "")
        context["reason"] = reason
        if request.POST.get("hold") != str(hold.pk):
            return render(
                request, "editing/end_reservation.html", context | {"changed": True}, status=409
            )
        try:
            reservations.end_reservation(hold, cast(User, request.user), reason)
        except reservations.ReasonRefused:
            context["refused"] = True
        except reservations.ReservationRefused as refused:
            if refused.reason == "not_allowed":
                return not_found(request)
            return render(
                request, "editing/end_reservation.html", context | {"changed": True}, status=409
            )
        except LockTimeout:
            context["busy"] = True
        else:
            hold.refresh_from_db(fields=["release_kind"])
            if hold.release_kind == "finished":
                # The holder's own finish had stopped after its commit; the end completed it.
                messages.info(
                    request,
                    _(
                        "The holder's finish that had stopped was completed: the version awaits "
                        "review, and the document is free."
                    ),
                )
            return HttpResponseRedirect(f"/document/{number}/")
    return render(request, "editing/end_reservation.html", context)


@never_cache
@login_required
def administration(request: HttpRequest) -> HttpResponse:
    """Administration › reservations: every reservation in the organisation with its document,
    holder and date (DL-0227), each with *end the reservation…*; an administrator's alone."""
    from access.views import administers

    if request.method != "GET" or not administers(request):
        return not_found(request)
    from identity.naming import person

    reserved = (
        Hold.objects.filter(released_at__isnull=True, reserved_at__isnull=False)
        .select_related("document", "user")
        .order_by("reserved_at", "document__number")
    )
    rows = [{"hold": hold, "holder": person(hold.user)} for hold in reserved]
    return render(request, "editing/reservations.html", {"reserved": rows})


@never_cache
@login_required
def force(request: HttpRequest, number: int) -> HttpResponse:
    """*Force release* of an ordinary hold (ADR-0006): to the document page once released; `409`
    when the hold the page named is no longer the one open, so a newer hold is never forced from
    a stale page; `404` for anyone but an administrator, on a free or a reserved hold — a
    reservation is ended with a reason — or for its own holder."""
    from access.views import administers
    from documents.models import Document, DocumentState

    if request.method != "POST" or not administers(request):
        return not_found(request)
    document = Document.objects.filter(number=number, state=DocumentState.ACTIVE).first()
    hold = holds.open_hold(document) if document is not None else None
    if hold is None or hold.reserved_at is not None or hold.user_id == request.user.pk:
        return not_found(request)
    if request.POST.get("hold") != str(hold.pk):
        return _refused(request, number, "changed", 409)
    try:
        reservations.force_release(hold, cast(User, request.user))
    except reservations.ReservationRefused as refused:
        if refused.reason != "released":
            return not_found(request)
    except LockTimeout:
        return _refused(request, number, "busy", 503)
    return HttpResponseRedirect(f"/document/{number}/")
