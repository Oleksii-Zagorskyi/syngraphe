"""The freeze on the document's pages: the band every reader sees (DL-0236); and the version an
appendix's editing page names, until that page draws the document's frame."""

from __future__ import annotations

import logging
from typing import Any

from django import template

from access.rights import HISTORY, rights_on
from editions.models import open_freeze
from identity.naming import person

register = template.Library()
logger = logging.getLogger(__name__)


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
