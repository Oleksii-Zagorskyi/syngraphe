"""The *Pending edits* tab (DL-0040, DL-0170): the whole document, every change since the last
acceptance marked in place, the run's versions listed with the parts each changed, each line's
author behind *show author*, each appendix the run changed and the parts changed in the run, and
the roles, actions and terms the run added, relabelled or removed.

The run's lines are attributed at render from the run itself — a blame of the head bounded by the
base, which costs the run's size — never by waiting for the worker (`technical-design.md
§ Runtime`, DL-0266); the base's own lines take the base's rows, or the creator when the base is
the `created` commit (DL-0268), and render without an author while those rows are not there.
Nothing is queued from here.
"""

from __future__ import annotations

from typing import Any, cast

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache

from access.rights import Right, rights_on_many
from documents import gitstore
from documents.holds import held_by
from documents.models import Document, DocumentState, Version, VersionKind
from documents.parts import lists_at, part_operations
from documents.path import frame
from documents.views import ABSENT, is_member
from editing import holds, numbering
from editing.authorship import DOCUMENT_FILE, blame_at
from editing.diffview import render_changes
from editing.models import LineAuthorship
from identity.models import User, UserPreference
from identity.naming import person
from review import services
from shell.views import not_found

SHOW_AUTHOR = "show_author"


def show_author(user: Any) -> bool:
    """Whether the person keeps *show author* on; off until they turn it on."""
    return UserPreference.objects.filter(user_id=user.pk, key=SHOW_AUTHOR, value="on").exists()


def _body(text: str) -> tuple[int, str]:
    """The lines before `document.md`'s body, and the body."""
    _frontmatter, body = holds.split(text)
    return text[: len(text) - len(body)].count("\n"), body


def _authors(
    tenant_number: int,
    document: Document,
    head: str,
    base: Version,
    offset: int,
    *,
    path: str = DOCUMENT_FILE,
    at_base: bool = True,
) -> dict[int, str]:
    """Each line of `path` at the head after its first `offset` — the body of `document.md`, or
    an appendix's whole text — by its index, to the name of its author; an appendix the base does
    not hold (`at_base` false) attributed from the run alone."""
    lines = blame_at(
        gitstore.repository_path(tenant_number, document.number),
        head,
        base=base.commit_sha if at_base else None,
        path=path,
    )
    versions = {
        v.commit_sha: v for v in Version.objects.filter(document=document).select_related("author")
    }
    base_rows: dict[int, Any] = {}
    if base.kind != VersionKind.CREATED and at_base:
        base_rows = dict(
            LineAuthorship.objects.filter(version=base, file=path).values_list(
                "line", "introduced_by__author"
            )
        )
    people = {u.pk: u for u in User.objects.filter(pk__in=set(base_rows.values()))}
    authors: dict[int, str] = {}
    for n, line in enumerate(lines):
        if n < offset or not line.text.strip():
            continue
        who: User | None
        if line.commit == base.commit_sha:
            if base.kind == VersionKind.CREATED:
                who = base.author
            else:
                introduced = base_rows.get(line.orig_line or 0)
                who = people.get(introduced) if introduced is not None else None
        else:
            version = versions.get(line.commit)
            who = version.author if version is not None else None
        name = person(who)
        if name:
            authors[n - offset] = name
    return authors


def _edit_blocked(document: Document, user: User) -> str:
    """Why a reviewer's edit cannot take the document now, or `""`: a reservation, naming its
    holder to a holder of *accept* (DL-0516), or anyone else's hold, as a fact (ADR-0006)."""
    from editing.models import Hold
    from review.views.accept import reason

    hold = Hold.objects.filter(document=document, released_at__isnull=True).first()
    if hold is None or hold.user_id == user.pk and hold.reserved_at is None:
        return "" if services.run(document) else reason(document, user, "nothing_to_accept")
    if hold.reserved_at is not None:
        return reason(document, user, "reserved")
    from django.utils.translation import pgettext

    from identity.naming import person

    # Every caller holds *accept*, whom DL-0516 names the holder to.
    return pgettext("the reason beside a disabled act", "%(name)s is editing.") % {
        "name": person(hold.user)
    }


def _undo_blocked(document: Document, user: User) -> str:
    """Why the undo controls cannot act now, or `""`: a reservation, named to a holder of
    *accept* (DL-0516), someone else's hold, named the same way, or a kept draft of the
    reviewer's — drawn disabled with it, never hidden (DL-0233)."""
    from review.undo import refusal
    from review.views.accept import reason

    refused = refusal(document, user)
    if refused == "reserved":
        return reason(document, user, "reserved")
    if refused == "held":
        return _edit_blocked(document, user)
    if refused == "draft_kept":
        from review.views.undo import reason as undo_reason

        return undo_reason(document, user, "draft_kept")
    return ""


def readable_pending(
    request: HttpRequest, number: int, *, archived: bool = False
) -> Document | None:
    """The active document `number` when the person holds *view pending* on it; `None`
    otherwise, a missing document costing what a forbidden one does (ADR-0008). With `archived`,
    an archived one too, which only administrators hold a right on: the *Pending edits* page reads
    it, the acts never pass it (DL-0450)."""
    if getattr(request, "tenant", None) is None or not is_member(request):
        return None
    states = (DocumentState.ACTIVE, DocumentState.ARCHIVED) if archived else (DocumentState.ACTIVE,)
    document = Document.objects.filter(number=number, state__in=states).first()
    rights = rights_on_many(request.user, [document.pk if document is not None else ABSENT])
    if document is None or Right.VIEW_PENDING not in rights.get(document.pk, frozenset()):
        return None
    return document


@never_cache
@login_required
def page(request: HttpRequest, number: int) -> HttpResponse:
    """The tab: the head against the base, the run above it."""
    document = readable_pending(request, number, archived=True)
    if document is None or request.method != "GET":
        return not_found(request)
    tenant_number = holds.tenant_number()
    repo = gitstore.open_repository(tenant_number, document.number)
    head = gitstore.head(repo)
    assert head is not None
    base = services.base(document)
    run = services.run(document, head=head)
    offset, head_body = _body(gitstore.read(repo, DOCUMENT_FILE, head).decode("utf-8"))
    _offset, base_body = _body(gitstore.read(repo, DOCUMENT_FILE, base.commit_sha).decode("utf-8"))
    attributed = show_author(request.user)
    authors = _authors(tenant_number, document, head, base, offset) if attributed else None
    # Counted from the later of the latest edition and the latest acceptance (DL-0267).
    accepted = numbering.accepted(document)
    versions = [
        {
            "number": f"{accepted}-{n}",
            "summary": version.summary,
            "author": person(version.author),
            "at": version.committed_at,
            "author_id": version.author_id,
        }
        for n, version in enumerate(run, 1)
    ]
    from editing import parts
    from rendering import reading

    head_number = f"{accepted}-{len(run)}" if run else accepted
    # The run's parts beside its body: each appendix's text, the part operations, the
    # frontmatter, from the base to the head (DL-0168).
    found = parts.changes_between(parts.side_at(repo, base.commit_sha), parts.side_at(repo, head))
    reader = reading.context(
        request.user,
        document,
        base_body,
        head_body,
        *(text for change in found.appendices for text in (change.older, change.newer)),
        images=reading.committed_images(document),
        sides=(accepted, head_number),
    )
    # Raw HTML in the text is escaped by the renderer, and every name is escaped: safe to mark.
    changes = render_changes(
        base_body.encode(), head_body.encode(), authors=authors, context=reader
    )
    # The head's own number, from its row: none while a finish stopped after its commit has left
    # it underived, and then no *new* file is drawn rather than the version before's.
    head_version = Version.objects.filter(document=document, commit_sha=head).first()
    at_head = numbering.number_of(document, head_version) if head_version is not None else ""
    drawn = parts.drawn(
        found,
        reader,
        older_file=lambda n: f"/document/{document.number}/version/{accepted}/attachment/{n}/",
        newer_file=lambda n: (
            f"/document/{document.number}/version/{at_head}/attachment/{n}/" if at_head else None
        ),
        appendix_link=lambda n: f"/document/{document.number}/appendix/{n}/",
        authors=_appendix_authors(tenant_number, document, head, base, found)
        if attributed
        else None,
    )
    for version, before, row in zip(run, [base, *run], versions, strict=False):
        row["parts"] = parts.drawn(
            parts.PartChanges([], part_operations(lists_at(before), lists_at(version)), []),
            reader,
            older_file=lambda n: None,
            newer_file=lambda n: None,
            appendix_link=lambda n: "",
        )["part_rows"]
    rights = rights_on_many(request.user, [document.pk])[document.pk]
    shown = frame(request, document, here="review", rights=rights)
    acts = None
    undo_blocked = ""
    if Right.ACCEPT in rights:
        from review.views.accept import reason

        user = cast(User, request.user)
        refused = services.refusal(document, user)
        from review.views.return_run import reason as return_reason

        refused_return = services.return_refusal(document, user)
        acts = {
            "accept": reason(document, user, refused) if refused else "",
            "return": return_reason(document, user, refused_return) if refused_return else "",
            "head": head_number,
            "becomes": numbering.next_accepted(document),
            # *Edit* and the freeze's toggle, the path's own acts, stand here as well (DL-0518).
            "path": [
                act
                for item in (shown.path or [])
                for act in item.acts
                if act.command in ("edit", "freeze", "unfreeze")
            ],
        }
        # The undo beside each version (DL-0522): *undo this edit*, and on each author's newest
        # *undo all of this author's edits* (ADR-0015, DL-0243).
        undo_blocked = _undo_blocked(document, user)
        seen_authors: set[Any] = set()
        for row in reversed(versions):
            row["undo"] = {"author": row["author_id"], "all": row["author_id"] not in seen_authors}
            seen_authors.add(row["author_id"])
    from rendering.outline import outline
    from rendering.renderer import labelled
    from rendering.views import panes

    context = {
        "document": document,
        "frame": shown,
        **panes(request),
        # The outline beside the run's text, read from the head's (DL-0518).
        "headings": outline(labelled(head_body)),
        "undo_blocked": undo_blocked,
        "since": accepted,
        "tab": "pending",
        "can_edit": Right.EDIT in rights,
        "holding": held_by(document, request.user),
        "acts": acts,
        "run": versions,
        "changes": mark_safe(changes),  # noqa: S308
        "show_author": attributed,
        "entity_changes": _entity_changes(repo, base.commit_sha, head, document.number),
        **drawn,
        "parts_heading": _("Parts changed in the run"),
        # *Revert* on each row, for a holder of *accept* (DL-0446): the head the page shows.
        "revert_head": head if Right.ACCEPT in rights else "",
    }
    return render(request, "review/pending.html", context)


def _appendix_authors(
    tenant_number: int, document: Document, head: str, base: Version, found: Any
) -> dict[int, dict[int, str]]:
    """Each changed appendix the head holds, its lines by index to their authors."""
    from editing import parts

    authors = {}
    for change in found.appendices:
        if not change.newer:
            continue
        authors[change.number] = _authors(
            tenant_number,
            document,
            head,
            base,
            0,
            path=parts.appendix_key(change.number),
            at_base=bool(change.older),
        )
    return authors


def _entity_changes(repo: Any, base: str, head: str, number: int) -> list[Any]:
    """The run's roles, actions and terms added, relabelled or removed: the base's
    `entities.yaml` against the head's. Nothing for a file that does not read as one."""
    from documents import entities

    before = entities.readable(holds.entities_at(repo, base), number)
    after = entities.readable(holds.entities_at(repo, head), number)
    if before is None or after is None:
        return []
    return entities.compare(before, after)
