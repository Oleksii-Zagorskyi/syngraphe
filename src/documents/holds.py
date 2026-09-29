"""Whether someone holds a document for editing (ADR-0006).

A hold is opened only while the document's row is locked with `select_for_update()`, the lock
under which its links change (ADR-0007); `editing.holds` keeps that contract.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.apps import apps

if TYPE_CHECKING:
    from documents.models import Document


def is_held(document: Document) -> bool:
    """`True` while an open hold exists on `document`."""
    # Looked up by name, so this app never imports the editing app as it loads.
    hold = apps.get_model("editing", "Hold")
    return bool(hold.objects.filter(document=document, released_at__isnull=True).exists())


def held_by(document: Document, user: object) -> bool:
    """`True` while `user` holds `document`."""
    hold = apps.get_model("editing", "Hold")
    user_id = getattr(user, "pk", None)
    return user_id is not None and bool(
        hold.objects.filter(document=document, released_at__isnull=True, user_id=user_id).exists()
    )
