"""Which version introduced each line of a document: the authorship worker's computation (DL-0135,
DL-0266, ADR-0011).

Blame is the git binary's (ADR-0011), run as a process with an explicit argument list and never a
shell; pygit2 stays in `documents.gitstore`. The blame is bounded to the commits since the nearest
version whose rows are cached, and the lines older than that version take its rows: git has no
incremental blame, and this bound is the incremental job. With no cached version the blame is cold.

A moved sentence is followed by the platform's rule, not by git's `-M`, which cannot follow
Cyrillic text: a line removed and re-added byte for byte in one commit keeps the version that
introduced it. When the moved text stands on more than one line of the file, before or after the
commit, the text cannot say which line moved; every line carrying it is recorded `ambiguous_move`
and keeps what blame says — the move is not guessed.

The move rule needs the attribution of the file just before each moving commit, so a range holding
moves is blamed in steps — to the parent of each moving commit, across it, then on — each step
bounded by the last.

Blank lines and the frontmatter carry no authorship; `line` counts the frontmatter.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from django.db import connection, transaction

from documents import bundle
from documents.housekeeping import GIT_ENV
from documents.models import Document, Version, VersionKind
from editing.models import LineAuthorship
from tenancy.schemas import current_tenant

logger = logging.getLogger(__name__)

DOCUMENT_FILE = "document.md"
MAIN = "refs/heads/main"
GIT_TIMEOUT_SECONDS = 60
SHA = re.compile(r"^[0-9a-f]{40}$")
BLAME_GROUP = re.compile(rb"^\^?([0-9a-f]{40}) ([0-9]+) ([0-9]+)(?: [0-9]+)?$")
HUNK = re.compile(rb"^@@ -([0-9]+)(?:,([0-9]+))? \+([0-9]+)(?:,([0-9]+))? @@")
# Starts each commit of `git log`'s output; a hunk's lines are read by count, never by this mark.
COMMIT_MARK = b"\x01"
# Neither the host's nor a developer's git configuration, nor any git variable of the process,
# may shape a blame or a diff: the platform's own configuration alone, which also carries the
# ownership exception the application's repositories need.
GIT_ENVIRONMENT = {**GIT_ENV, "GIT_TERMINAL_PROMPT": "0"}


def _environment() -> dict[str, str]:
    inherited = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    return {**inherited, **GIT_ENVIRONMENT}


class AuthorshipError(RuntimeError):
    """git failed, or answered something the worker cannot read."""


# The kinds of version whose text a reader reads: a passport commit changes no text.
CONTENT_KINDS = (VersionKind.CREATED, VersionKind.EDIT, VersionKind.REVIEWER_EDIT)


class VersionMissing(LookupError):
    """A commit the attribution needs has no version row; the reconciler derives it first."""

    def __init__(self, commits: Iterable[str]) -> None:
        self.commits = tuple(sorted(commits))
        super().__init__("no version row for commit " + ", ".join(self.commits))


@dataclass(frozen=True)
class ComputeResult:
    """What one computation wrote."""

    version: Version
    # The commit whose rows the blame was bounded by and overlaid; `None` for a cold run.
    base: str | None
    rows: int
    # Rows of versions neither kept nor computed here, deleted (DL-0266).
    deleted: int
    # Per file, the lines whose attribution came from the commits blamed, not from the cache.
    reattributed: dict[str, tuple[int, ...]]
    moves: int
    ambiguous: int


@dataclass(frozen=True)
class _Line:
    commit: str
    ambiguous: bool = False
    # Attributed inside the range blamed, rather than carried over from the cached rows.
    fresh: bool = True
    # The line's number in `commit`, where blame gave it.
    orig: int | None = None


@dataclass(frozen=True)
class BlamedLine:
    """One line of a file at a commit: its text, the commit that wrote it — the base itself for a
    line the base already held — its number in that commit, and whether the move rule found the
    text more than once."""

    text: bytes
    commit: str
    orig_line: int | None
    ambiguous: bool


class _Boundary(Mapping[int, "_Line | None"]):
    """Every line the base held, attributed to the base: what a blame bounded by it reports."""

    def __init__(self, base: str) -> None:
        self.base = base

    def __getitem__(self, orig: int) -> _Line:
        return _Line(self.base, fresh=False, orig=orig)

    def __iter__(self) -> Iterator[int]:
        return iter(())

    def __len__(self) -> int:
        return 0


# A file's lines at one commit, by line number; `None` where the cache holds no row for a line.
_Lines = Mapping[int, _Line | None]


@dataclass
class _Hunk:
    old_start: int
    removed: list[bytes]
    new_start: int
    added: list[bytes]


@dataclass
class _Change:
    """One commit's `-U0` hunks of one file."""

    commit: str
    parent: str | None
    hunks: list[_Hunk]

    def moves(self) -> bool:
        removed = {text for hunk in self.hunks for text in hunk.removed if not _blank(text)}
        return any(text in removed for hunk in self.hunks for text in hunk.added)


def compute(
    document: Document,
    commit_sha: str,
    *,
    repository_path: Path,
) -> ComputeResult:
    """Write the rows of the version at `commit_sha` of `document`, whose bare repository is at
    `repository_path`, in the tenant's schema the connection is set to; then delete the rows of
    every version of the document other than the repository's head and its latest accepted
    version (DL-0266) — both found here, so no two callers can keep different sets; rows with an
    expiry are left to it.

    Idempotent: computing again writes the same rows. Raises `VersionMissing` naming every commit
    the rows would point at that has no version row, and writes nothing.
    """
    if current_tenant(connection) is None:
        raise RuntimeError("authorship is computed inside a tenant's schema")
    if not SHA.fullmatch(commit_sha):
        raise ValueError(f"not a commit id: {commit_sha!r}")
    version = Version.objects.filter(document=document, commit_sha=commit_sha).first()
    if version is None:
        raise VersionMissing([commit_sha])
    base = _base(document, version, repository_path)
    cached = _cached(base, document) if base is not None else {}

    texts, lines, moves = _file(
        repository_path, DOCUMENT_FILE, commit_sha, base, cached.get(DOCUMENT_FILE, {})
    )
    body_start, listed = _frontmatter(texts, commit_sha)
    files = {DOCUMENT_FILE: (texts, lines, body_start)}
    for path in _present(repository_path, listed, commit_sha):
        texts, lines, appendix_moves = _file(
            repository_path, path, commit_sha, base, cached.get(path, {})
        )
        # An appendix has no frontmatter of its own.
        files[path] = (texts, lines, 1)
        moves += appendix_moves

    attributed: dict[str, dict[int, _Line]] = {}
    for path, (texts, lines, start) in files.items():
        known = _known(texts, lines, start)
        if known is None:
            # The cached rows lack a line the bound carried over: the cache is not what blame
            # would say, so this file is computed again without it.
            logger.warning(
                "authorship cache incomplete; computing cold",
                extra={"document": document.number, "commit": commit_sha, "file": path},
            )
            texts, lines, file_moves = _file(repository_path, path, commit_sha, None, {})
            moves += file_moves
            known = _known(texts, lines, start)
            if known is None:
                raise AuthorshipError(f"a cold blame of {path} left a line unattributed")
        attributed[path] = known

    versions = dict(
        Version.objects.filter(
            document=document,
            commit_sha__in={line.commit for kept in attributed.values() for line in kept.values()},
        ).values_list("commit_sha", "pk")
    )
    missing = {
        line.commit
        for kept in attributed.values()
        for line in kept.values()
        if line.commit not in versions
    }
    if missing:
        raise VersionMissing(missing)

    rows = [
        LineAuthorship(
            version=version,
            file=path,
            line=n,
            introduced_by_id=versions[line.commit],
            ambiguous_move=line.ambiguous,
        )
        for path, kept in attributed.items()
        for n, line in sorted(kept.items())
    ]
    kept_versions = {version.pk}
    accepted = latest_accepted(document)
    if accepted is not None:
        kept_versions.add(accepted.pk)
    with transaction.atomic():
        # One writer per document, and the head read under it: a job for an older commit that
        # finishes after the head's never deletes the head's rows.
        list(Document.objects.select_for_update().filter(pk=document.pk))
        head = _head(repository_path)
        if head is not None:
            kept_versions.update(
                Version.objects.filter(document=document, commit_sha=head).values_list(
                    "pk", flat=True
                )
            )
        LineAuthorship.objects.filter(version=version).delete()
        LineAuthorship.objects.bulk_create(rows)
        deleted, _ = (
            LineAuthorship.objects.filter(version__document=document, expires_at__isnull=True)
            .exclude(version_id__in=kept_versions)
            .delete()
        )
    return ComputeResult(
        version=version,
        base=base,
        rows=len(rows),
        deleted=deleted,
        reattributed={
            path: tuple(n for n, line in sorted(kept.items()) if line.fresh)
            for path, kept in attributed.items()
        },
        moves=moves,
        ambiguous=sum(row.ambiguous_move for row in rows),
    )


def _git(repository: Path, *args: str) -> bytes:
    """The standard output of `git -C <repository> <args>`; `AuthorshipError` for anything but
    success within the timeout."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repository), *args],
            capture_output=True,
            env=_environment(),
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        raise AuthorshipError(f"git {args[0]} timed out") from error
    if result.returncode != 0:
        raise AuthorshipError(
            f"git {args[0]} failed: {result.stderr.decode('utf-8', 'replace').strip()}"
        )
    return result.stdout


def _blank(text: bytes) -> bool:
    return not text.strip()


def _known(
    texts: list[bytes], lines: Mapping[int, _Line | None], start: int
) -> dict[int, _Line] | None:
    """The non-blank lines from `start` on with their attribution; `None` when one has none."""
    known: dict[int, _Line] = {}
    for n in range(start, len(texts) + 1):
        line = lines[n]
        if _blank(texts[n - 1]):
            continue
        if line is None:
            return None
        known[n] = line
    return known


def _base(document: Document, version: Version, repository: Path) -> str | None:
    """The nearest ancestor of `version`'s commit whose version has rows, if any does."""
    candidates = set(
        LineAuthorship.objects.filter(version__document=document)
        .exclude(version=version)
        .values_list("version__commit_sha", flat=True)
    )
    if not candidates:
        return None
    for sha in _git(repository, "rev-list", "--first-parent", version.commit_sha).split():
        if sha.decode() in candidates:
            return sha.decode()
    return None


def _cached(base: str, document: Document) -> dict[str, dict[int, _Line | None]]:
    cached: dict[str, dict[int, _Line | None]] = defaultdict(dict)
    for path, line, introduced_by, ambiguous in LineAuthorship.objects.filter(
        version__document=document, version__commit_sha=base
    ).values_list("file", "line", "introduced_by__commit_sha", "ambiguous_move"):
        cached[path][line] = _Line(introduced_by, ambiguous, fresh=False)
    return cached


def blame_at(
    repository_path: Path, commit: str, *, base: str | None, path: str = DOCUMENT_FILE
) -> list[BlamedLine]:
    """`path` at `commit`, every line with the commit that wrote it, blamed back to `base` with the
    move rule applied: a line `base` already held carries `base`; with no base the blame is cold.
    Frontmatter lines are included; the caller reads what it needs."""
    for sha in (commit, base):
        if sha is not None and not SHA.fullmatch(sha):
            raise ValueError(f"not a commit id: {sha!r}")
    before: _Lines = _Boundary(base) if base is not None else {}
    texts, lines, _ = _file(repository_path, path, commit, base, before)
    blamed = []
    for n, text in enumerate(texts, 1):
        line = lines[n]
        if line is None:
            raise AuthorshipError(f"{path} at {commit}: line {n} unattributed")
        blamed.append(BlamedLine(text, line.commit, line.orig, line.ambiguous))
    return blamed


def latest_accepted(document: Document) -> Version | None:
    """The content version the document's latest acceptance accepted, as its passport section
    records it; `None` before any acceptance."""
    from review.services import accepted_content_version, latest_acceptance

    acceptance = latest_acceptance(document)
    if acceptance is None:
        return None
    try:
        return accepted_content_version(acceptance)
    except (LookupError, ValueError, Version.DoesNotExist):
        # A row the passport does not bear out is the reconciler's to report; the rows of the
        # head are computed all the same.
        logger.warning("the latest acceptance does not read", extra={"document": document.number})
        return None


def _head(repository: Path) -> str | None:
    out = _git(repository, "for-each-ref", "--format=%(objectname)", MAIN).strip()
    return out.decode() or None


def _frontmatter(texts: list[bytes], commit: str) -> tuple[int, list[str]]:
    """The number of `document.md`'s first body line, after its frontmatter, and the appendix
    files the frontmatter lists."""
    try:
        text = (b"\n".join(texts) + b"\n").decode("utf-8")
        frontmatter, body = bundle.parse(text)
    except ValueError as error:
        raise AuthorshipError(f"{DOCUMENT_FILE} at {commit} does not parse: {error}") from error
    return (
        text[: len(text) - len(body)].count("\n") + 1,
        [f"appendices/{int(item['number'])}.md" for item in frontmatter.appendices],
    )


def _present(repository: Path, listed: list[str], commit: str) -> list[str]:
    """The files of `listed` the commit holds; a missing one is logged and left out, as the
    caches leave it out (`documents.caches.rebuild`)."""
    if not listed:
        return []
    present = set(
        _git(repository, "ls-tree", "--name-only", commit, "--", *listed).decode().splitlines()
    )
    for path in listed:
        if path not in present:
            logger.error(
                "an appendix listed in the frontmatter is missing",
                extra={"commit": commit, "file": path},
            )
    return [path for path in listed if path in present]


def _file(
    repository: Path, path: str, target: str, base: str | None, cached: _Lines
) -> tuple[list[bytes], dict[int, _Line | None], int]:
    """`path` at `target`: its lines' texts, their attribution and the moves followed, blamed
    from `base` (cold when `None`) in steps around each commit that moves a line."""
    moving = [change for change in _changes(repository, path, base, target) if change.moves()]
    at, before, moves = base, cached, 0
    texts: list[bytes] = []
    lines: dict[int, _Line | None] = {}
    for change in moving:
        if change.parent != at:
            assert change.parent is not None
            _, before = _blame(repository, path, at, before, change.parent)
            at = change.parent
        texts, lines = _blame(repository, path, at, before, change.commit)
        moves += _follow_moves(texts, lines, change, before)
        at, before = change.commit, lines
    if at != target:
        texts, lines = _blame(repository, path, at, before, target)
    return texts, lines, moves


def _blame(
    repository: Path, path: str, base: str | None, before: _Lines, target: str
) -> tuple[list[bytes], dict[int, _Line | None]]:
    """`path` at `target` blamed back to `base`: a line `base` already held takes its entry in
    `before`; any other, the commit blame names."""
    bound = [f"^{base}"] if base is not None else []
    out = _git(repository, "blame", "--porcelain", *bound, target, "--", path)
    texts: list[bytes] = []
    lines: dict[int, _Line | None] = {}
    for commit, orig, text in _porcelain(out):
        texts.append(text)
        lines[len(texts)] = before.get(orig) if commit == base else _Line(commit, orig=orig)
    return texts, lines


def _porcelain(out: bytes) -> list[tuple[str, int, bytes]]:
    """`git blame --porcelain` as `(commit, line in that commit, text)` per line, in order."""
    result: list[tuple[str, int, bytes]] = []
    group: tuple[str, int] | None = None
    for raw in out.split(b"\n")[:-1]:
        if raw.startswith(b"\t"):
            if group is None:
                raise AuthorshipError("blame: a line with no header")
            result.append((*group, raw[1:]))
            group = None
        elif group is None:
            match = BLAME_GROUP.match(raw)
            if match is None or int(match.group(3)) != len(result) + 1:
                raise AuthorshipError("blame: an unexpected header")
            group = (match.group(1).decode(), int(match.group(2)))
        # Otherwise a header field of the group's commit, which the worker does not read.
    if group is not None:
        raise AuthorshipError("blame: a header with no line")
    return result


Change = _Change


def changes(repository_path: Path, path: str, base: str | None, target: str) -> list[Change]:
    """The `-U0` hunks of `path` in every commit after `base` up to `target` that changes it,
    oldest first along the first parent; from the root when `base` is `None`."""
    for sha in (target, base):
        if sha is not None and not SHA.fullmatch(sha):
            raise ValueError(f"not a commit id: {sha!r}")
    return _changes(repository_path, path, base, target)


def file_at(repository_path: Path, commit: str, path: str = DOCUMENT_FILE) -> list[bytes]:
    """`path` at `commit` as its lines, without their line ends."""
    if not SHA.fullmatch(commit):
        raise ValueError(f"not a commit id: {commit!r}")
    data = _git(repository_path, "show", f"{commit}:{path}")
    lines = data.split(b"\n")
    return lines[:-1] if data.endswith(b"\n") else lines


def _changes(repository: Path, path: str, base: str | None, target: str) -> list[_Change]:
    """Every commit after `base` up to `target` that changes `path`, oldest first, with its
    hunks."""
    bound = [f"^{base}"] if base is not None else []
    out = _git(
        repository,
        "log",
        "-p",
        "-U0",
        "--reverse",
        "--first-parent",
        "--no-color",
        "--no-ext-diff",
        "--no-textconv",
        "--no-renames",
        "--format=%x01%H %P",
        *bound,
        target,
        "--",
        path,
    )
    raw = out.split(b"\n")
    changes: list[_Change] = []
    i = 0
    while i < len(raw):
        line = raw[i]
        i += 1
        if line.startswith(COMMIT_MARK):
            commit, *parents = line[1:].decode().split()
            changes.append(_Change(commit, parents[0] if parents else None, []))
            continue
        match = HUNK.match(line)
        if match is None:
            continue
        if not changes:
            raise AuthorshipError("log: a hunk before any commit")
        old_count = 1 if match.group(2) is None else int(match.group(2))
        new_count = 1 if match.group(4) is None else int(match.group(4))
        removed, i = _hunk_lines(raw, i, old_count, b"-")
        added, i = _hunk_lines(raw, i, new_count, b"+")
        changes[-1].hunks.append(_Hunk(int(match.group(1)), removed, int(match.group(3)), added))
    return changes


def _hunk_lines(raw: list[bytes], i: int, count: int, sign: bytes) -> tuple[list[bytes], int]:
    lines = raw[i : i + count]
    if len(lines) != count or not all(line.startswith(sign) for line in lines):
        raise AuthorshipError("log: a hunk shorter than its header")
    i += count
    if i < len(raw) and raw[i].startswith(b"\\"):
        # "\ No newline at end of file"
        i += 1
    return [line[1:] for line in lines], i


def _follow_moves(
    texts: list[bytes], lines: dict[int, _Line | None], change: _Change, before: _Lines
) -> int:
    """Apply the move rule to `lines`, the file at `change.commit`; `before` is the file at its
    parent. Returns the lines followed."""
    removed_at: dict[bytes, list[int]] = defaultdict(list)
    added_at: dict[bytes, list[int]] = defaultdict(list)
    for hunk in change.hunks:
        for offset, text in enumerate(hunk.removed):
            if not _blank(text):
                removed_at[text].append(hunk.old_start + offset)
        for offset, text in enumerate(hunk.added):
            if not _blank(text):
                added_at[text].append(hunk.new_start + offset)
    after_count = Counter(texts)
    followed = 0
    for text, added in added_at.items():
        removed = removed_at.get(text)
        if not removed:
            continue
        before_count = after_count[text] - len(added) + len(removed)
        if after_count[text] == 1 and before_count == 1:
            previous = before.get(removed[0])
            lines[added[0]] = None if previous is None else replace(previous, fresh=True)
            followed += 1
            continue
        for n, line_text in enumerate(texts, 1):
            line = lines[n]
            if line_text == text and line is not None:
                lines[n] = replace(line, ambiguous=True)
    return followed
