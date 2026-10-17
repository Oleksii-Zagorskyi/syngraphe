"""The draft as an editor opens it: `load` opens an editor on the whole draft or on one section of
it (ADR-0006), recording it as an open editor with the hash of the range it saw, and hands it that
range's text, the validator's verdict and the draft's declared roles, actions and terms, which
*Mark* offers."""

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
from editing import holds, sections, services
from editing.markdown.validator import validate
from editing.models import OpenEditor
from editing.views.edit_tab import editable
from shell.views import not_found

OPEN_EDITORS_MOST = 5
LOAD_LOCK_SECONDS = 10


def range_hash(text: str) -> str:
    """The hash an editor keeps of the range it saw: SHA-256 over its UTF-8 bytes."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _range(request: HttpRequest) -> str | None:
    """The range the editor asks for — `whole`, the default, or `section:<ordinal>`; `None` for
    anything else."""
    data: Any = {}
    if request.content_type == "application/json":
        try:
            data = json.loads(request.body or b"{}")
        except (ValueError, RecursionError):
            return None
    asked = data.get("range", sections.WHOLE) if isinstance(data, dict) else sections.WHOLE
    if asked == sections.WHOLE:
        return sections.WHOLE
    return asked if isinstance(asked, str) and sections.ordinal_of(asked) is not None else None


@never_cache
@login_required
def load(request: HttpRequest, number: int) -> HttpResponse:
    """For the holder alone: a new open editor on the whole body or on one section, and that
    range's text with its verdict — `ok`, or `refused` with each refusal's code and line — and the
    draft's declarations. The
    whole-document editor is refused while a section editor is open, `409 {"sections_open": n}`,
    and a section editor while the whole one is, `409 {"whole_open": true}` (ADR-0006)."""
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
    declared = _declared(editor.draft)
    verdict = (
        {"state": "refused", "refusals": [{"code": r.code, "line": r.line} for r in refusals]}
        if refusals
        else {"state": "ok"}
    )
    return JsonResponse(
        {
            "body": body,
            "verdict": verdict,
            "editor": str(editor.pk),
            "base_hash": editor.base_hash,
            "range": editor.range,
            # The picker offers the draft's own declarations (DL-0073).
            "entities": declared,
        }
    )


def _declared(draft: Any) -> list[dict[str, str]]:
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
    """A new open editor on the holder's draft over `asked` of `file` — the body, or an appendix
    the draft lists — and the text it saw; the refusal when the whole and a section of one file
    would be open at once, when a section's lines are another open editor's, or past the most
    section editors open at once on the draft, every file counted; `409` *closed* for an appendix
    the draft no longer lists; `None` for anyone else, or a section the text does not have."""
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
    still_open = OpenEditor.objects.filter(draft=draft, closed_at__isnull=True)
    same_file = still_open.filter(file=file)
    if asked == sections.WHOLE:
        open_sections = same_file.exclude(range=sections.WHOLE).count()
        if open_sections:
            return JsonResponse({"sections_open": open_sections}, status=409)
        # The holder's tabs each open a whole editor; past a few, the oldest of the file's are
        # closed — a capture from one would be refused as stale anyway once another has captured.
        # Section editors are never closed for another: each may hold text no other has.
        whole_ids = list(same_file.order_by("-last_seen_at").values_list("pk", flat=True))
        if len(whole_ids) >= OPEN_EDITORS_MOST:
            OpenEditor.objects.filter(pk__in=whole_ids[OPEN_EDITORS_MOST - 1 :]).update(
                closed_at=timezone.now()
            )
        text = body
    else:
        found = sections.ranges(body)
        ordinal = sections.ordinal_of(asked)
        if ordinal is None or ordinal >= len(found):
            return None
        if same_file.filter(range=sections.WHOLE).exists():
            return JsonResponse({"whole_open": True}, status=409)
        wanted = found[ordinal]
        # Two editors over the same section — two tabs — are the case capture settles: the later
        # stops, its text kept (ADR-0006). A parent and its subsection open at once would stop
        # each other over lines neither page shows whole, so they are refused.
        for other in same_file:
            span = sections.span_of(other.range)
            covered = sections.extent(body, *span) if span is not None else None
            same = covered is not None and (covered.start, covered.end) == (
                wanted.start,
                wanted.end,
            )
            if (
                covered is not None
                and not same
                and covered.start < wanted.end
                and wanted.start < covered.end
            ):
                return JsonResponse({"overlaps": True}, status=409)
        # At most so many section editors on the draft, whatever file each is on (DL-0418).
        if still_open.exclude(range=sections.WHOLE).count() >= OPEN_EDITORS_MOST:
            return JsonResponse({"too_many": True}, status=409)
        text = sections.section_text(body, wanted)
        # The editor spans its subsections too; its range says how many headings it holds.
        asked = sections.span_name(ordinal, sections.headings_in(text))
    editor = OpenEditor.objects.create(
        draft=draft,
        file=file,
        range=asked,
        base_hash=range_hash(text),
        last_seen_at=timezone.now(),
    )
    return editor, text
