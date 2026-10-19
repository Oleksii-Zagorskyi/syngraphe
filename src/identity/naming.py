"""How the platform names a person to a reader, wherever it does: on a page and in an export."""

from __future__ import annotations

from django.utils.translation import gettext as _

from identity.models import User


def person(user: User | None) -> str:
    """How a page names a person to its reader: the name; *former user* once erased (DL-0108);
    *anonymous editor* to everyone when the person has no name (DL-0339)."""
    if user is None:
        return ""
    if user.is_tombstoned:
        return _("former user")
    if user.display_name:
        return user.display_name
    return _("anonymous editor")


def by_address(user: User | None, actor_kind: str) -> str:
    """How an administration page names who acted: a person by address, which the administrator
    typed or must act on (DL-0434); an act with no person by its kind."""
    if user is not None:
        return str(user.email)
    return _("agent") if actor_kind == "agent" else _("system")
