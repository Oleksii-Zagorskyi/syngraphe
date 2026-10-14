"""The hold on the document page: its band (DL-0226, DL-0233) — a reservation says so across the
top, with what waits until it ends, its holder reads that it is theirs, and an ordinary hold draws
none, the state tag and the edit tab saying it — and the administrator's acts on it under *More ▾*
(ADR-0006, DL-0214)."""

from __future__ import annotations

from typing import Any

from django import template

from access.rights import Right, rights_on
from documents.holds import open_holds

register = template.Library()


@register.inclusion_tag("editing/band.html", takes_context=True)
def hold_band(context: dict[str, Any], document: Any) -> dict[str, Any]:
    """The band's context: `reserved`, the open reserved hold or `None`; `mine`, whether the reader
    holds it; `since`, its date; `by`, the holder's name, empty where the reader may not see it
    (DL-0226); `kept`, whether the reader has a draft kept from an ended hold of theirs."""
    from access.views import administers
    from editing.holds import preserved_draft
    from identity.naming import person
    from review.state import NAMED_ON_A_RESERVATION, reserved_since

    request = context["request"]
    hold = open_holds([document.pk]).get(document.pk)
    if hold is None:
        # The holder whose editing was ended learns of it on the document, and where to go — the
        # edit tab, so only while they may still edit.
        kept = (
            not context.get("returning")
            and Right.EDIT in rights_on(request.user, document)
            and preserved_draft(document, request.user) is not None
        )
        return {"reserved": None, "kept": kept, "document": document}
    if hold.reserved_at is None:
        return {"reserved": None}
    mine = hold.user_id == request.user.pk
    named = administers(request) or bool(rights_on(request.user, document) & NAMED_ON_A_RESERVATION)
    return {
        "reserved": hold,
        "mine": mine,
        "since": reserved_since(hold.reserved_at),
        "by": person(hold.user) if named and not mine else "",
    }


@register.inclusion_tag("editing/hold_acts.html", takes_context=True)
def hold_acts(context: dict[str, Any], document: Any, menu: bool = False) -> dict[str, Any]:
    """An administrator's acts on someone else's hold, as the document page's *More ▾* when
    `menu` (ADR-0006, DL-0214): *end the reservation…* on a reserved hold, *force release* on an
    ordinary one; nothing on a free document, to anyone else, or to the holder."""
    from access.views import administers

    request = context["request"]
    hold = open_holds([document.pk]).get(document.pk)
    if hold is None or hold.user_id == request.user.pk or not administers(request):
        return {"hold": None}
    return {
        "hold": hold,
        "document": document,
        "menu": menu,
        "csrf_token": context.get("csrf_token"),
    }
