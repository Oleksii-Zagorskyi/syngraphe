"""Capture without a Save control (ASR-22, ADR-0006): an open editor posts the text of its range
after a pause, and the server takes it only while the draft's range still hashes to what that
editor last saw; a heartbeat keeps the editor known; the editor closes itself. Every route is the
holder's alone, for an editor of the holder's own draft."""

from __future__ import annotations

import json
import re
from datetime import timedelta
from typing import Any, cast

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache

from documents.locks import LockTimeout, document_lock
from editing import holds, sections
from editing.markdown import load_spec
from editing.models import Draft, Hold, OpenEditor
from editing.views.draft import range_hash
from editing.views.edit_tab import editable
from identity.models import User
from shell.views import not_found

# The pause after the last keystroke before a capture, the heartbeat's period, and how long an
# editor may stay silent before it is closed: two seconds of typing at most are ever lost (ASR-22).
CAPTURE_PAUSE_SECONDS = 0.75
HEARTBEAT_SECONDS = 30
SILENT_AFTER = timedelta(minutes=3)
# A capture waits this long for the document's writer lock — held through a commit of the draft —
# then answers busy, which the editor retries.
CAPTURE_LOCK_SECONDS = 5
# Two line endings in a row at a text's end: the blank line before the next heading.
BLANK_LINE_AT_END = re.compile(r"(?:\r\n|\r|\n){2}$")


def _payload(request: HttpRequest) -> dict[str, Any]:
    """The request's JSON fields; nothing for any other body, which no editor sends."""
    if request.content_type != "application/json":
        return {}
    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, RecursionError):
        return {}
    return data if isinstance(data, dict) else {}


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


def _released(request: HttpRequest, number: int) -> HttpResponse | None:
    """The answer to the holder of a hold released since their editor opened — ended by an
    administrator, by inactivity, by a block: `409` *closed* with how it was released, so the
    editor says so and offers the document back (DL-0225); `None` for anyone else."""
    document = editable(request, number)
    if document is None or request.method != "POST":
        return None
    editor_id = _payload(request).get("editor")
    if not isinstance(editor_id, str):
        return None
    try:
        editor = (
            OpenEditor.objects.filter(
                pk=editor_id,
                draft__hold__document=document,
                draft__hold__user_id=cast(User, request.user).pk,
                draft__hold__released_at__isnull=False,
            )
            .select_related("draft__hold")
            .first()
        )
    except (ValueError, ValidationError):
        return None
    if editor is None:
        return None
    return JsonResponse({"closed": True, "released": editor.draft.hold.release_kind}, status=409)


def text_of(draft: Draft, file: str) -> str | None:
    """The text an editor of `file` edits in `draft` — the body, or an appendix the draft lists;
    `None` for an appendix it no longer lists, whose editor writes nothing more."""
    from editing import parts

    if file == holds.BODY:
        return str(draft.content[holds.BODY])
    number = parts.number_of(file)
    if number is None or not parts.lists(draft, number):
        return None
    return parts.appendix_text(draft, number)


def _gone(editor: OpenEditor, now: Any) -> HttpResponse:
    """The editor's appendix is no longer in the draft: it is closed, and says so."""
    OpenEditor.objects.filter(pk=editor.pk, closed_at__isnull=True).update(closed_at=now)
    return JsonResponse({"closed": True}, status=409)


def idle(hold: Hold, tenant: Any) -> bool:
    """Whether `hold` is idle: not reserved, and no activity for the organisation's timeout — the
    prompt derived, never stored (DL-0377)."""
    if hold.reserved_at is not None or tenant is None:
        return False
    timeout = timedelta(minutes=tenant.hold_inactivity_minutes)
    return timezone.now() - hold.last_activity_at > timeout


@never_cache
@login_required
def capture(request: HttpRequest, number: int) -> HttpResponse:
    """Take the editor's text when the draft's range still hashes to the editor's base, closing the
    editor too when the body says `close`: `200` with the new hash; `409` *stale* when the draft
    changed elsewhere, *closed* when the editor or the hold was; `413` over the size allowed;
    `503` while the document is being committed.

    The right to edit is decided when the hold is taken, under the document's locks, and again
    when the draft is committed; a capture writes only the holder's own draft under the hold, so
    it checks the hold under the lock, not the right."""
    found = _own_editor(request, number)
    if found is None:
        return _released(request, number) or not_found(request)
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
    gone = renumbered = False
    with transaction.atomic():
        draft = Draft.objects.select_for_update().filter(pk=editor.draft_id).first()
        locked = OpenEditor.objects.select_for_update().filter(pk=editor.pk).first()
        kind = Hold.objects.filter(pk=hold.pk).values_list("release_kind", flat=True).first()
        if kind:
            # Released while this capture waited for the lock: the editor says how.
            return JsonResponse({"closed": True, "released": kind}, status=409)
        if draft is None or locked is None or locked.closed_at is not None:
            return JsonResponse({"closed": True}, status=409)
        text = text_of(draft, locked.file)
        if text is None:
            return _gone(locked, now)
        whole: str = text
        span = sections.span_of(locked.range)
        found = sections.extent(whole, *span) if span is not None else None
        if span is not None and found is None:
            # The headings this editor spans are gone — removed by another editor's text.
            return _stale(locked, now, close)
        current_text = sections.section_text(whole, found) if found is not None else whole
        stored = _kept_apart(body, current_text) if found is not None else body
        current, new = range_hash(current_text), range_hash(stored)
        # The same text again — a retry whose first answer was lost, or the flush a closing page
        # repeats — is accepted as it stands, whatever base the editor sent.
        if current != new:
            if current != base or locked.base_hash != base:
                return _stale(locked, now, close)
            changed = sections.splice(whole, found, stored) if found is not None else stored
            # Each section is within the size allowed; the draft its capture leaves must be too.
            if len(changed.encode("utf-8")) > load_spec().max_bytes:
                return JsonResponse({"too_large": True}, status=413)
            draft.content = {**draft.content, locked.file: changed}
            draft.save(update_fields=["content", "updated_at"])
            Hold.objects.filter(pk=hold.pk).update(last_activity_at=now)
            if span is not None:
                moved = sections.shift(whole, changed, span[0])
                _renumber(locked, span, moved)
                # The page's other *edit* buttons read the sections it drew before this capture:
                # a heading added, removed or moved to another level changes them.
                renumbered = moved != 0 or [r.level for r in sections.ranges(whole)] != [
                    r.level for r in sections.ranges(changed)
                ]
                if not _leads_with_a_heading(stored):
                    # Its own heading is gone: it names no section now, and must not name the
                    # next one. Its text is captured; the editor closes, and the tab says so.
                    close = True
                    gone = True
        locked.base_hash = new
        locked.last_seen_at = now
        if close:
            locked.closed_at = now
        locked.save(update_fields=["range", "base_hash", "last_seen_at", "closed_at"])
    answer: dict[str, Any] = {"base_hash": new}
    if renumbered:
        answer["sections_changed"] = True
    if gone:
        answer["closed"] = True
    return JsonResponse(answer)


def _leads_with_a_heading(text: str) -> bool:
    found = sections.ranges(text)
    return bool(found) and found[0].start == 0


def _stale(locked: OpenEditor, now: Any, close: bool) -> HttpResponse:
    """The range changed underneath the editor. A closing page's stale capture still closes its
    editor, so the holder's other tab is not kept from finishing until the silent-editor sweep."""
    if close:
        locked.closed_at = now
        locked.save(update_fields=["closed_at"])
    return JsonResponse({"stale": True}, status=409)


def _kept_apart(text: str, current: str) -> str:
    """A section's captured text, the blank line that parted it from the next heading kept: the
    editor's serialiser ends a text with one newline, and the section's lines end with two."""
    ending = BLANK_LINE_AT_END.search(current)
    if ending and text and not BLANK_LINE_AT_END.search(text):
        return text.rstrip("\r\n") + ending.group(0)
    return text


def _renumber(editor: OpenEditor, span: tuple[int, int], shift: int) -> None:
    """After a splice that added or removed `shift` headings inside `editor`'s span, in the same
    write: its own span counts them, and every other open editor of the same file whose ordinal
    lies after it still names its heading (ADR-0006)."""
    if not shift:
        return
    ordinal, count = span
    editor.range = sections.span_name(ordinal, max(1, count + shift))
    others = (
        OpenEditor.objects.select_for_update()
        .filter(draft_id=editor.draft_id, file=editor.file, closed_at__isnull=True)
        .exclude(pk=editor.pk)
    )
    for other in others:
        found = sections.span_of(other.range)
        if found is not None and found[0] > ordinal:
            other.range = sections.span_name(found[0] + shift, found[1])
            other.save(update_fields=["range"])


@never_cache
@login_required
def heartbeat(request: HttpRequest, number: int) -> HttpResponse:
    """The editor is still open: `200` with how many *other* editors are open on the draft, which
    decides whether *finish editing* is offered, and whether the hold is idle — the editor then
    asks *are you still working?*; `"active": true` is the answer, which restarts the hold's
    clock as a capture does (DL-0377). `409` when the editor was closed, with how the hold was
    released when it was."""
    found = _own_editor(request, number)
    if found is None:
        return _released(request, number) or not_found(request)
    hold, editor = found
    now = timezone.now()
    if editor.file != holds.BODY:
        from editing import parts

        # The listing alone decides, and the heartbeat writes nothing in the draft: no lock.
        appendix = parts.number_of(editor.file)
        draft = Draft.objects.filter(pk=editor.draft_id).first()
        if draft is None:
            # Finished or discarded in another tab since the editor was read: closed with it.
            return JsonResponse({"closed": True}, status=409)
        if appendix is None or not parts.lists(draft, appendix):
            return _gone(editor, now)
    updated = OpenEditor.objects.filter(pk=editor.pk, closed_at__isnull=True).update(
        last_seen_at=now
    )
    if not updated:
        return JsonResponse({"closed": True}, status=409)
    tenant = getattr(request, "tenant", None)
    # The answer to the prompt, and only while it is asked: no client keeps an ordinary hold
    # for good by answering what was never asked (ADR-0009).
    if _payload(request).get("active") is True and idle(hold, tenant):
        if not Hold.objects.filter(pk=hold.pk, released_at__isnull=True).update(
            last_activity_at=now
        ):
            return _released(request, number) or JsonResponse({"closed": True}, status=409)
        hold.last_activity_at = now
    others = (
        OpenEditor.objects.filter(draft_id=editor.draft_id, closed_at__isnull=True)
        .exclude(pk=editor.pk)
        .count()
    )
    return JsonResponse({"others": others, "prompt": idle(hold, tenant)})


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


@never_cache
@login_required
def changes(request: HttpRequest, number: int) -> HttpResponse:
    """What a stopped editor shows (ADR-0006): the person's unsaved text as changes against its
    range of the draft as it now stands, to carry over by hand, and the way to open the range
    again; the editor's own holder alone. The text is shown as typed where the whitelist refuses
    it, where its lines are gone, and with `alone` — an editor the server closed when its capture
    removed its own heading, whose ordinal names another section now."""
    from django.shortcuts import render
    from django.utils.safestring import mark_safe

    from editing.diffview import render_changes
    from editing.markdown.validator import validate

    found = _own_editor(request, number)
    if found is None:
        return not_found(request)
    _, editor = found
    body = _payload(request).get("body")
    # What capture refuses, this refuses: no NUL or lone surrogate, nothing over the size allowed.
    if not isinstance(body, str) or "\x00" in body:
        return JsonResponse({"refused": True}, status=400)
    try:
        size = len(body.encode("utf-8"))
    except UnicodeEncodeError:
        return JsonResponse({"refused": True}, status=400)
    if size > load_spec().max_bytes:
        return JsonResponse({"too_large": True}, status=413)
    try:
        with document_lock(holds.tenant_number(), number, timeout=CAPTURE_LOCK_SECONDS):
            text = text_of(Draft.objects.get(pk=editor.draft_id), editor.file)
            if text is None:
                return _gone(editor, timezone.now())
    except LockTimeout:
        return JsonResponse({"busy": True}, status=503)
    whole: str = text
    span = sections.span_of(editor.range)
    found_range = sections.extent(whole, *span) if span is not None else None
    context: dict[str, Any] = {"number": number}
    if (span is not None and found_range is None) or _payload(request).get("alone") is True:
        # Its lines are gone from the draft, or its heading went in a capture that closed it: the
        # text alone, nothing to compare it with.
        context["typed"] = body
        html = render(request, "editing/stopped_editor.html", context).content.decode("utf-8")
        return JsonResponse({"html": html})
    current = sections.section_text(whole, found_range) if found_range is not None else whole
    if validate(body) or validate(current):
        context["typed"] = body
    else:
        from rendering import reading

        draft = Draft.objects.get(pk=editor.draft_id)
        document = draft.hold.document
        reader = reading.context(
            request.user,
            document,
            current,
            body,
            images=reading.draft_images(document, draft),
        )
        # Built from text the whitelist accepted, by the renderer that escapes it.
        context["changes"] = mark_safe(  # noqa: S308
            render_changes(current.encode("utf-8"), body.encode("utf-8"), context=reader)
        )
    html = render(request, "editing/stopped_editor.html", context).content.decode("utf-8")
    return JsonResponse({"html": html})
