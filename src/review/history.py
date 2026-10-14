"""What a reader may see of a document's past (ADR-0007, DL-0209, DL-0251, DL-0286): the History
tab's entries, and the one resolver every page that opens a past version asks.

**The ceiling.** A viewing right reaches the current version of each stance it includes — *view
canonical* the latest edition; *view accepted* also the latest accepted content version, the
`created` one before any acceptance; *view pending* also every version of the run. A history right
widens that within the reader's stances, never past them: *view previous canonical versions* adds
every edition, *view all history* every content version up to the latest the reader's ladder
reaches. A passport commit is never opened as a version: its entry opens the version it decides
on.

**The tab's breadth** is the history rights' and *accept*'s: every entry within the ceiling to a
holder of *view all history*, the canonisations to a holder of *view previous canonical versions*,
the pending run to a holder of *accept* (DL-0251); nobody else holds the tab.

A page reads the ceiling once, as a `Ceiling`, and asks it everything: a forbidden number then
costs exactly what a missing one does, so neither answer tells the other apart (ADR-0008).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from access.rights import Right, rights_on
from documents.models import Document, Version, VersionKind
from editing import numbering

CONTENT = (VersionKind.CREATED, VersionKind.EDIT, VersionKind.REVIEWER_EDIT)
PASSPORT = (VersionKind.ACCEPTANCE, VersionKind.RETURN, VersionKind.APPROVAL)
HISTORY_RIGHTS = frozenset({Right.VIEW_ALL_HISTORY, Right.VIEW_PREVIOUS_CANONICAL, Right.ACCEPT})


@dataclass(frozen=True)
class Entry:
    """One line of the History tab: a version and its event — `created`, `edit`,
    `reviewer_edit`, `acceptance`, `return`, `approval` — or a freeze's `freeze` or `unfreeze`,
    with no version and no number. `number` opens the version the entry concerns, whose commit is
    `target`; `boundary` marks the latest accepted content version, to a reader of accepted
    text."""

    version: Version | None
    number: str
    event: str
    actor: Any
    at: datetime
    boundary: bool = False
    target: str | None = None


def has_tab(rights: frozenset[Right]) -> bool:
    """Whether a reader with `rights` holds the History tab."""
    return bool(rights & HISTORY_RIGHTS)


# A commit id no version carries: looked up in place of a number no version carries, so that a
# missing number costs the query a forbidden one does.
ABSENT = "0" * 40


@dataclass(frozen=True)
class Ceiling:
    """One reader's reach into one document's past, read once per request."""

    document: Document
    rights: frozenset[Right]
    history: numbering.History
    reach: frozenset[str]
    accepted: str

    def version(self, number: str) -> Version | None:
        """The content version `number` names when the ceiling reaches it, else `None` — one
        query either way."""
        sha = self.history.aliases.get(number) if numbering.NUMBER.fullmatch(number) else None
        found = Version.objects.filter(
            document=self.document, commit_sha=sha or ABSENT, kind__in=CONTENT
        ).first()
        return found if found is not None and found.commit_sha in self.reach else None

    def reaches(self, version: Version) -> bool:
        return version.commit_sha in self.reach

    def number(self, version: Version) -> str:
        return self.history.number(version.commit_sha) or ""

    def reachable(self) -> list[tuple[str, Version]]:
        """Every content version within the ceiling as `(number, version)`, oldest first."""
        rows = {
            v.commit_sha: v
            for v in Version.objects.filter(document=self.document, commit_sha__in=self.reach)
        }
        return [
            (c.number, rows[c.sha])
            for c in self.history.commits
            if c.kind in CONTENT and c.sha in rows
        ]


def ceiling(user: Any, document: Document) -> Ceiling:
    """What `user`'s rights reach of `document`'s past. `ValueError` or `LookupError` for a record
    that does not read, which every page answers as a missing one."""
    from editions.models import Edition
    from editions.visible import latest_edition
    from review import services

    rights = rights_on(user, document)
    history = numbering.history(document)
    accepted = services.base(document).commit_sha
    edition = latest_edition(document)
    pending = [v.commit_sha for v in services.run(document)]
    reach: set[str] = set()
    cap: str | None = None
    if edition is not None and rights & {Right.VIEW_CANONICAL, Right.VIEW_ACCEPTED}:
        reach.add(edition.version.commit_sha)
        cap = edition.version.commit_sha
    if Right.VIEW_ACCEPTED in rights:
        reach.add(accepted)
        cap = accepted
    if Right.VIEW_PENDING in rights:
        reach.add(accepted)
        reach.update(pending)
        cap = pending[-1] if pending else accepted
    content = [c.sha for c in history.commits if c.kind in CONTENT]
    if cap is not None and Right.VIEW_PREVIOUS_CANONICAL in rights:
        reach.update(
            Edition.objects.filter(version__document=document).values_list(
                "version__commit_sha", flat=True
            )
        )
    if cap is not None and Right.VIEW_ALL_HISTORY in rights and cap in content:
        reach.update(content[: content.index(cap) + 1])
    return Ceiling(document, rights, history, frozenset(reach), accepted)


def version_for(user: Any, document: Document, number: str) -> Version | None:
    """The version `number` names, when `user`'s ceiling reaches it; else `None`, which every page
    answers as a missing one (ADR-0008)."""
    return ceiling(user, document).version(number)


def reaches(user: Any, document: Document, version: Version) -> bool:
    """Whether `user`'s ceiling reaches `version`."""
    return ceiling(user, document).reaches(version)


def reachable(user: Any, document: Document) -> list[tuple[str, Version]]:
    """Every content version `user`'s ceiling reaches, as `(number, version)`, oldest first: the
    choosers of the historical page, the compare page and a kept draft read it (DL-0417)."""
    return ceiling(user, document).reachable()


def entries(user: Any, document: Document) -> list[Entry]:
    """The History tab's entries for `user`, oldest first; empty for a reader without the tab."""
    past = ceiling(user, document)
    rights = past.rights
    if not has_tab(rights):
        return []
    from review import services

    everything = Right.VIEW_ALL_HISTORY in rights
    run = {v.commit_sha for v in services.run(document)} if Right.ACCEPT in rights else set()
    rows = {
        v.commit_sha: v for v in Version.objects.filter(document=document).select_related("author")
    }
    # Where accepted text ends, to those who read accepted text: a reader of canonical text alone
    # never learns whether accepted work lies beyond the edition (DL-0209).
    accepted = past.accepted if Right.VIEW_ACCEPTED in rights else None
    found: list[tuple[datetime, Entry]] = []
    for commit in past.history.commits:
        version = rows.get(commit.sha)
        if version is None:
            # A commit whose row is not derived yet is not part of the history until it is.
            continue
        target = commit.decides if commit.kind in PASSPORT else commit.sha
        if everything:
            shown = target in past.reach
        else:
            canonisation = Right.VIEW_PREVIOUS_CANONICAL in rights and (
                commit.kind == VersionKind.APPROVAL and target in past.reach
            )
            shown = canonisation or commit.sha in run
        if not shown:
            continue
        entry = Entry(
            version=version,
            number=commit.number,
            event=commit.kind,
            actor=version.author,
            at=version.committed_at,
            boundary=commit.sha == accepted and commit.kind in CONTENT,
            target=target,
        )
        # Placed among the freezes by when its row was written, never later than its commit's
        # own second: a row derived again after a repair keeps its commit's place.
        found.append((min(version.created_at, version.committed_at + timedelta(seconds=1)), entry))
    if not everything:
        return [entry for _key, entry in found]
    # The commits keep git's order; a freeze goes before the first commit written after it.
    freezes = sorted(_freezes(past, rows), key=lambda pair: pair[0])
    ordered: list[Entry] = []
    for key, entry in found:
        while freezes and freezes[0][0] < key:
            ordered.append(freezes.pop(0)[1])
        ordered.append(entry)
    return ordered + [entry for _key, entry in freezes]


def _freezes(past: Ceiling, rows: dict[str, Version]) -> list[tuple[datetime, Entry]]:
    """Each freeze and each *unfreeze* as entries of their own, keyed to fall between the versions
    they fell between. A freeze's own time counts whole seconds while a version row's does not, so
    each is keyed by the time of its audit event, written in the same transaction; without one, a
    freeze falls after every version of its second. One that *make canonical* ended falls before
    its approval at the latest. To a reader of canonical text alone, only the freezes their stance
    reaches: the open one, which every reader sees (DL-0236), and those an edition they reach
    ended; a later one would tell them that accepted work lies beyond the edition."""
    from audit.models import AuditEvent
    from editions.models import Edition, Freeze, FreezeEnd

    editions = {
        e.freeze_id: e
        for e in Edition.objects.filter(version__document=past.document).select_related(
            "approval_version", "version"
        )
    }
    accepted_reader = Right.VIEW_ACCEPTED in past.rights
    audited: dict[tuple[str, str], datetime] = {
        (event.action, str((event.after or {}).get("freeze", ""))): event.at
        for event in AuditEvent.objects.filter(
            action__in=("document.frozen", "document.unfrozen"), object_id=past.document.pk
        ).only("action", "after", "at")
    }
    found: list[tuple[datetime, Entry]] = []
    for freeze in Freeze.objects.filter(document=past.document).select_related(
        "frozen_by", "ended_by"
    ):
        edition = editions.get(freeze.pk)
        if (
            not accepted_reader
            and freeze.ended_at is not None
            and (edition is None or edition.version.commit_sha not in past.reach)
        ):
            continue
        key = audited.get(
            ("document.frozen", str(freeze.pk)), freeze.frozen_at.replace(microsecond=999_999)
        )
        approval = rows.get(edition.approval_version.commit_sha) if edition is not None else None
        if approval is not None:
            key = min(key, approval.created_at - timedelta(microseconds=1))
        found.append((key, Entry(None, "", "freeze", freeze.frozen_by, freeze.frozen_at)))
        if freeze.ended_by_kind == FreezeEnd.UNFROZEN and freeze.ended_at is not None:
            ended = audited.get(("document.unfrozen", str(freeze.pk)), freeze.ended_at)
            ended = max(ended, key + timedelta(microseconds=1))
            found.append((ended, Entry(None, "", "unfreeze", freeze.ended_by, freeze.ended_at)))
    return found
