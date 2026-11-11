"""The draft as an editor opens it: `load` opens an editor on the whole draft (ADR-0006,
DL-0517), recording it as an open editor with the hash of the text it saw, and hands it that
text, the validator's verdict and the draft's declared roles, actions and terms, which *Mark*
offers."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache

from documents import entities, gitstore
from documents.locks import LockTimeout, document_lock
from documents.models import Document
from editing import holds, services
from editing.markdown.validator import validate
from editing.models import OpenEditor
from editing.views.edit_tab import editable
from shell.views import not_found

OPEN_EDITORS_MOST = 5
# The one range an editor opens: the whole text (DL-0517). The column keeps it.
WHOLE = "whole"
LOAD_LOCK_SECONDS = 10


def range_hash(text: str) -> str:
    """The hash an editor keeps of the range it saw: SHA-256 over its UTF-8 bytes."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _asked(request: HttpRequest) -> dict[str, Any] | None:
    """The editor's JSON ask; empty for none, `None` for one that does not read."""
    if request.content_type != "application/json":
        return {}
    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, RecursionError):
        return None
    return data if isinstance(data, dict) else {}


def _range(request: HttpRequest) -> str | None:
    """The range the editor asks for — `whole`, the default and the only one (DL-0517); `None`
    for anything else."""
    data = _asked(request)
    if data is None:
        return None
    return WHOLE if data.get("range", WHOLE) == WHOLE else None


def _declarations_asked(request: HttpRequest) -> bool:
    """Whether the editor asks for the draft's declarations: always, unless its page handed them
    over already (`"entities": false`), read from the same pass over the draft that page made."""
    return (_asked(request) or {}).get("entities", True) is not False


@never_cache
@login_required
def load(request: HttpRequest, number: int) -> HttpResponse:
    """For the holder alone: a new open editor on the whole body, its text with its verdict — `ok`,
    or `refused` with each refusal's code and line — and the draft's declarations."""
    document = editable(request, number)
    asked = _range(request)
    if document is None or request.method != "POST" or asked is None:
        return not_found(request)
    return opened_on(request, document, asked, holds.BODY)


def opened_on(request: HttpRequest, document: Document, asked: str, file: str) -> HttpResponse:
    """`load`'s answer for an editor over `asked` of `file` — the body, or an appendix's text."""
    try:
        # Under the writer lock, so no editor opens on a draft a commit is consuming; the body's
        # verdict, which costs seconds at the ceiling, is reached after the lock is released.
        with document_lock(holds.tenant_number(), document.number, timeout=LOAD_LOCK_SECONDS):
            opened = _open(request, document, asked, file=file)
    except LockTimeout:
        return JsonResponse({"busy": True}, status=503)
    if opened is None:
        return not_found(request)
    if isinstance(opened, HttpResponse):
        return opened
    editor, body = opened
    refusals = validate(body)
    verdict = (
        {"state": "refused", "refusals": [{"code": r.code, "line": r.line} for r in refusals]}
        if refusals
        else {"state": "ok"}
    )
    answer: dict[str, Any] = {
        "body": body,
        "verdict": verdict,
        "editor": str(editor.pk),
        "base_hash": editor.base_hash,
        "range": editor.range,
    }
    if _declarations_asked(request):
        # The picker offers the draft's own declarations (DL-0073).
        answer["entities"] = offered(editor.draft)
    return JsonResponse(answer)


def offered(draft: Any) -> list[dict[str, str]]:
    """What the picker offers, as declaring answers it: the declarations the commit of the draft
    will write; none for a file that does not read as one."""
    document = draft.hold.document
    repo = gitstore.open_repository(holds.tenant_number(), document.number)
    head = gitstore.head(repo) or draft.base_commit
    own = entities.readable(holds.draft_entities(draft, repo, head), document.number)
    if own is None:
        return []
    found = services.draft_declarations(draft, repo, head, document, own)
    return [{"kind": e.kind, "key": e.key, "label": e.label} for e in found.committed]


def _open(
    request: HttpRequest, document: Document, asked: str, *, file: str = holds.BODY
) -> tuple[OpenEditor, str] | HttpResponse | None:
    """A new open editor on the holder's draft over the whole of `file` — the body, or an appendix
    the draft lists — and the text it saw; `409` *closed* for an appendix the draft no longer
    lists; `None` for anyone else."""
    from editing import parts

    hold = holds.open_hold(document)
    if hold is None or hold.user_id != request.user.pk:
        return None
    draft = hold.draft
    if file == holds.BODY:
        body: str = draft.content[holds.BODY]
    else:
        number = parts.number_of(file)
        if number is None or not parts.lists(draft, number):
            return JsonResponse({"closed": True}, status=409)
        body = parts.appendix_text(draft, number)
    # The holder's tabs each open an editor; past a few, the oldest of the file's are closed — a
    # capture from one would be refused as stale anyway once another has captured (ADR-0006).
    same_file = OpenEditor.objects.filter(draft=draft, closed_at__isnull=True, file=file)
    still = list(same_file.order_by("-last_seen_at").values_list("pk", flat=True))
    if len(still) >= OPEN_EDITORS_MOST:
        OpenEditor.objects.filter(pk__in=still[OPEN_EDITORS_MOST - 1 :]).update(
            closed_at=timezone.now()
        )
    text = body
    editor = OpenEditor.objects.create(
        draft=draft,
        file=file,
        range=asked,
        base_hash=range_hash(text),
        last_seen_at=timezone.now(),
    )
    return editor, text
