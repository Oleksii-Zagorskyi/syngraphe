"""Ending an editing session: finishing — the screen's content, and the commit that turns a draft
into a version (ADR-0003, DL-0222, DL-0261) — or discarding the draft, the holder's own or one
kept from an ended hold (DL-0180, DL-0381).

The commit is a write across both stores, under the document's writer lock throughout, in this
order: the git commit, which is the commit point; the version row and its caches, audited; the hold
released as finished; the draft deleted; the authorship asked of the worker. A stop after any step
leaves a state that is finished either way (DL-0318): by the holder's next *send for review*, which
resumes it, or by the reconciler, which derives the row, releases the hold whose draft is behind
an `edit` commit of its holder and holds nothing more, deletes a finished hold's draft, and asks
again for the head's authorship when it has none.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, NoReturn

import pygit2
from django.db import transaction

from access.rights import Right, rights_on
from audit.record import record
from documents import entities, gitstore, images, services
from documents.identity import identity_for
from documents.locks import document_lock
from documents.models import Document, DocumentState, Version
from editing import holds, numbering, parts, summary, tasks
from editing.diffview import render_changes
from editing.markdown.validator import Refusal, validate, validating_once
from editing.models import (
    Draft,
    DraftFileKind,
    DraftFileOperation,
    Hold,
    OpenEditor,
    ReleaseKind,
)
from editing.normalizer import (
    RULESET,
    Emptied,
    Lists,
    NormalizerDefect,
    TooLarge,
    normalize,
    trailer,
)
from tenancy.models import Tenant

if TYPE_CHECKING:
    from identity.models import User

logger = logging.getLogger(__name__)


class EditorsOpen(Exception):
    """An editor is still open on the draft; finishing or discarding waits for every one to
    close."""


class NothingChanged(Exception):
    """No path of the draft differs from the head's tree: there is no version to make."""


class InvalidSummary(ValueError):
    """The summary as the holder left it cannot be a commit's first line."""


class DraftRefused(Exception):
    """The draft holds text the whitelist refuses — typed in the source view — and is corrected
    there before it is shown as changes or committed; `appendix` the title of the appendix whose
    text it is, where it is one's."""

    def __init__(self, refusals: list[Refusal], appendix: str | None = None) -> None:
        super().__init__(refusals)
        self.refusals = refusals
        self.appendix = appendix


@dataclass(frozen=True, order=True)
class MissingImage(Refusal):
    """A reference to an image neither the tree nor the draft holds, in `file` at `line`."""

    file: str = holds.BODY


class MissingImages(DraftRefused):
    """The draft's texts reference images the document does not hold (DL-0439): each one named
    by its file and line, corrected in the source view before anything is committed."""


@dataclass(frozen=True, order=True)
class AppendixRefusal(Refusal):
    """A refusal in an appendix's text, `file` its path, at `line`."""

    file: str = holds.BODY


class AppendixHeading(DraftRefused):
    """An appendix's text does not start with its one level-1 heading, or holds a second one
    (ADR-0005): `title` the appendix's."""

    def __init__(self, title: str, file: str, line: int = 1) -> None:
        super().__init__([AppendixRefusal(line, "appendix-heading", file)], appendix=title)
        self.title = title


class PartRightLost(Exception):
    """The draft changes parts whose right its holder no longer holds (ADR-0007): `parts` their
    titles. Nothing is committed; the draft stays."""

    def __init__(self, parts: list[str]) -> None:
        super().__init__(parts)
        self.parts = parts


class InjectedFault(Exception):
    """Raised by `commit_draft` after the step a crash test names; never set in production."""


@dataclass(frozen=True)
class Finishing:
    """What the finishing screen shows: the changes, the drafted summary, the number to come, the
    roles, actions and terms the commit adds, relabels or removes, and the changed appendices and
    part operations."""

    changes: str
    summary: str
    number: str
    entities: list[ListedEntity] = field(default_factory=list)
    # The part changes partial's context: the appendices, the part operations, the frontmatter.
    parts: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ListedEntity:
    """An entity the draft changes against the head; `from_words` when it is declared at the
    commit from a span the draft marks without declaring it (DL-0440)."""

    kind: str
    key: str
    change: str
    before: str
    after: str
    from_words: bool = False


@dataclass(frozen=True)
class DraftDeclarations:
    """What the commit of a draft will declare — its own declarations, then each span its texts
    mark with a key they lack (DL-0440) — and every key a declaration or a span holds."""

    committed: list[entities.Declared]
    keys: set[str]


def draft_declarations(
    draft: Draft,
    repo: pygit2.Repository,
    head: str,
    document: Document,
    own: list[entities.Declared],
) -> DraftDeclarations:
    """The draft's declarations as the commit will write them, `own` its file's: the body read as
    the commit normalises it, so a span's words are the label the commit writes; while the
    whitelist refuses the body, as the draft holds it. Its texts are read once."""
    texts = list(draft_texts(draft, repo).values())
    body = texts[0]
    if not validate(body):
        _, head_body = holds.split(gitstore.read(repo, holds.BODY, head).decode("utf-8"))
        try:
            body = _normalised(head_body, body, _lists(document)).decode("utf-8")
        except (DraftRefused, NormalizerDefect):
            pass
    found = list(entities.spans(body, *texts[1:]))
    committed = entities.with_spans(own, found)
    return DraftDeclarations(
        committed, {e.key for e in committed} | {key for _, key, _ in found if key}
    )


def entity_changes(
    draft: Draft, repo: pygit2.Repository, head: str, normalised: str
) -> list[ListedEntity]:
    """What the commit of `draft` would change in `entities.yaml` against `head`: the draft's own
    declarations and those its spans will add, as the commit writes them (DL-0440)."""
    current = holds.entities_at(repo, head)
    held = holds.draft_entities(draft, repo, head)
    texts = draft_texts(draft, repo)
    declared = entities.declared_with(held, normalised, *list(texts.values())[1:])
    own = {(e.kind, e.key) for e in entities.parse(held)}
    return [
        ListedEntity(
            c.kind,
            c.key,
            c.change,
            c.before,
            c.after,
            from_words=c.change == "added" and (c.kind, c.key) not in own,
        )
        for c in entities.changes(current, declared)
    ]


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


_ONCE: ContextVar[dict[tuple[str, str, Lists], bytes] | None] = ContextVar(
    "normalised_once", default=None
)


@contextmanager
def normalising_once() -> Iterator[None]:
    """Within the block, the normalizer runs once for each head, body and lists, and each text is
    validated once: an edit tab that asks whether the draft holds edits and what it declares reads
    both from one pass over the draft, which is most of what opening it costs (ASR-21). Nothing
    outlives the block; an inner block shares the outer one's."""
    if _ONCE.get() is not None:
        yield
        return
    token = _ONCE.set({})
    try:
        with validating_once():
            yield
    finally:
        _ONCE.reset(token)


def _normalised(head_body: str, body: str, lists: Lists) -> bytes:
    """`body` normalised against the head; `DraftRefused` as too large when its stored form would
    pass the size the platform accepts (DL-0329)."""
    once = _ONCE.get()
    key = (head_body, body, lists)
    if once is not None and key in once:
        return once[key]
    try:
        normalised = normalize(head_body.encode(), body, lists)
    except TooLarge as error:
        raise DraftRefused([Refusal(1, "too-large")]) from error
    except Emptied as error:
        raise DraftRefused(error.refusals) from error
    if once is not None:
        once[key] = normalised
    return normalised


CONTENT_KINDS = (gitstore.Kind.EDIT, gitstore.Kind.REVIEWER_EDIT)


def _stopped(repo: pygit2.Repository, head: str, draft: Draft, user: User) -> str | None:
    """The sha of the holder's own content version — either kind (DL-0335) — committed from this
    draft by a finish that stopped before it released the hold, with nothing but acceptances and
    returns after it; else `None`. A head that does not descend from the draft's base — moved by
    a restore — never has one, as the reconciler reads it."""
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
        if kind in (gitstore.Kind.ACCEPTANCE, gitstore.Kind.RETURN):
            # A reviewer's decision on the run changes no text: the finish's version is below it.
            continue
        if kind in CONTENT_KINDS and commit.author.name == str(user.pk):
            return str(commit.id)
        return None
    return None


APPENDIX = re.compile(r"appendices/[1-9][0-9]*\.md")
# An attachment's place in the tree (ADR-0005): one name under `attachments/`.
ATTACHMENT = re.compile(r"attachments/[A-Za-z0-9][A-Za-z0-9._-]{0,99}")


def _data(value: Any) -> Any:
    """`value` as the draft's JSON holds it, so a mapping read from git compares with it."""
    return json.loads(json.dumps(value))


def _differs(repo: pygit2.Repository, commit: str, path: str, content: bytes | None) -> bool:
    try:
        existing: bytes | None = gitstore.read(repo, path, commit)
    except KeyError:
        existing = None
    return existing != content


def _appendix_order(path: str) -> int:
    return int(path.removeprefix("appendices/").removesuffix(".md"))


def staged_changes(
    draft: Draft, repo: pygit2.Repository, against: str, lists: Lists
) -> dict[str, bytes | None]:
    """Every path the draft changes against the tree of `against`, as `gitstore.commit` takes them:
    `document.md` when the normalised body or the frontmatter (as data) differs; `entities.yaml`
    with every undeclared span declared (DL-0440); `appendices/<n>.md` for each appendix the draft
    lists, validated, held to one level-1 heading and normalised against `against`'s text of it,
    and `None` for one the tree holds and the draft does not list; the staged attachments'
    operations; the images the texts reference and the tree lacks, and `None` for each the tree
    holds and no text references (DL-0439). Only entries whose bytes, or absence, differ from the
    tree; a change only to the declarations the commit adds for spans of text the tree already
    holds is no change. `DraftRefused` for a body or an appendix the whitelist refuses (its
    `appendix` the title) or a text or declarations past the size the platform accepts,
    `AppendixHeading` for an appendix out of its one-heading rule, `MissingImages` for a reference
    to an image neither the tree nor the draft holds, `NormalizerDefect` for a body that does not
    normalise, `ValueError` for a draft `entities.yaml` that does not read or a staged file out of
    its place."""
    body = _accepted(draft)
    frontmatter, against_body = holds.split(
        gitstore.read(repo, holds.BODY, against).decode("utf-8")
    )
    normalised = _normalised(against_body, body, lists).decode("utf-8")
    changes: dict[str, bytes | None] = {}
    held_frontmatter = draft.content[holds.FRONTMATTER]
    if normalised != against_body or _data(held_frontmatter) != _data(frontmatter):
        changes[holds.BODY] = holds.join(held_frontmatter, normalised).encode("utf-8")
    listed = _listed_appendices(held_frontmatter)
    for number, title in listed.items():
        changes[parts.appendix_key(number)] = _appendix(draft, repo, against, number, title, lists)
    for name in gitstore.listing(repo, "appendices", against):
        path = f"appendices/{name}"
        if APPENDIX.fullmatch(path) and _appendix_order(path) not in listed:
            changes[path] = None
    # Each staged row's path and kind are read first, and its bytes only where they are written.
    rows = list(draft.files.order_by("at").values_list("pk", "kind", "path", "operation"))
    attachments: dict[str, tuple[Any, str]] = {}
    for pk, kind, path, operation in rows:
        if kind == DraftFileKind.ATTACHMENT:
            if not ATTACHMENT.fullmatch(path):
                raise ValueError(f"a staged attachment outside attachments/: {path!r}")
            attachments[path] = (pk, operation)
    for path, (pk, operation) in attachments.items():
        if operation == DraftFileOperation.REMOVE:
            changes[path] = None
        else:
            changes[path] = _staged_bytes(draft, pk)

    # The texts the committed tree will hold, the body as the draft holds it, so a refusal's line
    # is the one the source view shows.
    texts = draft_texts(draft, repo)

    current = holds.entities_at(repo, against)
    held = holds.draft_entities(draft, repo, against)
    declared = entities.declared_with(held, normalised, *list(texts.values())[1:]).encode("utf-8")
    if len(declared) > entities.MAX_BYTES:
        raise DraftRefused([Refusal(1, "entities-full")])
    changes[holds.ENTITIES] = declared

    in_tree = {f"{images.FOLDER}/{name}" for name in gitstore.listing(repo, images.FOLDER, against)}
    staged = {
        path: pk
        for pk, kind, path, operation in rows
        if kind == DraftFileKind.IMAGE and operation != DraftFileOperation.REMOVE
    }
    wanted: set[str] = set()
    missing: list[Refusal] = []
    for reference in images.referenced(texts):
        if reference.src in in_tree or reference.src in staged:
            wanted.add(reference.src)
        else:
            missing.append(MissingImage(reference.line, "image-missing", reference.file))
    if missing:
        raise MissingImages(missing)
    for path in sorted(wanted - in_tree):
        content = _staged_bytes(draft, staged[path])
        name = path.removeprefix(f"{images.FOLDER}/")
        if not images.is_image_path(path) or hashlib.sha256(content).hexdigest() != name[:64]:
            raise ValueError(f"a staged image not at its content's name: {path!r}")
        changes[path] = content
    for path in sorted(in_tree - wanted):
        changes[path] = None
    changed = {
        path: content for path, content in changes.items() if _differs(repo, against, path, content)
    }
    if list(changed) == [holds.ENTITIES] and held == current:
        # Declaring spans of text the tree already holds rides on a commit and never makes one.
        return {}
    return changed


def _listed_appendices(frontmatter: dict[str, Any]) -> dict[int, str]:
    """The appendices a frontmatter lists, their titles by number, in its order."""
    return {int(e["number"]): str(e.get("title", "")) for e in frontmatter.get("appendices", [])}


def _one_heading(text: str) -> int | None:
    """The line breaking the one-heading rule — the text not starting with a level-1 heading, or a
    second one — or `None` when it holds."""
    from editing.markdown.parser import parser

    tokens = parser().parse(text)
    if not tokens or tokens[0].type != "heading_open" or tokens[0].tag != "h1":
        return 1
    for token in tokens[1:]:
        if token.type == "heading_open" and token.tag == "h1":
            return token.map[0] + 1 if token.map else 1
    return None


def _appendix(
    draft: Draft, repo: pygit2.Repository, against: str, number: int, title: str, lists: Lists
) -> bytes:
    """Appendix `number`'s text as the commit writes it: held to the whitelist and the one-heading
    rule, then normalised against `against`'s text of it, or the empty text where it holds none,
    within the size the platform accepts per file (DL-0329)."""
    key = parts.appendix_key(number)
    text = parts.appendix_text(draft, number, repo)
    refusals = validate(text)
    if refusals:
        raise DraftRefused([AppendixRefusal(r.line, r.code, key) for r in refusals], appendix=title)
    broken = _one_heading(text)
    if broken is not None:
        raise AppendixHeading(title, key, broken)
    try:
        current = gitstore.read(repo, key, against)
    except KeyError:
        current = b""
    try:
        return normalize(current, text, lists)
    except TooLarge as error:
        raise DraftRefused([AppendixRefusal(1, "too-large", key)], appendix=title) from error
    except Emptied as error:
        refused: list[Refusal] = [AppendixRefusal(r.line, r.code, key) for r in error.refusals]
        raise DraftRefused(refused, appendix=title) from error


def _staged_bytes(draft: Draft, pk: Any) -> bytes:
    content = draft.files.filter(pk=pk).values_list("content", flat=True).get()
    if content is None:
        raise ValueError("a staged file without its bytes")
    return bytes(content)


def draft_texts(draft: Draft, repo: pygit2.Repository) -> dict[str, str]:
    """The draft's texts as it holds them: its body, then every appendix its list holds — through
    `parts.appendix_text`, its own key or else the file at the draft's base — in its number's
    order. What its images are read from."""
    texts = {holds.BODY: str(draft.content.get(holds.BODY, ""))}
    for number in sorted(_listed_appendices(draft.content.get(holds.FRONTMATTER, {}))):
        texts[parts.appendix_key(number)] = parts.appendix_text(draft, number, repo)
    return texts


def holds_later_work(draft: Draft, repo: pygit2.Repository, commit: str, lists: Lists) -> bool:
    """Whether the draft holds anything `commit` does not — text, entities, appendices or files.
    A draft that cannot be committed as it stands is later work too: it is kept, never released
    as finished. Never raises: a release that asks must go ahead whatever the draft holds."""
    known = _later_work(draft, repo, commit, lists)
    return True if known is None else known


def _later_work(draft: Draft, repo: pygit2.Repository, commit: str, lists: Lists) -> bool | None:
    """`holds_later_work`'s answer, `None` where the comparison failed for a reason outside the
    draft — an answer that may not be kept."""
    try:
        return bool(staged_changes(draft, repo, commit, lists))
    except (DraftRefused, NormalizerDefect, ValueError):
        return True
    except Exception:  # noqa: BLE001 — a release never fails on what a draft holds
        logger.exception("a draft that cannot be compared", extra={"draft": str(draft.pk)})
        return None


def has_edits(hold: Hold) -> bool:
    """Whether the hold's draft holds anything the head does not — captured text, a part
    operation, a title page change: *no edits* is its negation (DL-0510). The head read once, the
    lists once, as `holds_later_work` compares them. Never raises: what cannot be compared counts
    as edited, so it is kept."""
    try:
        document = hold.document
        draft = hold.draft
        repo = gitstore.open_repository(holds.tenant_number(), document.number)
        head = gitstore.head(repo) or draft.base_commit
        lists = _lists(document)
    except Exception:  # noqa: BLE001 — a release never fails on what a draft holds (DL-0256)
        logger.exception("a hold whose draft cannot be compared", extra={"hold": str(hold.pk)})
        # Unknown is kept: a draft is never thrown away for a repository that cannot be read.
        return True
    return holds_later_work(draft, repo, head, lists)


def declarations_offered(
    draft: Draft, repo: pygit2.Repository | None = None, head: str | None = None
) -> list[dict[str, str]]:
    """What *Mark*'s picker offers, as declaring answers it: the declarations the commit of the
    draft will write, read against `head` — the document's head by default; none for a file that
    does not read as one."""
    document = draft.hold.document
    if repo is None:
        repo = gitstore.open_repository(holds.tenant_number(), document.number)
    if head is None:
        head = gitstore.head(repo) or draft.base_commit
    own = entities.readable(holds.draft_entities(draft, repo, head), document.number)
    if own is None:
        return []
    found = draft_declarations(draft, repo, head, document, own)
    return [{"kind": e.kind, "key": e.key, "label": e.label} for e in found.committed]


# The reading of the edit tab's stored answers, in their key: raised whenever a change to the code
# that reads whether a draft holds edits or what it declares — the comparison, the span reader, the
# declarations' shape — could answer differently for the same draft, so every stored answer is
# read again (DL-23-001).
OPENING_ANSWERS = 1


@dataclass(frozen=True)
class _Inputs:
    """What the edit tab's answers are read from, read once, and the key over it."""

    repo: pygit2.Repository
    head: str
    lists: Lists
    key: str


def _opening_inputs(hold: Hold) -> _Inputs:
    document = hold.document
    draft = hold.draft
    repo = gitstore.open_repository(holds.tenant_number(), document.number)
    head = gitstore.head(repo) or draft.base_commit
    lists = _lists(document)
    return _Inputs(repo, head, lists, _opening_key(draft, head, lists))


def _opening_key(draft: Draft, head: str, lists: Lists) -> str:
    """A hash of everything `staged_changes` and `draft_declarations` read: the draft's content and
    base, the head, the staged files' rows, the sentence lists, and the rules the reading follows —
    the normalizer's ruleset, the whitelist specification and `OPENING_ANSWERS`."""
    from django.db.models import BooleanField, ExpressionWrapper, Q

    from editing.markdown import raw_spec

    held = ExpressionWrapper(Q(content__isnull=False), output_field=BooleanField())
    rows = draft.files.annotate(held=held).order_by("at", "pk")
    files = [
        [str(pk), kind, path, operation, sha256, has]
        for pk, kind, path, operation, sha256, has in rows.values_list(
            "pk", "kind", "path", "operation", "sha256", "held"
        )
    ]
    read = [
        OPENING_ANSWERS,
        RULESET,
        raw_spec(),
        head,
        draft.base_commit,
        draft.content,
        files,
        [lists.language, list(lists.never_final), list(lists.may_be_final)],
    ]
    encoded = json.dumps(read, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def opening(hold: Hold) -> tuple[list[dict[str, str]] | None, bool]:
    """What the holder's edit tab opens with (DL-23-001): the declarations *Mark* offers — `None`
    for ones that do not read, which the editor's `load` then answers — and whether the draft holds
    edits. The draft's stored answers while their key matches; otherwise both read in one pass of
    the normalizer, and stored when nothing outside the draft failed and nothing moved meanwhile."""
    draft = hold.draft
    try:
        inputs: _Inputs | None = _opening_inputs(hold)
    except Exception:  # noqa: BLE001 — the tab never fails on what its draft's inputs hold
        logger.exception("a draft whose inputs cannot be read", extra={"hold": str(hold.pk)})
        inputs = None
    stored = draft.opening
    if inputs is not None and isinstance(stored, dict) and stored.get("key") == inputs.key:
        return stored.get("declared"), bool(stored.get("edited"))
    with normalising_once():
        try:
            declared: list[dict[str, str]] | None = (
                declarations_offered(draft, inputs.repo, inputs.head)
                if inputs is not None
                else declarations_offered(draft)
            )
        except Exception:  # noqa: BLE001 — what only `load` answered may not cost the tab itself
            logger.exception("declarations that do not read", extra={"hold": str(hold.pk)})
            declared = None
        if inputs is None:
            return declared, has_edits(hold)
        edited = _later_work(draft, inputs.repo, inputs.head, inputs.lists)
    if declared is not None and edited is not None:
        _store_opening(hold, inputs, {"edited": edited, "declared": declared})
    return declared, True if edited is None else edited


def _store_opening(hold: Hold, inputs: _Inputs, answer: dict[str, Any]) -> None:
    """Keep `answer` under the inputs' key, unless the head or the staged files moved while it was
    read: an answer kept under a key must be the answer to that key."""
    draft = hold.draft
    try:
        moved = _opening_inputs(hold).key != inputs.key
    except Exception:  # noqa: BLE001 — not keeping an answer costs one slower opening
        logger.exception("a draft whose inputs cannot be read", extra={"hold": str(hold.pk)})
        return
    if moved:
        return
    kept = {"key": inputs.key, **answer}
    # Not `save`: the draft's own time is its holder's last write, not this answer's. Only on the
    # draft as it was read: an answer read before a newer write never replaces that write's own.
    Draft.objects.filter(pk=draft.pk, updated_at=draft.updated_at).update(opening=kept)
    draft.opening = kept


def refresh_opening(hold_pk: Any, written_at: Any) -> None:
    """After the write at `written_at` to the hold's draft, its edit tab's answers read again and
    stored, so that the next opening reads them rather than the draft (DL-23-001). Nothing when
    the draft was written again since — that write's own refresh reads it — or is gone with its
    hold. Run outside the document's writer lock; never raises, since the write it follows has
    already landed."""
    try:
        hold = Hold.objects.select_related("document").filter(pk=hold_pk, release_kind="").first()
        draft = Draft.objects.filter(hold_id=hold_pk).first() if hold is not None else None
        if hold is None or draft is None or draft.updated_at != written_at:
            return
        hold.draft = draft
        opening(hold)
    except Exception:  # noqa: BLE001 — a missed refresh costs one slower opening, never a wrong one
        from django.db import connection

        from tenancy.schemas import current_tenant

        logger.exception(
            "an edit tab's answers not refreshed",
            extra={"hold": str(hold_pk), "tenant": current_tenant(connection)},
        )


def draft_text(hold: Hold) -> tuple[str, str, str]:
    """The head's sha and body, and the draft normalised against it — the text *my edits* shows
    and exports; `DraftRefused` for a draft the whitelist refuses, `MissingImages` for one that
    references an image the document does not hold."""
    head, head_body, normalised, _ = _draft_text(hold)
    return head, head_body, normalised


def draft_export(hold: Hold) -> tuple[dict[str, Any], str, list[tuple[int, str, str]]]:
    """The draft's state as a *my edits* export writes it (DL-0193, DL-0209): its frontmatter —
    its lists and every key it holds — its body normalised against the head, and each appendix
    its list holds, `(number, title, text)` in its order, as the commit would write it; the
    head's own text where the draft changed none. `DraftRefused` as `draft_text` refuses."""
    head, _head_body, normalised, staged = _draft_text(hold)
    draft = Draft.objects.get(hold=hold)
    document = Document.objects.get(pk=hold.document_id)
    current = parts.side_at(gitstore.open_repository(holds.tenant_number(), document.number), head)
    frontmatter = dict(draft.content[holds.FRONTMATTER])
    appendices = []
    for number, title in _listed_appendices(frontmatter).items():
        content = staged.get(parts.appendix_key(number))
        text = content.decode("utf-8") if content is not None else current[1].get(number, "")
        appendices.append((number, title, text))
    return frontmatter, normalised, appendices


def _draft_text(hold: Hold) -> tuple[str, str, str, dict[str, bytes | None]]:
    """`draft_text`, and what the commit would write against the head."""
    document = Document.objects.select_related("language").get(pk=hold.document_id)
    tenant_number = holds.tenant_number()
    head, head_body = _head_body(tenant_number, document)
    draft = Draft.objects.get(hold=hold)
    lists = _lists(document)
    staged = staged_changes(
        draft, gitstore.open_repository(tenant_number, document.number), head, lists
    )
    normalised = _normalised(head_body, draft.content[holds.BODY], lists)
    return head, head_body, normalised.decode("utf-8"), staged


def _head_number(document: Document, head: str) -> str:
    try:
        version = Version.objects.get(document=document, commit_sha=head)
        return numbering.number_of(document, version)
    except (Version.DoesNotExist, LookupError):
        # A head a stopped finish left underived: its side is named without a number.
        return ""


def _holders_reading(hold: Hold, document: Document, head: str, *bodies: str) -> Any:
    """The holder's context for their draft's changes: the draft's images through its own route,
    the two sides the head's number and *your draft*."""
    from django.utils.translation import gettext

    from rendering import reading

    head_number = _head_number(document, head)
    draft = Draft.objects.get(hold=hold)
    return reading.context(
        hold.user,
        document,
        *bodies,
        images=reading.draft_images(document, draft),
        sides=(head_number, gettext("your draft")),
    )


def _draft_parts(
    hold: Hold, repo: pygit2.Repository, head: str, staged: dict[str, bytes | None]
) -> parts.PartChanges:
    """The draft's part changes against the head: each appendix as the commit will write it —
    `staged`, what `staged_changes` returned, or the head's own text where it changed nothing."""
    draft = Draft.objects.get(hold=hold)
    current = parts.side_at(repo, head)

    def written(number: int) -> str:
        content = staged.get(parts.appendix_key(number))
        return content.decode("utf-8") if content is not None else current[1].get(number, "")

    return parts.changes_between(current, parts.draft_side(draft, written))


def _drawn_for_the_holder(
    document: Document, head: str, changes: parts.PartChanges, reader: Any
) -> dict[str, Any]:
    """The draft's part changes as the person editing is shown them: an attachment's file at the
    head's version and in the draft, an appendix's link to its edit tab."""
    number, at = document.number, _head_number(document, head)
    return parts.drawn(
        changes,
        reader,
        older_file=lambda n: f"/document/{number}/version/{at}/attachment/{n}/" if at else None,
        newer_file=lambda n: f"/document/{number}/edit/parts/attachment/{n}/",
        appendix_link=lambda n: f"/document/{number}/appendix/{n}/edit/",
    )


def _appendix_texts(changes: parts.PartChanges) -> list[str]:
    return [text for change in changes.appendices for text in (change.older, change.newer)]


def my_edits(hold: Hold) -> tuple[str, str, list[ListedEntity], dict[str, Any]]:
    """The draft normalised against the head, its changes rendered, the entities it changes and
    its part changes; `DraftRefused` for a draft the whitelist refuses."""
    head, head_body, normalised, staged = _draft_text(hold)
    document = Document.objects.select_related("language").get(pk=hold.document_id)
    repo = gitstore.open_repository(holds.tenant_number(), document.number)
    found = _draft_parts(hold, repo, head, staged)
    reader = _holders_reading(hold, document, head, head_body, normalised, *_appendix_texts(found))
    changes = render_changes(head_body.encode(), normalised.encode(), context=reader)
    listed = entity_changes(Draft.objects.get(hold=hold), repo, head, normalised)
    return head_body, changes, listed, _drawn_for_the_holder(document, head, found, reader)


def finish(hold: Hold) -> Finishing:
    """The finishing screen for `hold`; `EditorsOpen` while an editor is open on its draft (the
    browser closes its own before it asks); `DraftRefused` for a draft the whitelist refuses."""
    if OpenEditor.objects.filter(draft__hold=hold, closed_at__isnull=True).exists():
        raise EditorsOpen(hold.pk)
    document = Document.objects.select_related("language").get(pk=hold.document_id)
    tenant_number = holds.tenant_number()
    head, head_body = _head_body(tenant_number, document)
    draft = Draft.objects.get(hold=hold)
    lists = _lists(document)
    repo = gitstore.open_repository(tenant_number, document.number)
    staged = staged_changes(draft, repo, head, lists)
    normalised = _normalised(head_body, draft.content[holds.BODY], lists)
    found = _draft_parts(hold, repo, head, staged)
    reader = _holders_reading(
        hold, document, head, head_body, normalised.decode("utf-8"), *_appendix_texts(found)
    )
    return Finishing(
        changes=render_changes(head_body.encode(), normalised, context=reader),
        summary=summary.drafted(
            head_body,
            normalised.decode("utf-8"),
            appendices=[change.title for change in found.appendices],
        ),
        number=_number(document, repo, head, draft, lists),
        entities=entity_changes(draft, repo, head, normalised.decode("utf-8")),
        parts=_drawn_for_the_holder(document, head, found, reader),
    )


def _number(
    document: Document, repo: pygit2.Repository, head: str, draft: Draft, lists: Lists
) -> str:
    """The number *send for review* will give: after a finish that stopped past its commit, the
    stopped version's own when the draft holds nothing beyond it, else the one after it — counted
    whether or not its row has been derived yet."""
    stopped = _stopped(repo, head, draft, draft.hold.user)
    if stopped is None:
        return numbering.pending(document)
    derived = Version.objects.filter(document=document, commit_sha=stopped).exists()
    if not holds_later_work(draft, repo, stopped, lists):
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
    nobody, once an acceptance has taken it in or a return has sent it back (DL-0114)."""
    from access.rights import holders_of
    from notifications.models import Category, Event
    from notifications.services import notify, others
    from review.services import returned_since, run

    pending = run(document)
    position = next((n for n, v in enumerate(pending, 1) if v.commit_sha == sha), None)
    if position is None or returned_since(document, sha):
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


def finish_accepting(hold: Hold) -> None:
    """The *accepting* mark lifted once *accept as* has landed or told the reviewers."""
    Hold.objects.filter(pk=hold.pk, release_kind=ReleaseKind.ACCEPTING).update(
        release_kind=ReleaseKind.FINISHED
    )


def commit_draft(hold: Hold, user: User, message: str, *, fault_at: int | None = None) -> Version:
    """Commit the draft of `hold` as one version, under the document's lock: of kind
    `reviewer_edit` when the holder holds *accept* at that moment, `edit` otherwise (ADR-0014). A
    finish that stopped after its commit is resumed first: its row derived, then whatever the
    holder wrote since committed as the next version, or nothing when they wrote nothing."""
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
        _accepted(draft)
        listed = _listed_appendices(draft.content[holds.FRONTMATTER])
        if any(APPENDIX.fullmatch(k) and _appendix_order(k) not in listed for k in draft.content):
            # Every part operation drops a key with its entry: one left behind is a defect, and
            # the commit leaves it out.
            logger.error("a draft holds an unlisted appendix", extra={"draft": str(draft.pk)})
        head = gitstore.head(repo)
        if head is None:
            raise RuntimeError(f"document {document.number} has no commit")
        stopped = _stopped(repo, head, draft, user)
        lists = _lists(document)
        _part_rights(draft, repo, head, rights)
        changes = staged_changes(draft, repo, head, lists)
        _consistent(draft, repo)
        if stopped is not None and (not changes or not staged_changes(draft, repo, stopped, lists)):
            # Nothing beyond the stop: the version is the stopped commit.
            changes = {}
        elif not changes:
            raise NothingChanged(document.number)
    if (
        stopped is not None
        and not Version.objects.filter(document=document, commit_sha=stopped).exists()
    ):
        _derive(document, repo, stopped, user)
    if not changes:
        # Nothing written since the stop: the version is the stopped commit, whatever an
        # acceptance has written above it since.
        assert stopped is not None
        sha = stopped
    else:
        # (1) The commit point: the body and every path the draft stages, in one commit.
        sha = gitstore.commit(
            repo,
            changes,
            identity_for(user),
            summary.as_message(message),
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
        # *Accept as* tells nobody here: the hold stays *accepting* until its acceptance lands,
        # and a process that dies between the two leaves that mark for the reconciler.
        holds.release(hold, ReleaseKind.FINISHED if tell else ReleaseKind.ACCEPTING, actor=user)
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


# The right each net part operation needs at the commit beyond *edit* (ADR-0007); renaming and
# reordering need none (DL-0470).
PART_RIGHTS = {
    ("appendix", "added"): Right.CREATE_APPENDIX,
    ("appendix", "removed"): Right.DELETE_APPENDIX,
    ("attachment", "added"): Right.UPLOAD_ATTACHMENT,
    ("attachment", "replaced"): Right.REPLACE_ATTACHMENT,
    ("attachment", "removed"): Right.DELETE_ATTACHMENT,
}
# The operation a revert of each change stages (DL-0446).
REVERTED_BY = {"added": "removed", "removed": "added", "replaced": "replaced", "renamed": "renamed"}


def _part_rights(
    draft: Draft, repo: pygit2.Repository, head: str, rights: frozenset[Right]
) -> None:
    """The rights decided again, under the locks, on what the commit changes in the parts against
    the head: a right lost since staging refuses the commit and names each part. An operation a
    revert staged needs *accept* instead (DL-0446) — only while the draft still holds what the
    revert staged: the entry it recorded, or the part's absence."""
    from documents.parts import part_operations

    current, _ = holds.split(gitstore.read(repo, holds.BODY, head).decode("utf-8"))
    held = draft.content[holds.FRONTMATTER]
    reverted = {
        (str(r.get("part")), REVERTED_BY.get(str(r.get("change")), "")): r.get("staged")
        for r in draft.content.get("revert", [])
    }
    lost = []
    for operation in part_operations(
        (current["appendices"], current["attachments"]),
        (held.get("appendices", []), held.get("attachments", [])),
    ):
        right = PART_RIGHTS.get((operation.kind, operation.change))
        if right is None or right in rights:
            continue
        recorded = (f"{operation.kind}:{operation.number}", operation.change)
        if (
            recorded in reverted
            and reverted[recorded] == operation.newer
            and Right.ACCEPT in rights
        ):
            continue
        entry = operation.newer or operation.older or {}
        lost.append(str(entry.get("title", operation.number)))
    if lost:
        raise PartRightLost(lost)


def _consistent(draft: Draft, repo: pygit2.Repository) -> None:
    """Every listed attachment has its bytes — a staged row, or its file at the draft's base — and
    each describes the other: a row's hash is its bytes', and its hash, size and file name the
    entry's; a removal is of an attachment the draft no longer lists. Anything else is a defect:
    `RuntimeError`, logged, nothing written."""
    entries = {int(e["number"]): e for e in draft.content[holds.FRONTMATTER].get("attachments", [])}
    staged: set[int] = set()
    rows = draft.files.filter(kind=DraftFileKind.ATTACHMENT).values_list(
        "path", "operation", "sha256", "file_name", "content"
    )
    for path, operation, sha256, file_name, content in rows:
        number_text = path.removeprefix("attachments/")
        number = int(number_text) if number_text.isdigit() else None
        entry = entries.get(number) if number is not None else None
        if operation == DraftFileOperation.REMOVE:
            if number is None or entry is not None:
                _defect(draft, f"a removal of a listed attachment: {path!r}")
            continue
        data = bytes(content or b"")
        if (
            number is None
            or entry is None
            or hashlib.sha256(data).hexdigest() != sha256
            or entry.get("sha256") != sha256
            or entry.get("bytes") != len(data)
            or entry.get("file_name") != file_name
        ):
            _defect(draft, f"a staged attachment its entry does not describe: {path!r}")
        staged.add(number)
    for number, entry in entries.items():
        if number in staged:
            continue
        try:
            data = gitstore.read(repo, parts.attachment_path(number), draft.base_commit)
        except KeyError:
            _defect(draft, f"a listed attachment without its file: {number}")
        if hashlib.sha256(data).hexdigest() != entry.get("sha256"):
            _defect(draft, f"a listed attachment whose file is not the one listed: {number}")


def _defect(draft: Draft, what: str) -> NoReturn:
    logger.error("a draft that cannot be committed: %s", what, extra={"draft": str(draft.pk)})
    raise RuntimeError(what)


def discard_preserved(draft: Draft, user: User) -> bool:
    """Throw away the draft kept for `user` from a released hold of theirs (DL-0381): the draft and
    its staged files deleted without a hold, audited with what was thrown away. Under the
    document's writer lock and its row, as every writer of the draft; whether this call deleted
    it — `False` once it is gone, or taken back meanwhile."""
    tenant_number = holds.tenant_number()
    document = Document.objects.get(pk=draft.hold.document_id)
    with (
        document_lock(tenant_number, document.number, timeout=holds.LOCK_WAIT_SECONDS),
        transaction.atomic(),
    ):
        locked = Document.objects.select_for_update().get(pk=document.pk)
        kept = holds.preserved_draft(locked, user)
        if kept is None or kept.pk != draft.pk:
            return False
        state = holds.draft_state(kept.hold)
        kept.files.all().delete()
        kept.delete()
        record(
            actor=user,
            action="document.draft_discarded",
            obj=locked,
            before=None,
            after={"number": locked.number, **state},
            tenant=Tenant.objects.get(number=tenant_number),
        )
    return True


def finish_stopped(hold: Hold, *, actor: User | None, reason: str = "") -> bool:
    """Complete a finish of `hold` that stopped after its commit (DL-0414), for a release that is
    not the holder's own. The record is settled first — every commit the rows do not know derived,
    as every writer does — then the commit path's own test: the holder's content version above
    the draft's base with nothing but acceptances or returns after it, and the draft holding
    nothing beyond it. Then the hold is released `finished` by `actor`, who acted, with `reason`
    where they gave one, the audit saying the finish was completed; the reviewers are told the
    version awaits them, where it still does; and the draft is deleted. Whether it was. A version
    found under a draft holding later work is committed all the same: its reviewers are told, and
    the draft is kept as asked. A record that cannot be settled, or a repository that cannot be
    read, leaves the release as asked and the stop to the reconciler's report: no release depends
    on git. The caller holds the document's writer lock and, in a transaction, its row and the
    hold's."""
    from rendering.views import UNREADABLE
    from review.services import RecordIncomplete, settle_head

    draft = Draft.objects.filter(hold=hold).first()
    if draft is None:
        return False
    document = Document.objects.select_related("language").get(pk=hold.document_id)
    user = hold.user
    try:
        settle_head(document)
        repo = gitstore.open_repository(holds.tenant_number(), document.number)
        head = gitstore.head(repo)
        stopped = _stopped(repo, head, draft, user) if head is not None else None
        if stopped is None:
            return False
        later = holds_later_work(draft, repo, stopped, _lists(document))
    except (RecordIncomplete, *UNREADABLE):
        logger.warning(
            "a release over a record that cannot be read", extra={"document": document.number}
        )
        return False
    if later:
        # Written since the commit: that work is at risk and is kept as asked; the version the
        # stop made stands, and its reviewers are told it awaits them.
        tell_reviewers(document, stopped, user)
        return False
    holds.release(hold, ReleaseKind.FINISHED, actor=actor, reason=reason, finish_completed=True)
    tell_reviewers(document, stopped, user)
    draft.delete()
    return True


class HasEdits(Exception):
    """*Release the document* asked of a draft that holds edits: the page was drawn before the
    first one, and the holder discards them instead (DL-0510)."""


def discard(hold: Hold, user: User, *, release: bool = False) -> tuple[str, str | None]:
    """Throw the holder's draft away — its text and every staged file (DL-0180) — and release the
    hold `discarded`, a reservation ending with it (ADR-0009). What was thrown away is audited as a
    kept draft's discard is. A finish of the hold that stopped after its commit made a version no
    discard takes back: the record is settled, and the reviewers are told it awaits them. Under the
    document's writer lock and, in a transaction, its row and the hold's. The sha of such a
    version, or `None`; `EditorsOpen` while an editor is open on the draft — it may hold text not
    yet captured, and the page closes its editors before it asks; `holds.NotEditable` for a hold
    not the user's, or ended. The draft decides, never the button (DL-0510): a draft with no
    edits and no stopped finish is released `released`, nothing discarded and nothing kept;
    `release` — *Release the document* pressed on a page drawn before the first edit — over a
    draft with edits raises `HasEdits`, the hold untouched. Answers `("released", None)` or
    `("discarded", <the stopped version's sha or None>)`."""
    from rendering.views import UNREADABLE
    from review.services import RecordIncomplete, settle_head

    tenant_number = holds.tenant_number()
    document = Document.objects.get(pk=hold.document_id)
    with document_lock(tenant_number, document.number, timeout=holds.LOCK_WAIT_SECONDS):
        try:
            settle_head(document)
        except (RecordIncomplete, *UNREADABLE):
            # The record is the reconciler's to report; the draft is still the holder's to drop.
            logger.warning(
                "a discard over a record that cannot be settled",
                extra={"document": document.number},
            )
        with transaction.atomic():
            Document.objects.select_for_update().get(pk=document.pk)
            locked = Hold.objects.select_for_update().get(pk=hold.pk)
            if locked.released_at is not None or locked.user_id != user.pk:
                raise holds.NotEditable(document.number)
            if OpenEditor.objects.filter(draft__hold=locked, closed_at__isnull=True).exists():
                raise EditorsOpen(locked.pk)
            draft = Draft.objects.select_for_update().filter(hold=locked).first()
            try:
                repo = gitstore.open_repository(tenant_number, document.number)
                head = gitstore.head(repo)
                stopped = (
                    _stopped(repo, head, draft, user)
                    if draft is not None and head is not None
                    else None
                )
            except UNREADABLE:
                stopped = None
            if stopped is None:
                edited = draft is not None and has_edits(locked)
                if not edited:
                    holds.release(locked, ReleaseKind.RELEASED, actor=user)
                    return "released", None
                if release:
                    raise HasEdits(locked.pk)
            # Released first, so the release records the draft's state; then the draft goes.
            holds.release(locked, ReleaseKind.DISCARDED, actor=user)
            if draft is not None:
                record(
                    actor=user,
                    action="document.draft_discarded",
                    obj=document,
                    before=None,
                    after={
                        "number": document.number,
                        "reserved": locked.reserved_at is not None,
                        "files": draft.files.count(),
                        "version_kept": stopped,
                    },
                    tenant=Tenant.objects.get(number=tenant_number),
                )
                draft.files.all().delete()
                draft.delete()
            if stopped is not None:
                tell_reviewers(document, stopped, user)
    return "discarded", stopped
