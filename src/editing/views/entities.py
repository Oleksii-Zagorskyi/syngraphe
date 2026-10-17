"""Declaring a role, an action or a term in the holder's draft (DL-0073): the picker's *Declare a
new one*. The draft's `entities.yaml` gains the declaration under the writer lock, as an image is
staged; the commit writes it with the rest of the draft.
"""

from __future__ import annotations

import unicodedata
from typing import Any, cast

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache

from audit.record import record
from documents import entities, gitstore
from documents.locks import LockTimeout, document_lock
from editing import holds, services
from editing.messages import NOTICES
from editing.models import Draft, Hold
from editing.views import capture, images
from editing.views.edit_tab import editable
from identity.models import User
from shell.views import not_found
from tenancy.models import Tenant


def listed(declared: list[entities.Declared]) -> list[dict[str, str]]:
    """Declarations as the picker reads them."""
    return [{"kind": e.kind, "key": e.key, "label": e.label} for e in declared]


def _next_key(kind: str, taken: set[str]) -> str:
    """The kind and the first number no key in `taken` holds."""
    number = 1
    while f"{kind}-{number}" in taken:
        number += 1
    return f"{kind}-{number}"


def _typed(label: str) -> bool:
    """A label a person types: one printable line of 1 to 200 characters, with something to see
    in it and no control that turns the text around it (DL-0378)."""
    from editions.services import BIDI_CONTROLS

    return (
        entities.valid_label(label)
        and not any(ch in BIDI_CONTROLS for ch in label)
        and any(unicodedata.category(ch) != "Cf" for ch in label)
    )


@never_cache
@login_required
def declare(request: HttpRequest, number: int) -> HttpResponse:
    """The holder's declaration: `200` with its key and the draft's declarations — the key a label
    of that kind already has, in any capitals, when it has one, a span's included; `400`
    *refused* with the rule a kind or a label breaks, or when the file holds as many as the
    platform accepts, nothing written; `409` *closed* with how the hold ended, to the editor the
    request names (`editor`), as an upload answers it; `503` while the document is being
    committed."""
    document = editable(request, number)
    if document is None or request.method != "POST":
        return not_found(request)
    user = cast(User, request.user)
    hold = holds.open_hold(document)
    if hold is None or hold.user_id != user.pk:
        return images.closed_answer(document, user, request.POST.get("editor")) or not_found(
            request
        )
    kind = request.POST.get("kind", "")
    label = " ".join(request.POST.get("label", "").split())
    if kind not in entities.KINDS:
        return JsonResponse({"refused": str(NOTICES["entity_kind"])}, status=400)
    if not _typed(label):
        return JsonResponse({"refused": str(NOTICES["entity_label"])}, status=400)
    # The keys the editor's own text holds, captured or not yet, are as taken as the draft's.
    shown = {key for key in request.POST.get("taken", "").split() if entities.KEY.fullmatch(key)}
    tenant_number = holds.tenant_number()
    try:
        with document_lock(tenant_number, number, timeout=capture.CAPTURE_LOCK_SECONDS):
            with transaction.atomic():
                return _declare_locked(document, hold, user, kind, label, shown, tenant_number)
    except LockTimeout:
        return JsonResponse({"busy": True}, status=503)


def _declare_locked(
    document: Any,
    hold: Hold,
    user: User,
    kind: str,
    label: str,
    shown: set[str],
    tenant_number: int,
) -> JsonResponse:
    locked = Hold.objects.select_for_update(of=("self",)).filter(pk=hold.pk).first()
    if locked is None or locked.released_at is not None:
        released = locked.release_kind if locked is not None else ""
        return JsonResponse({"closed": True, "released": released}, status=409)
    draft = Draft.objects.select_for_update(of=("self",)).get(hold=locked)
    repo = gitstore.open_repository(tenant_number, document.number)
    head = gitstore.head(repo) or draft.base_commit
    own = entities.parse(holds.draft_entities(draft, repo, head))
    # A new declaration takes no key the commit will declare or a span holds, and a label a span
    # already reads as, in any capitals, is that span's entity.
    found = services.draft_declarations(draft, repo, head, document, own)
    committed = found.committed
    # The same label in other capitals is the same entity (DL-11-013); its first form stands.
    wanted = label.casefold()
    same = next((e for e in committed if e.kind == kind and e.label.casefold() == wanted), None)
    if same is not None:
        return JsonResponse({"key": same.key, "entities": listed(committed)})
    added = entities.Declared(kind, _next_key(kind, found.keys | shown), label)
    text = entities.dump([*own, added])
    if len(text.encode("utf-8")) > entities.MAX_BYTES:
        return JsonResponse({"refused": str(NOTICES["entities_full"])}, status=400)
    draft.content = {**draft.content, holds.ENTITIES: text}
    draft.save(update_fields=["content", "updated_at"])
    # Declaring is working on the draft, as typing is.
    Hold.objects.filter(pk=locked.pk).update(last_activity_at=timezone.now())
    record(
        actor=user,
        action="entity.declared",
        obj=document,
        before=None,
        after={"number": document.number, "kind": kind, "key": added.key},
        tenant=Tenant.objects.get(number=tenant_number),
    )
    return JsonResponse({"key": added.key, "entities": listed([*committed, added])})
