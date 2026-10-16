"""The reversal of versions of a run (ADR-0015, DL-0243, DL-0380): for the versions a reviewer
undoes — one version, or every version of one author — what reverts cleanly against the run's
last commit, the head, and what a later version built on and is listed for the reviewer to edit by
hand. Nothing is removed from history; `apply` merges the result into the reviewer's draft.

`prepare` reads the document's repository — the file at the base and the run's `-U0` log — and
walks the run forward with the correction notice's walk (`review.notices`), carrying for every
line who wrote it: the commit and the line's number there, moves followed by the platform's rule
(ADR-0011). That identity is stable across later commits, so an undone version's line is found at
the head wherever it moved, and `reverse` answers from memory for any set of the run's versions.
The frontmatter is never reverted and blank lines are never classified; a line is never re-split
(ASR-20).
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import pygit2

from editing import authorship
from editing.markdown import load_spec
from review.notices import _applied, _body_start, _carry, _moves, _Step, _Written, _written


@dataclass(frozen=True)
class Classified:
    """One non-blank body line an undone version added or removed. `line` is its number in that
    version for an `added` line, in its parent for a `removed` one; `listed` is false for every
    clean line, and for a built-on added line a later version deleted (DL-0422)."""

    version: str
    side: str
    line: int
    text: str
    verdict: str
    listed: bool


@dataclass(frozen=True)
class Listed:
    """One place a later version built on, for the reviewer to edit by hand. `where` is the
    head's number of its first line there, or of the line it would follow — the frontmatter's last
    line, or 0 without one, for the top of the body; `before` the text the undone versions replaced
    there, `""` where they only added; `after` the head's text there, `""` where nothing stands."""

    where: int
    before: str
    after: str
    # What the undone versions wrote there, lines joined by "\n"; "" where they only removed.
    wrote: str = ""


@dataclass(frozen=True)
class Reversal:
    """The reversal of a set of versions against `head`. `body` is the whole of `document.md` at
    the head with `removed` (head line numbers) taken out and `inserted` (head line number → the
    lines restored after it, 0 for before the first) put in; `head_text` the head's own file, to
    which the line numbers refer."""

    head: str
    body: str
    removed: frozenset[int]
    inserted: dict[int, tuple[str, ...]]
    listed: tuple[Listed, ...]
    classified: tuple[Classified, ...]
    head_text: str = ""


CLEAN = "clean"
BUILT_ON = "built_on"


@dataclass
class _Version:
    """One commit of the run as `reverse` needs it: its step, and the file and its writers at its
    parent. `removed` holds the parent's lines it removed, its moves aside."""

    step: _Step
    texts: list[bytes]
    written: list[_Written]
    removed: frozenset[int]

    @property
    def commit(self) -> str:
        return self.step.change.commit


@dataclass
class _Place:
    """One hunk of an undone version, followed to the head."""

    version: int
    hunk: int
    verdicts: list[str] = field(default_factory=list)
    listed: bool = False
    # Head lines the reversal takes out for this place's non-blank added lines.
    taken: set[int] = field(default_factory=set)
    blank_added: list[int] = field(default_factory=list)
    missing_blanks: int = 0
    # The added lines left for the reviewer: what the undone version wrote that still stands
    # changed by a later one.
    wrote: list[str] = field(default_factory=list)

    @property
    def whole(self) -> bool:
        return bool(self.verdicts) and all(verdict == CLEAN for verdict in self.verdicts)


@dataclass
class _Region:
    """The parent's lines between two neighbours an undone version did not remove: the places of
    that version inside it, and the non-blank lines it restores there."""

    places: list[_Place] = field(default_factory=list)
    restored: set[int] = field(default_factory=set)


def _blank(text: bytes) -> bool:
    return not text.strip()


def _checked(sha: str) -> str:
    if not isinstance(sha, str) or not authorship.SHA.fullmatch(sha):
        raise ValueError(f"not a commit id: {sha!r}")
    return sha


class Prepared:
    """A run walked once, from its base to `head`; `reverse` answers from it without git."""

    def __init__(
        self,
        head: str,
        versions: list[_Version],
        texts: list[bytes],
        written: list[_Written],
        removed_by: dict[tuple[str, int], tuple[int, int]],
    ) -> None:
        self._head = head
        self._versions = versions
        self._index = {version.commit: k for k, version in enumerate(versions)}
        self._texts = texts
        self._written = written
        self._body = _body_start(texts)
        self._at = {(by.commit, by.line): n for n, by in enumerate(written, 1)}
        # Which version, and which of its hunks, removed each line identity that is gone.
        self._removed_by = removed_by

    @property
    def versions(self) -> frozenset[str]:
        """The run's commits that change `document.md`: the versions `reverse` can undo."""
        return frozenset(self._index)

    def reverse(self, undone: Collection[str]) -> Reversal:
        """The reversal of the `undone` versions of the run, taken together: a line one of them
        wrote and another later changed is their own business, never built on. `ValueError` for an
        empty set or a commit that is not a version of the run changing `document.md`."""
        chosen = set(undone)
        if not chosen or any(commit not in self._index for commit in chosen):
            raise ValueError("undo needs one or more versions of the run")
        return _Reversing(self, chosen).result()


class _Reversing:
    """One call of `reverse`: the classification first, then the restored lines, then the blank
    lines a reverted paragraph leaves doubled."""

    def __init__(self, prepared: Prepared, chosen: set[str]) -> None:
        self.p = prepared
        self.chosen = chosen
        self.classified: list[Classified] = []
        self.listed: list[Listed] = []
        self.removed: set[int] = set()
        self.inserted: dict[int, list[bytes]] = {}
        self.places: list[_Place] = []
        self.regions: dict[tuple[int, int, int], _Region] = {}

    # The head, and the anchors of a version's parent lines there.

    def standing(self, by: _Written) -> int | None:
        """The head line carrying the identity `by`, unless gone or ambiguous there."""
        at = self.p._at.get((by.commit, by.line))
        if at is None or self.p._written[at - 1].ambiguous:
            return None
        return at

    def anchor(self, version: _Version, line: int) -> int | None:
        """The head line standing for line `line` of the version's parent; the top of the body is
        the line before it, the end the line after the file's last."""
        if line == 0:
            return self.p._body - 1
        if line > len(version.texts):
            return len(self.p._texts) + 1
        return self.standing(version.written[line - 1])

    def neighbours(self, version: _Version, first: int, last: int) -> tuple[int, int]:
        """The nearest non-blank body line of the parent above `first` and below `last` that the
        version did not remove; 0 and one past the end where there is none."""
        texts, body = version.texts, version.step.body_before
        above = first - 1
        while above >= body and (_blank(texts[above - 1]) or above in version.removed):
            above -= 1
        below = last + 1
        while below <= len(texts) and (_blank(texts[below - 1]) or below in version.removed):
            below += 1
        return (above if above >= body else 0), below

    def clean_between(self, a: int | None, b: int | None) -> bool:
        if a is None or b is None or a >= b:
            return False
        for n in range(a + 1, b):
            by = self.p._written[n - 1]
            if not _blank(self.p._texts[n - 1]) and (by.commit not in self.chosen or by.ambiguous):
                return False
        return True

    # Classification.

    def result(self) -> Reversal:
        for k, version in enumerate(self.p._versions):
            if version.commit in self.chosen:
                for index in range(len(version.step.change.hunks)):
                    self.place(k, index)
        for (k, above, below), region in self.regions.items():
            self.restore(self.p._versions[k], above, below, region)
        for place in self.places:
            if place.whole and place.missing_blanks:
                self.close_up(place)
        return self.reversal()

    def place(self, k: int, index: int) -> None:
        version = self.p._versions[k]
        step = version.step
        hunk = step.change.hunks[index]
        commit = version.commit
        place = _Place(k, index)
        moved_in = set(step.moved.values())
        removed = [
            hunk.old_start + offset
            for offset in range(len(hunk.removed))
            if hunk.old_start + offset >= step.body_before
            and hunk.old_start + offset not in step.moved
            and hunk.old_start + offset not in step.ambiguous_removed
        ]
        region: _Region | None = None
        clean = False
        if removed:
            above, below = self.neighbours(version, removed[0], removed[-1])
            region = self.regions.setdefault((k, above, below), _Region())
            region.places.append(place)
            clean = self.clean_between(self.anchor(version, above), self.anchor(version, below))
        before: list[str] = []
        for r in removed:
            text = version.texts[r - 1]
            if _blank(text):
                continue
            by = version.written[r - 1]
            if by.commit in self.chosen and not by.ambiguous:
                # The undone versions' own text goes as a whole: nothing is restored.
                self.classify(place, commit, "removed", r, text, CLEAN, False)
                continue
            before.append(text.decode())
            if region is not None and clean and not by.ambiguous:
                region.restored.add(r)
                self.classify(place, commit, "removed", r, text, CLEAN, False)
            else:
                self.classify(place, commit, "removed", r, text, BUILT_ON, True)
        for offset, text in enumerate(hunk.added):
            n = hunk.new_start + offset
            if n < step.body_after or n in moved_in or n in step.ambiguous_added:
                continue
            if _blank(text):
                place.blank_added.append(n)
                continue
            self.added(place, commit, n, text)
        if place.whole:
            self.blank_lines(place, commit)
        if place.listed:
            self.listed.append(self.listing(k, hunk, before, place.wrote))
        self.places.append(place)

    def added(self, place: _Place, commit: str, n: int, text: bytes) -> None:
        at = self.p._at.get((commit, n))
        if at is not None:
            if self.p._written[at - 1].ambiguous:
                self.classify(place, commit, "added", n, text, BUILT_ON, True)
            else:
                self.removed.add(at)
                place.taken.add(at)
                self.classify(place, commit, "added", n, text, CLEAN, False)
            return
        j, index = self.p._removed_by[(commit, n)]
        later = self.p._versions[j]
        if later.commit in self.chosen:
            self.classify(place, commit, "added", n, text, CLEAN, False)
            return
        # Listed unless the later version removed it and wrote nothing new in its place
        # (DL-0422): a line moved into that place is not new.
        hunk = later.step.change.hunks[index]
        moved_in = set(later.step.moved.values())
        replacing = {
            hunk.new_start + i
            for i, added in enumerate(hunk.added)
            if not _blank(added) and hunk.new_start + i not in moved_in
        }
        # Listed only while something of the replacement stands at the head: a chain rewritten
        # and then deleted leaves nothing to edit (DL-0422).
        later_steps = [v.step for v in self.p._versions[j + 1 :]]
        stands = any(self.theirs_not(h) for h in _carry(replacing, later_steps))
        self.classify(place, commit, "added", n, text, BUILT_ON, stands)

    def classify(
        self,
        place: _Place,
        commit: str,
        side: str,
        line: int,
        text: bytes,
        verdict: str,
        listed: bool,
    ) -> None:
        place.verdicts.append(verdict)
        place.listed = place.listed or listed
        if side == "added" and listed:
            place.wrote.append(text.decode())
        self.classified.append(Classified(commit, side, line, text.decode(), verdict, listed))

    def blank_lines(self, place: _Place, commit: str) -> None:
        """A whole place's blank added lines go with it where they stand next to its other lines
        at the head; one a later version rewrote, around a move of the paragraph, is counted and
        taken from the blank lines left doubled there (`close_up`)."""
        for n in place.blank_added:
            at = self.p._at.get((commit, n))
            if (
                at is not None
                and place.taken
                and min(place.taken) - 1 <= at <= max(place.taken) + 1
            ):
                self.removed.add(at)
            else:
                place.missing_blanks += 1

    def listing(self, k: int, hunk: Any, before: list[str], wrote: list[str]) -> Listed:
        """The place's entry: its text before, and what stands in its place at the head — the
        lines it added, carried through every later version to the head (`notices._carry`); for a
        place that only removed, the head's lines between the nearest lines around it that stand
        there in order. Lines the undone versions wrote are theirs to take out, never listed."""
        version = self.p._versions[k]
        added = {
            hunk.new_start + i
            for i, text in enumerate(hunk.added)
            if not _blank(text) and hunk.new_start + i >= version.step.body_after
        }
        if added:
            later = [v.step for v in self.p._versions[k + 1 :]]
            carried = sorted(_carry(added, later))
            there = [n for n in carried if self.theirs_not(n)]
            first = carried[0] if carried else self.p._body - 1
            return Listed(
                where=there[0] if there else first,
                before="\n".join(before),
                after="\n".join(self.p._texts[n - 1].decode() for n in there),
                wrote="\n".join(wrote),
            )
        return self.between(version, hunk.old_start, len(hunk.removed), before)

    def theirs_not(self, n: int) -> bool:
        """Whether head line `n` is text a reviewer reads in the place: not blank, and not
        written by a version being undone."""
        if n < 1 or n > len(self.p._texts) or _blank(self.p._texts[n - 1]):
            return False
        return self.p._written[n - 1].commit not in self.chosen

    def between(self, version: _Version, start: int, count: int, before: list[str]) -> Listed:
        if count:
            above, below = self.neighbours(version, start, start + count - 1)
        else:
            # With nothing removed, `start` is the line the hunk's lines follow.
            above, below = self.neighbours(version, start + 1, start)
        a = self.anchor(version, above)
        while a is None:
            above, _ = self.neighbours(version, above, above)
            a = self.anchor(version, above)
        b = self.anchor(version, below)
        while b is None or b <= a:
            _, below = self.neighbours(version, below, below)
            b = self.anchor(version, below)
        there = [n for n in range(a + 1, b) if self.theirs_not(n)]
        return Listed(
            where=there[0] if there else a,
            before="\n".join(before),
            after="\n".join(self.p._texts[n - 1].decode() for n in there),
        )

    # Applying.

    def restore(self, version: _Version, above: int, below: int, region: _Region) -> None:
        """Put back the region's restored lines between its neighbours, in the parent's order.
        The head's blank lines there stand for the parent's that the version kept; a region whose
        every place is whole gets the parent's blank lines back too, never two in a row."""
        whole = all(place.whole for place in region.places)
        if not region.restored and not whole:
            return
        a, b = self.anchor(version, above), self.anchor(version, below)
        if a is None or b is None or not self.clean_between(a, b):
            return
        step = version.step
        first = above + 1 if above else step.body_before
        wanted: list[bytes] = []
        for r in range(first, below):
            text = version.texts[r - 1]
            if r not in version.removed:
                wanted.append(text)
            elif r in region.restored:
                wanted.append(text)
            elif (
                whole
                and _blank(text)
                and r not in step.ambiguous_removed
                and version.written[r - 1].commit not in self.chosen
            ):
                wanted.append(text)
        if whole:
            wanted = [
                text
                for i, text in enumerate(wanted)
                if not (_blank(text) and i and _blank(wanted[i - 1]))
            ]
        blanks = [n for n in range(a + 1, b) if n not in self.removed]
        at, used = a, 0
        for text in wanted:
            if _blank(text):
                if used < len(blanks):
                    at = blanks[used]
                    used += 1
                    continue
                if not whole:
                    continue
            self.inserted.setdefault(at, []).append(text)
        if whole:
            self.removed.update(blanks[used:])

    def close_up(self, place: _Place) -> None:
        """Take out a blank line the place added and the head no longer carries: one of the two
        its reverted lines leave side by side, or the one they leave at the end."""
        texts, last = self.p._texts, len(self.p._texts)
        for n in sorted(place.taken):
            if not place.missing_blanks:
                return
            low, high = n, n
            while low - 1 in self.removed:
                low -= 1
            while high + 1 in self.removed:
                high += 1
            if any(self.inserted.get(at) for at in range(low - 1, high + 1)):
                continue
            prev_blank = low - 1 >= self.p._body and _blank(texts[low - 2])
            next_blank = high + 1 <= last and _blank(texts[high])
            if next_blank and (prev_blank or low - 1 < self.p._body):
                self.removed.add(high + 1)
            elif prev_blank and high == last:
                self.removed.add(low - 1)
            else:
                continue
            place.missing_blanks -= 1

    def reversal(self) -> Reversal:
        texts = self.p._texts
        out = list(self.inserted.get(0, []))
        for n, text in enumerate(texts, 1):
            if n not in self.removed:
                out.append(text)
            out.extend(self.inserted.get(n, []))
        body = b"".join(text + b"\n" for text in out)
        listed: list[Listed] = []
        for entry in sorted(self.listed, key=lambda entry: entry.where):
            if entry not in listed:
                listed.append(entry)
        return Reversal(
            head=self.p._head,
            body=body.decode(),
            removed=frozenset(self.removed),
            inserted={
                at: tuple(text.decode() for text in lines)
                for at, lines in sorted(self.inserted.items())
                if lines
            },
            listed=tuple(listed),
            classified=tuple(self.classified),
            head_text=b"".join(text + b"\n" for text in texts).decode(),
        )


def prepare(repository_path: Path, *, base: str, head: str) -> Prepared:
    """Read the run from `base` to `head` once and walk it forward. `ValueError` for a sha that is
    not 40 lowercase hex characters; `authorship.AuthorshipError` passes through."""
    _checked(base)
    _checked(head)
    texts = authorship.file_at(repository_path, base)
    changes = authorship.changes(repository_path, authorship.DOCUMENT_FILE, base, head)
    written = [_Written(base, n) for n in range(1, len(texts) + 1)]
    versions: list[_Version] = []
    removed_by: dict[tuple[str, int], tuple[int, int]] = {}
    for change in changes:
        step = _Step(change, body_before=_body_start(texts))
        after = _applied(texts, change)
        _moves(step, texts, after)
        step.body_after = _body_start(after)
        removed: set[int] = set()
        for index, hunk in enumerate(change.hunks):
            for offset in range(len(hunk.removed)):
                number = hunk.old_start + offset
                if number not in step.moved:
                    removed.add(number)
                    by = written[number - 1]
                    removed_by[(by.commit, by.line)] = (len(versions), index)
        versions.append(_Version(step, texts, written, frozenset(removed)))
        written = _written(written, step, change.commit)
        texts = after
        if step.ambiguous_texts:
            # Every line carrying an ambiguous text, as `notices.entries` marks it (ADR-0011).
            written = [
                replace(by, ambiguous=True) if texts[n] in step.ambiguous_texts else by
                for n, by in enumerate(written)
            ]
    return Prepared(head, versions, texts, written, removed_by)


# --- the reviewer's act: the reversal typed into their own draft ----------------------------------

# The draft's key for the undo: the versions undone into it, and the places left for the holder's
# hand (DL-0380).
UNDO = "undo"


class UndoRefused(Exception):
    """An undo the document's state does not allow; `reason` names why: `not_a_reviewer`,
    `reserved` (DL-0224), `held` — someone else holds the document — `draft_kept` — the reviewer
    has a kept draft to take back or discard first — `nothing_to_undo`, or `too_large`, a draft
    the platform would not hold (DL-0329)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _undone(pending: list[Any], version: Any, author: Any) -> list[Any]:
    if version is not None:
        return [v for v in pending if v.pk == version.pk]
    return [v for v in pending if author is not None and v.author_id == author.pk]


def _undone_into(hold: Any) -> set[str]:
    """The versions already undone into the hold's draft."""
    from editing.models import Draft

    draft = Draft.objects.filter(hold=hold).first()
    if draft is None:
        return set()
    return set((draft.content.get(UNDO) or {}).get("undone", []))


def refusal(document: Any, reviewer: Any, *, version: Any = None, author: Any = None) -> str | None:
    """Why `reviewer` may not undo `version`, or every version of `author`, in the pending run
    now; `None` when they may. A reservation stops it whoever holds it, the reviewer's own
    included (DL-0224); someone else's hold, and a kept draft of the reviewer's own, stop it too;
    so do versions already undone into the reviewer's draft. With neither `version` nor `author`,
    what stops every undo — the controls' reason."""
    from access.rights import Right, rights_on
    from editing.holds import open_hold, preserved_draft
    from review.services import run

    if Right.ACCEPT not in rights_on(reviewer, document):
        return "not_a_reviewer"
    hold = open_hold(document)
    if hold is not None and hold.reserved_at is not None:
        return "reserved"
    if hold is not None and hold.user_id != reviewer.pk:
        return "held"
    if hold is None and preserved_draft(document, reviewer) is not None:
        return "draft_kept"
    if version is None and author is None:
        return None
    wanted = {v.commit_sha for v in _undone(run(document), version, author)}
    if not wanted or (hold is not None and wanted <= _undone_into(hold)):
        return "nothing_to_undo"
    return None


def plan(
    document: Any,
    *,
    version: Any = None,
    author: Any = None,
    already: Collection[str] = (),
) -> tuple[str, Reversal]:
    """The reversal of `version`, or of every version of `author`, in the pending run — together
    with the versions `already` undone into the draft — against the head (ADR-0015); and the text
    the draft was last derived from: the reversal of `already` alone, or the head's file. A second
    undo is merged from the first, so nothing is typed in twice. `UndoRefused` with
    `nothing_to_undo` when the asked versions change no text."""
    from documents import gitstore
    from editing.holds import tenant_number
    from review.services import base, run

    number = tenant_number()
    repo = gitstore.open_repository(number, document.number)
    head = gitstore.head(repo)
    asked = {v.commit_sha for v in _undone(run(document), version, author)}
    if head is None or not asked:
        raise UndoRefused("nothing_to_undo")
    path = gitstore.repository_path(number, document.number)
    prepared = prepare(path, base=base(document).commit_sha, head=head)
    new = (asked - set(already)) & prepared.versions
    if not new or not prepared.reverse(new).classified:
        raise UndoRefused("nothing_to_undo")
    earlier = set(already) & prepared.versions
    derived_from = (
        prepared.reverse(earlier).body
        if earlier
        else gitstore.read(repo, "document.md", head).decode("utf-8")
    )
    return derived_from, prepared.reverse(new | earlier)


def _frontmatter_changed(document: Any, versions: list[Any]) -> bool:
    """Whether any of `versions` changed `document.md`'s frontmatter — a title, a part — which an
    undo of text leaves standing (part operations revert through the parts' own controls)."""
    from documents import bundle, gitstore
    from editing.holds import tenant_number

    repo = gitstore.open_repository(tenant_number(), document.number)
    for version in versions:
        commit = gitstore.commit_at(repo, version.commit_sha)
        if not commit.parents:
            continue
        before = gitstore.read(repo, "document.md", str(commit.parents[0].id)).decode("utf-8")
        after = gitstore.read(repo, "document.md", version.commit_sha).decode("utf-8")
        if bundle.parse(before)[0] != bundle.parse(after)[0]:
            return True
    return False


def _stage_images(repo: Any, draft: Any, head: str | None, undone: Collection[str]) -> None:
    """Every image the draft's texts reference that neither the head's tree nor the draft's rows
    hold, staged from the newest of the undone versions and the versions they were written on
    that holds it — an image an undone edit had removed comes back with the text that shows it
    (DL-0439), and nothing the undone run never showed is read."""
    import hashlib

    from django.utils import timezone

    from documents import gitstore, images
    from editing.models import DraftFile, DraftFileKind, DraftFileOperation
    from editing.services import draft_texts

    if head is None:
        return
    in_tree = {f"{images.FOLDER}/{name}" for name in gitstore.listing(repo, images.FOLDER, head)}
    staged = set(draft.files.filter(kind=DraftFileKind.IMAGE).values_list("path", flat=True))
    wanted = [
        reference.src
        for reference in images.referenced(draft_texts(draft, repo, head))
        if images.is_image_path(reference.src)
        and reference.src not in in_tree
        and reference.src not in staged
    ]
    if not wanted:
        return
    sources = set(undone)
    for sha in undone:
        sources.update(str(parent.id) for parent in gitstore.commit_at(repo, sha).parents)
    newest_first = [c for c in list(gitstore.history(repo))[::-1] if str(c.id) in sources]
    for path in dict.fromkeys(wanted):
        for commit in newest_first:
            try:
                entry = commit.tree[path]
            except KeyError:
                continue
            data = entry.peel(pygit2.Blob).data
            DraftFile.objects.create(
                draft=draft,
                kind=DraftFileKind.IMAGE,
                path=path,
                operation=DraftFileOperation.ADD,
                content=data,
                file_name=path.rsplit("/", 1)[-1],
                sha256=hashlib.sha256(data).hexdigest(),
                at=timezone.now(),
            )
            break


def apply(document: Any, reviewer: Any, *, version: Any = None, author: Any = None) -> Any:
    """Undo `version`, or every version of `author`, into the reviewer's draft (ADR-0015,
    DL-0243): the one they have open, else one opened for it — and only then, in the transaction
    that writes, so a refused undo leaves nobody holding the document. Under the organisation's
    and the membership's rows, then the document's writer lock with the record settled, then the
    document's, the hold's and the draft's rows: the reversal, computed against the head, is
    merged into the draft line by line — a line the draft changed is left and listed, never
    overwritten — and the places left for the reviewer's hand are kept beside the text in
    `content["undo"]`, never in it (DL-0380); the images the reversal brings back that the head
    lacks are staged in the draft (DL-0439). An open editor whose range changed is told it is
    stale at its next capture. Nothing is committed; finishing does that. Audited. Returns the
    hold; `UndoRefused` with the reason otherwise.

    The record is settled first, under the lock on its own and outside the act's transaction, so
    the rows a stop left underived are committed before the lock is let go (DL-0111); a head
    stopped again in between answers `RecordIncomplete` rather than settle inside a transaction
    that commits after the lock."""
    from django.db import connection, transaction
    from django.utils import timezone

    from audit.record import record
    from documents import gitstore
    from documents.locks import document_lock
    from documents.models import Document, Version
    from editing import holds
    from editing.models import Draft, Hold
    from identity.models import Membership
    from review.services import LOCK_WAIT_SECONDS, RecordIncomplete, run, settle_head
    from tenancy.models import Tenant

    refused = refusal(document, reviewer, version=version, author=author)
    if refused is not None:
        raise UndoRefused(refused)
    number = holds.tenant_number()
    with document_lock(number, document.number, timeout=LOCK_WAIT_SECONDS):
        settle_head(document)
    with transaction.atomic():
        # The order `holds.take` keeps: a block being written is waited for, then seen.
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM tenancy_tenant WHERE number = %s FOR SHARE", [number])
        list(
            Membership.objects.select_for_update(no_key=True, of=("self",)).filter(
                user=reviewer, tenant__number=number
            )
        )
        with document_lock(number, document.number, timeout=LOCK_WAIT_SECONDS):
            head = gitstore.head(gitstore.open_repository(number, document.number))
            if (
                head is not None
                and not Version.objects.filter(document=document, commit_sha=head).exists()
            ):
                raise RecordIncomplete("a commit the rows do not know")
            with transaction.atomic():
                locked = Document.objects.select_for_update(of=("self",)).get(pk=document.pk)
                refused = refusal(locked, reviewer, version=version, author=author)
                if refused is not None:
                    raise UndoRefused(refused)
                try:
                    hold = holds.hold_locked(locked, reviewer, number)
                except holds.HeldByOther as error:
                    raise UndoRefused("held") from error
                except holds.DraftPreserved as error:
                    raise UndoRefused("draft_kept") from error
                except (holds.NotEditable, holds.Frozen) as error:
                    raise UndoRefused("not_a_reviewer") from error
                hold = Hold.objects.select_for_update(of=("self",)).get(pk=hold.pk)
                draft = Draft.objects.select_for_update(of=("self",)).get(hold=hold)
                already = (draft.content.get(UNDO) or {}).get("undone", [])
                derived_from, reversal = plan(
                    locked, version=version, author=author, already=already
                )
                body, conflicts, applied = merge(derived_from, reversal, draft.content[holds.BODY])
                if len(body.encode("utf-8")) > load_spec().max_bytes:
                    raise UndoRefused("too_large")
                undone = _undone(run(locked), version, author)
                listed = [
                    {"before": e.before, "after": e.after, "wrote": e.wrote}
                    for e in reversal.listed
                ]
                listed += conflicts
                if _frontmatter_changed(locked, undone):
                    listed.append({"before": "", "after": "", "frontmatter": "kept"})
                # An earlier undo's places stay until the reviewer finishes or discards: a place
                # the draft had changed is not seen again by a merge from the derived text.
                earlier = (draft.content.get(UNDO) or {}).get("listed", [])
                listed = earlier + [place for place in listed if place not in earlier]
                draft.content = {
                    **draft.content,
                    holds.BODY: body,
                    UNDO: {
                        "version": version.commit_sha if version is not None else None,
                        "author": str(author.pk) if author is not None else None,
                        "undone": sorted(set(already) | {v.commit_sha for v in undone}),
                        "listed": listed,
                    },
                }
                draft.save(update_fields=["content", "updated_at"])
                _stage_images(
                    gitstore.open_repository(number, document.number),
                    draft,
                    head,
                    [v.commit_sha for v in undone],
                )
                Hold.objects.filter(pk=hold.pk).update(last_activity_at=timezone.now())
                record(
                    actor=reviewer,
                    action="document.undo_applied",
                    obj=locked,
                    before=None,
                    after={
                        "number": locked.number,
                        "version": version.commit_sha if version is not None else None,
                        "author": str(author.pk) if author is not None else None,
                        **applied,
                        "listed": len(listed),
                    },
                    tenant=Tenant.objects.get(number=number),
                )
    return hold


def merge(
    derived_from: str, reversal: Reversal, draft_body: str
) -> tuple[str, list[dict[str, str]], dict[str, int]]:
    """The draft with the undo merged in, line by line, three ways: what the reversal changes
    against the text the draft was derived from is applied where the draft still holds that text,
    and listed where the draft changed it — never overwritten (ADR-0015). Lines are taken out and
    put in whole, never re-split (ASR-20). Both alignments are the diff view's, bounded under the
    writer lock: a stretch too costly to align is one change, applied only where the draft holds it
    whole and listed otherwise. Returns the body, the places listed, and the non-blank lines taken
    out and put back."""
    from documents import bundle
    from editing.diffview import opcodes

    base = bundle.parse(derived_from)[1].splitlines(keepends=True)
    wanted = bundle.parse(reversal.body)[1].splitlines(keepends=True)
    draft = draft_body.splitlines(keepends=True)
    same: dict[int, int] = {}
    for op, b1, b2, d1, _d2 in opcodes(base, draft):
        if op == "equal":
            same.update({b1 + k: d1 + k for k in range(b2 - b1)})
    changes = [
        (b1, b2, wanted[w1:w2]) for op, b1, b2, w1, w2 in opcodes(base, wanted) if op != "equal"
    ]
    out = list(draft)
    listed: list[dict[str, str]] = []
    taken = put = 0
    for b1, b2, lines in reversed(changes):
        span = [same.get(b) for b in range(b1, b2)]
        held = all(d is not None for d in span) and span == list(
            range(span[0], span[0] + len(span)) if span and span[0] is not None else []
        )
        if b1 == b2:
            # An insertion: between two lines the draft keeps side by side, or at an end.
            above = same.get(b1 - 1) if b1 > 0 else -1
            below = same.get(b1) if b1 < len(base) else len(draft)
            held = above is not None and below is not None and below == above + 1
            at = (above + 1) if above is not None else 0
        else:
            at = span[0] if held and span[0] is not None else 0
        if held:
            out[at : at + (b2 - b1)] = lines
            taken += sum(1 for line in base[b1:b2] if line.strip())
            put += sum(1 for line in lines if line.strip())
            continue
        before = "".join(line for line in lines if line.strip()).strip("\n")
        wrote = "".join(line for line in base[b1:b2] if line.strip()).strip("\n")
        region = _draft_region(base, draft, same, b1, b2)
        if before or region:
            listed.append({"before": before, "after": region, "wrote": wrote})
    return "".join(out), listed[::-1], {"taken": taken, "put": put}


def _draft_region(base: list[str], draft: list[str], same: dict[int, int], b1: int, b2: int) -> str:
    """The draft's non-blank text where the base held lines `b1` to `b2`: between the nearest
    lines around them the draft keeps."""
    above = next((same[b] for b in range(b1 - 1, -1, -1) if b in same), -1)
    below = next((same[b] for b in range(b2, len(base)) if b in same), len(draft))
    return "".join(line for line in draft[above + 1 : below] if line.strip()).strip("\n")
