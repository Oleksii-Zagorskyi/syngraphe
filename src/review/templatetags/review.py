"""The document page's header, the same on every tab: the state tags and whether the *Pending
edits* and *History* tabs are drawn, each through the person's rights (DL-0233, DL-0251)."""

from __future__ import annotations

from typing import Any

from django import template

from access.rights import Right, rights_on
from review.state import tags

register = template.Library()


@register.inclusion_tag("review/state_tag.html", takes_context=True)
def state_tag(context: dict[str, Any], document: Any) -> dict[str, Any]:
    from access.views import administers

    request = context["request"]
    return {
        "tags": tags(request.user, [document], administrator=administers(request)).get(
            document.pk, []
        )
    }


@register.simple_tag(takes_context=True)
def views_pending(context: dict[str, Any], document: Any) -> bool:
    return Right.VIEW_PENDING in rights_on(context["request"].user, document)


@register.simple_tag(takes_context=True)
def holds_history(context: dict[str, Any], document: Any) -> bool:
    """Whether the History tab is drawn: a history right, or *accept* (DL-0251)."""
    from review.history import has_tab

    return has_tab(rights_on(context["request"].user, document))
