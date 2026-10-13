"""Which version of a document a person reads (DL-0209, DL-0272): the latest content version to a
holder of *view pending*, the latest accepted to a holder of *view accepted* — the `created` text
before any acceptance — and the latest edition's to a holder of *view canonical*, for whom a
document without an edition does not exist. The page, the list and the attachment route all read
it, so a reader downloads exactly what they read.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from access.rights import Right, rights_on_many
from documents.models import Document, Version, VersionKind
from editing.numbering import BEFORE_ANY_ACCEPTANCE
from editions.models import Edition
from review.models import Acceptance
from review.services import accepted_content_version, number_key, run

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Visible:
    """The version a person reads; its number — `0.0` for the `created` text, the document's first
    version (DL-0358); what the text is — `pending`, `accepted` or `canonical`; and the latest
    edition's number, `None` before the first."""

    version: Version
    number: str
    stance: str
    canonical: str | None


def latest_edition(document: Document) -> Edition | None:
    """The document's latest edition, or `None` before the first."""
    editions = Edition.objects.filter(version__document=document).select_related("version")
    return max(editions, key=lambda e: number_key(e.number), default=None)


def visible(user: Any, document: Document) -> Visible | None:
    """What `user` reads of `document`, or `None` when the document does not exist for them.
    Each number is read with its version, from one row, so the header never names another version
    than the text it heads."""
    return visible_many(user, [document])[document.pk]


def visible_many(user: Any, documents: list[Document]) -> dict[Any, Visible | None]:
    """`visible` for several documents: the rights, the editions and the acceptances in a fixed
    number of queries, then each document's repository — the accepted version's passport and,
    for a reader of pending work, its run."""
    ids = [d.pk for d in documents]
    rights_of = rights_on_many(user, ids)
    editions, acceptances = _latest(ids)
    created = {
        v.document_id: v
        for v in Version.objects.filter(document_id__in=ids, kind=VersionKind.CREATED)
    }
    return {
        d.pk: _visible(
            d, rights_of.get(d.pk, frozenset()), editions.get(d.pk), acceptances.get(d.pk), created
        )
        for d in documents
    }


def _latest(ids: list[Any]) -> tuple[dict[Any, Edition], dict[Any, Acceptance]]:
    """Each document's latest edition and latest acceptance, in two queries."""
    editions: dict[Any, Edition] = {}
    for edition in Edition.objects.filter(version__document_id__in=ids).select_related("version"):
        known = editions.get(edition.version.document_id)
        if known is None or number_key(edition.number) > number_key(known.number):
            editions[edition.version.document_id] = edition
    acceptances: dict[Any, Acceptance] = {}
    for acceptance in Acceptance.objects.filter(version__document_id__in=ids).select_related(
        "version__document"
    ):
        document_id = acceptance.version.document_id
        known_acceptance = acceptances.get(document_id)
        if known_acceptance is None or number_key(acceptance.number) > number_key(
            known_acceptance.number
        ):
            acceptances[document_id] = acceptance
    return editions, acceptances


def _past_edition(edition: Edition | None, acceptance: Acceptance | None) -> bool:
    """Whether the text starts beyond the latest edition before any pending run: no edition
    yet, or an acceptance since it — the opposite of `_visible`'s canonical start."""
    return edition is None or (
        acceptance is not None and number_key(edition.number) <= number_key(acceptance.number)
    )


def any_beyond_edition(documents: list[Document]) -> bool:
    """Whether a holder of *view pending* reads any of `documents` beyond its latest edition, as
    `visible_many` would show it, stopping at the first: a document without an edition, or
    accepted since it, decides in two queries; the rest are read one repository at a time for a
    run since the edition. One whose record cannot be read is passed over with a warning, since
    every page asks this."""
    editions, acceptances = _latest([d.pk for d in documents])
    rest = []
    for document in documents:
        edition = editions.get(document.pk)
        if _past_edition(edition, acceptances.get(document.pk)):
            return True
        rest.append((document, edition))
    for document, edition in rest:
        try:
            if run(document, since=edition.version if edition is not None else None):
                return True
        except Exception:  # noqa: BLE001 — one unreadable record must not fail every page
            logger.warning(
                "a document's version could not be read", extra={"document": document.number}
            )
    return False


def _visible(
    document: Document,
    rights: frozenset[Right],
    edition: Edition | None,
    acceptance: Acceptance | None,
    created: dict[Any, Version],
) -> Visible | None:
    canonical = edition.number if edition is not None else None
    if Right.VIEW_PENDING not in rights and Right.VIEW_ACCEPTED not in rights:
        if Right.VIEW_CANONICAL not in rights or edition is None:
            return None
        return Visible(edition.version, edition.number, "canonical", canonical)
    if edition is not None and not _past_edition(edition, acceptance):
        start, number, stance = edition.version, edition.number, "canonical"
    elif acceptance is not None:
        start, number, stance = accepted_content_version(acceptance), acceptance.number, "accepted"
    else:
        start, number, stance = created[document.pk], BEFORE_ANY_ACCEPTANCE, "accepted"
    pending = run(document, since=start) if Right.VIEW_PENDING in rights else []
    if pending:
        return Visible(pending[-1], f"{number}-{len(pending)}", "pending", canonical)
    return Visible(start, number, stance, canonical)


def latest_visible(user: Any, document: Document) -> Version | None:
    """The version `visible` names, or `None`."""
    seen = visible(user, document)
    return seen.version if seen is not None else None
