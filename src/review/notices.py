"""The correction notice (ADR-0001, ADR-0014, DL-0113): at acceptance, for every version of the run
committed by a holder of *accept*, each line of `document.md` or of an appendix another author of
the run wrote that the version replaced or removed, or removed and the version restored; and each
part — an appendix or an attachment — whose state another author's version of the run set and the
version changed: removed, replaced, renamed, or restored after another's removal.

The core, `entries`, reads the document's repository twice — the file at the base and the run's
`-U0` log — then walks the run forward, carrying for every line the version that wrote it and its
number there. So the author of a line at any version's parent is known without a blame, and the
cost follows the run's size. A line the accepted base already held is ordinary editing and
generates nothing; so does a line in the frontmatter, which carries no authorship. Moves follow
the platform's rule (ADR-0011): a line removed and added byte for byte in one commit, met once in
the file before it and once after, keeps its writer; text met more than once is ambiguous, and an
ambiguous line generates nothing — the move is recorded, never guessed. An added line equal to a
line an earlier version of the run removed, and nobody added back since, is a restored line and
discloses the remover's act. Nobody is named about their own change.

Ranges count the lines of the whole file, frontmatter included, as `LINE_AUTHORSHIP.line` does;
the frontmatter is not parsed, only found between its delimiters. A carried range is the span of
the lines it became.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Collection, Hashable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

from editing import authorship


@dataclass(frozen=True)
class RunCommit:
    """One content commit of the run, oldest first; `author` identifies who committed it."""

    sha: str
    parent: str
    author: Hashable


@dataclass(frozen=True)
class Entry:
    """One disclosed change. `author` is whose change is disclosed — the writer of a replaced or
    removed line, or the remover of a restored one — and `author_version` the version that made
    it; `changing_version` and `changer` the covered version that replaced or reversed it and who
    committed that. `range_before` is the line in `author_version` for a `line` entry, and in the
    removing version's parent for a `restored` one; `range_after` the lines that stand in its place
    in the run's last version, `""` when none do. A range is `"n"` or `"n-m"`."""

    kind: Literal["line", "restored", "part_operation"]
    author: Hashable
    author_version: str
    changing_version: str
    changer: Hashable
    range_before: str
    range_after: str
    # file: the file a line entry is in. part: a part entry's path beside `document.md`; ""
    # for a line entry.
    file: str = authorship.DOCUMENT_FILE
    part: str = ""


@dataclass(frozen=True)
class _Written:
    """Who wrote a line: the commit — the base itself for the base's lines — and the line's number
    there; `ambiguous` when a move of its text could not be told apart."""

    commit: str
    line: int
    ambiguous: bool = False


@dataclass
class _Step:
    """One commit of the run as the walk sees it: its hunks, its moves (removed line → added line),
    the lines whose text moved ambiguously on either side, and where the body starts before and
    after it."""

    change: authorship.Change
    moved: dict[int, int] = field(default_factory=dict)
    ambiguous_texts: set[bytes] = field(default_factory=set)
    ambiguous_removed: set[int] = field(default_factory=set)
    ambiguous_added: set[int] = field(default_factory=set)
    body_before: int = 1
    body_after: int = 1


def _blank(text: bytes) -> bool:
    return not text.strip()


def _body_start(texts: Sequence[bytes], path: str = authorship.DOCUMENT_FILE) -> int:
    """The number of the first line after the frontmatter; 1 when there is none, as for an
    appendix, whose whole text is its body."""
    if path == authorship.DOCUMENT_FILE and texts and texts[0] == b"---":
        for n in range(1, len(texts)):
            if texts[n] == b"---":
                return n + 2
    return 1


def _applied(texts: list[bytes], change: authorship.Change) -> list[bytes]:
    """The file after `change`, from the file before it; `AuthorshipError` when a hunk does not
    remove what the file holds."""
    out = list(texts)
    for hunk in reversed(change.hunks):
        if hunk.removed:
            at = hunk.old_start - 1
            if out[at : at + len(hunk.removed)] != hunk.removed:
                raise authorship.AuthorshipError(f"{change.commit}: a hunk the file does not hold")
            del out[at : at + len(hunk.removed)]
        else:
            at = hunk.old_start
        out[at:at] = hunk.added
    return out


def _moves(step: _Step, before: Sequence[bytes], after: Sequence[bytes]) -> None:
    """The move rule over one commit, text counted in the whole file on each side, as the
    authorship worker counts it."""
    removed_at: dict[bytes, list[int]] = defaultdict(list)
    added_at: dict[bytes, list[int]] = defaultdict(list)
    for hunk in step.change.hunks:
        for offset, text in enumerate(hunk.removed):
            if not _blank(text):
                removed_at[text].append(hunk.old_start + offset)
        for offset, text in enumerate(hunk.added):
            if not _blank(text):
                added_at[text].append(hunk.new_start + offset)
    count_before, count_after = Counter(before), Counter(after)
    for text, added in added_at.items():
        removed = removed_at.get(text)
        if not removed:
            continue
        if len(added) == len(removed) == count_before[text] == count_after[text] == 1:
            step.moved[removed[0]] = added[0]
        else:
            step.ambiguous_texts.add(text)
            step.ambiguous_removed.update(removed)
            step.ambiguous_added.update(added)


def _written(written: list[_Written], step: _Step, commit: str) -> list[_Written]:
    """Who wrote each line after `step`, from who wrote each line before it."""
    out = list(written)
    source = {new: old for old, new in step.moved.items()}
    for hunk in reversed(step.change.hunks):
        at = hunk.old_start - 1 if hunk.removed else hunk.old_start
        del out[at : at + len(hunk.removed)]
        fresh = []
        for offset in range(len(hunk.added)):
            number = hunk.new_start + offset
            if number in source:
                fresh.append(written[source[number] - 1])
            else:
                fresh.append(_Written(commit, number, number in step.ambiguous_added))
        out[at:at] = fresh
    return out


def entries(
    repository_path: Path,
    *,
    base: str,
    run: Sequence[RunCommit],
    covered: Collection[str],
    path: str = authorship.DOCUMENT_FILE,
    from_empty: bool = False,
) -> list[Entry]:
    """The entries the run's `covered` versions generate, in run order, for the file at `path` —
    walked from the empty file with `from_empty`, an appendix the base does not hold.

    `base` is the commit the run starts from — the latest accepted content version, or the
    document's first commit. A commit outside `covered` generates nothing of its own, but still
    writes and removes lines and moves the ranges carried to the last version."""
    if not run:
        return []
    authors = {commit.sha: commit.author for commit in run}
    changes = authorship.changes(repository_path, path, base, run[-1].sha)
    parents = {commit.sha: commit.parent for commit in run}
    at_base = [] if from_empty else authorship.file_at(repository_path, base, path)
    texts = at_base
    written = [_Written(base, n) for n in range(1, len(texts) + 1)]
    steps: list[_Step] = []
    for change in changes:
        if change.commit in parents and change.parent != parents[change.commit]:
            raise ValueError(f"run commit {change.commit} is not a child of {change.parent}")
        step = _Step(change, body_before=_body_start(texts, path))
        after = _applied(texts, change)
        _moves(step, texts, after)
        step.body_after = _body_start(after, path)
        steps.append(step)
        texts = after

    # The latest removal of each text, by a commit of the run, that nobody added back since.
    removals: dict[bytes, tuple[str, int]] = {}
    result: list[Entry] = []
    texts = at_base
    for k, step in enumerate(steps):
        commit = step.change.commit
        later = steps[k + 1 :]
        if commit in covered and commit in authors:
            replaced = list(_replaced(step, written, authors, base, later))
            result.extend(replaced)
            result.extend(_restored(step, removals, authors, later, replaced))
        moved_in = set(step.moved.values())
        for hunk in step.change.hunks:
            for offset, text in enumerate(hunk.added):
                if hunk.new_start + offset not in moved_in:
                    removals.pop(text, None)
        for hunk in step.change.hunks:
            for offset, text in enumerate(hunk.removed):
                line = hunk.old_start + offset
                if (
                    not _blank(text)
                    and line >= step.body_before
                    and line not in step.moved
                    and line not in step.ambiguous_removed
                ):
                    removals[text] = (commit, line)
        written = _written(written, step, commit)
        texts = _applied(texts, step.change)
        if step.ambiguous_texts:
            # Every line carrying an ambiguous text, as the worker marks it — the copy the diff
            # left in place included (ADR-0011).
            written = [
                replace(by, ambiguous=True) if texts[n] in step.ambiguous_texts else by
                for n, by in enumerate(written)
            ]
    if path != authorship.DOCUMENT_FILE:
        result = [replace(e, file=path) for e in result]
    return result


def _replaced(
    step: _Step,
    written: list[_Written],
    authors: dict[str, Hashable],
    base: str,
    later: list[_Step],
) -> Iterable[Entry]:
    """A `line` entry for each body line of another author of the run that the step's commit
    removed or replaced, without moving it."""
    commit = step.change.commit
    moved_in = set(step.moved.values())
    for hunk in step.change.hunks:
        after: str | None = None
        for offset, text in enumerate(hunk.removed):
            number = hunk.old_start + offset
            if (
                _blank(text)
                or number < step.body_before
                or number in step.moved
                or number in step.ambiguous_removed
            ):
                continue
            by = written[number - 1]
            writer = authors.get(by.commit)
            if by.commit == base or by.ambiguous or writer is None or writer == authors[commit]:
                continue
            if after is None:
                # The replacement is what the hunk added, less the lines moved into it.
                added = {
                    hunk.new_start + i
                    for i, added_text in enumerate(hunk.added)
                    if not _blank(added_text) and hunk.new_start + i not in moved_in
                }
                after = _range(_carry(added, later))
            yield Entry(
                kind="line",
                author=writer,
                author_version=by.commit,
                changing_version=commit,
                changer=authors[commit],
                range_before=str(by.line),
                range_after=after,
            )


def _restored(
    step: _Step,
    removals: dict[bytes, tuple[str, int]],
    authors: dict[str, Hashable],
    later: list[_Step],
    replaced: list[Entry],
) -> Iterable[Entry]:
    """A `restored` entry for each body line the step's commit added that an earlier version of the
    run, by another author, removed without moving it — unless the same act is already disclosed
    as that author's replaced line."""
    commit = step.change.commit
    moved_in = set(step.moved.values())
    disclosed = {(entry.author, entry.author_version) for entry in replaced}
    for hunk in step.change.hunks:
        for offset, text in enumerate(hunk.added):
            number = hunk.new_start + offset
            if (
                _blank(text)
                or number < step.body_after
                or number in moved_in
                or number in step.ambiguous_added
                or text not in removals
            ):
                continue
            remover, before = removals[text]
            if authors.get(remover) in (None, authors[commit]):
                continue
            if (authors[remover], remover) in disclosed:
                continue
            yield Entry(
                kind="restored",
                author=authors[remover],
                author_version=remover,
                changing_version=commit,
                changer=authors[commit],
                range_before=str(before),
                range_after=_range(_carry({number}, later)),
            )


def _carry(lines: set[int], later: Iterable[_Step]) -> set[int]:
    """`lines` of one version, followed through the hunks of each later version to the last: a
    moved line to where it moved, a line inside a hunk's removed range to the hunk's new range,
    any other shifted by the hunks before it."""
    for step in later:
        carried: set[int] = set()
        for number in lines:
            carried |= _through(number, step)
        lines = carried
    return lines


def _through(number: int, step: _Step) -> set[int]:
    if number in step.moved:
        return {step.moved[number]}
    shift = 0
    for hunk in step.change.hunks:
        removed = len(hunk.removed)
        if removed and hunk.old_start <= number < hunk.old_start + removed:
            return set(range(hunk.new_start, hunk.new_start + len(hunk.added)))
        # With nothing removed, `old_start` is the line the hunk's lines follow.
        if hunk.old_start + max(removed, 1) - 1 < number:
            shift += len(hunk.added) - removed
    return {number + shift}


def _range(lines: set[int]) -> str:
    """`"n"`, `"n-m"` spanning the lines, or `""` for none."""
    if not lines:
        return ""
    first, last = min(lines), max(lines)
    return str(first) if first == last else f"{first}-{last}"


def touched(repo: Any, run: Sequence[RunCommit]) -> list[str]:
    """Every appendix file a commit of the run changed, in its number's order."""
    found: set[str] = set()
    for commit in run:
        diff = repo.diff(repo.get(commit.parent), repo.get(commit.sha))
        for patch in diff:
            for path in (patch.delta.old_file.path, patch.delta.new_file.path):
                if path.startswith("appendices/") and path.endswith(".md"):
                    found.add(path)
    return sorted(found, key=lambda p: int(p.removeprefix("appendices/").removesuffix(".md")))


# What each kind of part operation sets of a part's state: its presence, its file, its title.
SETS = {
    "added": ("presence", "file", "title"),
    "removed": ("presence", "file", "title"),
    "replaced": ("file",),
    "renamed": ("title",),
}


def part_entries(base: Any, versions: Sequence[Any], covered: Collection[str]) -> list[Entry]:
    """The part entries of the run: walking its versions oldest first, each part's presence, file
    and title carried with the version that last set it in the run — none for the base's — and,
    for each covered version, one entry per other author's version that set what it changed. A
    reorder sets nothing and generates nothing."""
    from documents.parts import lists_at, part_operations

    set_by: dict[tuple[str, int, str], Any] = {}
    result: list[Entry] = []
    before = lists_at(base)
    for version in versions:
        after = lists_at(version)
        changed: dict[tuple[str, int], set[str]] = {}
        for operation in part_operations(before, after):
            if operation.number is not None:
                key = (operation.kind, operation.number)
                changed.setdefault(key, set()).update(SETS[operation.change])
        for (kind, number), attributes in sorted(changed.items()):
            setters = {
                setter.commit_sha: setter
                for attribute in sorted(attributes)
                if (setter := set_by.get((kind, number, attribute))) is not None
            }
            for setter in setters.values():
                if version.commit_sha not in covered or setter.author_id == version.author_id:
                    continue
                result.append(
                    Entry(
                        kind="part_operation",
                        author=setter.author_id,
                        author_version=setter.commit_sha,
                        changing_version=version.commit_sha,
                        changer=version.author_id,
                        range_before="",
                        range_after="",
                        part=f"appendices/{number}.md"
                        if kind == "appendix"
                        else f"attachments/{number}",
                    )
                )
            for attribute in attributes:
                set_by[(kind, number, attribute)] = version
        before = after
    return result


def compute(acceptance: Any) -> list[Any]:
    """The correction notices of `acceptance`, written once: one `CORRECTION_NOTICE` per author,
    a `CORRECTION_LINE` per entry, one `NOTIFICATION` per notice, one `accepted` notification to
    each author of the run but the reviewer who can still open the document, and
    `notices_computed_at` set in the same transaction — so an acceptance with no notice is told
    from one never computed.
    Idempotent: computed again, it writes nothing and returns what is there. The versions covered
    are the run's `reviewer_edit` versions and the acceptor's own, whatever their kind
    (ADR-0014)."""
    from django.db import connection, transaction
    from django.utils import timezone

    from access.rights import readable
    from documents import gitstore
    from documents.models import Version, VersionKind
    from identity.models import User
    from notifications.models import Category, Event
    from notifications.services import notify, others
    from review import services
    from review.models import Acceptance, CorrectionLine, CorrectionNotice
    from tenancy.schemas import current_tenant

    if acceptance.notices_computed_at is not None:
        return list(acceptance.notices.all())
    document = acceptance.version.document
    tenant_number = current_tenant(connection)
    if tenant_number is None:
        raise RuntimeError("notices are computed inside a tenant's schema")
    repo = gitstore.open_repository(tenant_number, document.number)
    base = acceptance.accepted_from
    accepted = services.accepted_content_version(acceptance)
    versions = services.run(document, since=base, head=accepted.commit_sha)
    run = [
        RunCommit(
            version.commit_sha,
            str(gitstore.commit_at(repo, version.commit_sha).parents[0].id),
            version.author_id,
        )
        for version in versions
    ]
    covered = {
        version.commit_sha
        for version in versions
        if version.kind == VersionKind.REVIEWER_EDIT or version.author_id == acceptance.reviewer_id
    }
    path = gitstore.repository_path(tenant_number, document.number)
    found = entries(path, base=base.commit_sha, run=run, covered=covered)
    at_base = {
        f"appendices/{name}" for name in gitstore.listing(repo, "appendices", base.commit_sha)
    }
    for appendix in touched(repo, run):
        found += entries(
            path,
            base=base.commit_sha,
            run=run,
            covered=covered,
            path=appendix,
            from_empty=appendix not in at_base,
        )
    found += part_entries(base, versions, covered)
    by_sha = {v.commit_sha: v for v in Version.objects.filter(document=document)}
    by_author: dict[Any, list[Entry]] = {}
    for entry in found:
        by_author.setdefault(entry.author, []).append(entry)
    authors = User.objects.in_bulk(list(by_author))
    with transaction.atomic():
        locked = Acceptance.objects.select_for_update().get(pk=acceptance.pk)
        if locked.notices_computed_at is not None:
            return list(locked.notices.all())
        now = timezone.now()
        notices = []
        for author, listed in by_author.items():
            notice = CorrectionNotice.objects.create(acceptance=locked, author_id=author, at=now)
            CorrectionLine.objects.bulk_create(
                CorrectionLine(
                    notice=notice,
                    changing_version=by_sha[entry.changing_version],
                    entry=entry.kind,
                    author_version=by_sha[entry.author_version],
                    file=entry.file,
                    part=entry.part,
                    range_before=entry.range_before,
                    range_after=entry.range_after,
                )
                for entry in listed
            )
            # No actor: the acceptor may be an author whose line a reviewer's version replaced;
            # each entry already leaves out its own changer (ADR-0014).
            notify(
                users=[authors[author]],
                category=Category.DOCUMENT,
                event=Event.CORRECTION_NOTICE,
                document=document,
                version=locked.version,
                correction_notice=notice,
                at=now,
            )
            notices.append(notice)
        # The run's authors told it was accepted, once, with the notices: whichever path
        # finishes the acceptance — the act, the next writer, the reconciler — tells them, at
        # the acceptance's own time, and only those who can still open the document.
        reviewer = User.objects.get(pk=locked.reviewer_id)
        notify(
            users=[
                author
                for author in others({version.author_id for version in versions}, reviewer)
                if document.pk in readable(author, [document.pk])
            ],
            category=Category.DOCUMENT,
            event=Event.ACCEPTED,
            actor=reviewer,
            document=document,
            version=locked.version,
            facts={"accepted": locked.number},
            at=locked.at,
        )
        locked.notices_computed_at = now
        locked.save(update_fields=["notices_computed_at"])
        acceptance.notices_computed_at = now
    return notices


def counted(notice: Any) -> str:
    """How much a notice holds, as its list line and its page say it: its lines and its parts
    counted apart, a count of none left out (DL-0480)."""
    from django.utils.translation import gettext, ngettext

    from review.models import CorrectionLine
    from review.models import Entry as Kind

    rows = CorrectionLine.objects.filter(notice=notice)
    parts = rows.filter(entry=Kind.PART_OPERATION).count()
    lines = rows.count() - parts
    said = [
        ngettext("%(count)s line", "%(count)s lines", lines) % {"count": lines} if lines else "",
        ngettext("%(count)s part", "%(count)s parts", parts) % {"count": parts} if parts else "",
    ]
    if all(said):
        return gettext("%(lines)s and %(parts)s") % {"lines": said[0], "parts": said[1]}
    return said[0] or said[1]
