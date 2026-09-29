"""The document page's header, the same on every tab: the state tag and whether the *Pending
edits* tab is drawn, both through the person's rights (DL-0233)."""

from __future__ import annotations

from typing import Any

from django import template

from access.rights import Right, rights_on
from review.state import LABELS, tags

register = template.Library()


@register.inclusion_tag("review/state_tag.html", takes_context=True)
def state_tag(context: dict[str, Any], document: Any) -> dict[str, Any]:
    shown = tags(context["request"].user, [document]).get(document.pk)
    return {"state": shown, "label": LABELS.get(shown) if shown else None}


@register.simple_tag(takes_context=True)
def views_pending(context: dict[str, Any], document: Any) -> bool:
    return Right.VIEW_PENDING in rights_on(context["request"].user, document)
