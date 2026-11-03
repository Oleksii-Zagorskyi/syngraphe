"""The *Edit* tab: the editor's mount point for the holder, *held* for anyone else with *edit*,
the freeze's reason to an editor without *accept* while frozen, and nothing for a reader without
*edit*. Loading the tab changes nothing; the editor takes the hold
with a POST as it mounts (DL-0319) — at once only when the tab was opened from the application
itself or typed in, and otherwise on a *Start editing* the person presses (DL-0325)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, cast

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache

from access.rights import Right, rights_on_many
from documents.locks import LockTimeout
from documents.models import Document, DocumentState
from documents.path import frame
from documents.views import ABSENT
from editing import holds, messages
from identity.models import User
from shell.views import not_found


def editable(request: HttpRequest, number: int) -> Document | None:
    """The active document `number` of the request's organisation, when the person holds *edit*
    on it; `None` otherwise. A missing document costs what a forbidden one does (ADR-0008)."""
    if getattr(request, "tenant", None) is None:
        return None
    document = Document.objects.filter(number=number, state=DocumentState.ACTIVE).first()
    rights = rights_on_many(request.user, [document.pk if document is not None else ABSENT])
    if document is None or Right.EDIT not in rights.get(document.pk, frozenset()):
        return None
    return document


def correcting(request: HttpRequest, document: Document) -> bool:
    """Whether the person holds *accept* on a document with pending edits: their changes become a
    version of their own (ADR-0014)."""
    from review.services import run

    rights = rights_on_many(request.user, [document.pk]).get(document.pk, frozenset())
    if Right.ACCEPT not in rights:
        return False
    try:
        return bool(run(document))
    except LookupError:
        # A head that no longer follows the accepted version: nothing to call pending here.
        return False


@never_cache
@login_required
def page(request: HttpRequest, number: int) -> HttpResponse:
    """The tab: the mount point, told whether to take the hold at once or wait to be asked."""
    document = editable(request, number)
    if document is None or request.method != "GET":
        return not_found(request)
    return tab_response(request, document)


def tab_response(
    request: HttpRequest,
    document: Document,
    *,
    extra: dict[str, Any] | None = None,
    status: int = 200,
) -> HttpResponse:
    """The tab drawn for a document the caller's gate opened; `extra` what a refused form keeps,
    drawn with `status`."""
    from editing import title_page
    from editing.views.capture import settings_for_the_editor as capture_settings

    hold = holds.open_hold(document)
    # The browser's own word for where the navigation came from; a request without it is treated
    # as coming from elsewhere.
    own = request.headers.get("Sec-Fetch-Site") in ("same-origin", "none")
    holding = hold is not None and hold.user_id == request.user.pk
    context = {
        "correcting": correcting(request, document),
        "document": document,
        "can_edit": True,
        "holding": holding,
        "take_on_mount": own or holding,
        "tab": "edit",
        "words": {**messages.for_the_editor(), "capture": capture_settings()},
    }
    from editions.models import open_freeze

    frozen = open_freeze(document)
    # Asked only of a frozen document: while frozen only holders of *accept* edit (ADR-0016).
    accepts = frozen is not None and Right.ACCEPT in rights_on_many(
        request.user, [document.pk]
    ).get(document.pk, frozenset())
    if hold is None:
        kept = holds.preserved_draft(document, request.user)
        if kept is not None:
            # The kept draft is offered back before any new hold is taken (DL-0225, DL-0318) —
            # on a frozen document too, read only to a holder who may not edit it now (DL-0511).
            may_take = frozen is None or accepts
            context |= {"frozen": frozen, "may_take": may_take}
            return render(
                request,
                "editing/draft_readonly.html",
                context
                | {"frame": frame(request, document, here="kept")}
                | returning(request, document, kept, read_only=not may_take),
            )
    if frozen is not None and not accepts:
        # While frozen only holders of *accept* edit (ADR-0016); the tab says why and offers
        # nothing.
        context["frozen"] = frozen
        # A holder whose document was frozen while they held it stands on their draft point.
        context["frame"] = frame(request, document, here="draft" if holding else "latest")
        return render(request, "editing/held_by_other.html", context)
    if hold is not None and hold.user_id != request.user.pk:
        context["frame"] = frame(request, document, here="latest")
        return render(request, "editing/held_by_other.html", context)
    context["reservation"] = _reservation(request, document, hold, frozen, context)
    context["draft_view"] = _draft_view(document, hold if holding else None, request.user)
    from editing.views.parts import panel
    from identity.views.preferences import PANEL_WIDTH, PANEL_WIDTH_MAX, PANEL_WIDTH_MIN
    from rendering.views import _kept

    # The edit tab's own parts panel (DL-0442), as wide as the person keeps the View tab's; drawn
    # hidden until a hold is taken — on mount or by *Start editing* — whose take reveals it.
    context["parts_panel"] = panel(document, request.user, hold if holding else None)
    context["panel_width"] = _kept(
        request, "panel_width", PANEL_WIDTH, PANEL_WIDTH_MIN, PANEL_WIDTH_MAX
    )
    context["panel_bounds"] = (PANEL_WIDTH_MIN, PANEL_WIDTH_MAX)
    if holding and hold is not None:
        # What an undo left for the holder's hand, beside the text and never in it (DL-0380).
        context["undo"] = hold.draft.content.get("undo")
    # The title page's switch and text in the panel, as the draft has them (DL-0463, DL-0476).
    context["title_page"] = title_page.state(document, hold if holding else None)
    # The page is served before the editor takes the hold on mount (DL-0325): the draft point is
    # drawn for the take to come.
    taking = own and not holding
    on_draft = holding or taking
    context["frame"] = frame(
        request, document, here="draft" if on_draft else "latest", taking=taking
    )
    context |= extra or {}
    return render(request, "editing/edit_tab.html", context, status=status)


def _draft_view(document: Document, hold: Any, user: Any) -> Any:
    """The text the tab opens on, rendered for `user` as the View tab renders a version, with no
    editor until one is chosen (ADR-0006): the holder's draft, or the head's text the hold will
    start from. `None` for a text the whitelist refuses, which only the whole editor opens — in its
    source view, with the refusal named."""
    from django.utils.safestring import mark_safe

    from documents import gitstore
    from editing.markdown.validator import validate
    from rendering import reading
    from rendering.renderer import labelled, render_tokens

    repo = gitstore.open_repository(holds.tenant_number(), document.number)
    if hold is not None:
        body: str = hold.draft.content[holds.BODY]
        images = reading.draft_images(document, hold.draft, repo)
    else:
        head = gitstore.head(repo)
        if head is None:
            return None
        _, body = holds.split(gitstore.read(repo, holds.BODY, head).decode("utf-8"))
        images = reading.committed_images(document)
    if validate(body):
        return None
    reader = reading.context(user, document, body, images=images)
    # Raw HTML is off and every value escaped.
    return mark_safe(render_tokens(labelled(body), context=reader))  # noqa: S308


def ended_how(released: Any) -> str:
    """How a kept draft's hold ended, as its holder is told: their reservation ended by an
    administrator; their editing ended by an administrator, or by one archiving the document; by
    the platform's operator, whose
    note is for the audit trail alone; for inactivity; or by a block."""
    from editing.models import ReleaseKind

    if released.release_kind == ReleaseKind.FORCED:
        # Ended by archiving (DL-0456) — tested before the reservation, which archiving
        # ends too.
        if _ended_by_archiving(released):
            return "archived"
        if released.released_by_id is None:
            return "operator"
        return "reservation" if released.reserved_at is not None else "administrator"
    if released.release_kind == ReleaseKind.INACTIVITY:
        return "inactivity"
    return "blocked"


def _ended_by_archiving(released: Any) -> bool:
    """Whether archiving released the hold: the platform's reason, and the archive's own event by
    the same administrator, written in the release's transaction. The audit trail is the record of
    archiving (DL-0433); the reason alone is not — an administrator could type it as a
    reservation's end before it was refused."""
    from audit.models import AuditEvent
    from documents.archive import ARCHIVED_REASON

    if released.release_reason != ARCHIVED_REASON or released.released_by_id is None:
        return False
    return AuditEvent.objects.filter(
        action="document.archived",
        object_type="document",
        object_id=released.document_id,
        actor_id=released.released_by_id,
        at__gte=released.released_at,
        at__lte=released.released_at + ARCHIVE_AND_RELEASE,
    ).exists()


# The archive's event follows its release within the one transaction; a typed reason ended a
# reservation alone, and no archive by the same administrator follows it this closely.
ARCHIVE_AND_RELEASE = timedelta(minutes=1)


def returning(
    request: HttpRequest, document: Document, kept: Any, *, read_only: bool = False
) -> dict[str, Any]:
    """What the holder of a kept draft is shown on their return (DL-0225): who released it, when
    and why; *take the document back* while nobody has committed since; otherwise — or, with
    `read_only`, whenever they may not take it back — the draft as changes against the current
    text, or a version they choose (DL-0379), and *discard this draft* (DL-0381). Nothing here
    takes a hold."""
    from django.utils.safestring import mark_safe

    from documents import gitstore
    from editing.diffview import render_changes
    from editing.markdown.validator import validate
    from identity.naming import person
    from rendering.views import UNREADABLE
    from review.history import reachable

    released = kept.hold
    repo = gitstore.open_repository(holds.tenant_number(), document.number)
    head = gitstore.head(repo)
    if head is None:
        raise RuntimeError(f"document {document.number} has no commit")
    shown: dict[str, Any] = {
        "kept": kept,
        "released": released,
        "ended_how": ended_how(released),
        "released_by": person(released.released_by) if released.released_by else "",
        "moved": kept.base_commit != head,
        # The edit tab is where the kept draft is shown: the page's band does not point here.
        "returning": True,
    }
    if not shown["moved"] and not read_only:
        return shown
    try:
        # What the holder's ceiling reaches, newest first: the run, the latest accepted version
        # and edition, and what a history right adds (DL-0417).
        choices = [(n, v.commit_sha) for n, v in reachable(request.user, document)][::-1]
    except UNREADABLE:
        # A head that no longer follows the accepted version: the current text alone.
        choices = []
    chosen = request.GET.get("against", "")
    against = dict(choices).get(chosen)
    if against is None:
        chosen, against = "", head
    body: str = kept.content[holds.BODY]
    shown |= {"choices": [number for number, _ in choices], "chosen": chosen}
    if validate(body):
        # A capture takes any text under the size limit, so a kept draft may hold what the
        # whitelist refuses; it is shown as plain text, never rendered (ADR-0010).
        return shown | {"refused_text": body}
    _, old = holds.split(gitstore.read(repo, holds.BODY, against).decode("utf-8"))
    from django.utils.translation import gettext

    from editing import parts
    from rendering import reading

    # The draft's parts against the same side: its appendices as it holds them.
    current = parts.side_at(repo, head)
    found = parts.changes_between(parts.side_at(repo, against), parts.draft_side(kept))
    # An appendix only the draft holds has no page to open.
    on_head = {int(e["number"]) for e in current[0].get("appendices", [])}
    side = chosen or {sha: n for n, sha in choices}.get(head, "")
    reader = reading.context(
        request.user,
        document,
        old,
        body,
        *(text for change in found.appendices for text in (change.older, change.newer)),
        images=reading.draft_images(document, kept, repo),
        # The side compared with is named by its number, the head's when none was chosen.
        sides=(side, gettext("your draft")),
    )
    # Built from text the whitelist accepted, by the renderer that escapes it.
    changes = mark_safe(  # noqa: S308
        render_changes(old.encode("utf-8"), body.encode("utf-8"), context=reader)
    )
    number = document.number
    drawn = parts.drawn(
        found,
        reader,
        older_file=lambda n: f"/document/{number}/version/{side}/attachment/{n}/" if side else None,
        newer_file=lambda n: f"/document/{number}/edit/parts/attachment/{n}/",
        appendix_link=lambda n: f"/document/{number}/appendix/{n}/" if n in on_head else "",
    )
    return shown | {
        "changes": changes,
        **drawn,
        "parts_heading": gettext("Parts changed in this draft"),
    }


def _reservation(
    request: HttpRequest, document: Document, hold: Any, frozen: Any, context: dict[str, Any]
) -> dict[str, Any] | None:
    """The tab's reservation control (ADR-0009): *Cancel the reservation* on the person's own
    reservation; *Reserve for editing* to a holder of the right in an editing session — the one
    path in (DL-0219) — disabled with the freeze's reason while frozen (DL-0252); nothing
    otherwise."""
    if hold is not None and hold.reserved_at is not None:
        return {"reserved": True}
    if not (context["holding"] or context["take_on_mount"]):
        return None
    rights = rights_on_many(request.user, [document.pk]).get(document.pk, frozenset())
    if Right.RESERVE_FOR_EDITING not in rights:
        return None
    return {"reserved": False, "frozen": frozen}


@never_cache
@login_required
def take(request: HttpRequest, number: int) -> HttpResponse:
    """Take the hold, or keep the one the person already has; `409` while someone else holds,
    `503` while the document's lock stays busy."""
    document = editable(request, number)
    if document is None or request.method != "POST":
        return not_found(request)
    try:
        holds.take(document, cast(User, request.user))
    except holds.DraftPreserved:
        return JsonResponse({"preserved": True}, status=409)
    except holds.NotEditable:
        return not_found(request)
    except holds.HeldByOther:
        return JsonResponse({"held": True}, status=409)
    except holds.Frozen:
        return JsonResponse({"frozen": True}, status=409)
    except LockTimeout:
        return JsonResponse({"busy": True}, status=503)
    return JsonResponse({"held": False})
