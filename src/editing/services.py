"""Finishing an editing session: the screen's content, and the commit that turns a draft into a
version (ADR-0003, DL-0222, DL-0261).

The commit is a write across both stores, under the document's writer lock throughout, in this
order: the git commit, which is the commit point; the version row and its caches, audited; the hold
released as finished; the draft deleted; the authorship asked of the worker. A stop after any step
leaves a state that is finished either way (DL-0318): by the holder's next *send for review*, which
resumes it, or by the reconciler, which derives the row, releases the hold whose draft is behind
an `edit` commit of its holder and holds nothing more, deletes a finished hold's draft, and asks
again for the head's authorship when it has none.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pygit2
from django.db import transaction

from access.rights import Right, rights_on
from audit.record import record
from documents import gitstore, services
from documents.identity import identity_for
from documents.locks import document_lock
from documents.models import Document, DocumentState, Version
from editing import holds, numbering, summary, tasks
from editing.diffview import render_changes
from editing.markdown.validator import Refusal, validate
from editing.models import Draft, Hold, OpenEditor, ReleaseKind
from editing.normalizer import RULESET, Lists, TooLarge, normalize, trailer
from tenancy.models import Tenant

if TYPE_CHECKING:
    from identity.models import User

logger = logging.getLogger(__name__)


class EditorsOpen(Exception):
    """An editor is still open on the draft; finishing waits for every one to close."""


class NothingChanged(Exception):
    """The draft, normalised, is the head's text: there is no version to make."""


class InvalidSummary(ValueError):
    """The summary as the holder left it cannot be a commit's first line."""


class DraftRefused(Exception):
    """The draft holds text the whitelist refuses — typed in the source view — and is corrected
    there before it is shown as changes or committed."""

    def __init__(self, refusals: list[Refusal]) -> None:
        super().__init__(refusals)
        self.refusals = refusals


class InjectedFault(Exception):
    """Raised by `commit_draft` after the step a crash test names; never set in production."""


@dataclass(frozen=True)
class Finishing:
    """What the finishing screen shows: the changes, the drafted summary, the number to come."""

    changes: str
    summary: str
    number: str


def _lists(document: Document) -> Lists:
    return Lists.of(document.language)


def _head_body(tenant_number: int, document: Document) -> tuple[str, str]:
    """The head's sha and body."""
    repo = gitstore.open_repository(tenant_number, document.number)
    head = gitstore.head(repo)
    if head is None:
        raise RuntimeError(f"document {document.number} has no commit")
    _, body = holds.split(gitstore.read(repo, holds.BODY, head).decode("utf-8"))
    return head, body


def _accepted(draft: Draft) -> str:
    """The draft's body; `DraftRefused` when the whitelist refuses it."""
    body: str = draft.content[holds.BODY]
    refusals = validate(body)
    if refusals:
        raise DraftRefused(refusals)
    return body


def _normalised(head_body: str, body: str, lists: Lists) -> bytes:
    """`body` normalised against the head; `DraftRefused` as too large when its stored form would
    pass the size the platform accepts (DL-0329)."""
    try:
        return normalize(head_body.encode(), body, lists)
    except TooLarge as error:
        raise DraftRefused([Refusal(1, "too-large")]) from error


CONTENT_KINDS = (gitstore.Kind.EDIT, gitstore.Kind.REVIEWER_EDIT)


def _stopped(repo: pygit2.Repository, head: str, draft: Draft, user: User) -> str | None:
    """The sha of the holder's own content version — either kind (DL-0335) — committed from this
    draft by a finish that stopped before it released the hold, with nothing but acceptances
    after it; else `None`. A head that does not descend from the draft's base — moved by a
    restore — never has one, as the reconciler reads it."""
    if head == draft.base_commit:
        return None
    try:
        if not repo.descendant_of(head, draft.base_commit):
            return None
    except (KeyError, ValueError, pygit2.GitError):
        return None
    walker = repo.walk(head, pygit2.enums.SortMode.TOPOLOGICAL)
    walker.hide(draft.base_commit)
    for commit in walker:
        kind = gitstore.kind_of(commit.message)
        if kind is gitstore.Kind.ACCEPTANCE:
            continue
        if kind in CONTENT_KINDS and commit.author.name == str(user.pk):
            return str(commit.id)
        return None
    return None


def draft_text(hold: Hold) -> tuple[str, str, str]:
    """The head's sha and body, and the draft normalised against it — the text *my edits* shows
    and exports; `DraftRefused` for a draft the whitelist refuses."""
    document = Document.objects.select_related("language").get(pk=hold.document_id)
    head, head_body = _head_body(holds.tenant_number(), document)
    draft = Draft.objects.get(hold=hold)
    _accepted(draft)
    normalised = _normalised(head_body, draft.content[holds.BODY], _lists(document))
    return head, head_body, normalised.decode("utf-8")


def my_edits(hold: Hold) -> tuple[str, str]:
    """The draft normalised against the head, and its changes rendered; `DraftRefused` for a
    draft the whitelist refuses."""
    _, head_body, normalised = draft_text(hold)
    changes = render_changes(head_body.encode(), normalised.encode())
    return head_body, changes


def finish(hold: Hold) -> Finishing:
    """The finishing screen for `hold`; `EditorsOpen` while an editor is open on its draft (the
    browser closes its own before it asks); `DraftRefused` for a draft the whitelist refuses."""
    if OpenEditor.objects.filter(draft__hold=hold, closed_at__isnull=True).exists():
        raise EditorsOpen(hold.pk)
    document = Document.objects.select_related("language").get(pk=hold.document_id)
    tenant_number = holds.tenant_number()
    head, head_body = _head_body(tenant_number, document)
    draft = Draft.objects.get(hold=hold)
    _accepted(draft)
    normalised = _normalised(head_body, draft.content[holds.BODY], _lists(document))
    return Finishing(
        changes=render_changes(head_body.encode(), normalised),
        summary=summary.drafted(head_body, normalised.decode("utf-8")),
        number=_number(
            document, tenant_number, head, draft, normalised.decode("utf-8") == head_body
        ),
    )


def _number(document: Document, tenant_number: int, head: str, draft: Draft, same: bool) -> str:
    """The number *send for review* will give: after a finish that stopped past its commit, the
    stopped version's own when nothing was typed since, else the one after it — counted whether
    or not its row has been derived yet."""
    repo = gitstore.open_repository(tenant_number, document.number)
    stopped = _stopped(repo, head, draft, draft.hold.user)
    if stopped is None:
        return numbering.pending(document)
    derived = Version.objects.filter(document=document, commit_sha=stopped).exists()
    if same:
        return numbering.latest(document) if derived else numbering.pending(document)
    return numbering.pending(document) if derived else numbering.pending(document, ahead=1)


def _fault(step: int, fault_at: int | None) -> None:
    if fault_at == step:
        raise InjectedFault(step)


def _derive(document: Document, repo: pygit2.Repository, sha: str, user: User) -> None:
    derive_committed(document, repo, sha, user)


def derive_committed(document: Document, repo: pygit2.Repository, sha: str, user: User) -> None:
    """The version row of `sha` and its caches, audited as committed: the editor's commit and the
    loader's share it, so both leave the same record."""
    with transaction.atomic():
        services.derive_version(document, gitstore.commit_at(repo, sha), user)
        record(
            actor=user,
            action="document.version_committed",
            obj=document,
            before=None,
            after={"number": document.number, "version": numbering.latest(document)},
            tenant=Tenant.objects.get(number=holds.tenant_number()),
        )


def tell_reviewers(document: Document, sha: str, user: User) -> None:
    """The holders of *accept* told that the version `sha` awaits them, by its number in the run —
    nobody, once an acceptance has taken it in."""
    from access.rights import holders_of
    from notifications.models import Category, Event
    from notifications.services import notify, others
    from review.services import run

    pending = run(document)
    position = next((n for n, v in enumerate(pending, 1) if v.commit_sha == sha), None)
    if position is None:
        return
    reviewers = holders_of([Right.ACCEPT], [document.pk])[document.pk]
    notify(
        users=others(reviewers, user),
        category=Category.DOCUMENT,
        event=Event.VERSION_COMMITTED,
        actor=user,
        document=document,
        version=pending[position - 1],
        facts={"version": f"{numbering.accepted(document)}-{position}"},
    )


def commit_draft(hold: Hold, user: User, message: str, *, fault_at: int | None = None) -> Version:
    """Commit the draft of `hold` as one version, under the document's lock: of kind
    `reviewer_edit` when the holder holds *accept* at that moment, `edit` otherwise (ADR-0014). A
    finish that stopped after its commit is resumed first: its row derived, then whatever the
    holder typed since committed as the next version, or nothing when they typed nothing."""
    problem = summary.problem(message)
    if problem is not None:
        raise InvalidSummary(problem)
    tenant_number = holds.tenant_number()
    document = Document.objects.select_related("language").get(pk=hold.document_id)
    with document_lock(tenant_number, document.number, timeout=holds.LOCK_WAIT_SECONDS):
        version = commit_draft_locked(hold, user, message, fault_at=fault_at)
    ask_authorship(tenant_number, document, version.commit_sha)
    return version


def ask_authorship(tenant_number: int, document: Document, sha: str) -> None:
    """The authorship asked of the worker once the rows are committed. The version stands
    whatever the broker says: the reconciler asks again for a head without its rows."""
    try:
        tasks.queue_authorship(tenant_number, document.number, sha)
    except Exception:  # noqa: BLE001 — any failure to publish is the reconciler's to repair
        logger.warning("authorship not queued", extra={"document": document.number})


def commit_draft_locked(
    hold: Hold, user: User, message: str, *, fault_at: int | None = None, tell: bool = True
) -> Version:
    """`commit_draft`'s body, for a caller that holds the document's writer lock; the caller asks
    for the authorship afterwards (`ask_authorship`). `tell` false leaves the reviewers untold,
    for a caller that accepts the version in the same act."""
    problem = summary.problem(message)
    if problem is not None:
        raise InvalidSummary(problem)
    from editions.models import open_freeze
    from review.services import settle_head

    tenant_number = holds.tenant_number()
    document = Document.objects.select_related("language").get(pk=hold.document_id)
    # An acceptance a stop left at the head is settled before anything is written on it.
    settle_head(document)
    repo = gitstore.open_repository(tenant_number, document.number)
    with transaction.atomic():
        locked_document = Document.objects.select_for_update().get(pk=document.pk)
        # The right and the state are decided here, under the locks, as taking the hold does.
        rights = rights_on(user, locked_document)
        if locked_document.state != DocumentState.ACTIVE or Right.EDIT not in rights:
            raise holds.NotEditable(document.number)
        # While frozen only holders of *accept* commit (ADR-0016): a right lost since the hold
        # was taken is seen here, and the draft stays.
        frozen = open_freeze(locked_document)
        if frozen is not None and Right.ACCEPT not in rights:
            raise holds.Frozen(frozen.reason)
        kind = gitstore.Kind.REVIEWER_EDIT if Right.ACCEPT in rights else gitstore.Kind.EDIT
        locked = Hold.objects.select_for_update().get(pk=hold.pk)
        if locked.released_at is not None or locked.user_id != user.pk:
            raise holds.NotEditable(document.number)
        if OpenEditor.objects.filter(draft__hold=locked, closed_at__isnull=True).exists():
            raise EditorsOpen(locked.pk)
        draft = Draft.objects.get(hold=locked)
        body = _accepted(draft)
        head, head_body = _head_body(tenant_number, document)
        stopped = _stopped(repo, head, draft, user)
        lists = _lists(document)
        normalised = _normalised(head_body, body, lists).decode("utf-8")
        if normalised == head_body and stopped is None:
            raise NothingChanged(document.number)
        text = (
            None
            if normalised == head_body
            else holds.join(draft.content[holds.FRONTMATTER], normalised)
        )
    if (
        stopped is not None
        and not Version.objects.filter(document=document, commit_sha=stopped).exists()
    ):
        _derive(document, repo, stopped, user)
    if text is None:
        # Nothing typed since the stop: the version is the stopped commit, whatever an acceptance
        # has written above it since.
        assert stopped is not None
        sha = stopped
    else:
        # (1) The commit point.
        sha = gitstore.commit(
            repo,
            {holds.BODY: text.encode("utf-8")},
            identity_for(user),
            message.strip(),
            kind,
            trailers={"Normalizer": trailer(RULESET, lists).removeprefix("Normalizer: ")},
        )
        _fault(1, fault_at)
        # (2) The version row and its caches, audited.
        _derive(document, repo, sha, user)
    _fault(2, fault_at)
    # (3) The hold released as finished, and the reviewers told, in one transaction. A finish
    # stopped before this step tells them when it is completed — by its holder's next finish or
    # by the reconciler's repair — while the version still awaits review.
    with transaction.atomic():
        Document.objects.select_for_update().get(pk=document.pk)
        holds.release(hold, ReleaseKind.FINISHED, actor=user)
        if tell:
            if stopped is not None and stopped != sha:
                tell_reviewers(document, stopped, user)
            tell_reviewers(document, sha, user)
    _fault(3, fault_at)
    # (4) The draft consumed.
    Draft.objects.filter(hold=hold).delete()
    _fault(4, fault_at)
    # (5), by the caller once the lock is released: the authorship asked of the worker.
    return Version.objects.get(document=document, commit_sha=sha)
