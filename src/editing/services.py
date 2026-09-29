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
from editing.normalizer import RULESET, Lists, normalize, trailer
from tenancy.models import Tenant

if TYPE_CHECKING:
    import pygit2

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


def _stopped(repo: pygit2.Repository, head: str, draft: Draft, user: User) -> str | None:
    """The head's sha when it is the holder's own `edit` committed from this draft by a finish
    that stopped before it released the hold; else `None`."""
    if head == draft.base_commit:
        return None
    commit = gitstore.commit_at(repo, head)
    if gitstore.kind_of(commit.message) is not gitstore.Kind.EDIT:
        return None
    return head if commit.author.name == str(user.pk) else None


def my_edits(hold: Hold) -> tuple[str, str]:
    """The draft normalised against the head, and its changes rendered; `DraftRefused` for a
    draft the whitelist refuses."""
    document = Document.objects.select_related("language").get(pk=hold.document_id)
    _, head_body = _head_body(holds.tenant_number(), document)
    draft = Draft.objects.get(hold=hold)
    _accepted(draft)
    normalised = normalize(head_body.encode(), draft.content[holds.BODY], _lists(document))
    changes = render_changes(head_body.encode(), normalised)
    return head_body, changes


def finish(hold: Hold) -> Finishing:
    """The finishing screen for `hold`; `EditorsOpen` while an editor is open on its draft (the
    browser closes its own before it asks); `DraftRefused` for a draft the whitelist refuses."""
    if OpenEditor.objects.filter(draft__hold=hold, closed_at__isnull=True).exists():
        raise EditorsOpen(hold.pk)
    document = Document.objects.select_related("language").get(pk=hold.document_id)
    _, head_body = _head_body(holds.tenant_number(), document)
    draft = Draft.objects.get(hold=hold)
    _accepted(draft)
    normalised = normalize(head_body.encode(), draft.content[holds.BODY], _lists(document))
    return Finishing(
        changes=render_changes(head_body.encode(), normalised),
        summary=summary.drafted(head_body, normalised.decode("utf-8")),
        number=numbering.pending(document),
    )


def _fault(step: int, fault_at: int | None) -> None:
    if fault_at == step:
        raise InjectedFault(step)


def _derive(document: Document, repo: pygit2.Repository, sha: str, user: User) -> None:
    """The version row of `sha` and its caches, audited as committed."""
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


def commit_draft(hold: Hold, user: User, message: str, *, fault_at: int | None = None) -> Version:
    """Commit the draft of `hold` as one version of kind `edit`, under the document's lock. A
    finish that stopped after its commit is resumed first: its row derived, then whatever the
    holder typed since committed as the next version, or nothing when they typed nothing."""
    problem = summary.problem(message)
    if problem is not None:
        raise InvalidSummary(problem)
    tenant_number = holds.tenant_number()
    document = Document.objects.select_related("language").get(pk=hold.document_id)
    with document_lock(tenant_number, document.number, timeout=holds.LOCK_WAIT_SECONDS):
        repo = gitstore.open_repository(tenant_number, document.number)
        with transaction.atomic():
            locked_document = Document.objects.select_for_update().get(pk=document.pk)
            # The right and the state are decided here, under the locks, as taking the hold does.
            if locked_document.state != DocumentState.ACTIVE or Right.EDIT not in rights_on(
                user, locked_document
            ):
                raise holds.NotEditable(document.number)
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
            normalised = normalize(head_body.encode(), body, lists).decode("utf-8")
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
            sha = head
        else:
            # (1) The commit point.
            sha = gitstore.commit(
                repo,
                {holds.BODY: text.encode("utf-8")},
                identity_for(user),
                message.strip(),
                gitstore.Kind.EDIT,
                trailers={"Normalizer": trailer(RULESET, lists).removeprefix("Normalizer: ")},
            )
            _fault(1, fault_at)
            # (2) The version row and its caches, audited.
            _derive(document, repo, sha, user)
        _fault(2, fault_at)
        # (3) The hold released as finished.
        with transaction.atomic():
            Document.objects.select_for_update().get(pk=document.pk)
            holds.release(hold, ReleaseKind.FINISHED, actor=user)
        _fault(3, fault_at)
        # (4) The draft consumed.
        Draft.objects.filter(hold=hold).delete()
        _fault(4, fault_at)
    # (5) The authorship, asked of the worker once the rows are committed. The version stands
    # whatever the broker says: the reconciler asks again for a head without its rows.
    try:
        tasks.queue_authorship(tenant_number, document.number, sha)
    except Exception:  # noqa: BLE001 — any failure to publish is the reconciler's to repair
        logger.warning("authorship not queued", extra={"document": document.number})
    return Version.objects.get(document=document, commit_sha=sha)
