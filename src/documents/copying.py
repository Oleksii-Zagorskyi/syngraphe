"""Copying a document (ST-0067, DL-0451, DL-0455, DL-0268): a new document whose one `created`
commit holds a version of the source the copier may see — its text under the title they give, the
source's language and title page, the appendices they chose renumbered from 1 in the source's
order, the images its texts reference and the source's entities — and never an attachment.

The source is recorded in `document.copied` before any repository exists (DL-0455), so a copy
that stops is recognised as one: the reconciler reports it and never finishes it from the
template; an operator removes it (`remove_stopped_copy`).

The images are those the reading parser finds in the copied texts, and `entities.yaml` is carried
as the source's bytes."""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any

from django.db import connection, transaction

from audit.record import record
from documents import bundle, gitstore
from documents.locks import document_lock
from documents.models import (
    Document,
    DocumentState,
    DocumentTemplate,
    DocumentType,
    Folder,
    next_document_number,
)
from syngraphe.provenance import ActorKind
from tenancy.models import Tenant
from tenancy.schemas import current_tenant

if TYPE_CHECKING:
    from identity.models import User

IMAGES = "images/"


class CopyRefused(Exception):
    """Nothing written: `changed` — the version offered is no longer the one the dialog showed;
    `unreadable` — the source's text or a part of it cannot be read; `archived`; `no_such_appendix`;
    `not_allowed` — the copier may no longer create, or read the source."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class CopyStopped(Exception):
    """The copy's row and its record exist, the rest did not finish: it stays invisible, and an
    operator removes it."""

    def __init__(self, number: int) -> None:
        super().__init__(f"copy {number} was not finished")
        self.number = number


def copy_document(
    user: User,
    source: Document,
    *,
    title: str,
    document_type: DocumentType,
    folder: Folder,
    view: str,
    number: str,
    appendices: list[int] | None,
    fault_at: int | None = None,
) -> Document:
    """Copy `source` at the offer `view` numbered `number`, with `appendices` — `None` for all,
    `[]` for none, else the source's part numbers — and return the new document, active."""
    from documents import services

    if connection.in_atomic_block:
        raise RuntimeError("a copy commits before its fallible step; call it outside one")
    tenant_number = current_tenant(connection)
    if tenant_number is None:
        raise RuntimeError("a document is copied inside a tenant's schema")
    tenant = Tenant.objects.get(number=tenant_number)
    template = DocumentTemplate.objects.get()
    content, offered, chosen = _read_source(user, tenant, source, view, number, appendices)

    # (1) The row, and the record of its source, before anything leaves the database.
    with transaction.atomic():
        rows = Folder.objects.select_for_update(no_key=True, of=("self",))
        if rows.filter(pk=folder.pk).first() is None:
            raise services.ChoiceGone("folder")
        held = (
            DocumentType.objects.select_for_update(no_key=True, of=("self",))
            .filter(pk=document_type.pk, retired_at__isnull=True)
            .first()
        )
        if held is None:
            raise services.ChoiceGone("document_type")
        document = Document.objects.create(
            number=next_document_number(),
            title=title,
            language_id=source.language_id,
            document_type=document_type,
            folder=folder,
            author_only=True,
            copied_from=source,
            state=DocumentState.CREATING,
            created_by=user,
            actor_kind=ActorKind.USER,
        )
        record(
            actor=user,
            action="document.copied",
            obj=document,
            before=None,
            after={
                "number": document.number,
                "source_number": source.number,
                "source_version": offered.number,
                "source_commit": offered.version.commit_sha,
                "appendices": chosen,
            },
            tenant=tenant,
        )
    try:
        services._fault(1, fault_at)
        tree = {
            **content,
            "document.md": _document_md(content["document.md"], title),
            "passport.md": bundle.passport_header(tenant_number, document.number).encode(),
        }
        with document_lock(tenant_number, document.number):
            from notifications.models import Event

            services.resume_creation(
                document,
                tenant,
                template,
                user,
                adopt=False,
                fault_at=fault_at,
                tree=tree,
                event=Event.DOCUMENT_COPIED,
            )
    except Exception as error:
        raise CopyStopped(document.number) from error
    return document


def _document_md(source_md: bytes, title: str) -> bytes:
    frontmatter, body = bundle.parse(source_md.decode("utf-8"))
    return bundle.render(dataclasses.replace(frontmatter, title=title), body).encode("utf-8")


def _read_source(
    user: User,
    tenant: Tenant,
    source: Document,
    view: str,
    number: str,
    appendices: list[int] | None,
) -> tuple[dict[str, bytes], Any, list[int]]:
    """Under the source's writer lock, its head settled: the offer recomputed and matched, its
    commit read once, the copy's first tree but its passport built in memory. The title in the
    returned `document.md` is the source's; the caller puts the copy's own."""
    from access.rights import can_create, readable
    from editing.holds import LOCK_WAIT_SECONDS
    from rendering.export.compose import offers
    from rendering.models import ExportView
    from review.services import settle_head

    with document_lock(tenant.number, source.number, timeout=LOCK_WAIT_SECONDS):
        settle_head(source)
        locked = Document.objects.get(pk=source.pk)
        if locked.state == DocumentState.ARCHIVED:
            raise CopyRefused("archived")
        if locked.state != DocumentState.ACTIVE:
            raise CopyRefused("unreadable")
        if not can_create(user, tenant) or locked.pk not in readable(user, [locked.pk]):
            raise CopyRefused("not_allowed")
        offered = next(
            (o for o in offers(user, locked) if o.view == view and o.view != ExportView.MY_EDITS),
            None,
        )
        if offered is None or offered.number != number:
            raise CopyRefused("changed")
        sha = offered.version.commit_sha
        repo = gitstore.open_repository(tenant.number, locked.number)
        try:
            frontmatter, body = bundle.parse(gitstore.read(repo, "document.md", sha).decode())
        except (KeyError, ValueError, UnicodeDecodeError):
            raise CopyRefused("unreadable") from None
        listed = [int(entry["number"]) for entry in frontmatter.appendices]
        if appendices is None:
            chosen = listed
        else:
            if any(n not in listed for n in appendices):
                raise CopyRefused("no_such_appendix")
            chosen = [n for n in listed if n in appendices]
        titles = {int(e["number"]): str(e["title"]) for e in frontmatter.appendices}
        tree: dict[str, bytes] = {}
        texts = [body]
        renumbered = []
        try:
            for new, old in enumerate(chosen, 1):
                text = gitstore.read(repo, f"appendices/{old}.md", sha)
                tree[f"appendices/{new}.md"] = text
                texts.append(text.decode("utf-8"))
                renumbered.append({"number": new, "title": titles[old]})
            for path in sorted({p for text in texts for p in _referenced_images(text)}):
                tree[path] = gitstore.read(repo, path, sha)
        except (KeyError, UnicodeDecodeError):
            raise CopyRefused("unreadable") from None
        try:
            tree["entities.yaml"] = gitstore.read(repo, "entities.yaml", sha)
        except KeyError:
            tree["entities.yaml"] = b"[]\n"
        tree["document.md"] = bundle.render(
            dataclasses.replace(frontmatter, appendices=renumbered, attachments=[]), body
        ).encode("utf-8")
        return tree, offered, chosen


def _referenced_images(text: str) -> set[str]:
    """The images a text references, as the reading parser finds them: `image` tokens whose
    source is under `images/`."""
    from rendering.renderer import labelled

    found: set[str] = set()

    def walk(tokens: Any) -> None:
        for token in tokens:
            if token.type == "image":
                src = str(token.attrs.get("src", ""))
                if src.startswith(IMAGES):
                    found.add(src)
            if token.children:
                walk(token.children)

    walk(labelled(text))
    return found


def offered(user: User, source: Document) -> list[Any]:
    """The versions the dialog offers, newest first as it draws them: pending, accepted,
    canonical, among those `user` may see — never the copier's own draft."""
    from rendering.export.compose import offers
    from rendering.models import ExportView

    return [o for o in reversed(offers(user, source)) if o.view != ExportView.MY_EDITS]


def default_offer(choices: list[Any], view: str = "") -> Any:
    """The offer named by `view` when it is offered; else the newest — pending when offered."""
    return next((o for o in choices if o.view == view), choices[0] if choices else None)


def listed_appendices(source: Document, offer: Any) -> list[tuple[int, str]]:
    """The appendices `offer`'s version lists, in its frontmatter's order: `(number, title)`;
    none when its text cannot be read, which the copy itself then refuses."""
    tenant_number = current_tenant(connection)
    assert tenant_number is not None
    repo = gitstore.open_repository(tenant_number, source.number)
    try:
        frontmatter, _ = bundle.parse(
            gitstore.read(repo, "document.md", offer.version.commit_sha).decode()
        )
    except (KeyError, ValueError, UnicodeDecodeError):
        return []
    return [(int(e["number"]), str(e["title"])) for e in frontmatter.appendices]


@dataclasses.dataclass(frozen=True)
class Provenance:
    """A copy's source as `document.copied` recorded it, for the *Info* tab (DL-0455)."""

    source: Document | None
    source_number: int
    version: str
    commit: str
    at: Any
    copier: User | None


def provenance(document: Document) -> Provenance | None:
    """The newest `document.copied` event for `document`; `None` for a document not copied."""
    from audit.models import AuditEvent

    event = (
        AuditEvent.objects.filter(
            action="document.copied", object_type="document", object_id=document.pk
        )
        .select_related("actor")
        .order_by("-at")
        .first()
    )
    if event is None or not isinstance(event.after, dict):
        return None
    number = int(event.after["source_number"])
    return Provenance(
        source=Document.objects.filter(number=number).first(),
        source_number=number,
        version=str(event.after["source_version"]),
        commit=str(event.after["source_commit"]),
        at=event.at,
        copier=event.actor,
    )
