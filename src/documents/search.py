"""Search and the type filter (DL-0197, DL-0236): titles of documents and of their appendices,
never text, at the version the searcher reads; archived documents are found by nobody
(DL-0233). Candidates are narrowed in SQL, then confirmed against the searcher's rights."""

from __future__ import annotations

from typing import Any

from django.db.models import Q
from django.db.models.functions import Collate, Lower

from documents.models import Document, DocumentState, DocumentType, PartIndex, PartKind

QUERY_MAX = 200


def query(text: str) -> str:
    """The words searched, or a type's code: stripped, a longer one cut to its first 200
    characters; a NUL character, which no title or code can hold, taken out."""
    return text.replace("\x00", "").strip()[:QUERY_MAX]


def _matching(field: str, words: str) -> Q:
    # Case folded as Ukrainian is read, whatever the database's own locale.
    return Q(**{f"{field}_folded__contains": words.lower()})


def find(user: Any, words: str, type_code: str | None) -> list[Document]:
    """The active documents `user` may read whose title, or the title of an appendix of the
    version they read, holds `words` in any case; with `type_code`, of that type alone — with no
    `words`, every one of the type. Ordered by title as Ukrainian is read, then number.

    The same rows are read whatever the words, and an appendix is a candidate only at a version
    its reader could read at some time, chosen in the database (DL-10-003): the work a search costs
    tells nothing of a version they could never read. The residual the threat model accepts — a
    title of text they could read when it was current, and a version committed in the same second
    as an acceptance — stays."""
    from access.rights import readable

    rows = Document.objects.filter(state=DocumentState.ACTIVE)
    if type_code is not None:
        rows = rows.filter(document_type__code=type_code)
    allowed = readable(user, list(rows.values_list("pk", flat=True)))
    rows = rows.filter(pk__in=allowed)
    if words:
        rows = rows.annotate(title_folded=Lower(Collate("title", "uk-x-icu"))).filter(
            _matching("title", words) | Q(pk__in=appendix_candidates(user, allowed, words))
        )
    shown = list(
        rows.select_related("document_type", "folder").order_by(
            Collate("title", "uk-x-icu"), "number"
        )
    )
    if not words:
        return shown
    # The rule the prefilter applies, lower case, so nothing it let through is judged otherwise.
    folded = words.lower()
    by_title = {d.pk for d in shown if folded in d.title.lower()}
    by_appendix = _by_appendix(user, [d for d in shown if d.pk not in by_title], folded)
    return [d for d in shown if d.pk in by_title or d.pk in by_appendix]


def appendix_candidates(user: Any, documents: set[Any], words: str) -> set[Any]:
    """Of `documents`, those with an appendix title holding `words` at a version `user` could
    read at some time — decided in the query, so no row beyond that reaches the application."""
    every, versions = _readable_versions(user, documents)
    return set(
        PartIndex.objects.filter(kind=PartKind.APPENDIX)
        .filter(Q(document_id__in=every) | Q(version_id__in=versions))
        .annotate(title_folded=Lower(Collate("title", "uk-x-icu")))
        .filter(_matching("title", words))
        .values_list("document_id", flat=True)
    )


def _readable_versions(user: Any, documents: set[Any]) -> tuple[set[Any], set[Any]]:
    """The documents of which `user` could read every version — a reader of pending work — and,
    of the others, the versions they could read when each was current: to a reader of accepted
    text the first version, every edition's, every accepted one — each acceptance's predecessor
    as its row records it, and the latest acceptance's as the latest content version committed
    by its moment, to the second; to a reader of canonical text alone every edition's. From the
    database alone, in a fixed number of queries whatever the words."""
    from access.rights import Right, rights_on_many
    from documents.models import Version, VersionKind
    from editions.models import Edition
    from review.models import Acceptance

    ids = list(documents)
    rights = rights_on_many(user, ids)
    every = {pk for pk in ids if Right.VIEW_PENDING in rights.get(pk, frozenset())}
    accepted = {
        pk for pk in ids if pk not in every and Right.VIEW_ACCEPTED in rights.get(pk, frozenset())
    }
    canonical = {
        pk
        for pk in ids
        if pk not in every | accepted and Right.VIEW_CANONICAL in rights.get(pk, frozenset())
    }
    versions = set(
        Edition.objects.filter(version__document_id__in=accepted | canonical).values_list(
            "version_id", flat=True
        )
    )
    if not accepted:
        return every, versions
    latest: dict[Any, Any] = {}
    for document, previous, at in Acceptance.objects.filter(
        version__document_id__in=accepted
    ).values_list("version__document_id", "accepted_from_id", "version__committed_at"):
        versions.add(previous)
        latest[document] = max(at, latest.get(document, at))
    content = (VersionKind.CREATED, VersionKind.EDIT, VersionKind.REVIEWER_EDIT)
    newest: dict[Any, tuple[Any, Any]] = {}
    for document, version, kind, at in Version.objects.filter(
        document_id__in=accepted, kind__in=content
    ).values_list("document_id", "id", "kind", "committed_at"):
        if kind == VersionKind.CREATED:
            versions.add(version)
        # The latest acceptance accepted the newest content committed by its moment.
        bound = latest.get(document)
        if bound is not None and at <= bound and at >= newest.get(document, (at, None))[0]:
            newest[document] = (at, version)
    versions |= {version for _at, version in newest.values()}
    return every, versions


def _by_appendix(user: Any, documents: list[Document], folded: str) -> set[Any]:
    """Of `documents`, those an appendix of the version `user` reads names `folded`: an appendix
    title only pending work holds is never found by someone who may not see it (DL-0197)."""
    if not documents:
        return set()
    from documents.views import _versions

    # As the list reads them: a document whose record cannot be read is read as nothing.
    seen = _versions(user, documents)
    reads = {pk: shown.version.pk for pk, shown in seen.items() if shown is not None}
    titles = PartIndex.objects.filter(
        kind=PartKind.APPENDIX, version_id__in=reads.values()
    ).values_list("version_id", "title")
    matching = {version for version, title in titles if folded in title.lower()}
    return {pk for pk, version in reads.items() if version in matching}


def filter_types(user: Any) -> list[DocumentType]:
    """The types the filter offers: those of the active documents `user` may open, retired ones
    included, by label as Ukrainian is read. A fixed number of queries whatever the corpus."""
    from access.rights import readable

    held = list(
        Document.objects.filter(state=DocumentState.ACTIVE).values_list("pk", "document_type_id")
    )
    allowed = readable(user, [pk for pk, _kind in held])
    kinds = {kind for pk, kind in held if pk in allowed}
    return list(
        DocumentType.objects.filter(pk__in=kinds).order_by(Collate("label", "uk-x-icu"), "code")
    )
