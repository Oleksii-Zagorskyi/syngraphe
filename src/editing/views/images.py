"""Images in a draft (DL-0232, DL-0439): the holder's upload, checked and staged beside the draft's
text until the commit, and the draft's images served to the person whose draft it is.
"""

from __future__ import annotations

import hashlib
import re
from typing import cast

import pygit2
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache

from audit.record import record
from documents import gitstore
from documents import images as tree_images
from documents.locks import LockTimeout, document_lock
from documents.models import Document
from editing import holds
from editing import images as checks
from editing.messages import NOTICES
from editing.models import Draft, DraftFile, DraftFileKind, DraftFileOperation, Hold, OpenEditor
from editing.views import capture
from editing.views.edit_tab import editable
from identity.models import User
from shell.views import not_found
from tenancy.models import Tenant

# A description is one line of printable text; the brackets and the backslash would end it early
# in the stored form.
UNPRINTABLE = re.compile(r"[\x00-\x1f\x7f-\x9f  \[\]\\]+")
ALT_MAX = 200


def _description(file_name: str) -> str:
    """The file's name without its extension, as the image's first description."""
    stem = file_name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    stem = stem.rsplit(".", 1)[0] if "." in stem else stem
    return " ".join(UNPRINTABLE.sub(" ", stem).split())[:ALT_MAX].strip()


def _refusal(refused: checks.ImageRefused) -> str:
    """The editor's line for a refused image, naming its rule and its limit."""
    key = f"image_refused_{refused.code}"
    if refused.code == "dimensions" and not refused.params.get("width"):
        key = "image_refused_dimensions_unknown"
    params = {**refused.params, "megapixels": checks.MAX_PIXELS // 1_000_000}
    return str(NOTICES[key]) % params


def _released(document: Document, user: User, editor_id: object) -> HttpResponse | None:
    """`409` *closed* with how the hold was released, for the person whose hold ended under the
    editor the upload names — as a capture answers it (DL-11-001); `None` otherwise."""
    if not isinstance(editor_id, str):
        return None
    try:
        editor = (
            OpenEditor.objects.filter(
                pk=editor_id,
                draft__hold__document=document,
                draft__hold__user_id=user.pk,
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


def _open_editor(hold: Hold, editor_id: object) -> OpenEditor | None:
    """The editor of the hold's draft the upload names, as a capture names it; `None` for none."""
    if not isinstance(editor_id, str):
        return None
    try:
        return OpenEditor.objects.filter(pk=editor_id, draft__hold=hold).first()
    except (ValueError, ValidationError):
        return None


@never_cache
@login_required
def upload(request: HttpRequest, number: int) -> HttpResponse:
    """The holder's image, checked before any lock and staged in their draft under the writer
    lock: `200` with its stored path and a first description; `400` *refused* with the rule it
    breaks; `409` *closed* once the hold has ended; `503` while the document is being committed."""
    document = editable(request, number)
    if document is None or request.method != "POST":
        return not_found(request)
    user = cast(User, request.user)
    hold = holds.open_hold(document)
    editor_id = request.POST.get("editor")
    if hold is None or hold.user_id != user.pk:
        return _released(document, user, editor_id) or not_found(request)
    editor = _open_editor(hold, editor_id)
    if editor is None:
        return _released(document, user, editor_id) or not_found(request)
    if editor.closed_at is not None:
        return JsonResponse({"closed": True}, status=409)
    files = request.FILES.getlist("file")
    if len(files) != 1:
        return JsonResponse({"refused": str(NOTICES["image_refused_one"])}, status=400)
    chosen = files[0]
    if chosen.size is None or chosen.size > checks.limit():
        refused = checks.ImageRefused("too_large", {"limit_mb": checks.limit() // (1024 * 1024)})
        return JsonResponse({"refused": _refusal(refused)}, status=400)
    try:
        checked = checks.check(chosen.read())
    except checks.ImageRefused as refused:
        return JsonResponse({"refused": _refusal(refused)}, status=400)
    digest = hashlib.sha256(checked.data).hexdigest()
    path = f"{tree_images.FOLDER}/{digest}.{checked.ext}"
    tenant_number = holds.tenant_number()
    try:
        with document_lock(tenant_number, number, timeout=capture.CAPTURE_LOCK_SECONDS):
            with transaction.atomic():
                locked = Hold.objects.select_for_update(of=("self",)).filter(pk=hold.pk).first()
                if locked is None or locked.released_at is not None:
                    released = locked.release_kind if locked is not None else ""
                    return JsonResponse({"closed": True, "released": released}, status=409)
                draft = Draft.objects.select_for_update(of=("self",)).get(hold=locked)
                if OpenEditor.objects.filter(pk=editor.pk, closed_at__isnull=False).exists():
                    return JsonResponse({"closed": True}, status=409)
                now = timezone.now()
                if not draft.files.filter(kind=DraftFileKind.IMAGE, path=path).exists():
                    DraftFile.objects.create(
                        draft=draft,
                        kind=DraftFileKind.IMAGE,
                        path=path,
                        operation=DraftFileOperation.ADD,
                        content=checked.data,
                        file_name=chosen.name or "",
                        sha256=digest,
                        at=now,
                    )
                # Uploading is working on the draft, as typing is.
                Hold.objects.filter(pk=locked.pk).update(last_activity_at=now)
                record(
                    actor=user,
                    action="image.uploaded",
                    obj=document,
                    before=None,
                    after={"number": document.number, "path": path, "bytes": len(checked.data)},
                    tenant=Tenant.objects.get(number=tenant_number),
                )
    except LockTimeout:
        return JsonResponse({"busy": True}, status=503)
    return JsonResponse({"src": path, "alt": _description(chosen.name or "")})


@never_cache
@login_required
def draft_image(request: HttpRequest, number: int, name: str) -> HttpResponse:
    """An image of the person's own draft — the open hold's, else the one kept for them: staged in
    it, or held by the commit it was taken from, whose text the person was shown, so a paragraph
    cut and pasted back shows its image again (DL-0439: a tree holds only the images its text
    shows). Nobody else's, and nothing once their *edit* right is gone or the document is
    archived."""
    document = editable(request, number)
    if document is None or request.method != "GET" or not tree_images.NAME.fullmatch(name):
        return not_found(request)
    user = cast(User, request.user)
    hold = holds.open_hold(document)
    draft = (
        Draft.objects.filter(hold=hold).first()
        if hold is not None and hold.user_id == user.pk
        else holds.preserved_draft(document, user)
    )
    if draft is None:
        return not_found(request)
    path = f"{tree_images.FOLDER}/{name}"
    staged = (
        draft.files.filter(kind=DraftFileKind.IMAGE, path=path, content__isnull=False)
        .values_list("content", flat=True)
        .first()
    )
    if staged is not None:
        return tree_images.served(bytes(staged), name)
    try:
        repo = gitstore.open_repository(holds.tenant_number(), document.number)
        data = gitstore.read(repo, path, draft.base_commit)
    except (LookupError, ValueError, OSError, UnicodeDecodeError, pygit2.GitError):
        # A file or a repository that does not read shows nothing.
        return not_found(request)
    return tree_images.served(data, name)
