"""Freezing a document, unfreezing it and making it canonical (DL-0189, DL-0260, DL-0267, DL-0353,
ADR-0016).

A freeze is taken under the document's writer lock with its row locked, as a hold is, so a hold
opened meanwhile is seen: a document is frozen only when nobody holds it, a reserved hold
included (DL-0223).

Making canonical is one act under the same lock: the approval's passport section committed as
`approval`, which is the commit point; its annotated tag; the version and `EDITION` rows,
audited; the freeze ended. A stop after the commit is finished by the next writer under the lock
(`review.services.settle_head`) or by the reconciler, both by one rule: `derivable_approval`,
then `derive_approval`, which does whatever of the rest is missing (DL-0111).
"""

from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

import pygit2
from django.db import transaction
from django.utils import timezone

from access.rights import Right, rights_on
from audit.record import record
from documents import bundle, gitstore
from documents import services as documents
from documents.identity import identity_for
from documents.locks import document_lock
from documents.models import Document, DocumentState, Version
from editing import holds
from editions.models import REASON_MAX, Edition, Freeze, FreezeEnd, open_freeze
from notifications.models import Category, Event
from review import services as review
from review.models import Acceptance
from tenancy.models import Tenant

if TYPE_CHECKING:
    from identity.models import User

logger = logging.getLogger(__name__)

# How long an act waits for the document's writer lock before it answers that the document is
# busy, as taking a hold does.
LOCK_WAIT_SECONDS = holds.LOCK_WAIT_SECONDS


class NotFrozen(ValueError):
    """The freeze an unfreeze would end is not open."""


class FreezeRefused(Exception):
    """A freeze, or its end, the document's state or the person's rights do not allow; `reason`
    names why: `already_frozen`, `held`, `held_unfreeze`, `made_canonical`, `not_active`,
    `not_permitted`, `reason_invalid`."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# Characters that reorder the text around them — the embeddings, overrides and isolates, and the
# implicit marks that move neutral characters: a reason is drawn beside who gave it, and must
# read as it was stored (DL-0378).
BIDI_CONTROLS = frozenset(
    "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069\u200e\u200f\u061c"
)


def valid_reason(reason: str) -> bool:
    """One line of printable text, at most `REASON_MAX` characters, or nothing."""
    return len(reason) <= REASON_MAX and not any(
        unicodedata.category(ch) in ("Cc", "Cs", "Cn", "Zl", "Zp") or ch in BIDI_CONTROLS
        for ch in reason
    )


def freeze_refusal(document: Document, user: User) -> str | None:
    """Why `user` may not freeze `document` now, or `None`, checked in the act's order."""
    if document.state != DocumentState.ACTIVE:
        return "not_active"
    if Right.FREEZE not in rights_on(user, document):
        return "not_permitted"
    if open_freeze(document) is not None:
        return "already_frozen"
    if holds.open_hold(document) is not None:
        return "held"
    return None


def freeze(document: Document, user: User, reason: str = "", *, via: str = "") -> Freeze:
    """Freeze `document` as `user`, with an optional reason; `FreezeRefused` with the reason
    when it may not be. `via` names the operator's command that acted as `user`, for the audit
    trail. `documents.locks.LockTimeout` when the lock stays busy; `RecordIncomplete` when a
    stopped act at the head cannot be finished."""
    with document_lock(holds.tenant_number(), document.number, timeout=LOCK_WAIT_SECONDS):
        return freeze_locked(document, user, reason, via=via)


def freeze_locked(document: Document, user: User, reason: str = "", *, via: str = "") -> Freeze:
    """`freeze`'s body, for a caller that already holds the document's writer lock. A stopped
    approval at the head is finished first, so its freeze is never taken for this one's."""
    reason = reason.strip()
    if not valid_reason(reason):
        raise FreezeRefused("reason_invalid")
    number = holds.tenant_number()
    review.settle_head(document)
    with transaction.atomic():
        locked = Document.objects.select_for_update().get(pk=document.pk)
        refused = freeze_refusal(locked, user)
        if refused is not None:
            raise FreezeRefused(refused)
        made = Freeze.objects.create(
            # Whole seconds, as the passport counts an approval's time: a freeze and the approval
            # that ends it in one second then read in their order.
            document=locked,
            reason=reason,
            frozen_by=user,
            frozen_at=timezone.now().replace(microsecond=0),
        )
        record(
            actor=user,
            action="document.frozen",
            obj=locked,
            before=None,
            after={"number": locked.number, "freeze": str(made.pk), **_via(via)},
            tenant=Tenant.objects.get(number=number),
        )
        _tell_readers(locked, Event.FROZEN, user)
    return made


def _tell_readers(
    document: Document,
    event: Event,
    actor: User | None,
    *,
    version: Version | None = None,
    facts: dict[str, Any] | None = None,
    at: datetime | None = None,
) -> None:
    """The document's readers and the organisation's administrators told of a freeze, its end
    or an edition — never the person who acted; at the act's own time when it is given, so an
    edition the reconciler derives later is dated when it was made."""
    from notifications.services import notify, others, readers_and_administrators

    notify(
        users=others(readers_and_administrators(document), actor),
        category=Category.DOCUMENT,
        event=event,
        actor=actor,
        document=document,
        version=version,
        facts=facts,
        at=at,
    )


def _via(via: str) -> dict[str, str]:
    return {"via": via} if via else {}


class CanonicalRefused(Exception):
    """*Make canonical* the document's state or the person's rights do not allow; `reason` names
    why: `not_permitted`, `not_frozen`, `nothing_accepted`, `unaccepted_changes`,
    `distinct_approver`, `accepted_changed`. It never names a pending number (DL-0234)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _latest_edition(document: Document) -> Edition | None:
    editions = list(Edition.objects.filter(version__document=document))
    return max(editions, key=lambda e: review.number_key(e.number), default=None)


def _since_edition(document: Document) -> list[Acceptance]:
    """The acceptances after the latest edition — all of them before the first."""
    previous = _latest_edition(document)
    acceptances = Acceptance.objects.filter(version__document=document)
    if previous is None:
        return list(acceptances)
    floor = review.number_key(previous.number)
    return [a for a in acceptances if review.number_key(a.number) > floor]


def canonical_refusal(document: Document, user: User, *, once_frozen: bool = False) -> str | None:
    """Why `user` may not make `document` canonical now, or `None`, in the act's order: the
    right; a freeze; an acceptance since the previous edition; no content version since the
    latest acceptance (DL-0267); with the tenant's check on, an approver who accepted none of the
    runs since the previous edition (DL-0115). `once_frozen` asks what would refuse it once
    frozen, so a command freezes nothing it could not then make canonical."""
    if document.state != DocumentState.ACTIVE or Right.MAKE_CANONICAL not in rights_on(
        user, document
    ):
        return "not_permitted"
    if not once_frozen and open_freeze(document) is None:
        return "not_frozen"
    # Ending the freeze beneath a holder changes their rules mid-session: it waits (DL-0419).
    if holds.open_hold(document) is not None:
        return "held"
    since = _since_edition(document)
    if not since:
        return "nothing_accepted"
    if review.run(document):
        return "unaccepted_changes"
    tenant = Tenant.objects.get(number=holds.tenant_number())
    if tenant.require_distinct_approver and any(a.reviewer_id == user.pk for a in since):
        return "distinct_approver"
    return None


def next_edition(entries: list[bundle.PassportEntry]) -> str:
    """The number the next edition carries: the approvals the passport records, plus one."""
    return f"{sum(1 for e in entries if e.kind == 'approval') + 1}.0"


@dataclass(frozen=True)
class ApprovalDerivation:
    """What an approval's passport commit implies: its section, the accepted content version it
    made canonical, the approver, and the freeze it ends."""

    entry: bundle.PassportEntry
    version: Version
    approver: User
    # `None` when no freeze row stands behind it — a restore that lost it — and one is derived.
    freeze: Freeze | None


def derivable_approval(
    document: Document, repo: pygit2.Repository, sha: str
) -> ApprovalDerivation | str:
    """The rows commit `sha` implies when it is an approval exactly as `make_canonical` writes one,
    or why not: it changes the passport alone, appending one approval section by its author,
    timed as the commit, numbered as the next edition in its heading and its `edition` field
    alike, making canonical the content version the latest acceptance since the previous approval
    accepted, with no content version after it (DL-0267); no tag of its number names another
    commit; and a freeze of the document taken before it that no edition and no *unfreeze*
    ended — or, when the rows hold none, the freeze it proves is derived with it (DL-0355)."""
    commit = gitstore.commit_at(repo, sha)
    if gitstore.kind_of(commit.message) is not gitstore.Kind.APPROVAL or not commit.parents:
        return "not an approval"
    parent = commit.parents[0]
    approver = review.committer(commit, holds.tenant_number())
    if approver is None:
        return "its author is not of this tenant"
    try:
        entries = review.passport_at(repo, sha)
        before = review.passport_at(repo, str(parent.id))
    except (KeyError, ValueError, UnicodeDecodeError):
        return "its passport does not read"
    if len(entries) != len(before) + 1 or entries[: len(before)] != before:
        return "it does not append one section"
    if [d.new_file.path for d in repo.diff(parent, commit).deltas] != [review.PASSPORT]:
        return "it changes more than the passport"
    entry = entries[-1]
    if entry.kind != "approval" or entry.by != str(approver.pk):
        return "its section is not its author's approval"
    number = next_edition(before)
    if entry.number != number or entry.edition != number:
        return "its section is not numbered as the next edition"
    if int(entry.at.timestamp()) != commit.author.time:
        return "its section is not timed as the commit"
    last_approval = max((n for n, e in enumerate(before) if e.kind == "approval"), default=-1)
    accepted = [e for e in before[last_approval + 1 :] if e.kind == "acceptance"]
    if not accepted or accepted[-1].version != entry.version:
        return "it does not make canonical the version accepted last"
    try:
        since = review.commits_after(repo, entry.version, str(parent.id))
    except LookupError:
        return "it does not follow the version it makes canonical"
    if any(gitstore.kind_of(gitstore.commit_at(repo, s).message) in CONTENT_KINDS for s in since):
        return "a version waits for review before it"
    found = tagged(repo, number)
    if found is not None and found != sha:
        return f"a tag {number} names another commit"
    version = Version.objects.filter(document=document, commit_sha=entry.version).first()
    if version is None:
        return "the version it makes canonical has no row"
    made = Edition.objects.filter(
        version__document=document, approval_version__commit_sha=sha
    ).select_related("freeze")
    if made.exists():
        freeze: Freeze | None = made.get().freeze
    else:
        freeze = (
            Freeze.objects.filter(document=document, frozen_at__lte=entry.at, edition__isnull=True)
            .exclude(ended_by_kind=FreezeEnd.UNFROZEN)
            .order_by("-frozen_at")
            .first()
        )
    return ApprovalDerivation(entry, version, approver, freeze)


TAGS = "refs/tags/"
CONTENT_KINDS = (gitstore.Kind.EDIT, gitstore.Kind.REVIEWER_EDIT)


def tagged(repo: pygit2.Repository, name: str) -> str | None:
    """The commit the tag `name` points at, or `None` when there is no such tag."""
    ref = repo.references.get(TAGS + name)
    if ref is None:
        return None
    return str(ref.peel(pygit2.Commit).id)


def tags(repo: pygit2.Repository) -> dict[str, str]:
    """Every tag of the repository and the commit it points at."""
    return {
        ref.removeprefix(TAGS): str(repo.references[ref].peel(pygit2.Commit).id)
        for ref in repo.references
        if ref.startswith(TAGS)
    }


def tags_its_approval(repo: pygit2.Repository, name: str, sha: str) -> bool:
    """Whether commit `sha` is an approval whose own section is approval `name`: the only
    commit a tag of an edition may name (DL-0260)."""
    commit = gitstore.commit_at(repo, sha)
    if gitstore.kind_of(commit.message) is not gitstore.Kind.APPROVAL:
        return False
    try:
        entries = review.passport_at(repo, sha)
    except (KeyError, ValueError, UnicodeDecodeError):
        return False
    return bool(entries) and entries[-1].kind == "approval" and entries[-1].number == name


def derive_approval(document: Document, sha: str, derivation: ApprovalDerivation) -> Edition:
    """Whatever of an approval the repository and the rows lack, from its passport section: the
    tag, then the approval's version row, the `EDITION` and the freeze's end in one transaction,
    audited with the approver as the actor — each step skipped where it is already done, so a
    repeat changes nothing."""
    entry = derivation.entry
    assert entry.number is not None
    repo = gitstore.open_repository(holds.tenant_number(), document.number)
    if tagged(repo, entry.number) is None:
        _tag(repo, sha, derivation)
    return _edition_rows(document, sha, derivation)


def _tag(repo: pygit2.Repository, sha: str, derivation: ApprovalDerivation) -> None:
    """The edition's annotated tag, by the approver's identity at the approval's time (DL-0260),
    the same whoever writes it."""
    entry = derivation.entry
    assert entry.number is not None
    gitstore.tag(
        repo,
        entry.number,
        sha,
        identity_for(derivation.approver, at=entry.at),
        f"Edition {entry.number}",
    )


def _edition_rows(
    document: Document, sha: str, derivation: ApprovalDerivation, *, via: str = ""
) -> Edition:
    """The approval's version row, its `EDITION` and the freeze's end, in one transaction: an
    edition is never recorded with its freeze still open."""
    entry, approver = derivation.entry, derivation.approver
    assert entry.number is not None
    repo = gitstore.open_repository(holds.tenant_number(), document.number)
    with transaction.atomic():
        freeze = derivation.freeze
        if freeze is None:
            freeze = _derived_freeze(document, derivation)
        approval = Version.objects.filter(document=document, commit_sha=sha).first()
        if approval is None:
            approval = documents.derive_version(document, gitstore.commit_at(repo, sha), approver)
        edition = Edition.objects.filter(approval_version=approval).first()
        if edition is None:
            edition = Edition.objects.create(
                version=derivation.version,
                approval_version=approval,
                freeze=freeze,
                number=entry.number,
                approved_by=approver,
                approved_at=entry.at,
            )
            record(
                actor=approver,
                action="document.made_canonical",
                obj=document,
                before=None,
                after={
                    "number": document.number,
                    "edition": entry.number,
                    "commit": sha,
                    **_via(via),
                },
                tenant=Tenant.objects.get(number=holds.tenant_number()),
            )
            _tell_readers(
                document,
                Event.MADE_CANONICAL,
                approver,
                version=approval,
                facts={"edition": entry.number},
                at=entry.at,
            )
        Freeze.objects.filter(pk=edition.freeze_id, ended_at__isnull=True).update(
            ended_by_kind=FreezeEnd.MADE_CANONICAL, ended_by=approver, ended_at=entry.at
        )
    return edition


def _derived_freeze(document: Document, derivation: ApprovalDerivation) -> Freeze:
    """The freeze an approval proves, where the rows lost it (DL-0355): frozen and ended at the
    approval's time by the approver, made canonical, no reason — audited as the platform's."""
    entry = derivation.entry
    freeze = Freeze.objects.create(
        document=document,
        reason="",
        frozen_by=derivation.approver,
        frozen_at=entry.at,
        ended_by_kind=FreezeEnd.MADE_CANONICAL,
        ended_by=derivation.approver,
        ended_at=entry.at,
    )
    record(
        actor=None,
        action="document.freeze_derived",
        obj=document,
        before=None,
        after={"number": document.number, "freeze": str(freeze.pk), "edition": entry.number},
        tenant=Tenant.objects.get(number=holds.tenant_number()),
    )
    return freeze


def next_edition_tagged(document: Document) -> bool:
    """Whether a tag already bears the number the next edition would take."""
    repo = gitstore.open_repository(holds.tenant_number(), document.number)
    head = gitstore.head(repo)
    number = next_edition(review.passport_at(repo, head) if head else [])
    return tagged(repo, number) is not None


def edition_number_agrees(document: Document) -> bool:
    """Whether the next edition's number reads the same from the rows and from the passport, and
    no tag bears it yet — what a confirmation may name without the lock."""
    repo = gitstore.open_repository(holds.tenant_number(), document.number)
    head = gitstore.head(repo)
    from_passport = next_edition(review.passport_at(repo, head) if head else [])
    latest = _latest_edition(document)
    from_rows = f"{int(latest.number.split('.')[0]) + 1}.0" if latest is not None else "1.0"
    return from_passport == from_rows and tagged(repo, from_passport) is None


def canonical_target(document: Document) -> tuple[Version, str] | None:
    """The accepted content version *make canonical* would turn into the next edition, and the
    number of the acceptance that accepted it; `None` when nothing is accepted since the latest
    edition. A reader of accepted text may see both (DL-0234)."""
    since = _since_edition(document)
    if not since:
        return None
    latest = max(since, key=lambda a: review.number_key(a.number))
    return review.accepted_content_version(latest), latest.number


def make_canonical(
    document: Document,
    approver: User,
    *,
    confirmed: str | None = None,
    via: str = "",
    fault_at: int | None = None,
) -> Edition:
    """Make the document's latest accepted version its next edition, as `approver`, under the
    document's lock; `CanonicalRefused` with the reason when it may not be. `confirmed` is the
    accepted version the confirmation named: another accepted since is refused as
    `accepted_changed`, so an edition is only ever the text its approver was shown."""
    with document_lock(holds.tenant_number(), document.number, timeout=LOCK_WAIT_SECONDS):
        return make_canonical_locked(
            document, approver, confirmed=confirmed, via=via, fault_at=fault_at
        )


def make_canonical_locked(
    document: Document,
    approver: User,
    *,
    confirmed: str | None = None,
    via: str = "",
    fault_at: int | None = None,
) -> Edition:
    """`make_canonical`'s body, for a caller that already holds the document's writer lock.
    `fault_at` stops the act after a step for the crash tests: 1 the passport commit, 2 the
    tag, 3 the rows and the freeze's end."""
    tenant_number = holds.tenant_number()
    review.settle_head(document)
    repo = gitstore.open_repository(tenant_number, document.number)
    with transaction.atomic():
        locked = Document.objects.select_for_update().get(pk=document.pk)
        refused = canonical_refusal(locked, approver)
        if refused is not None:
            raise CanonicalRefused(refused)
        target = canonical_target(locked)
        assert target is not None
        accepted = target[0]
        if confirmed is not None and accepted.commit_sha != confirmed:
            raise CanonicalRefused("accepted_changed")
        freeze = open_freeze(locked)
        assert freeze is not None
        head = gitstore.head(repo)
        assert head is not None
        number = next_edition(review.passport_at(repo, head))
        if tagged(repo, number) is not None:
            # A tag of the number the edition would take: written by no act of the platform, and
            # a person decides what it was; nothing is committed under it.
            raise review.RecordIncomplete(f"a tag {number} exists already")
        now = timezone.now().replace(microsecond=0)
        entry = bundle.PassportEntry(
            kind="approval",
            number=number,
            at=now,
            by=str(approver.pk),
            version=accepted.commit_sha,
            edition=number,
        )
        passport = gitstore.read(repo, review.PASSPORT, head).decode("utf-8")
        # (1) The commit point: the passport's section.
        sha = gitstore.commit(
            repo,
            {review.PASSPORT: bundle.append_passport(passport, entry).encode("utf-8")},
            identity_for(approver, at=now),
            f"Made canonical as {number}",
            gitstore.Kind.APPROVAL,
        )
    _fault(1, fault_at)
    derivation = ApprovalDerivation(entry, accepted, approver, freeze)
    # (2) The tag.
    _tag(repo, sha, derivation)
    _fault(2, fault_at)
    # (3) The version and `EDITION` rows, audited, and the freeze ended.
    edition = _edition_rows(document, sha, derivation, via=via)
    _fault(3, fault_at)
    # The edition's rows kept beside the new head's (DL-0266), as an acceptance asks.
    for kept in (accepted.commit_sha, sha):
        _ask_authorship(tenant_number, document, kept)
    return edition


def _fault(step: int, fault_at: int | None) -> None:
    if fault_at == step:
        raise review.InjectedFault(step)


def _ask_authorship(tenant_number: int, document: Document, sha: str) -> None:
    """The worker asked for a version's authorship rows; the edition stands whatever the broker
    says, and the reconciler asks again for a kept version without them."""
    from editing import tasks

    try:
        tasks.queue_authorship(tenant_number, document.number, sha)
    except Exception:  # noqa: BLE001 — any failure to publish is the reconciler's to repair
        logger.warning("authorship not queued", extra={"document": document.number})


def end_freeze(document: Document, reason: str = "", *, user: User | None = None) -> Freeze:
    """End the document's open freeze, `unfrozen` (DL-0189): by `user`, a holder of *freeze* —
    *unfreeze* — or, with no user, by the operator's command, for a freeze nobody can end
    otherwise. Ordinary editing resumes at the accepted number. A person's reason is optional, an
    operator's required, one line either way. A stopped approval at the head is finished first, so
    the freeze it ends is never recorded as unfrozen. `FreezeRefused`: `not_permitted` for a person
    without *freeze*, read under the locks; `held_unfreeze` while someone holds the document;
    `made_canonical` when a stopped approval, settled first, ended the freeze; `reason_invalid`.
    `NotFrozen`, a `ValueError`, when the document is not frozen; `ValueError` when an
    operator's reason is empty or invalid."""
    reason = reason.strip()
    if user is None and not reason:
        raise ValueError("an operator ends a freeze with a reason of one line")
    if not valid_reason(reason):
        if user is None:
            raise ValueError("an operator ends a freeze with a reason of one line")
        raise FreezeRefused("reason_invalid")
    number = holds.tenant_number()
    with document_lock(number, document.number, timeout=LOCK_WAIT_SECONDS):
        was_frozen = open_freeze(document) is not None
        review.settle_head(document)
        with transaction.atomic():
            locked = Document.objects.select_for_update().get(pk=document.pk)
            # Epic 10: an archived document is read, never acted on (DL-0450) — decided on the
            # locked row, so an archive that landed after the caller read the document refuses.
            if locked.state == DocumentState.ARCHIVED:
                if user is None:
                    raise ValueError(f"document {locked.number} is archived; restore it first")
                raise FreezeRefused("not_active")
            if user is not None and Right.FREEZE not in rights_on(user, locked):
                raise FreezeRefused("not_permitted")
            frozen = open_freeze(locked)
            if frozen is None:
                # An approval that had stopped after its commit, settled just now, ended it.
                if was_frozen and user is not None:
                    raise FreezeRefused("made_canonical")
                raise NotFrozen(f"document {locked.number} is not frozen")
            # As freezing does, unfreezing waits for whoever holds the document (DL-0223).
            if user is not None and holds.open_hold(locked) is not None:
                raise FreezeRefused("held_unfreeze")
            frozen.ended_by_kind = FreezeEnd.UNFROZEN
            frozen.ended_at = timezone.now()
            frozen.ended_by = user
            frozen.save(update_fields=["ended_by_kind", "ended_at", "ended_by"])
            record(
                actor=user,
                action="document.unfrozen",
                obj=locked,
                before=None,
                after={"number": locked.number, "freeze": str(frozen.pk), "reason": reason},
                tenant=Tenant.objects.get(number=number),
            )
            _tell_readers(locked, Event.UNFROZEN, user)
    return frozen
