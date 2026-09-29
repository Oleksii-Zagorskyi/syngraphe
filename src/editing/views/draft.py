"""The draft as an editor opens it: `load` opens an editor on the whole draft, recording it as an
open editor with the hash of what it saw, and hands it the body and the validator's verdict."""

from __future__ import annotations

import hashlib

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache

from documents.locks import LockTimeout, document_lock
from documents.models import Document
from editing import holds
from editing.markdown.validator import validate
from editing.models import OpenEditor
from editing.views.edit_tab import editable
from shell.views import not_found

WHOLE = "whole"
OPEN_EDITORS_MOST = 5
LOAD_LOCK_SECONDS = 10


def range_hash(text: str) -> str:
    """The hash an editor keeps of the range it saw: SHA-256 over its UTF-8 bytes."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@never_cache
@login_required
def load(request: HttpRequest, number: int) -> HttpResponse:
    """For the holder alone: a new open editor on the whole body, and the body with its verdict —
    `ok`, or `refused` with each refusal's code and line."""
    document = editable(request, number)
    if document is None or request.method != "POST":
        return not_found(request)
    try:
        # Under the writer lock, so no editor opens on a draft a commit is consuming.
        with document_lock(holds.tenant_number(), document.number, timeout=LOAD_LOCK_SECONDS):
            return _open(request, document)
    except LockTimeout:
        return JsonResponse({"busy": True}, status=503)


def _open(request: HttpRequest, document: Document) -> HttpResponse:
    hold = holds.open_hold(document)
    if hold is None or hold.user_id != request.user.pk:
        return not_found(request)
    draft = hold.draft
    body = draft.content[holds.BODY]
    # The holder's tabs each open an editor; past a few, the oldest are closed — a capture from
    # one would be refused as stale anyway once another has captured.
    open_ids = list(
        OpenEditor.objects.filter(draft=draft, closed_at__isnull=True)
        .order_by("-last_seen_at")
        .values_list("pk", flat=True)
    )
    if len(open_ids) >= OPEN_EDITORS_MOST:
        OpenEditor.objects.filter(pk__in=open_ids[OPEN_EDITORS_MOST - 1 :]).update(
            closed_at=timezone.now()
        )
    editor = OpenEditor.objects.create(
        draft=draft,
        file=holds.BODY,
        range=WHOLE,
        base_hash=range_hash(body),
        last_seen_at=timezone.now(),
    )
    refusals = validate(body)
    verdict = (
        {"state": "refused", "refusals": [{"code": r.code, "line": r.line} for r in refusals]}
        if refusals
        else {"state": "ok"}
    )
    return JsonResponse(
        {"body": body, "verdict": verdict, "editor": str(editor.pk), "base_hash": editor.base_hash}
    )
