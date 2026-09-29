"""Which version of a document a person reads, while editions do not exist yet (DL-0348): the
alpha preview's thin rule, standing where Epic 6's `latest_visible` will."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from access.rights import Right, rights_on
from documents.models import Document, Version, VersionKind
from editing import numbering
from review.services import accepted_content_version, latest_acceptance, run


@dataclass(frozen=True)
class Shown:
    """The version a person reads, its number — empty when nothing has been accepted and nothing
    is pending, since `0.0` is never shown alone (DL-0272) — and whether an acceptance stands
    behind it."""

    version: Version
    number: str
    accepted: bool


def shown(user: Any, document: Document) -> Shown | None:
    """The newest content version to a holder of *view pending*; the latest accepted one — the
    `created` text before any acceptance (DL-0272) — to a holder of *view accepted*; `None`
    otherwise, and the document then does not exist for that person. The number is read with
    the version, from one acceptance, so the header never names another version than its text."""
    rights = rights_on(user, document)
    if Right.VIEW_PENDING not in rights and Right.VIEW_ACCEPTED not in rights:
        return None
    acceptance = latest_acceptance(document)
    if acceptance is not None:
        start = accepted_content_version(acceptance)
    else:
        start = Version.objects.get(document=document, kind=VersionKind.CREATED)
    pending = run(document, since=start) if Right.VIEW_PENDING in rights else []
    accepted_number = acceptance.number if acceptance is not None else ""
    if pending:
        base_number = accepted_number or numbering.BEFORE_ANY_ACCEPTANCE
        return Shown(pending[-1], f"{base_number}-{len(pending)}", False)
    return Shown(start, accepted_number, acceptance is not None)


def latest_visible(user: Any, document: Document) -> Version | None:
    """The version `shown` names — the name Epic 6's editions will take over."""
    visible = shown(user, document)
    return visible.version if visible is not None else None


def label(user: Any, document: Document, version: Version) -> str:
    """The number `shown` gives the version it names."""
    visible = shown(user, document)
    return visible.number if visible is not None and visible.version == version else ""
