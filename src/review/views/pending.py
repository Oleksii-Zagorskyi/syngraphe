"""The *Pending edits* tab (DL-0040, DL-0170): the whole document, every change since the last
acceptance marked in place, the run's versions listed, each line's author behind *show author*.

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
    tenant_number: int, document: Document, head: str, base: Version, offset: int
) -> dict[int, str]:
    """Each body line of the head by its index, to the name of its author."""
    lines = blame_at(
        gitstore.repository_path(tenant_number, document.number), head, base=base.commit_sha
    )
    versions = {
        v.commit_sha: v for v in Version.objects.filter(document=document).select_related("author")
    }
    base_rows: dict[int, Any] = {}
    if base.kind != VersionKind.CREATED:
        base_rows = dict(
            LineAuthorship.objects.filter(version=base, file=DOCUMENT_FILE).values_list(
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


def _correct_blocked(document: Document, user: User) -> str:
    """Why *Correct* cannot take the document now, or `""`: a reservation, naming its holder to a
    holder of *accept* (DL-0226), or anyone else's hold, as a fact (ADR-0006)."""
    from editing.models import Hold
    from review.views.accept import reason

    hold = Hold.objects.filter(document=document, released_at__isnull=True).first()
    if hold is None or hold.user_id == user.pk and hold.reserved_at is None:
        return "" if services.run(document) else reason(document, user, "nothing_to_accept")
    if hold.reserved_at is not None:
        return reason(document, user, "reserved")
    return _("This document is held: someone is editing it.")


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
        }
        for n, version in enumerate(run, 1)
    ]
    # Raw HTML in the text is escaped by the renderer, and every name is escaped: safe to mark.
    changes = render_changes(base_body.encode(), head_body.encode(), authors=authors)
    rights = rights_on_many(request.user, [document.pk])[document.pk]
    acts = None
    if Right.ACCEPT in rights:
        from review.views.accept import reason

        user = cast(User, request.user)
        refused = services.refusal(document, user)
        from review.views.return_run import reason as return_reason

        refused_return = services.return_refusal(document, user)
        acts = {
            "accept": reason(document, user, refused) if refused else "",
            "return": return_reason(document, user, refused_return) if refused_return else "",
            "correct": _correct_blocked(document, user),
        }
    context = {
        "document": document,
        "tab": "pending",
        "can_edit": Right.EDIT in rights,
        "holding": held_by(document, request.user),
        "acts": acts,
        "run": versions,
        "changes": mark_safe(changes),  # noqa: S308
        "show_author": attributed,
    }
    return render(request, "review/pending.html", context)
