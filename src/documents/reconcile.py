"""The reconciler: the second path from git to the rows (DL-0111).

Git is the commit point and the rows are its cache. Report mode lists what disagrees and writes
nothing. Repair derives what git implies, finishes stopped creations, finishes a *send for review*
that stopped after its commit (DL-0318), asks again for the head's missing authorship (DL-0266)
and recreates a row for a repository without one, fail closed; a row is deleted only on
`prune_rows`, and only a version row whose commit its existing repository no longer holds
(ADR-0018, DL-0276). A repository is trusted only where its passport names the tenant and the
number it sits at. Every repair runs under the document's lock and is audited with numbers, never
a title. One document's fault is reported and the run goes on.
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

# The kinds of finding.
CREATING_WITHOUT_REPOSITORY = "creating_without_repository"
CREATING_WITHOUT_COMMIT = "creating_without_commit"
CREATING_WITHOUT_VERSION = "creating_without_version"
CREATING_UNFINISHED = "creating_unfinished"
ORPHAN_REPOSITORY = "orphan_repository"
REPOSITORY_MISSING = "repository_missing"
COMMIT_WITHOUT_ROW = "commit_without_row"
ROW_WITHOUT_COMMIT = "row_without_commit"
FRONTMATTER_DIFFERS = "frontmatter_differs"
PASSPORT_ENTRY_WITHOUT_ROW = "passport_entry_without_row"
IDENTITY_MISMATCH = "identity_mismatch"
SEQUENCE_BEHIND = "sequence_behind"
LOCKED = "locked"
AUTHORSHIP_MISSING = "authorship_missing"
FINISH_STOPPED = "finish_stopped"
UNREADABLE = "unreadable"


@dataclass(frozen=True)
class Finding:
    """One disagreement: `tenant` and `document` are numbers, `detail` a sha, a passport entry's
    kind or a reason, never a title."""

    kind: str
    tenant: int
    document: int
    detail: str = ""
    repaired: bool = False


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
            self.passport(document, repo, commits[-1])
            self.finishes(document, commits)
            self.authorship(document, str(commits[-1].id))

    def creating(self, document: Document) -> None:
        if document.created_at > timezone.now() - CREATING_GRACE:
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
            if (
                not self.repair
                or not replay
                or stopped
                or n < newest
                or author is None
                or kind not in REPLAYED
            ):
                reason = "" if author is not None else " (author not of this tenant)"
                self.found(COMMIT_WITHOUT_ROW, document.number, sha + reason)
                stopped = stopped or n > newest
                continue
            with transaction.atomic():
                services.derive_version(document, commit, author)
                _audit(self.tenant, COMMIT_WITHOUT_ROW, document, None, {"commit": sha})
            self.found(COMMIT_WITHOUT_ROW, document.number, sha, repaired=True)

    def finishes(self, document: Document, commits: list[pygit2.Commit]) -> None:
        """A finish that stopped after its commit (DL-0318). An open hold whose draft's base is
        behind an `edit` commit of its holder is released as finished and its draft deleted —
        only when the holder is a member, the commit has its row, and the draft holds nothing
        the commit does not; otherwise it is reported, and the holder's next *send for review*
        resumes it. A finished hold whose draft is still there has the draft deleted."""
        from editing import holds as editing
        from editing.models import Draft, Hold, ReleaseKind

        order = {str(commit.id): n for n, commit in enumerate(commits)}
        for hold in Hold.objects.filter(document=document, draft__isnull=False):
            draft = Draft.objects.get(hold=hold)
            edit, reason = "", ""
            if hold.released_at is not None:
                if hold.release_kind != ReleaseKind.FINISHED:
                    continue
            else:
                base = order.get(draft.base_commit)
                if base is None:
                    continue
                edits = [
                    commit
                    for commit in commits[base + 1 :]
                    if gitstore.kind_of(commit.message) is gitstore.Kind.EDIT
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
                    draft.delete()
                    _audit(self.tenant, FINISH_STOPPED, document, None, {"number": document.number})
            detail = f"{edit} ({reason})" if reason else edit
            self.found(FINISH_STOPPED, document.number, detail, repaired=self.repair and not reason)

    def unfinishable(self, document: Document, commit: pygit2.Commit, draft: Any) -> str:
        """Why a stopped finish is left for its holder: an empty string when it may be finished."""
        from editing.markdown.validator import validate
        from editing.normalizer import Lists, NormalizerDefect, normalize

        if self.author(commit) is None:
            return "its holder is not of this tenant"
        if not Version.objects.filter(document=document, commit_sha=str(commit.id)).exists():
            return "its commit has no row"
        body = draft.content["document.md"]
        _, committed = bundle.parse(
            gitstore.read(
                gitstore.open_repository(self.tenant.number, document.number),
                "document.md",
                str(commit.id),
            ).decode("utf-8")
        )
        if validate(body):
            return "the draft holds later text"
        lists = Lists.of(document.language)
        try:
            again = normalize(committed.encode(), body, lists).decode("utf-8")
        except NormalizerDefect:
            return "the draft does not normalise"
        if again != committed:
            return "the draft holds later text"
        return ""

    def authorship(self, document: Document, head: str) -> None:
        """The head version, of any kind, without rows while its text has a non-blank line: the
        worker is asked for it again (DL-0266, DL-0326). A version not derived yet waits for its
        row; a blank text has no rows by design and is never asked for."""
        from editing.models import LineAuthorship
        from editing.tasks import queue_authorship

        version = Version.objects.filter(document=document, commit_sha=head).first()
        if version is None:
            return
        if LineAuthorship.objects.filter(version=version, expires_at__isnull=True).exists():
            return
        if not self.has_lines(document, head):
            return
        if self.repair:
            queue_authorship(self.tenant.number, document.number, head)
        self.found(AUTHORSHIP_MISSING, document.number, head, repaired=self.repair)

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
        """Report, or prune, the version rows whose commit is gone; `True` while any remain."""
        missing = list(Version.objects.filter(document=document).exclude(commit_sha__in=present))
        for version in missing:
            sha = version.commit_sha
            if self.prune_rows:
                with transaction.atomic():
                    version.delete()
                    _audit(self.tenant, ROW_WITHOUT_COMMIT, document, {"commit": sha}, None)
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

    def passport(self, document: Document, repo: pygit2.Repository, head: Any) -> None:
        # No row records a passport entry, so each one is reported by its kind alone.
        text = gitstore.read(repo, "passport.md", str(head.id)).decode("utf-8")
        for match in PASSPORT_ENTRY.finditer(text):
            entry = PASSPORT_KIND.match(match.group("entry"))
            detail = entry.group("kind") if entry else "an entry the passport cannot name"
            self.found(PASSPORT_ENTRY_WITHOUT_ROW, document.number, detail)

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
    return one.findings
