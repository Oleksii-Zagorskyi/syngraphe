"""One audit event as the audit log draws it (DD-10), from its own payload: the set of actions is
open, so nothing here knows what an action means."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.utils.translation import gettext as _

from identity.naming import by_address

# A key or a value is cut here, and a row lists so many changes, so one large payload does not
# stretch the page.
VALUE_SHOWN = 120
CHANGES_SHOWN = 20


@dataclass(frozen=True)
class Row:
    at: datetime
    who: str
    kind: str
    organisation: str
    action: str
    object: str
    change: tuple[str, ...]


def row(event: Any) -> Row:
    return Row(
        at=event.at,
        who=by_address(event.actor, event.actor_kind),
        kind=_kind(event.actor_kind),
        organisation=event.tenant.name if event.tenant is not None else _("the platform"),
        action=event.action,
        object=_object(event),
        change=tuple(_changes(_mapping(event.before), _mapping(event.after))),
    )


def _kind(actor_kind: str) -> str:
    return {"user": _("person"), "system": _("system"), "agent": _("agent")}.get(
        actor_kind, actor_kind
    )


def _mapping(side: Any) -> dict[str, Any]:
    """A payload as keys and values: a mapping as it is, none as empty, anything else under one
    key — whatever a writer stored is drawn."""
    if side is None:
        return {}
    return side if isinstance(side, dict) else {"value": side}


def _object(event: Any) -> str:
    """The object's type, and its number where the payload holds one."""
    for side in (event.after, event.before):
        number = side.get("number") if isinstance(side, dict) else None
        if isinstance(number, int) and not isinstance(number, bool):
            return f"{event.object_type} #{number}"
    return str(event.object_type)


def _changes(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    lines = []
    for key in sorted({*before, *after}):
        old, new = before.get(key, _MISSING), after.get(key, _MISSING)
        # Compared as stored: `1` and `true` are equal in Python, not in the record.
        if _value(old, cut=False) == _value(new, cut=False):
            continue
        lines.append(f"{_cut(str(key))}: {_value(old)} → {_value(new)}")
    if len(lines) > CHANGES_SHOWN:
        more = len(lines) - CHANGES_SHOWN
        lines = [*lines[:CHANGES_SHOWN], _("… %(count)s more") % {"count": more}]
    return lines


_MISSING = object()


def _value(value: Any, *, cut: bool = True) -> str:
    """A value as stored: a string bare, anything else compact JSON."""
    if value is _MISSING:
        return "—"
    shown = (
        value
        if isinstance(value, str)
        else json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    )
    return _cut(shown) if cut else shown


def _cut(text: str) -> str:
    return text if len(text) <= VALUE_SHOWN else text[:VALUE_SHOWN] + "…"
