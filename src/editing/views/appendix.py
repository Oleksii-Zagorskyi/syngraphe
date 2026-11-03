"""An appendix's *Edit* tab (DL-0443, ADR-0006): the appendix's page drawn from the draft for the
person editing — from the head before the hold — with the whole-appendix and section editors over
its own file, and the draft's parts panel; `load` opens an editor on it. The editor is the
document's: one draft, one finish.
"""

from __future__ import annotations

from typing import Any, cast

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy
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

# The whole editor's control, named for what it opens here.
EDIT_WHOLE = gettext_lazy("Edit the whole appendix")


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
    *Edit* tab answers it; an appendix the side shown does not list, *Nothing to show here*."""
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
    words["labels"] = {**words["labels"], "edit_whole": str(EDIT_WHOLE)}
    from documents.path import frame

    taking = own and not holding
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
