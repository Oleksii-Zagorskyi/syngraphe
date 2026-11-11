"""An appendix's editor page (DL-0443, ADR-0006, DL-0517): the appendix's page drawn from the
draft for the person editing — from the head before the hold — under the document's path, with
the whole appendix in one editor over its own file and the draft's parts panel; `load` opens it.
The editor is the document's: one draft, one finish.
"""

from __future__ import annotations

from typing import Any, cast

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils.safestring import mark_safe
from django.views.decorators.cache import never_cache

from access.rights import Right, rights_on_many
from documents import bundle, gitstore
from documents.models import Document
from documents.parts import appendices
from editing import holds, messages, parts
from editing.views import draft as draft_views
from editing.views import edit_tab
from identity.models import User
from shell.views import not_found


def _head(document: Document) -> tuple[Any, str] | None:
    repo = gitstore.open_repository(holds.tenant_number(), document.number)
    head = gitstore.head(repo)
    return (repo, head) if head is not None else None


def _rendered(document: Document, user: Any, text: str, images: Any) -> Any:
    """The appendix's text as the tab opens on it, as the View tab renders one; `None` for a text
    the whitelist refuses, which only the whole editor opens, in its source view."""
    from editing.markdown.validator import validate
    from rendering import reading
    from rendering.renderer import labelled, render_tokens

    if validate(text):
        return None
    reader = reading.context(user, document, text, images=images)
    # Raw HTML is off and every value escaped.
    return mark_safe(render_tokens(labelled(text), context=reader))  # noqa: S308


@never_cache
@login_required
def page(request: HttpRequest, number: int, part: int) -> HttpResponse:
    """The tab for a person with *edit*: for the person editing, appendix `part` of their draft —
    one their draft alone holds included; before the hold, the head's. Anyone else holding the
    document, a freeze closed to them or a kept draft of theirs is answered as the document's own
    *Edit* tab answers it; an appendix the side shown does not list, *Nothing to show here*. The
    draft is normalised and validated once however many parts of the page ask of it (ASR-21)."""
    from editing import services

    with services.normalising_once():
        return _page(request, number, part)


def _page(request: HttpRequest, number: int, part: int) -> HttpResponse:
    from editing.views.capture import settings_for_the_editor
    from editing.views.parts import panel
    from editions.models import open_freeze
    from editions.visible import visible
    from rendering import reading
    from rendering.outline import outline
    from rendering.renderer import labelled
    from rendering.views import panes

    document = edit_tab.editable(request, number)
    if document is None or request.method != "GET":
        return not_found(request)
    user = cast(User, request.user)
    hold = holds.open_hold(document)
    holding = hold is not None and hold.user_id == user.pk
    rights = rights_on_many(user, [document.pk]).get(document.pk, frozenset())
    frozen = open_freeze(document) is not None and Right.ACCEPT not in rights
    # A freeze closed to the person comes first, as on the document's tab: no editor is offered.
    if frozen or (
        not holding and (hold is not None or holds.preserved_draft(document, user) is not None)
    ):
        return edit_tab.page(request, number)
    if holding and hold is not None:
        held = parts.draft_parts(hold.draft)
        entry = next((a for a in held.appendices if int(a["number"]) == part), None)
        if entry is None:
            return not_found(request)
        text = parts.appendix_text(hold.draft, part)
        images = reading.draft_images(document, hold.draft)
    else:
        found = _head(document)
        if found is None:
            return not_found(request)
        repo, head = found
        current, _ = bundle.parse(gitstore.read(repo, holds.BODY, head).decode("utf-8"))
        entry = next((a for a in current.appendices if int(a["number"]) == part), None)
        if entry is None:
            return not_found(request)
        try:
            text = gitstore.read(repo, parts.appendix_key(part), head).decode("utf-8")
        except KeyError:
            text = ""
        images = reading.committed_images(document)
    shown = visible(user, document)
    own = request.headers.get("Sec-Fetch-Site") in ("same-origin", "none")
    words = messages.for_the_editor()
    from documents.path import frame

    taking = own and not holding
    # Asked once, for the path and the page alike, with the declarations from the same pass over
    # the draft (ASR-21).
    declared, edited = edit_tab.opening(hold) if holding and hold is not None else (None, False)
    context = {
        "document": document,
        # The document's path for this appendix: the holder stands on their draft (DL-0522).
        "frame": frame(
            request,
            document,
            here="draft" if holding or taking else "latest",
            taking=taking,
            appendix=part,
            subtitle=entry["title"],
            rights=rights,
            seen=shown,
            edited=edited if holding else None,
        ),
        "appendix": {"number": part, "title": entry["title"]},
        "tab": "edit",
        "can_edit": True,
        "holding": holding,
        "take_on_mount": own or holding,
        "correcting": edit_tab.correcting(request, document),
        # A draft's own appendix has no View until a version lists it.
        "view_listed": shown is not None
        and any(a.number == part for a in appendices(shown.version)),
        "headings": outline(labelled(text)),
        "draft_view": _rendered(document, user, text, images),
        "load_path": f"/document/{document.number}/appendix/{part}/edit/load/",
        "edited": edited,
        "declared": declared,
        # The discard's sentence says a reservation ends with the draft, as on the document's
        # page (DL-0237).
        "reserved": holding and hold is not None and hold.reserved_at is not None,
        "words": {**words, "capture": settings_for_the_editor()},
        "parts_panel": panel(document, user, hold if holding else None),
        **panes(request),
    }
    return render(request, "editing/appendix_edit.html", context)


@never_cache
@login_required
def load(request: HttpRequest, number: int, part: int) -> HttpResponse:
    """An editor on appendix `part` of the holder's draft, as `draft.load` opens one on the body;
    `409` *closed* for an appendix the draft no longer lists."""
    document = edit_tab.editable(request, number)
    asked = draft_views._range(request)
    if document is None or request.method != "POST" or asked is None:
        return not_found(request)
    answer = draft_views.opened_on(request, document, asked, parts.appendix_key(part))
    return answer if answer is not None else JsonResponse({"closed": True}, status=409)
