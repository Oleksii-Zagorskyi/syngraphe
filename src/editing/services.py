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
from editing.markdown.validator import Refusal, validate
from editing.models import (
    Draft,
    DraftFileKind,
    DraftFileOperation,
    Hold,
    OpenEditor,
    ReleaseKind,
)
from editing.normalizer import RULESET, Lists, NormalizerDefect, TooLarge, normalize, trailer
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
    """What the finishing screen shows: the changes, the drafted summary, the number to come, and
    the roles, actions and terms the commit adds, relabels or removes."""

    changes: str
    summary: str
    number: str
    entities: list[ListedEntity] = field(default_factory=list)


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
    try:
        return bool(staged_changes(draft, repo, commit, lists))
    except (DraftRefused, NormalizerDefect, ValueError):
        return True
    except Exception:  # noqa: BLE001 — a release never fails on what a draft holds
        logger.exception("a draft that cannot be compared", extra={"draft": str(draft.pk)})
        return True


def draft_text(hold: Hold) -> tuple[str, str, str]:
    """The head's sha and body, and the draft normalised against it — the text *my edits* shows
    and exports; `DraftRefused` for a draft the whitelist refuses, `MissingImages` for one that
    references an image the document does not hold."""
    document = Document.objects.select_related("language").get(pk=hold.document_id)
    tenant_number = holds.tenant_number()
    head, head_body = _head_body(tenant_number, document)
    draft = Draft.objects.get(hold=hold)
    lists = _lists(document)
    staged_changes(draft, gitstore.open_repository(tenant_number, document.number), head, lists)
    normalised = _normalised(head_body, draft.content[holds.BODY], lists)
    return head, head_body, normalised.decode("utf-8")


def _holders_reading(hold: Hold, document: Document, head: str, *bodies: str) -> Any:
    """The holder's context for their draft's changes: the draft's images through its own route,
    the two sides the head's number and *your draft*."""
    from django.utils.translation import gettext

    from rendering import reading

    try:
        version = Version.objects.get(document=document, commit_sha=head)
        head_number = numbering.number_of(document, version)
    except (Version.DoesNotExist, LookupError):
        # A head a stopped finish left underived: its side is named without a number.
        head_number = ""
    draft = Draft.objects.get(hold=hold)
    return reading.context(
        hold.user,
        document,
        *bodies,
        images=reading.draft_images(document, draft),
        sides=(head_number, gettext("your draft")),
    )


def my_edits(hold: Hold) -> tuple[str, str, list[ListedEntity]]:
    """The draft normalised against the head, its changes rendered, and the entities it changes;
    `DraftRefused` for a draft the whitelist refuses."""
    head, head_body, normalised = draft_text(hold)
    document = Document.objects.get(pk=hold.document_id)
    reader = _holders_reading(hold, document, head, head_body, normalised)
    changes = render_changes(head_body.encode(), normalised.encode(), context=reader)
    repo = gitstore.open_repository(holds.tenant_number(), document.number)
    listed = entity_changes(Draft.objects.get(hold=hold), repo, head, normalised)
    return head_body, changes, listed


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
    staged_changes(draft, repo, head, lists)
    normalised = _normalised(head_body, draft.content[holds.BODY], lists)
    reader = _holders_reading(hold, document, head, head_body, normalised.decode("utf-8"))
    return Finishing(
        changes=render_changes(head_body.encode(), normalised, context=reader),
        summary=summary.drafted(head_body, normalised.decode("utf-8")),
        number=_number(document, repo, head, draft, lists),
        entities=entity_changes(draft, repo, head, normalised.decode("utf-8")),
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


def discard(hold: Hold, user: User) -> str | None:
    """Throw the holder's draft away — its text and every staged file (DL-0180) — and release the
    hold `discarded`, a reservation ending with it (ADR-0009). What was thrown away is audited as a
    kept draft's discard is. A finish of the hold that stopped after its commit made a version no
    discard takes back: the record is settled, and the reviewers are told it awaits them. Under the
    document's writer lock and, in a transaction, its row and the hold's. The sha of such a
    version, or `None`; `EditorsOpen` while an editor is open on the draft — it may hold text not
    yet captured, and the page closes its editors before it asks; `holds.NotEditable` for a hold
    not the user's, or ended."""
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
            draft = Draft.objects.filter(hold=locked).first()
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
    return stopped
