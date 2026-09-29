"""Whether someone holds a document for editing (ADR-0006).

No code opens a hold yet, so this answers `False`; every check that must refuse while a document
is held already calls it. The contract a hold keeps: it is opened only while the document's row is
locked with `select_for_update()`, the lock under which its links change (ADR-0007).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from documents.models import Document


def is_held(document: Document) -> bool:
    """`True` while an open hold exists on `document`."""
    return False
