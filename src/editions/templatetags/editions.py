"""The freeze on the document page, the same on every tab: the band every reader sees, and the
*Freeze*, *Unfreeze* and *Make canonical* controls to holders of each right, disabled with the
reason while they cannot be used (DL-0233, DL-0234, DL-0236); and the version the header names."""

from __future__ import annotations

import logging
from typing import Any

from django import template
from django.utils.translation import gettext as _

from access.rights import HISTORY, Right, rights_on
from editing import holds
from editions.models import REASON_MAX, open_freeze
from identity.naming import person

register = template.Library()
logger = logging.getLogger(__name__)


def _administrator(request: Any) -> bool:
    membership = getattr(request, "membership", None)
    return bool(getattr(request.user, "acts_as_platform_admin", False)) or bool(
        membership and membership.is_tenant_admin
    )


@register.inclusion_tag("editions/band.html", takes_context=True)
def freeze_band(context: dict[str, Any], document: Any) -> dict[str, Any]:
    """The frozen band: the reason to every reader, who froze it to holders of a history right,
    administrators among them (DL-0236)."""
    frozen = open_freeze(document)
    if frozen is None:
        return {"frozen": None}
    request = context["request"]
    # Administrators hold both history rights (ADR-0007), so the rights answer for them too.
    named = bool(rights_on(request.user, document) & set(HISTORY))
    return {"frozen": frozen, "by": person(frozen.frozen_by) if named else ""}


@register.inclusion_tag("editions/controls.html", takes_context=True)
def edition_controls(context: dict[str, Any], document: Any) -> dict[str, Any]:
    """*Freeze* to a holder of the right while the document is not frozen, and *Unfreeze* while it
    is (DL-0189); *Freeze* disabled while anyone
    holds it — naming the holder to an administrator (ADR-0006), and a reservation's holder to
    anyone who may edit, which *freeze* includes (ADR-0009); *Make canonical* to a holder of that
    right, disabled with the reason it may not be used now, or as incomplete where the record
    does not read."""
    from editions.services import canonical_refusal
    from editions.views import canonical_reason
    from rendering.views import UNREADABLE

    request = context["request"]
    rights = rights_on(request.user, document)
    shown: dict[str, Any] = {
        "document": document,
        "freeze": None,
        "unfreeze": False,
        "canonical": None,
        "reason_max": REASON_MAX,
        "csrf_token": context.get("csrf_token"),
    }
    # *Unfreeze* to a holder of *freeze* while a freeze is open, disabled while someone holds the
    # document — a holder of *accept* may (ADR-0016) — as *Freeze* is (DL-0223, DL-0233).
    if Right.FREEZE in rights and open_freeze(document) is not None:
        shown["unfreeze"] = {"held": holds.open_hold(document) is not None}
    if Right.FREEZE in rights and open_freeze(document) is None:
        hold = holds.open_hold(document)
        named = hold is not None and (_administrator(request) or hold.reserved_at is not None)
        shown["freeze"] = {
            "held": hold is not None,
            "held_by": person(hold.user) if hold is not None and named else "",
        }
    if Right.MAKE_CANONICAL in rights:
        try:
            refused = canonical_refusal(document, request.user)
            reason = canonical_reason(refused) if refused else ""
        except UNREADABLE:
            logger.exception(
                "a document's record could not be read", extra={"document": document.number}
            )
            reason = _(
                "The document's record is incomplete; it cannot be changed until it is repaired."
            )
        shown["canonical"] = {"refused": reason}
    return shown


@register.simple_tag(takes_context=True)
def version_shown(context: dict[str, Any], document: Any) -> str:
    """The version the header names beside the title on every tab: the latest the person may see,
    by the view's rule (DL-0209); empty when none can be read."""
    from editions.visible import visible
    from rendering.views import UNREADABLE

    try:
        seen = visible(context["request"].user, document)
    except UNREADABLE:
        # A record that cannot be read costs the number, never the page; logged for the operator.
        logger.exception(
            "a document's version could not be read", extra={"document": document.number}
        )
        return ""
    return seen.number if seen is not None else ""
