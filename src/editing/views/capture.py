"""Capture without a Save control (ASR-22, DL-0167): an open editor posts the text of its range
after a pause, and the server takes it only while the draft's range still hashes to what that
editor last saw; a heartbeat keeps the editor known; the editor closes itself. Every route is the
holder's alone, for an editor of the holder's own draft."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache

from documents.locks import LockTimeout, document_lock
from editing import holds
from editing.markdown import load_spec
from editing.models import Draft, Hold, OpenEditor
from editing.views.draft import range_hash
from editing.views.edit_tab import editable
from shell.views import not_found

# The pause after the last keystroke before a capture, the heartbeat's period, and how long an
# editor may stay silent before it is closed: two seconds of typing at most are ever lost (ASR-22).
CAPTURE_PAUSE_SECONDS = 0.75
HEARTBEAT_SECONDS = 30
SILENT_AFTER = timedelta(minutes=3)
# A capture waits this long for the document's writer lock — held through a commit of the draft —
# then answers busy, which the editor retries.
CAPTURE_LOCK_SECONDS = 5


def _payload(request: HttpRequest) -> dict[str, Any]:
    """The request's fields: a JSON body, or a form — what a page sends as it closes."""
    if request.content_type == "application/json":
        try:
            data = json.loads(request.body or b"{}")
        except (ValueError, RecursionError):
            return {}
        return data if isinstance(data, dict) else {}
    return {key: request.POST.get(key) for key in request.POST}


def _own_editor(request: HttpRequest, number: int) -> tuple[Hold, OpenEditor] | None:
    """The holder's hold on document `number` and the open editor the request names on its draft;
    `None` for anyone else, any other editor, or a wrong method."""
    document = editable(request, number)
    if document is None or request.method != "POST":
        return None
    hold = holds.open_hold(document)
    if hold is None or hold.user_id != request.user.pk:
        return None
    editor_id = _payload(request).get("editor")
    if not isinstance(editor_id, str):
        return None
    try:
        editor = OpenEditor.objects.filter(pk=editor_id, draft__hold=hold).first()
    except (ValueError, ValidationError):
        return None
    return (hold, editor) if editor is not None else None


@never_cache
@login_required
def capture(request: HttpRequest, number: int) -> HttpResponse:
    """Take the editor's text when the draft's range still hashes to the editor's base, closing the
    editor too when the body says `close`: `200` with the new hash; `409` *stale* when the draft
    changed elsewhere, *closed* when the editor or the hold was; `413` over the size allowed;
    `503` while the document is being committed."""
    found = _own_editor(request, number)
    if found is None:
        return not_found(request)
    hold, editor = found
    data = _payload(request)
    body, base = data.get("body"), data.get("base_hash")
    # A NUL or a lone surrogate is no text a draft can hold, nor the database store.
    if not isinstance(body, str) or not isinstance(base, str) or "\x00" in body:
        return JsonResponse({"refused": True}, status=400)
    try:
        size = len(body.encode("utf-8"))
    except UnicodeEncodeError:
        return JsonResponse({"refused": True}, status=400)
    if size > load_spec().max_bytes:
        return JsonResponse({"too_large": True}, status=413)
    try:
        # The writer lock a commit of this draft holds from its check to the draft's deletion: a
        # capture never lands in a draft that is being committed and is about to go (DL-0318).
        with document_lock(holds.tenant_number(), number, timeout=CAPTURE_LOCK_SECONDS):
            return _take(hold, editor, body, base, close=data.get("close") is True)
    except LockTimeout:
        return JsonResponse({"busy": True}, status=503)


def _take(hold: Hold, editor: OpenEditor, body: str, base: str, *, close: bool) -> HttpResponse:
    """The capture itself; with `close`, the editor closed in the same write — what a closing
    page sends, since it never reads an answer before sending its close."""
    now = timezone.now()
    with transaction.atomic():
        draft = Draft.objects.select_for_update().filter(pk=editor.draft_id).first()
        locked = OpenEditor.objects.select_for_update().filter(pk=editor.pk).first()
        still_held = Hold.objects.filter(pk=hold.pk, released_at__isnull=True).exists()
        if draft is None or locked is None or locked.closed_at is not None or not still_held:
            return JsonResponse({"closed": True}, status=409)
        current = range_hash(draft.content[holds.BODY])
        new = range_hash(body)
        # The same text again — a retry whose first answer was lost, or the flush a closing page
        # repeats — is accepted as it stands, whatever base the editor sent.
        if current != new:
            if current != base or locked.base_hash != base:
                return JsonResponse({"stale": True}, status=409)
            draft.content = {**draft.content, holds.BODY: body}
            draft.save(update_fields=["content", "updated_at"])
            Hold.objects.filter(pk=hold.pk).update(last_activity_at=now)
        locked.base_hash = new
        locked.last_seen_at = now
        if close:
            locked.closed_at = now
        locked.save(update_fields=["base_hash", "last_seen_at", "closed_at"])
    return JsonResponse({"base_hash": new})


@never_cache
@login_required
def heartbeat(request: HttpRequest, number: int) -> HttpResponse:
    """The editor is still open: `200` with how many *other* editors are open on the draft, which
    decides whether *finish editing* is offered; `409` when it was closed."""
    found = _own_editor(request, number)
    if found is None:
        return not_found(request)
    _, editor = found
    updated = OpenEditor.objects.filter(pk=editor.pk, closed_at__isnull=True).update(
        last_seen_at=timezone.now()
    )
    if not updated:
        return JsonResponse({"closed": True}, status=409)
    others = (
        OpenEditor.objects.filter(draft_id=editor.draft_id, closed_at__isnull=True)
        .exclude(pk=editor.pk)
        .count()
    )
    return JsonResponse({"others": others})


@never_cache
@login_required
def close(request: HttpRequest, number: int) -> HttpResponse:
    """The editor closes itself: as its page goes away, or before *finish editing*."""
    found = _own_editor(request, number)
    if found is None:
        return not_found(request)
    _, editor = found
    OpenEditor.objects.filter(pk=editor.pk, closed_at__isnull=True).update(closed_at=timezone.now())
    return JsonResponse({"closed": True})


def settings_for_the_editor() -> dict[str, float]:
    """The capture timings the page hands the editor."""
    return {"pause_seconds": CAPTURE_PAUSE_SECONDS, "heartbeat_seconds": HEARTBEAT_SECONDS}
