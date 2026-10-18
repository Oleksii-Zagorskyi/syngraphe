"""Creating a document: the one write across both stores (DL-0111, DL-0268).

The row is committed first, in state `creating`, with a number that is never given again; the
repository and its first commit follow under the document's lock; the rows derived from the commit
come after it; the row becomes `active` last. A crash between any two steps leaves one of four
states, each finished by the reconciler (DL-0111). The document's file lock is always taken before
any database row lock.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from django.db import connection, transaction

from audit.record import record
from documents import bundle, caches, gitstore
from documents.gitstore import Kind
from documents.identity import identity_for
from documents.locks import document_lock
from documents.models import (
    Document,
    DocumentState,
    DocumentTemplate,
    DocumentType,
    Folder,
    Version,
    VersionKind,
    next_document_number,
)
from documents.template import TemplateRefused, refusals, starting_body
from identity.models import Language
from syngraphe.provenance import ActorKind
from tenancy.models import Tenant
from tenancy.schemas import current_tenant

if TYPE_CHECKING:
    import pygit2

    from identity.models import User

# The summary of every first commit; a commit message never carries a title or a name.
CREATED_SUMMARY = "Document created"


class InjectedFault(Exception):
    """Raised by `create_document` after the step a crash test names; never set in production."""


class CreationStopped(Exception):
    """A creation stopped after its row was written; the reconciler finishes it."""

    def __init__(self, number: int) -> None:
        super().__init__(f"document {number} was not finished")
        self.number = number


class ChoiceGone(Exception):
    """A creation's chosen type or folder was deleted, or the type retired, after the form offered
    it; `field` names the choice. Nothing is written."""

    def __init__(self, field: str) -> None:
        super().__init__(f"the chosen {field} is no longer offered")
        self.field = field


def commit_message(kind: Kind) -> str:
    """The message of a commit the platform writes on its own account, from its kind alone."""
    if kind is Kind.CREATED:
        return CREATED_SUMMARY
    raise ValueError(f"no platform message for {kind}")


def _fault(step: int, fault_at: int | None) -> None:
    if fault_at == step:
        raise InjectedFault(step)


def create_document(
    user: User,
    title: str,
    language: str,
    document_type: DocumentType,
    folder: Folder,
    *,
    fault_at: int | None = None,
) -> Document:
    """Create a document in the tenant the connection is set to, author-only, from the
    organisation's template, and return it `active`."""
    if connection.in_atomic_block:
        raise RuntimeError("create_document commits before its fallible step; call it outside one")
    tenant_number = current_tenant(connection)
    if tenant_number is None:
        raise RuntimeError("a document is created inside a tenant's schema")
    tenant = Tenant.objects.get(number=tenant_number)
    template = DocumentTemplate.objects.get()
    # The template checked before any row or number is taken; step 3 puts this same row in
    # normal form, so a template saved in between reaches only documents created after it.
    refused = refusals(template.outline)
    if refused:
        raise TemplateRefused(refused)
    starting_body(template.outline, Language.objects.get(code=language))

    # (1) The row, with the next number, committed before anything leaves the database.
    with transaction.atomic():
        # The type and the folder read again and held, so a delete or a retire since the
        # form offered them refuses the creation rather than failing its row.
        # The folder first, then the type — the order a move and a type change take — so the
        # three acts never wait on each other in a cycle.
        rows = Folder.objects.select_for_update(no_key=True, of=("self",))
        if rows.filter(pk=folder.pk).first() is None:
            raise ChoiceGone("folder")
        held = (
            DocumentType.objects.select_for_update(no_key=True, of=("self",))
            .filter(pk=document_type.pk, retired_at__isnull=True)
            .first()
        )
        if held is None:
            raise ChoiceGone("document_type")
        document = Document.objects.create(
            number=next_document_number(),
            title=title,
            language_id=language,
            document_type=document_type,
            folder=folder,
            author_only=True,
            state=DocumentState.CREATING,
            created_by=user,
            actor_kind=ActorKind.USER,
        )
    _fault(1, fault_at)
    try:
        _finish(document, tenant, template, user, fault_at)
    except InjectedFault:
        raise
    except Exception as error:
        raise CreationStopped(document.number) from error
    return document


def _finish(
    document: Document,
    tenant: Tenant,
    template: DocumentTemplate,
    user: User,
    fault_at: int | None,
) -> None:
    """Steps 2 to 6, under the document's lock."""
    with document_lock(tenant.number, document.number):
        resume_creation(document, tenant, template, user, adopt=False, fault_at=fault_at)


def derive_version(document: Document, commit: pygit2.Commit, author: User) -> Version:
    """The `VERSION` row of a commit and the caches at it, in one transaction; the rows a commit
    implies, whoever derives them (DL-0111)."""
    kind = gitstore.kind_of(commit.message)
    if kind is None:
        raise ValueError(f"commit {commit.id} names no kind")
    with transaction.atomic():
        version = Version.objects.create(
            document=document,
            commit_sha=str(commit.id),
            author=author,
            summary=commit.message.splitlines()[0][:500],
            kind=VersionKind(kind.value),
            committed_at=datetime.fromtimestamp(commit.author.time, tz=UTC),
            actor_kind=ActorKind.USER,
            created_by=author,
        )
        caches.rebuild(document, version)
    return version


class NotAdoptable(Exception):
    """A repository at a creating document's number that its creation did not begin."""


def resume_creation(
    document: Document,
    tenant: Tenant,
    template: DocumentTemplate,
    user: User,
    *,
    adopt: bool = True,
    fault_at: int | None = None,
    # A copy's first tree and its administrators' event (DL-0451, DL-0455).
    tree: dict[str, bytes] | None = None,
    event: str | None = None,
) -> bool:
    """Steps 2 to 6 from wherever a creation stopped; the caller holds the document's lock.
    Returns whether this call made the document `active`. A copy passes `tree`, committed at step 3
    instead of the template's, and `event`, what its administrators are told.

    Creation runs it with `adopt` false: step 2 then always creates the repository and refuses
    one already there. The reconciler runs it with `adopt` true, and a repository already there
    is taken over only when its first commit is this document's `created` commit by its creator;
    anything else raises `NotAdoptable`.
    """
    tenant_number = tenant.number
    # (2) The repository.
    if adopt and gitstore.repository_path(tenant_number, document.number).exists():
        repo = gitstore.open_repository(tenant_number, document.number)
    else:
        repo = gitstore.init(tenant_number, document.number)
    _fault(2, fault_at)
    # (3) The `created` commit: git is the commit point.
    first = next(gitstore.history(repo), None)
    if first is not None and (
        gitstore.kind_of(first.message) is not Kind.CREATED or first.author.name != str(user.pk)
    ):
        raise NotAdoptable(f"tenant-{tenant_number}/document-{document.number}")
    if first is None:
        tree = tree or bundle.initial_tree(
            tenant=tenant_number,
            document=document.number,
            title=document.title,
            language=document.language_id,
            title_page=template.title_page,
            # Leniently: the reconciler resumes with the row as it stands then, and a creation
            # never sticks on a template the whitelist has since stopped accepting.
            outline=starting_body(template.outline, document.language, strict=False),
        )
        sha = gitstore.commit(
            repo, tree, identity_for(user), commit_message(Kind.CREATED), Kind.CREATED
        )
        first = gitstore.commit_at(repo, sha)
    _fault(3, fault_at)
    # (4) The rows derived from the commit.
    if not Version.objects.filter(document=document, commit_sha=str(first.id)).exists():
        derive_version(document, first, user)
    _fault(4, fault_at)
    # (5) Active, reaching its author alone, only from `creating`; (6) audited.
    with transaction.atomic():
        finished = Document.objects.filter(pk=document.pk, state=DocumentState.CREATING).update(
            state=DocumentState.ACTIVE, author_only=True, updated_by=user
        )
        if not finished:
            return False
        document.state, document.author_only = DocumentState.ACTIVE, True
        record(
            actor=user,
            action="document.created",
            obj=document,
            before=None,
            after={
                "number": document.number,
                "language": document.language_id,
                "document_type": document.document_type.code,
                "folder": document.folder.number,
                "author_only": True,
                "commit": str(first.id),
                # A copy names its source.
                **(
                    {"copied_from": document.copied_from.number}
                    if document.copied_from is not None
                    else {}
                ),
            },
            tenant=tenant,
        )
        tell_administrators(document, user, event=event)
    return True


def tell_administrators(
    document: Document, user: User | None, *, event: str | None = None, **facts: Any
) -> None:
    """The administrators of the organisation whose schema holds `document` told it exists —
    never its creator; the reconciler, recreating one, tells them with `recreated`."""
    from access.rights import administrators
    from notifications.models import Category, Event
    from notifications.services import notify, others

    tenant_number = current_tenant(connection)
    if tenant_number is None:
        raise RuntimeError("a document's administrators are read inside its organisation's schema")
    notify(
        users=others((admin.pk for admin in administrators(tenant_number)), user),
        category=Category.ADMINISTRATIVE,
        event=Event(event) if event is not None else Event.DOCUMENT_CREATED,
        actor=user,
        document=document,
        facts=facts or None,
    )
