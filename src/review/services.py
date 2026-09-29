"""The run, its base, and accepting it (ADR-0001, DL-0090, DL-0092, DL-0224, DL-0267, DL-0268).

The run is every content version — `edit`, `reviewer_edit` — after the base, in the order of the
repository's history, which is linear (ADR-0003); commit times share seconds, so the order is read
from git, never from the rows. The base is the content version the latest acceptance accepted, as
its passport section records it, or the document's `created` version before any acceptance.

Accepting is one act under the document's writer lock (DL-0111): the passport commit, which is the
commit point; its version row and the `ACCEPTANCE` row, audited; the correction notices (ADR-0014);
then the authorship asked of the worker. A stop after the commit is finished by the next writer
under the lock (`settle_head`), or by the reconciler, both deriving the rows from the passport
section by one rule (`derivable`) and computing the notices of an acceptance without them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pygit2
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from access.rights import Right, rights_on
from audit.record import record
from documents import bundle, gitstore
from documents import services as documents
from documents.identity import identity_for
from documents.locks import document_lock
from documents.models import Document, Version, VersionKind
from review.models import Acceptance
from tenancy.models import Tenant
from tenancy.schemas import current_tenant

if TYPE_CHECKING:
    from identity.models import User

logger = logging.getLogger(__name__)
# How long an acceptance waits for the document's writer lock before it answers that the document
# is busy, as taking a hold does.
LOCK_WAIT_SECONDS = 10.0

CONTENT = (VersionKind.EDIT, VersionKind.REVIEWER_EDIT)
PASSPORT = "passport.md"


def _tenant_number() -> int:
    from django.db import connection

    number = current_tenant(connection)
    if number is None:
        raise RuntimeError("a run is read inside a tenant's schema")
    return number


def number_key(number: str) -> tuple[int, int]:
    major, minor = number.split(".")
    return int(major), int(minor)


def latest_acceptance(document: Document) -> Acceptance | None:
    """The document's latest acceptance: the highest number, which only grows (DL-0183)."""
    acceptances = list(Acceptance.objects.filter(version__document=document))
    return max(acceptances, key=lambda a: number_key(a.number), default=None)


def accepted_sha(acceptance: Acceptance, document_number: int) -> str:
    """The commit of the content version `acceptance` decided on, as its passport section records
    it; `acceptance.version` should be loaded with it."""
    repo = gitstore.open_repository(_tenant_number(), document_number)
    text = gitstore.read(repo, PASSPORT, acceptance.version.commit_sha).decode("utf-8")
    entries = [
        entry
        for entry in bundle.passport_entries(text)
        if entry.kind == "acceptance" and entry.number == acceptance.number
    ]
    if not entries:
        raise LookupError(f"no passport section for acceptance {acceptance.number}")
    return entries[-1].version


def accepted_content_version(acceptance: Acceptance) -> Version:
    """The content version `acceptance` decided on, as its passport section records it."""
    document = acceptance.version.document
    return Version.objects.get(
        document=document, commit_sha=accepted_sha(acceptance, document.number)
    )


def base(document: Document) -> Version:
    """What the run is read against: the latest accepted content version, or the `created` one."""
    acceptance = latest_acceptance(document)
    if acceptance is not None:
        return accepted_content_version(acceptance)
    return Version.objects.get(document=document, kind=VersionKind.CREATED)


def commits_after(repo: pygit2.Repository, start: str, head: str) -> list[str]:
    """The commits after `start` up to `head`, oldest first, walked back from `head` and stopped
    at `start`, so the cost is the run's; `LookupError` when `start` is not behind `head`."""
    if start == head:
        return []
    if not repo.descendant_of(head, start):
        raise LookupError(f"commit {start} is not in the history of {head}")
    walker = repo.walk(head, pygit2.enums.SortMode.TOPOLOGICAL)
    walker.hide(start)
    return [str(commit.id) for commit in walker][::-1]


def _head(repo: pygit2.Repository) -> str:
    head = gitstore.head(repo)
    if head is None:
        raise LookupError("a document with no commit")
    return head


def run(
    document: Document, *, since: Version | None = None, head: str | None = None
) -> list[Version]:
    """The content versions after `since` — the base when not given — up to `head`, the head when
    not given, oldest first: the one definition of a run, shared by the state, the tab and
    accepting. A commit whose row is not derived yet is not part of it until it is."""
    start = since if since is not None else base(document)
    repo = gitstore.open_repository(_tenant_number(), document.number)
    shas = commits_after(repo, start.commit_sha, head if head is not None else _head(repo))
    rows = {
        version.commit_sha: version
        for version in Version.objects.filter(
            document=document, kind__in=CONTENT, commit_sha__in=shas
        ).select_related("author")
    }
    return [rows[sha] for sha in shas if sha in rows]


def next_number(entries: list[bundle.PassportEntry]) -> str:
    """The number the next acceptance carries after the passport's `entries`: `N` the editions
    made, `M` the acceptances since the latest one, plus one (DL-0183) — read from the passport,
    so no number is given twice."""
    editions = since = 0
    for entry in entries:
        if entry.kind == "approval":
            editions, since = editions + 1, 0
        elif entry.kind == "acceptance":
            since += 1
    return f"{editions}.{since + 1}"


def passport_at(repo: pygit2.Repository, sha: str) -> list[bundle.PassportEntry]:
    """The passport's sections at commit `sha`."""
    return bundle.passport_entries(gitstore.read(repo, PASSPORT, sha).decode("utf-8"))


class AcceptRefused(Exception):
    """An acceptance the document's state does not allow; `reason` names why, and `committed` is
    the version *accept as* made before the refusal, when it made one."""

    def __init__(self, reason: str, committed: Version | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.committed = committed


class InjectedFault(Exception):
    """Raised by `accept` after the step a crash test names; never set in production."""


def _fault(step: int, fault_at: int | None) -> None:
    if fault_at == step:
        raise InjectedFault(step)


def refusal(
    document: Document,
    reviewer: User,
    *,
    confirmed: str | None = None,
    pending: list[Version] | None = None,
) -> str | None:
    """Why `reviewer` may not accept the document's run now, or `None`: checked in this order —
    no linked group holds *accept*; someone has reserved the document (DL-0224); the run is empty;
    the reviewer does not hold *accept*; the run grew past the version the confirmation named.
    `pending` is the run when the caller has read it."""
    from editing.models import Hold
    from review.state import with_reviewer

    if document.pk not in with_reviewer([document.pk]):
        return "no_reviewer"
    if Hold.objects.filter(
        document=document, released_at__isnull=True, reserved_at__isnull=False
    ).exists():
        return "reserved"
    pending = run(document) if pending is None else pending
    if not pending:
        return "nothing_to_accept"
    if Right.ACCEPT not in rights_on(reviewer, document):
        return "not_a_reviewer"
    if confirmed is not None and pending[-1].commit_sha != confirmed:
        return "run_changed"
    return None


def accept(
    document: Document,
    reviewer: User,
    *,
    confirmed: str | None = None,
    fault_at: int | None = None,
) -> Acceptance:
    """Accept the document's run as `reviewer`, under the document's lock; `AcceptRefused` with
    the reason when it may not be accepted. `confirmed` is the last version the confirmation
    named, when there was one."""
    tenant_number = _tenant_number()
    with document_lock(tenant_number, document.number, timeout=LOCK_WAIT_SECONDS):
        acceptance = accept_locked(document, reviewer, confirmed=confirmed, fault_at=fault_at)
    ask_authorship(document, acceptance)
    return acceptance


def accept_locked(
    document: Document,
    reviewer: User,
    *,
    confirmed: str | None = None,
    fault_at: int | None = None,
) -> Acceptance:
    """`accept`'s body, for a caller that already holds the document's writer lock. The document's
    row stays locked from the refusal's check to the rows — the lock its group links change under,
    so a link removed meanwhile is seen; a right revoked from a group, or a member removed, is not
    ordered by it, as for holds."""
    tenant_number = _tenant_number()
    settle_head(document)
    repo = gitstore.open_repository(tenant_number, document.number)
    with transaction.atomic():
        locked = Document.objects.select_for_update().get(pk=document.pk)
        before = base(locked)
        head = _head(repo)
        pending = run(locked, since=before, head=head)
        reason = refusal(locked, reviewer, confirmed=confirmed, pending=pending)
        if reason is not None:
            raise AcceptRefused(reason)
        entries = passport_at(repo, head)
        now = timezone.now().replace(microsecond=0)
        entry = bundle.PassportEntry(
            kind="acceptance",
            number=next_number(entries),
            at=now,
            by=str(reviewer.pk),
            version=pending[-1].commit_sha,
        )
        passport = gitstore.read(repo, PASSPORT, head).decode("utf-8")
        # (1) The commit point: the passport's section.
        sha = gitstore.commit(
            repo,
            {PASSPORT: bundle.append_passport(passport, entry).encode("utf-8")},
            identity_for(reviewer, at=now),
            f"Accepted as {entry.number}",
            gitstore.Kind.ACCEPTANCE,
        )
        _fault(1, fault_at)
        # (2) Its version row and the acceptance, audited.
        acceptance = derive_acceptance(document, sha, Derivation(entry, before, reviewer))
    _fault(2, fault_at)
    # (3) The correction notices of the run (ADR-0014): computed here, and by the reconciler for an
    # acceptance whose notices a failure left uncomputed.
    compute_notices(acceptance)
    _fault(3, fault_at)
    return acceptance


def compute_notices(acceptance: Acceptance) -> None:
    """The notices of `acceptance`; a failure is logged and left to the reconciler, which computes
    them for any acceptance without them — the acceptance stands either way."""
    from review import notices

    try:
        notices.compute(acceptance)
    except Exception:  # noqa: BLE001 — the reconciler retries; the acceptance is committed
        logger.exception("correction notices not computed", extra={"accepted": acceptance.number})


class RecordIncomplete(Exception):
    """The head is an acceptance whose rows cannot be derived from its passport section; nothing
    is written on top of it until the reconciler's report is answered."""


@dataclass(frozen=True)
class Derivation:
    """What an acceptance's passport commit implies: its section, the content version the
    previous acceptance accepted — or the `created` one — and the reviewer."""

    entry: bundle.PassportEntry
    accepted_from: Version
    reviewer: User


def committer(commit: pygit2.Commit, tenant_number: int) -> User | None:
    """The commit's author, when a person of this tenant named as the platform names them."""
    from documents.identity import DOMAIN
    from identity.models import Membership, User

    name = commit.author.name
    if commit.author.email != f"{name}@{DOMAIN}":
        return None
    try:
        user = User.objects.filter(pk=name).first()
    except (ValueError, TypeError, ValidationError):
        return None
    if (
        user is None
        or not Membership.objects.filter(user=user, tenant__number=tenant_number).exists()
    ):
        return None
    return user


def derivable(document: Document, repo: pygit2.Repository, sha: str) -> Derivation | str:
    """The rows commit `sha` implies when it is an acceptance exactly as `accept` writes one, or
    why not: it changes the passport alone, appending one acceptance section by its author, timed
    as the commit, numbered next, deciding on the last content version before it, which follows
    the one accepted before."""
    commit = gitstore.commit_at(repo, sha)
    if gitstore.kind_of(commit.message) is not gitstore.Kind.ACCEPTANCE or not commit.parents:
        return "not an acceptance"
    parent = commit.parents[0]
    reviewer = committer(commit, _tenant_number())
    if reviewer is None:
        return "its author is not of this tenant"
    try:
        entries, before = passport_at(repo, sha), passport_at(repo, str(parent.id))
    except (KeyError, ValueError, UnicodeDecodeError):
        return "its passport does not read"
    if len(entries) != len(before) + 1 or entries[: len(before)] != before:
        return "it does not append one section"
    if [delta.new_file.path for delta in repo.diff(parent, commit).deltas] != [PASSPORT]:
        return "it changes more than the passport"
    entry = entries[-1]
    if entry.kind != "acceptance" or entry.by != str(reviewer.pk):
        return "its section is not its author's acceptance"
    if int(entry.at.timestamp()) != commit.author.time or entry.number != next_number(before):
        return "its section is not timed or numbered as the platform writes it"
    previous = [e for e in before if e.kind == "acceptance"]
    accepted_from = Version.objects.filter(
        document=document,
        **({"commit_sha": previous[-1].version} if previous else {"kind": VersionKind.CREATED}),
    ).first()
    if accepted_from is None:
        return "the version accepted before it has no row"
    try:
        shas = commits_after(repo, accepted_from.commit_sha, str(parent.id))
    except LookupError:
        return "it does not follow the version accepted before it"
    content = [
        s
        for s in shas
        if gitstore.kind_of(gitstore.commit_at(repo, s).message)
        in (
            gitstore.Kind.EDIT,
            gitstore.Kind.REVIEWER_EDIT,
        )
    ]
    if not content or content[-1] != entry.version:
        return "it does not decide on the last version before it"
    if not Version.objects.filter(document=document, commit_sha=entry.version).exists():
        return "the version it decides on has no row"
    return Derivation(entry, accepted_from, reviewer)


def settle_head(document: Document) -> None:
    """Under the document's writer lock, before anything is read for a write or written: every
    commit at the head whose rows a stop left underived — a content version a finish committed, an
    acceptance's passport commit — has them derived, oldest first, and an acceptance its notices
    computed; so nothing is written over a commit the rows do not know, no run is read short of
    git, and no number is given twice (DL-0111). `RecordIncomplete` when one cannot be."""
    tenant_number = _tenant_number()
    repo = gitstore.open_repository(tenant_number, document.number)
    head = gitstore.head(repo)
    if head is None:
        return
    known = set(Version.objects.filter(document=document).values_list("commit_sha", flat=True))
    unknown: list[pygit2.Commit] = []
    for commit in repo.walk(head, pygit2.enums.SortMode.TOPOLOGICAL):
        if str(commit.id) in known:
            break
        unknown.append(commit)
    for commit in reversed(unknown):
        sha = str(commit.id)
        kind = gitstore.kind_of(commit.message)
        if kind is gitstore.Kind.ACCEPTANCE:
            found = derivable(document, repo, sha)
            if isinstance(found, str):
                raise RecordIncomplete(found)
            compute_notices(derive_acceptance(document, sha, found))
        elif kind in (gitstore.Kind.EDIT, gitstore.Kind.REVIEWER_EDIT) and commit.parents:
            author = committer(commit, tenant_number)
            if author is None:
                raise RecordIncomplete("a version's author is not of this tenant")
            with transaction.atomic():
                documents.derive_version(document, commit, author)
                record(
                    actor=author,
                    action="document.version_committed",
                    obj=document,
                    before=None,
                    after={"number": document.number, "commit": sha},
                    tenant=Tenant.objects.get(number=tenant_number),
                )
        else:
            raise RecordIncomplete(f"a commit the rows do not know: {kind}")


def derive_acceptance(document: Document, sha: str, derivation: Derivation) -> Acceptance:
    """The rows an acceptance's passport commit implies — its version, when not there yet, and its
    `ACCEPTANCE` — audited with the reviewer as the actor whoever derives them, in one transaction
    (DL-0111)."""
    entry = derivation.entry
    if entry.kind != "acceptance" or entry.number is None:
        raise ValueError("not an acceptance's passport section")
    repo = gitstore.open_repository(_tenant_number(), document.number)
    with transaction.atomic():
        version = Version.objects.filter(document=document, commit_sha=sha).first()
        if version is None:
            version = documents.derive_version(
                document, gitstore.commit_at(repo, sha), derivation.reviewer
            )
        acceptance = Acceptance.objects.create(
            version=version,
            accepted_from=derivation.accepted_from,
            number=entry.number,
            reviewer=derivation.reviewer,
            at=entry.at,
        )
        record(
            actor=derivation.reviewer,
            action="document.accepted",
            obj=document,
            before=None,
            after={"number": document.number, "accepted": entry.number, "commit": sha},
            tenant=Tenant.objects.get(number=_tenant_number()),
        )
    return acceptance


def ask_authorship(document: Document, acceptance: Acceptance) -> None:
    """The worker asked for the rows of the accepted version, kept beside the head's (DL-0266),
    and of the new head. The acceptance stands whatever the broker says: the reconciler asks
    again for a kept version without its rows."""
    from editing import tasks

    tenant_number = _tenant_number()
    for sha in (accepted_sha(acceptance, document.number), acceptance.version.commit_sha):
        try:
            tasks.queue_authorship(tenant_number, document.number, sha)
        except Exception:  # noqa: BLE001 — any failure to publish is the reconciler's to repair
            logger.warning("authorship not queued", extra={"document": document.number})


def accept_as(hold: Any, user: User, summary: str, *, confirmed: str | None = None) -> Acceptance:
    """*Accept as N.M* (DL-0222): the holder's draft committed as their version, then the whole run
    accepted, in one acquisition of the document's lock so no other ref update falls between
    them. `confirmed` is the head the screen was drawn from: a head that moved since is refused as
    `run_changed`, like a refusal the draft cannot change, before anything is committed. A refusal
    after the version's commit leaves the version pending, as *create version* would, and names
    it (`AcceptRefused.committed`); the holder's own reservation ends with the hold (DL-0224)."""
    from editing import services as editing
    from review.state import with_reviewer

    tenant_number = _tenant_number()
    document = Document.objects.get(pk=hold.document_id)
    version: Version | None = None
    try:
        with document_lock(tenant_number, document.number, timeout=LOCK_WAIT_SECONDS):
            settle_head(document)
            repo = gitstore.open_repository(tenant_number, document.number)
            if confirmed is not None and gitstore.head(repo) != confirmed:
                raise AcceptRefused("run_changed")
            if document.pk not in with_reviewer([document.pk]):
                raise AcceptRefused("no_reviewer")
            if Right.ACCEPT not in rights_on(user, document):
                raise AcceptRefused("not_a_reviewer")
            version = editing.commit_draft_locked(hold, user, summary)
            try:
                acceptance = accept_locked(document, user)
            except AcceptRefused as refused:
                raise AcceptRefused(refused.reason, version) from refused
    finally:
        if version is not None:
            editing.ask_authorship(tenant_number, document, version.commit_sha)
    ask_authorship(document, acceptance)
    return acceptance
