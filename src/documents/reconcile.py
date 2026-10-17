"""The reconciler: the second path from git to the rows (DL-0111).

Git is the commit point and the rows are its cache. Report mode lists what disagrees and writes
nothing. Repair derives what git implies — an acceptance's or a return's rows from its passport
section, never from a trailer alone — computes the correction notices of an acceptance that has
none (ADR-0014), finishes stopped creations, finishes a *send for review* that stopped after its
commit (DL-0318, DL-0335), asks again for the authorship missing from the head or the latest
accepted version (DL-0266, DL-0326) and recreates a row for a repository without one, fail
closed; a row is deleted only on `prune_rows`, and only a version row whose commit its existing
repository no longer holds (ADR-0018, DL-0276). An export left queued is queued again. A
repository is trusted only where its passport names the tenant and the number it sits at. Every
repair runs under the document's lock and is audited with numbers, never a title. One
document's fault is reported and the run goes on.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import timedelta
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.utils import timezone

from audit.record import record
from documents import bundle, gitstore, services
from documents.identity import DOMAIN
from documents.locks import LockTimeout, document_lock
from documents.models import (
    DOCUMENT_NUMBER_SEQUENCE,
    ROOT_FOLDER,
    Document,
    DocumentState,
    DocumentTemplate,
    DocumentType,
    Folder,
    Version,
)
from identity.models import Language, Membership, User
from syngraphe.provenance import ActorKind
from tenancy.models import Tenant, visited_by_background_work
from tenancy.schemas import schema_context

if TYPE_CHECKING:
    import pygit2

logger = logging.getLogger(__name__)

# A creation younger than this may still be running, and is left to finish.
CREATING_GRACE = timedelta(minutes=10)
# An export queued longer than this lost its place in the queue — the render worker was down, or
# Redis lost the entry — and is queued again from its row.
EXPORT_GRACE = timedelta(minutes=10)
# An export still queued after this was killed with its worker, or queued behind a render that
# never ends; it is failed with the reason, and its person may ask again.
EXPORT_ABANDONED = timedelta(hours=1)
# A writer holding a document's lock longer than this is reported, never waited for.
LOCK_TIMEOUT_SECONDS = 30.0
NUMBER_MAX = 2**31 - 1
REPOSITORY = re.compile(r"^document-(?P<number>[1-9][0-9]{0,9})$")
PASSPORT_ENTRY = re.compile(r"^## (?P<entry>.*)$", re.MULTILINE)
PASSPORT_KIND = re.compile(r"^(?P<kind>acceptance|return|approval)(?: [0-9]+\.[0-9]+)?$")
PASSPORT_HEADER = re.compile(r"^---\ndocument: (?P<document>[0-9]+)\ntenant: (?P<tenant>[0-9]+)\n")
DEFAULT_TYPE = "document"
# Kinds a commit's trailer alone may turn into a row; a passport's kinds are never derived from a
# trailer.
REPLAYED = {gitstore.Kind.CREATED, gitstore.Kind.EDIT, gitstore.Kind.REVIEWER_EDIT}
CONTENT_KINDS = (gitstore.Kind.EDIT, gitstore.Kind.REVIEWER_EDIT)

# The kinds of finding.
CREATING_WITHOUT_REPOSITORY = "creating_without_repository"
CREATING_WITHOUT_COMMIT = "creating_without_commit"
CREATING_WITHOUT_VERSION = "creating_without_version"
CREATING_UNFINISHED = "creating_unfinished"
# A copy that stopped before it was made: its source is in the audit trail, so it is never
# finished from the template; reported, and removed by an operator (`remove_stopped_copy`,
# DL-0455).
COPY_STOPPED = "copy_stopped"
ORPHAN_REPOSITORY = "orphan_repository"
REPOSITORY_MISSING = "repository_missing"
COMMIT_WITHOUT_ROW = "commit_without_row"
ROW_WITHOUT_COMMIT = "row_without_commit"
FRONTMATTER_DIFFERS = "frontmatter_differs"
# A file under `appendices/` or `attachments/` the frontmatter does not list, and a listed part
# whose file is absent (ADR-0005): reported, never repaired — nothing tells which side is right.
ORPHAN_PART = "orphan_part"
PART_MISSING = "part_missing"
PASSPORT_ENTRY_WITHOUT_ROW = "passport_entry_without_row"
IDENTITY_MISMATCH = "identity_mismatch"
SEQUENCE_BEHIND = "sequence_behind"
LOCKED = "locked"
AUTHORSHIP_MISSING = "authorship_missing"
FINISH_STOPPED = "finish_stopped"
# A draft kept by a release — forced, inactivity, blocked — whose base lies below a content commit
# of its holder: the stopped finish the release met could not be completed. Reported, not repaired.
FINISH_STOPPED_KEPT = "finish_stopped_kept"
ACCEPT_AS_STOPPED = "accept_as_stopped"
ACCEPTANCE_DIFFERS = "acceptance_differs"
# A `RETURN` row that disagrees with its return's section: rewritten from the section on repair.
RETURN_DIFFERS = "return_differs"
NOTICES_MISSING = "notices_missing"
# A tag with no approval section of its number on the commit it names: reported, never repaired —
# the passport is believed (DL-0260).
TAG_WITHOUT_SECTION = "tag_without_section"
# An `EDITION` row that disagrees with its approval's section: reported.
EDITION_DIFFERS = "edition_differs"
# An approval's version whose `EDITION`, tag or freeze's end is missing: finished on repair.
EDITION_UNFINISHED = "edition_unfinished"
UNREADABLE = "unreadable"
EXPORT_STUCK = "export_stuck"
EXPORT_ABANDONED_KIND = "export_abandoned"


@dataclass(frozen=True)
class Finding:
    """One disagreement: `tenant` and `document` are numbers, `detail` a sha, a passport entry's
    kind or a reason, never a title."""

    kind: str
    tenant: int
    document: int
    detail: str = ""
    repaired: bool = False


def _derived_from(version: Version) -> dict[str, int]:
    """Delete the rows derived from `version` that would keep it from being pruned — its
    acceptances and returns, the correction notices naming it or theirs, their notifications, the
    export jobs that exported it or marked against it — and count them, for the audit."""
    from django.db.models import Q

    from notifications.models import Notification
    from rendering.models import ExportJob
    from review.models import Acceptance, CorrectionNotice, Return

    # A job records a download, never the text; its file, if still kept, goes with the sweep.
    exports, _ = ExportJob.objects.filter(Q(version=version) | Q(baseline_version=version)).delete()

    acceptances = Acceptance.objects.filter(Q(version=version) | Q(accepted_from=version))
    notices = CorrectionNotice.objects.filter(
        Q(acceptance__in=acceptances)
        | Q(lines__changing_version=version)
        | Q(lines__author_version=version)
    ).distinct()
    notifications, _ = Notification.objects.filter(
        Q(correction_notice__in=notices) | Q(version=version)
    ).delete()
    notice_count = notices.count()
    CorrectionNotice.objects.filter(pk__in=list(notices.values_list("pk", flat=True))).delete()
    acceptance_count, _ = acceptances.delete()
    returns, _ = Return.objects.filter(Q(version=version) | Q(returned_from=version)).delete()
    return {
        "acceptances": acceptance_count,
        "returns": returns,
        "correction_notices": notice_count,
        "notifications": notifications,
        "exports": exports,
    }


def _audit(tenant: Tenant, kind: str, document: Document | None, before: Any, after: Any) -> None:
    record(
        actor=None,
        action=f"reconcile.{kind}",
        obj=document,
        before=before,
        after=after,
        tenant=tenant,
    )


class _Run:
    """One pass over one tenant, the schema already set."""

    def __init__(self, tenant: Tenant, repair: bool, prune_rows: bool) -> None:
        self.tenant = tenant
        self.repair = repair
        self.prune_rows = prune_rows
        self.findings: list[Finding] = []
        self.directory = Path(settings.GIT_REPO_ROOT) / f"tenant-{tenant.number}"

    def found(self, kind: str, number: int, detail: str = "", repaired: bool = False) -> None:
        self.findings.append(Finding(kind, self.tenant.number, number, detail, repaired))

    # --- trust -------------------------------------------------------------------------------

    def path(self, number: int) -> Path | None:
        """The repository at `number`, if it is a real directory inside this tenant's own."""
        path = self.directory / f"document-{number}"
        own = Path(settings.GIT_REPO_ROOT).resolve() / f"tenant-{self.tenant.number}"
        if self.directory.is_symlink() or path.is_symlink() or not path.is_dir():
            return None
        if not path.resolve().is_relative_to(own):
            return None
        return path

    def trusted(self, number: int, commits: list[pygit2.Commit]) -> bool:
        """The repository's first commit names this tenant and this number in its passport."""
        if not commits:
            return True
        repo = gitstore.open_repository(self.tenant.number, number)
        try:
            passport = gitstore.read(repo, "passport.md", str(commits[0].id)).decode("utf-8")
        except (KeyError, UnicodeDecodeError):
            return False
        match = PASSPORT_HEADER.match(passport)
        return bool(
            match
            and int(match.group("tenant")) == self.tenant.number
            and int(match.group("document")) == number
        )

    def author(self, commit: pygit2.Commit) -> User | None:
        """The commit's author if it is a person of this tenant, named as the platform names them
        (DL-0093); `None` for anyone else."""
        name = commit.author.name
        if commit.author.email != f"{name}@{DOMAIN}":
            return None
        try:
            user = User.objects.filter(pk=name).first()
        except (ValueError, TypeError, ValidationError):
            return None
        if user is None or not Membership.objects.filter(user=user, tenant=self.tenant).exists():
            return None
        return user

    # --- a document with a row ------------------------------------------------------------

    def document(self, document: Document) -> None:
        if document.state == DocumentState.CREATING:
            self.creating(document)
            return
        if self.path(document.number) is None:
            # Nothing is pruned for a repository that is not there: it may be a mount, not a loss.
            self.found(REPOSITORY_MISSING, document.number)
            return
        repo = gitstore.open_repository(self.tenant.number, document.number)
        commits = list(gitstore.history(repo))
        if not self.trusted(document.number, commits):
            self.found(IDENTITY_MISMATCH, document.number)
            return
        missing = self.versions_without_commit(document, {str(c.id) for c in commits})
        self.commits_without_rows(document, commits, replay=not missing)
        if commits:
            self.frontmatter(document, repo, commits[-1])
            self.parts(document, repo, commits[-1])
            self.passport(document, repo, commits[-1])
            self.editions(document, repo, commits[-1])
            self.notices(document)
            self.finishes(document, commits)
            self.accepting(document)
            self.authorship(document, str(commits[-1].id))

    def creating(self, document: Document) -> None:
        if document.created_at > timezone.now() - CREATING_GRACE:
            return
        # A copy is never finished — in report and repair alike (DL-0455).
        if is_a_copy(document):
            self.found(COPY_STOPPED, document.number)
            return
        path = self.path(document.number)
        first = None
        if path is not None:
            repo = gitstore.open_repository(self.tenant.number, document.number)
            first = next(gitstore.history(repo), None)
        # A repository at this number that names another document is never taken over.
        if first is not None and not self.trusted(document.number, [first]):
            self.found(IDENTITY_MISMATCH, document.number)
            return
        if path is None:
            kind = CREATING_WITHOUT_REPOSITORY
        elif first is None:
            kind = CREATING_WITHOUT_COMMIT
        elif not Version.objects.filter(document=document, commit_sha=str(first.id)).exists():
            kind = CREATING_WITHOUT_VERSION
        else:
            kind = CREATING_UNFINISHED
        if not self.repair:
            self.found(kind, document.number)
            return
        # Any membership, as `author()` judges a commit: the creation's first commit may already
        # exist, and a blocked creator's finished document reaches nobody (DL-0308).
        creator = (
            Membership.objects.filter(user_id=document.created_by_id, tenant=self.tenant)
            .select_related("user")
            .first()
            if document.created_by_id is not None
            else None
        )
        if creator is None:
            self.found(kind, document.number, "its creator is not of this tenant")
            return
        template = DocumentTemplate.objects.get()
        try:
            moved = services.resume_creation(document, self.tenant, template, creator.user)
        except services.NotAdoptable:
            self.found(IDENTITY_MISMATCH, document.number)
            return
        if moved:
            _audit(self.tenant, kind, document, None, {"number": document.number})
        self.found(kind, document.number, repaired=moved)

    def commits_without_rows(
        self, document: Document, commits: list[pygit2.Commit], *, replay: bool
    ) -> None:
        known = set(Version.objects.filter(document=document).values_list("commit_sha", flat=True))
        # Only what follows the newest commit the rows know is replayed; a commit without a row
        # before it means the history changed under the rows, which is reported, never agreed to.
        # Replay stops at the first commit it cannot derive: one derived past it would leave a
        # hole no later run could fill.
        newest = max((n for n, c in enumerate(commits) if str(c.id) in known), default=-1)
        stopped = False
        for n, commit in enumerate(commits):
            sha = str(commit.id)
            if sha in known:
                continue
            author = self.author(commit)
            kind = gitstore.kind_of(commit.message)
            derivable = kind in REPLAYED or (
                kind in (gitstore.Kind.ACCEPTANCE, gitstore.Kind.RETURN, gitstore.Kind.APPROVAL)
                and author is not None
            )
            if (
                not self.repair
                or not replay
                or stopped
                or n < newest
                or author is None
                or not derivable
            ):
                reason = "" if author is not None else " (author not of this tenant)"
                self.found(COMMIT_WITHOUT_ROW, document.number, sha + reason)
                stopped = stopped or n > newest
                continue
            if kind is gitstore.Kind.APPROVAL:
                refused = self.approval(document, commit, author)
                if refused is not None:
                    self.found(COMMIT_WITHOUT_ROW, document.number, f"{sha} ({refused})")
                    stopped = True
                    continue
            elif kind is gitstore.Kind.RETURN:
                refused = self.return_(document, commit, author)
                if refused is not None:
                    self.found(COMMIT_WITHOUT_ROW, document.number, f"{sha} ({refused})")
                    stopped = True
                    continue
            elif kind is gitstore.Kind.ACCEPTANCE:
                if not self.acceptance(document, commit, author):
                    self.found(
                        COMMIT_WITHOUT_ROW,
                        document.number,
                        sha + " (its passport section does not read)",
                    )
                    stopped = True
                    continue
            else:
                with transaction.atomic():
                    services.derive_version(document, commit, author)
                    _audit(self.tenant, COMMIT_WITHOUT_ROW, document, None, {"commit": sha})
            self.found(COMMIT_WITHOUT_ROW, document.number, sha, repaired=True)

    def acceptance(self, document: Document, commit: pygit2.Commit, author: User) -> bool:
        """The rows of an acceptance's passport commit, derived by the rule `accept` itself is
        settled by (`review.services.derivable`); whether they were."""
        from review import services as review

        repo = gitstore.open_repository(self.tenant.number, document.number)
        sha = str(commit.id)
        found = review.derivable(document, repo, sha)
        if isinstance(found, str) or found.reviewer.pk != author.pk:
            return False
        with transaction.atomic():
            review.derive_acceptance(document, sha, found)
            _audit(self.tenant, COMMIT_WITHOUT_ROW, document, None, {"commit": sha})
        return True

    def return_(self, document: Document, commit: pygit2.Commit, author: User) -> str | None:
        """The rows of a return's passport commit, derived by the rule `return_run` itself is
        settled by (`review.services.derivable_return`); why not, or `None` when they were."""
        from review import services as review

        repo = gitstore.open_repository(self.tenant.number, document.number)
        sha = str(commit.id)
        found = review.derivable_return(document, repo, sha)
        if isinstance(found, str):
            return found
        if found.reviewer.pk != author.pk:
            return "its section is not its author's return"
        with transaction.atomic():
            review.derive_return(document, sha, found)
            _audit(self.tenant, COMMIT_WITHOUT_ROW, document, None, {"commit": sha})
        return None

    def approval(self, document: Document, commit: pygit2.Commit, author: User) -> str | None:
        """An approval's passport commit finished from its section — the tag, the rows, the
        freeze's end — by the rule `make_canonical` itself is settled by
        (`editions.services.derivable_approval`); why not, or `None` when it was."""
        from editions import services as editions

        repo = gitstore.open_repository(self.tenant.number, document.number)
        sha = str(commit.id)
        found = editions.derivable_approval(document, repo, sha)
        if isinstance(found, str):
            return found
        if found.approver.pk != author.pk:
            return "its section is not its author's approval"
        editions.derive_approval(document, sha, found)
        _audit(self.tenant, COMMIT_WITHOUT_ROW, document, None, {"commit": sha})
        return None

    def editions(self, document: Document, repo: pygit2.Repository, head: Any) -> None:
        """Every approval against its passport section, the passport believed: an approval
        commit's version without its `EDITION`, or an edition missing its tag or its freeze's
        end, finished on repair; a row that disagrees with its section, a section no `EDITION`
        records, and a tag that is not its approval's, reported."""
        from editions import services as editions
        from editions.models import Edition

        rows = {
            e.approval_version.commit_sha: e
            for e in Edition.objects.filter(version__document=document).select_related(
                "approval_version", "freeze"
            )
        }
        approvals = Version.objects.filter(document=document, kind="approval")
        # The sections an approval's version answers for, found or repaired here: each is
        # reported once, by what this loop says of it.
        answered: set[str] = {e.number for e in rows.values()}
        for sha in approvals.values_list("commit_sha", flat=True):
            found = editions.derivable_approval(document, repo, sha)
            if isinstance(found, str):
                self.found(EDITION_DIFFERS, document.number, f"{sha} ({found})")
                continue
            number = found.entry.number or ""
            answered.add(number)
            row = rows.get(sha)
            if row is not None and (
                row.number != number
                or row.version_id != found.version.pk
                or row.approved_by_id != found.approver.pk
                or row.approved_at != found.entry.at
            ):
                self.found(EDITION_DIFFERS, document.number, f"edition {number}")
                continue
            tagged = editions.tagged(repo, number)
            if row is not None and tagged is not None and row.freeze.ended_at is not None:
                continue
            if self.repair:
                editions.derive_approval(document, sha, found)
                _audit(self.tenant, EDITION_UNFINISHED, document, None, {"commit": sha})
            self.found(
                EDITION_UNFINISHED, document.number, f"edition {number}", repaired=self.repair
            )
        text = gitstore.read(repo, "passport.md", str(head.id)).decode("utf-8")
        try:
            sections = {e.number for e in bundle.passport_entries(text) if e.kind == "approval"}
        except ValueError:
            sections = set()  # a passport that does not read is the passport check's finding
        for number in sorted(n for n in sections - answered if n):
            self.found(PASSPORT_ENTRY_WITHOUT_ROW, document.number, f"approval {number}")
        for name, target in editions.tags(repo).items():
            if not editions.tags_its_approval(repo, name, target):
                self.found(TAG_WITHOUT_SECTION, document.number, name)

    def notices(self, document: Document) -> None:
        """An acceptance whose correction notices were never computed has them computed, so a stop
        after its rows never loses the disclosure ADR-0001 requires."""
        from review import notices
        from review.models import Acceptance

        for acceptance in Acceptance.objects.filter(
            version__document=document, notices_computed_at__isnull=True
        ).select_related("version__document"):
            if self.repair:
                try:
                    notices.compute(acceptance)
                except Exception as error:  # noqa: BLE001 — one acceptance's failure is reported
                    logger.exception(
                        "correction notices not computed",
                        extra={"tenant": self.tenant.number, "document": document.number},
                    )
                    self.found(
                        NOTICES_MISSING,
                        document.number,
                        f"{acceptance.number} ({type(error).__name__})",
                    )
                    continue
                _audit(
                    self.tenant,
                    NOTICES_MISSING,
                    document,
                    None,
                    {"number": document.number, "accepted": acceptance.number},
                )
            self.found(NOTICES_MISSING, document.number, acceptance.number, repaired=self.repair)

    def accepting(self, document: Document) -> None:
        """An *accept as* stopped between its version and its acceptance: the hold left
        *accepting*. Repaired by telling the reviewers the version awaits them — nobody, once an
        acceptance has taken it in — then finishing the hold and deleting what is left of its
        draft."""
        from editing import services as finishing
        from editing.models import Draft, Hold, ReleaseKind

        for hold in Hold.objects.filter(document=document, release_kind=ReleaseKind.ACCEPTING):
            version = (
                Version.objects.filter(
                    document=document,
                    author_id=hold.user_id,
                    kind__in=CONTENT_KINDS,
                    created_at__gte=hold.acquired_at,
                    created_at__lte=hold.released_at,
                )
                .order_by("-created_at")
                .first()
            )
            if self.repair:
                with transaction.atomic():
                    Document.objects.select_for_update().get(pk=document.pk)
                    if version is not None:
                        finishing.tell_reviewers(document, version.commit_sha, hold.user)
                    finishing.finish_accepting(hold)
                    Draft.objects.filter(hold=hold).delete()
                    _audit(
                        self.tenant, ACCEPT_AS_STOPPED, document, None, {"number": document.number}
                    )
            detail = version.commit_sha if version is not None else ""
            self.found(ACCEPT_AS_STOPPED, document.number, detail, repaired=self.repair)

    def finishes(self, document: Document, commits: list[pygit2.Commit]) -> None:
        """A finish that stopped after its commit (DL-0318, DL-0335). An open hold whose draft's
        base is behind a content commit of its holder, `edit` or `reviewer_edit`, is released as
        finished and its draft deleted —
        only when the holder is a member, the commit has its row, and the draft holds nothing
        the commit does not; otherwise it is reported, and the holder's next *send for review*
        resumes it. A finished hold whose draft is still there has the draft deleted."""
        from editing import holds as editing
        from editing import services as finishing
        from editing.models import Draft, Hold, ReleaseKind

        order = {str(commit.id): n for n, commit in enumerate(commits)}
        for hold in Hold.objects.filter(document=document, draft__isnull=False):
            draft = Draft.objects.get(hold=hold)
            edit, reason = "", ""
            if hold.released_at is not None:
                if hold.release_kind != ReleaseKind.FINISHED:
                    self.kept_over_a_stop(document, commits, order, hold, draft)
                    continue
            else:
                base = order.get(draft.base_commit)
                if base is None:
                    continue
                edits = [
                    commit
                    for commit in commits[base + 1 :]
                    if gitstore.kind_of(commit.message) in CONTENT_KINDS
                    and commit.author.name == str(hold.user_id)
                ]
                if not edits:
                    continue
                edit = str(edits[-1].id)
                reason = self.unfinishable(document, edits[-1], draft)
            if self.repair and not reason:
                with transaction.atomic():
                    Document.objects.select_for_update().get(pk=document.pk)
                    if hold.released_at is None:
                        editing.release(hold, ReleaseKind.FINISHED)
                        # The finish the holder could not complete tells the reviewers here.
                        finishing.tell_reviewers(document, edit, hold.user)
                    draft.delete()
                    _audit(self.tenant, FINISH_STOPPED, document, None, {"number": document.number})
            detail = f"{edit} ({reason})" if reason else edit
            self.found(FINISH_STOPPED, document.number, detail, repaired=self.repair and not reason)

    def kept_over_a_stop(
        self,
        document: Document,
        commits: list[pygit2.Commit],
        order: dict[str, int],
        hold: Any,
        draft: Any,
    ) -> None:
        """A kept draft over its holder's own content commit: a release met a stopped finish it
        could not complete — work written after the stop — and kept the draft (DL-0414). The version
        stands and its reviewers were told; the draft is the holder's, so it is named, not
        repaired."""
        base = order.get(draft.base_commit)
        if base is None:
            return
        edits = [
            commit
            for commit in commits[base + 1 :]
            if gitstore.kind_of(commit.message) in CONTENT_KINDS
            and commit.author.name == str(hold.user_id)
        ]
        if edits:
            self.found(FINISH_STOPPED_KEPT, document.number, str(edits[-1].id))

    def unfinishable(self, document: Document, commit: pygit2.Commit, draft: Any) -> str:
        """Why a stopped finish is left for its holder: an empty string when it may be finished."""
        from editing.markdown.validator import validate
        from editing.normalizer import Lists, NormalizerDefect, normalize

        if self.author(commit) is None:
            return "its holder is not of this tenant"
        if not Version.objects.filter(document=document, commit_sha=str(commit.id)).exists():
            return "its commit has no row"
        from editing.services import holds_later_work

        body = draft.content["document.md"]
        repo = gitstore.open_repository(self.tenant.number, document.number)
        _, committed = bundle.parse(
            gitstore.read(repo, "document.md", str(commit.id)).decode("utf-8")
        )
        if validate(body):
            return "the draft holds later work"
        lists = Lists.of(document.language)
        try:
            normalize(committed.encode(), body, lists)
        except NormalizerDefect:
            return "the draft does not normalise"
        # Text, entities, appendices or files written after the stop.
        if holds_later_work(draft, repo, str(commit.id), lists):
            return "the draft holds later work"
        return ""

    def authorship(self, document: Document, head: str) -> None:
        """The two kept versions — the head, of any kind, and the latest accepted — without rows
        while their text has a non-blank line: the worker is asked for them again (DL-0266,
        DL-0326). A version not derived yet waits for its row; a blank text has no rows by design
        and is never asked for."""
        from editing.authorship import latest_accepted
        from editing.models import LineAuthorship
        from editing.tasks import queue_authorship

        kept = [Version.objects.filter(document=document, commit_sha=head).first()]
        accepted = latest_accepted(document)
        if accepted is not None and accepted.commit_sha != head:
            kept.append(accepted)
        for version in kept:
            if version is None:
                continue
            if LineAuthorship.objects.filter(version=version, expires_at__isnull=True).exists():
                continue
            if not self.has_lines(document, version.commit_sha):
                continue
            if self.repair:
                queue_authorship(self.tenant.number, document.number, version.commit_sha)
            self.found(
                AUTHORSHIP_MISSING, document.number, version.commit_sha, repaired=self.repair
            )

    def has_lines(self, document: Document, head: str) -> bool:
        """Whether `document.md`'s body or an appendix it lists has a non-blank line at `head` —
        the lines the worker writes rows for."""
        repo = gitstore.open_repository(self.tenant.number, document.number)
        frontmatter, body = bundle.parse(gitstore.read(repo, "document.md", head).decode("utf-8"))
        texts = [body]
        for item in frontmatter.appendices:
            try:
                texts.append(
                    gitstore.read(repo, f"appendices/{int(item['number'])}.md", head).decode()
                )
            except KeyError:
                continue
        return any(line.strip() for text in texts for line in text.splitlines())

    def versions_without_commit(self, document: Document, present: set[str]) -> bool:
        """Report, or prune, the version rows whose commit is gone; `True` while any remain. A
        pruned version takes with it the rows derived from it — an acceptance it records or
        started from, a correction notice one of whose lines names it, and their notifications —
        since each is a cache of a commit that no longer exists."""
        missing = list(Version.objects.filter(document=document).exclude(commit_sha__in=present))
        for version in missing:
            sha = version.commit_sha
            if self.prune_rows:
                with transaction.atomic():
                    derived = _derived_from(version)
                    version.delete()
                    _audit(
                        self.tenant,
                        ROW_WITHOUT_COMMIT,
                        document,
                        {"commit": sha, **derived},
                        None,
                    )
                self.found(ROW_WITHOUT_COMMIT, document.number, sha, repaired=True)
            else:
                self.found(ROW_WITHOUT_COMMIT, document.number, sha)
        return bool(missing) and not self.prune_rows

    def frontmatter(self, document: Document, repo: pygit2.Repository, head: Any) -> None:
        text = gitstore.read(repo, "document.md", str(head.id)).decode("utf-8")
        frontmatter, _ = bundle.parse(text)
        changed = [
            name
            for name, before, after in (
                ("title", document.title, frontmatter.title),
                ("language", document.language_id, frontmatter.language),
            )
            if before != after
        ]
        if not changed:
            return
        if not self.repair or not Language.objects.filter(code=frontmatter.language).exists():
            self.found(FRONTMATTER_DIFFERS, document.number, ", ".join(changed))
            return
        with transaction.atomic():
            Document.objects.filter(pk=document.pk).update(
                title=frontmatter.title, language_id=frontmatter.language
            )
            _audit(
                self.tenant,
                FRONTMATTER_DIFFERS,
                document,
                {"number": document.number, "language": document.language_id},
                {"number": document.number, "language": frontmatter.language, "changed": changed},
            )
        self.found(FRONTMATTER_DIFFERS, document.number, ", ".join(changed), repaired=True)

    def parts(self, document: Document, repo: pygit2.Repository, head: Any) -> None:
        """The part files at the head against the lists of its frontmatter."""
        commit = str(head.id)
        frontmatter, _ = bundle.parse(gitstore.read(repo, "document.md", commit).decode("utf-8"))
        listed = {f"appendices/{int(e['number'])}.md" for e in frontmatter.appendices} | {
            f"attachments/{int(e['number'])}" for e in frontmatter.attachments
        }
        present = {
            f"{folder}/{name}"
            for folder in ("appendices", "attachments")
            for name in gitstore.listing(repo, folder, commit)
        }
        for path in sorted(present - listed):
            self.found(ORPHAN_PART, document.number, path)
        for path in sorted(listed - present):
            self.found(PART_MISSING, document.number, path)

    def passport(self, document: Document, repo: pygit2.Repository, head: Any) -> None:
        """Every acceptance row against the section its own commit appended, field by field, the
        passport believed — a disagreeing row rewritten from its section on repair; every section
        no row records, and every acceptance or return commit's version without its row,
        reported — a return's derived on repair, as `settle_head` derives it."""
        from review import services as review
        from review.models import Acceptance, Return

        text = gitstore.read(repo, "passport.md", str(head.id)).decode("utf-8")
        try:
            entries = bundle.passport_entries(text)
        except ValueError:
            # A passport that does not read: each heading reported by its kind alone.
            for match in PASSPORT_ENTRY.finditer(text):
                named = PASSPORT_KIND.match(match.group("entry"))
                detail = named.group("kind") if named else "an entry the passport cannot name"
                self.found(PASSPORT_ENTRY_WITHOUT_ROW, document.number, detail)
            return
        recorded: set[int] = set()
        for row in Acceptance.objects.filter(version__document=document).select_related("version"):
            if row.version.kind != "acceptance":
                self.found(
                    ACCEPTANCE_DIFFERS, document.number, f"{row.number} (not a passport commit)"
                )
                continue
            found = review.derivable(document, repo, row.version.commit_sha)
            if isinstance(found, str):
                self.found(ACCEPTANCE_DIFFERS, document.number, f"{row.number} ({found})")
                continue
            recorded.add(len(review.passport_at(repo, row.version.commit_sha)) - 1)
            expected = {
                "number": found.entry.number,
                "reviewer_id": found.reviewer.pk,
                "at": found.entry.at,
                "accepted_from_id": found.accepted_from.pk,
            }
            differs = [name for name, value in expected.items() if getattr(row, name) != value]
            if not differs:
                continue
            detail = (
                f"acceptance {found.entry.number} "
                f"(the row reads {row.number}: {', '.join(differs)})"
            )
            if self.repair:
                with transaction.atomic():
                    Acceptance.objects.filter(pk=row.pk).update(**expected)
                    _audit(
                        self.tenant,
                        ACCEPTANCE_DIFFERS,
                        document,
                        {"number": document.number, "accepted": row.number},
                        {"number": document.number, "accepted": found.entry.number},
                    )
            self.found(ACCEPTANCE_DIFFERS, document.number, detail, repaired=self.repair)
        for version in Version.objects.filter(
            document=document, kind="acceptance", acceptance__isnull=True
        ):
            found = review.derivable(document, repo, version.commit_sha)
            repaired = False
            if self.repair and not isinstance(found, str):
                with transaction.atomic():
                    review.derive_acceptance(document, version.commit_sha, found)
                    _audit(
                        self.tenant,
                        COMMIT_WITHOUT_ROW,
                        document,
                        None,
                        {"commit": version.commit_sha},
                    )
                recorded.add(len(review.passport_at(repo, version.commit_sha)) - 1)
                repaired = True
            self.found(COMMIT_WITHOUT_ROW, document.number, version.commit_sha, repaired=repaired)
        for returned in Return.objects.filter(version__document=document).select_related("version"):
            if self.return_row(document, repo, returned):
                recorded.add(len(review.passport_at(repo, returned.version.commit_sha)) - 1)
        for version in Version.objects.filter(
            document=document, kind="return", returned__isnull=True
        ):
            found_return = review.derivable_return(document, repo, version.commit_sha)
            repaired = False
            if self.repair and not isinstance(found_return, str):
                with transaction.atomic():
                    review.derive_return(document, version.commit_sha, found_return)
                    _audit(
                        self.tenant,
                        COMMIT_WITHOUT_ROW,
                        document,
                        None,
                        {"commit": version.commit_sha},
                    )
                recorded.add(len(review.passport_at(repo, version.commit_sha)) - 1)
                repaired = True
            self.found(COMMIT_WITHOUT_ROW, document.number, version.commit_sha, repaired=repaired)
        for position, entry in enumerate(entries):
            # Approvals are reported against their editions by `editions`.
            if entry.kind in ("acceptance", "return") and position not in recorded:
                detail = entry.kind + (f" {entry.number}" if entry.kind == "acceptance" else "")
                self.found(PASSPORT_ENTRY_WITHOUT_ROW, document.number, detail)

    def return_row(self, document: Document, repo: pygit2.Repository, row: Any) -> bool:
        """A `RETURN` row against the section its own commit appended, the passport believed: a
        row that disagrees is rewritten from it on repair, the reason named by field alone, never
        quoted (DL-0369). Whether the row answers for its section."""
        from review import services as review
        from review.models import Return

        if row.version.kind != "return":
            self.found(RETURN_DIFFERS, document.number, f"{row.version.commit_sha} (not a return)")
            return False
        found = review.derivable_return(document, repo, row.version.commit_sha)
        if isinstance(found, str):
            self.found(RETURN_DIFFERS, document.number, f"{row.version.commit_sha} ({found})")
            return False
        expected = {
            "reviewer_id": found.reviewer.pk,
            "at": found.entry.at,
            "reason": found.entry.reason,
            "returned_from_id": found.accepted_from.pk,
        }
        differs = [name for name, value in expected.items() if getattr(row, name) != value]
        if differs:
            detail = f"{row.version.commit_sha} (the row's {', '.join(differs)})"
            if self.repair:
                with transaction.atomic():
                    Return.objects.filter(pk=row.pk).update(**expected)
                    _audit(
                        self.tenant,
                        RETURN_DIFFERS,
                        document,
                        {"number": document.number, "differs": differs},
                        {"number": document.number, "commit": row.version.commit_sha},
                    )
            self.found(RETURN_DIFFERS, document.number, detail, repaired=self.repair)
        return True

    # --- a repository without a row -------------------------------------------------------

    def orphan(self, number: int) -> None:
        if Document.objects.filter(number=number).exists():
            return
        repo = gitstore.open_repository(self.tenant.number, number)
        commits = list(gitstore.history(repo))
        if not self.trusted(number, commits):
            self.found(IDENTITY_MISMATCH, number)
            return
        if not self.repair:
            self.found(ORPHAN_REPOSITORY, number)
            return
        if not commits:
            self.found(ORPHAN_REPOSITORY, number, "no commit to recreate it from")
            return
        creator = self.author(commits[0])
        text = gitstore.read(repo, "document.md", str(commits[-1].id)).decode("utf-8")
        frontmatter, _ = bundle.parse(text)
        if creator is None or not Language.objects.filter(code=frontmatter.language).exists():
            self.found(ORPHAN_REPOSITORY, number, "no creator of this tenant, or no such language")
            return
        with transaction.atomic():
            # No links and not author-only: nobody but administrators reaches it until the tenant
            # administrator links groups.
            document = Document.objects.create(
                number=number,
                title=frontmatter.title,
                language_id=frontmatter.language,
                document_type=DocumentType.objects.get(code=DEFAULT_TYPE),
                folder=Folder.objects.get(number=ROOT_FOLDER),
                author_only=False,
                state=DocumentState.ACTIVE,
                created_by=creator,
                actor_kind=ActorKind.USER,
            )
            _audit(
                self.tenant,
                ORPHAN_REPOSITORY,
                document,
                None,
                {
                    "number": number,
                    "created_by": str(creator.pk),
                    "document_type": DEFAULT_TYPE,
                    "folder": ROOT_FOLDER,
                    "author_only": False,
                },
            )
            services.tell_administrators(document, None, recreated=True)
        self.found(ORPHAN_REPOSITORY, number, repaired=True)
        self.commits_without_rows(document, commits, replay=True)

    # --- the whole tenant ------------------------------------------------------------------

    def repository_numbers(self) -> list[int]:
        if self.directory.is_symlink() or not self.directory.is_dir():
            return []
        numbers = []
        for entry in self.directory.iterdir():
            match = REPOSITORY.match(entry.name)
            if match is None:
                continue
            number = int(match.group("number"))
            if number <= NUMBER_MAX and self.path(number) is not None:
                numbers.append(number)
        return sorted(numbers)

    def guarded(self, number: int, work: Callable[[], None], *, lock: bool = True) -> None:
        """Run one document's work, under its lock when asked; a fault is reported and the run
        goes on."""
        try:
            if lock:
                with document_lock(self.tenant.number, number, timeout=LOCK_TIMEOUT_SECONDS):
                    work()
            else:
                work()
        except LockTimeout:
            self.found(LOCKED, number)
        except Exception as error:
            logger.exception(
                "the reconciler could not read a document",
                extra={"tenant": self.tenant.number, "document": number},
            )
            self.found(UNREADABLE, number, type(error).__name__)

    def sequence(self, numbers: list[int]) -> None:
        """The number sequence past every repository directory, rows or not, since creation
        refuses any directory already there; reported when behind. Numbers are never reused, so
        moving past one that cannot be recreated costs nothing."""
        highest = max(numbers, default=0)
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT last_value, is_called FROM {DOCUMENT_NUMBER_SEQUENCE}")
            last_value, is_called = cursor.fetchone() or (0, False)
        if (last_value + 1 if is_called else last_value) > highest:
            return
        if not self.repair:
            self.found(SEQUENCE_BEHIND, highest)
            return
        with connection.cursor() as cursor:
            # One statement: a number taken meanwhile is never handed out again.
            cursor.execute(
                f"SELECT setval(%s, %s) FROM {DOCUMENT_NUMBER_SEQUENCE}"
                " WHERE last_value < %s OR NOT is_called",
                [DOCUMENT_NUMBER_SEQUENCE, highest, highest],
            )
            _audit(self.tenant, SEQUENCE_BEHIND, None, None, {"number": highest})
        self.found(SEQUENCE_BEHIND, highest, repaired=True)


def _tenants(number: int | None) -> Iterator[Tenant]:
    tenants = visited_by_background_work()
    if number is not None:
        tenants = tenants.filter(number=number)
    yield from tenants


def tenant_exists(number: int) -> bool:
    """Whether the reconciler would visit tenant `number`."""
    return visited_by_background_work().filter(number=number).exists()


def run(
    tenant: int | None = None,
    document: int | None = None,
    *,
    repair: bool = False,
    prune_rows: bool = False,
) -> list[Finding]:
    """Reconcile every tenant, or one, or one document of one; return what was found.

    In report mode nothing is written. `repair` makes what git implies true of the rows;
    `prune_rows`, only with `repair`, deletes a version row whose commit its repository no longer
    holds.
    """
    if prune_rows and not repair:
        raise ValueError("pruning rows is a repair")
    if connection.in_atomic_block:
        raise RuntimeError("the reconciler commits each repair; call it outside a transaction")
    if not Path(settings.GIT_REPO_ROOT).is_dir():
        raise RuntimeError("the repository root is not there; nothing is reconciled against it")
    findings: list[Finding] = []
    for each in _tenants(tenant):
        with schema_context(each.number):
            try:
                findings.extend(_tenant(each, document, repair, prune_rows))
            except Exception:
                logger.exception(
                    "the reconciler stopped in a tenant", extra={"tenant": each.number}
                )
                findings.append(Finding(UNREADABLE, each.number, 0, "the tenant's pass stopped"))
    return findings


def _tenant(tenant: Tenant, only: int | None, repair: bool, prune_rows: bool) -> list[Finding]:
    one = _Run(tenant, repair, prune_rows)
    numbers = [n for n in one.repository_numbers() if only is None or n == only]
    rows = Document.objects.order_by("number")
    if only is not None:
        rows = rows.filter(number=only)
    listed = list(rows.values_list("number", flat=True))
    if one.prune_rows and listed and not one.directory.is_dir():
        # Rows and no tenant directory: a missing mount, never a reason to delete.
        one.found(REPOSITORY_MISSING, 0, "the tenant's directory is not there; nothing pruned")
        one.prune_rows = False
    for number in listed:

        def check(number: int = number) -> None:
            # Read under the lock: a creation or another run may have moved the row meanwhile.
            current = (
                Document.objects.select_related("document_type", "folder")
                .filter(number=number)
                .first()
            )
            if current is not None:
                one.document(current)

        # Report mode takes no lock, and so creates no file, where there is no repository.
        one.guarded(number, check, lock=repair or one.path(number) is not None)
    for number in numbers:
        if number not in listed:
            one.guarded(number, partial(one.orphan, number))
    one.sequence(numbers)
    _exports(one, only)
    return one.findings


def _exports(one: _Run, only: int | None) -> None:
    """Every export still queued after its grace: reported, and queued again on repair — failed
    instead once it has waited an hour. The job runs once whatever the queue holds: it leaves a
    job that is not queued alone. Each repair is audited with numbers."""
    # Imported here: exports are an app built on this one.
    from django.utils.translation import gettext as _

    from rendering.models import ExportJob, ExportState
    from rendering.tasks import render_export

    now = timezone.now()
    stuck = ExportJob.objects.filter(state=ExportState.QUEUED, created_at__lt=now - EXPORT_GRACE)
    if only is not None:
        stuck = stuck.filter(document__number=only)
    for job in stuck.select_related("document"):
        abandoned = job.created_at < now - EXPORT_ABANDONED
        kind = EXPORT_ABANDONED_KIND if abandoned else EXPORT_STUCK
        if one.repair:
            if abandoned:
                reason = _("The file was not made in time. Export again.")
                with transaction.atomic():
                    # A job a render holds is not abandoned: skipped, never waited for. The row
                    # is locked by a SELECT that skips it; an UPDATE alone would wait.
                    free = (
                        ExportJob.objects.select_for_update(skip_locked=True)
                        .filter(pk=job.pk, state=ExportState.QUEUED)
                        .values_list("pk", flat=True)
                        .first()
                    )
                    if free is not None:
                        ExportJob.objects.filter(pk=free).update(
                            state=ExportState.FAILED, failure_reason=reason
                        )
                if free is None:
                    continue
            else:
                render_export.delay(one.tenant.number, str(job.pk))
            _audit(one.tenant, kind, job.document, None, {"export": str(job.pk)})
        one.found(kind, job.document.number, str(job.pk), repaired=one.repair)


def is_a_copy(document: Document) -> bool:
    """Whether `document`'s creation is a copy: its source written to the audit trail before any
    repository (DL-0455)."""
    from audit.models import AuditEvent

    return AuditEvent.objects.filter(
        action="document.copied", object_type="document", object_id=document.pk
    ).exists()
