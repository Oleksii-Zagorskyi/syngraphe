"""Each event's category, and the words its entry reads. An entry is composed at render from the
row's ids and facts, so it never carries a line of a document (DL-0113)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from django.utils.translation import gettext as _

from notifications.models import PLATFORM_EVENTS, Category, Event


@dataclass(frozen=True)
class EventSpec:
    category: Category


EVENTS: dict[Event, EventSpec] = {
    Event.CORRECTION_NOTICE: EventSpec(Category.DOCUMENT),
    Event.VERSION_COMMITTED: EventSpec(Category.DOCUMENT),
    Event.ACCEPTED: EventSpec(Category.DOCUMENT),
    Event.FROZEN: EventSpec(Category.DOCUMENT),
    Event.UNFROZEN: EventSpec(Category.DOCUMENT),
    Event.MADE_CANONICAL: EventSpec(Category.DOCUMENT),
    Event.ACCESS_GRANTED: EventSpec(Category.ADMINISTRATIVE),
    Event.DOCUMENT_CREATED: EventSpec(Category.ADMINISTRATIVE),
    Event.DOCUMENT_COPIED: EventSpec(Category.ADMINISTRATIVE),
    Event.BACKUP_CONDITION: EventSpec(Category.ADMINISTRATIVE),
    Event.EMAIL_FAILED: EventSpec(Category.ADMINISTRATIVE),
    Event.USER_PARTIALLY_BLOCKED: EventSpec(Category.ADMINISTRATIVE),
    Event.TENANT_WITHOUT_ADMIN: EventSpec(Category.ADMINISTRATIVE),
    Event.RESERVATION_STARTED: EventSpec(Category.ADMINISTRATIVE),
    Event.RESERVATION_ENDED_BY_ADMIN: EventSpec(Category.DOCUMENT),
    Event.HOLD_EXPIRING: EventSpec(Category.DOCUMENT),
    Event.RETURNED: EventSpec(Category.DOCUMENT),
    Event.DOCUMENT_ARCHIVED: EventSpec(Category.DOCUMENT),
}

# The events a tenant administrator can receive in the organisation's schema, and what a platform
# administrator adds in the shared one; a member receives only `access_granted`, in the
# organisation's schema. The filters follow these lists (DL-0236).
TENANT_ADMINISTRATIVE = (
    Event.DOCUMENT_CREATED,
    # A copy tells the administrators as a creation does (DL-0455).
    Event.DOCUMENT_COPIED,
    Event.ACCESS_GRANTED,
    Event.EMAIL_FAILED,
    Event.RESERVATION_STARTED,
)
PLATFORM_ADMINISTRATIVE = PLATFORM_EVENTS


def label(event: Event) -> str:
    """The event's name in a filter."""
    return {
        Event.ACCESS_GRANTED: _("Added to a group"),
        Event.DOCUMENT_CREATED: _("Documents created"),
        Event.DOCUMENT_COPIED: _("Documents copied"),
        Event.BACKUP_CONDITION: _("Backup"),
        Event.EMAIL_FAILED: _("Failed email"),
        Event.USER_PARTIALLY_BLOCKED: _("Blocked, active elsewhere"),
        Event.TENANT_WITHOUT_ADMIN: _("Without an administrator"),
        Event.RESERVATION_STARTED: _("Reservations started"),
    }.get(event, event.value)


def _condition(facts: dict[str, Any]) -> str:
    began = facts.get("change") != "cleared"
    return {
        ("repository_failing", True): _("A document's backup is failing."),
        ("repository_failing", False): _("A document's backup works again."),
        ("backup_behind", True): _("The backup has fallen behind."),
        ("backup_behind", False): _("The backup has caught up."),
        ("archive_waiting", True): _("The database archive is waiting to be copied."),
        ("archive_waiting", False): _("The database archive has been copied."),
    }.get((str(facts.get("condition", "")), began), _("The backup's state changed."))


def _group(facts: dict[str, Any]) -> str:
    from access.models import AccessGroup

    try:
        group_id = uuid.UUID(str(facts.get("group", "")))
    except ValueError:
        return ""
    return AccessGroup.objects.filter(pk=group_id).values_list("name", flat=True).first() or ""


def _organisation(facts: dict[str, Any]) -> str:
    """The organisation a platform entry names, by its number; read in the shared schema."""
    from tenancy.models import Tenant

    number = facts.get("tenant")
    if not isinstance(number, int):
        return ""
    name = Tenant.objects.filter(number=number).values_list("name", flat=True).first()
    return name or f"#{number}"


def _address(facts: dict[str, Any]) -> str:
    """The person a platform entry names — to a platform administrator, by address."""
    from identity.models import User

    try:
        user_id = uuid.UUID(str(facts.get("user", "")))
    except ValueError:
        return _("former user")
    person = User.objects.filter(pk=user_id).first()
    if person is None or person.is_tombstoned:
        return _("former user")
    return person.email


def _named(facts: dict[str, Any], key: str) -> str:
    """The person a reservation's entry names under `key`, as the organisation's pages name
    them."""
    from identity.models import User
    from identity.naming import person

    try:
        user_id = uuid.UUID(str(facts.get(key, "")))
    except ValueError:
        return ""
    return person(User.objects.filter(pk=user_id).first())


def describe(row: Any, *, named: bool = True) -> str:
    """What the entry of a `Notification` or a `PlatformNotification` reads. `named` false leaves
    out who reserved a document, for a reader who no longer administers the organisation
    (DL-0226)."""
    facts: dict[str, Any] = row.facts or {}
    event = Event(row.event)
    if event == Event.BACKUP_CONDITION:
        return _condition(facts)
    if event == Event.EMAIL_FAILED:
        return _("An email could not be sent after three attempts.")
    if event == Event.USER_PARTIALLY_BLOCKED:
        blocked = _("%(person)s was blocked in %(organisation)s and is active in another one.")
        return blocked % {"person": _address(facts), "organisation": _organisation(facts)}
    if event == Event.TENANT_WITHOUT_ADMIN:
        return _("%(organisation)s has no active administrator.") % {
            "organisation": _organisation(facts)
        }
    # No document attached — its number and who archived it, never its title (DL-0471).
    if event == Event.DOCUMENT_ARCHIVED:
        archived = {"number": facts.get("number", ""), "by": _named(facts, "by")}
        # Entries written before the fact carried it kept the draft whatever it held.
        if facts.get("kept", True):
            return (
                _(
                    "Document #%(number)s, which you were editing, was archived by %(by)s; your"
                    " draft is kept."
                )
                % archived
            )
        return _("Document #%(number)s, which you were editing, was archived by %(by)s.") % archived
    if event == Event.ACCESS_GRANTED:
        group = _group(facts)
        if group:
            return _("You were added to the group %(group)s.") % {"group": group}
        return _("You were added to a group.")
    document = getattr(row, "document", None)
    document_named = {
        "number": document.number if document is not None else "",
        "title": document.title if document is not None else "",
    }
    if event == Event.CORRECTION_NOTICE:
        from review.notices import counted

        notice = row.correction_notice
        accepted = notice.acceptance.number if notice else ""
        # The counts alone; every line and part is on the notice's own page (DL-0480).
        return _(
            "Correction notice: #%(number)s %(title)s, accepted as %(accepted)s — %(changed)s "
            "changed."
        ) % {**document_named, "accepted": accepted, "changed": counted(notice) if notice else ""}
    words = {
        Event.VERSION_COMMITTED: _("#%(number)s %(title)s: version %(version)s awaits review."),
        Event.ACCEPTED: _("#%(number)s %(title)s: your edits were accepted as %(accepted)s."),
        Event.FROZEN: _("#%(number)s %(title)s was frozen."),
        Event.UNFROZEN: _("#%(number)s %(title)s is no longer frozen."),
        Event.MADE_CANONICAL: _("#%(number)s %(title)s was approved as edition %(edition)s."),
        Event.DOCUMENT_CREATED: _("#%(number)s %(title)s was created."),
        Event.DOCUMENT_COPIED: _("#%(number)s %(title)s was created as a copy."),
        Event.RESERVATION_STARTED: _("#%(number)s %(title)s was reserved for editing by %(name)s."),
        # The reason stays out of the sentence, which is also the email (DL-0369); the page draws
        # it beneath, from the facts.
        Event.RESERVATION_ENDED_BY_ADMIN: _(
            "#%(number)s %(title)s: your reservation was ended by %(by)s."
        ),
        Event.HOLD_EXPIRING: _("#%(number)s %(title)s: your editing will soon end for inactivity."),
        # As for an ended reservation, the reason is read on the page, never in the email
        # (DL-0369).
        Event.RETURNED: _("#%(number)s %(title)s: your edits were returned without accepting."),
    }
    if event == Event.DOCUMENT_CREATED and facts.get("recreated"):
        words[event] = _(
            "#%(number)s %(title)s was recreated by the platform; no group is linked to it."
        )
    if event == Event.RESERVATION_STARTED and not named:
        words[event] = _("#%(number)s %(title)s was reserved for editing.")
    numbers = {key: facts.get(key, "") for key in ("version", "accepted", "edition")}
    people = {"name": _named(facts, "holder"), "by": _named(facts, "by")}
    return words[event] % {**document_named, **numbers, **people}


def tag(row: Any) -> str | None:
    """The document list's own tag beside a created document's entry — *no reviewer assigned*,
    read at render, so it goes once a group holding *accept* is linked (DL-0233)."""
    document = getattr(row, "document", None)
    if row.event not in (Event.DOCUMENT_CREATED, Event.DOCUMENT_COPIED) or document is None:
        return None
    if (row.facts or {}).get("recreated"):
        # Its sentence already says no group is linked.
        return None
    from review.state import LABELS, State, with_reviewer

    if document.pk in with_reviewer([document.pk]):
        return None
    return str(LABELS[State.NO_REVIEWER_ASSIGNED])
