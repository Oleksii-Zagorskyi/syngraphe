"""Freezes and editions (DL-0189, DL-0260).

A freeze is a state of the document: a `FREEZE` row with no end means it is frozen. An edition is a
canonical version: derived from the approval's passport commit, which is the record, and tagged.
Like `ACCEPTANCE`, the tables carry their own facts under the data model's names, not the
provenance columns.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models
from django.db.models import F, Q

if TYPE_CHECKING:
    from documents.models import Document

# One line, as a version's summary (DL-0353).
REASON_MAX = 500


class FreezeEnd(models.TextChoices):
    MADE_CANONICAL = "made_canonical", "made_canonical"
    UNFROZEN = "unfrozen", "unfrozen"


class Freeze(models.Model):
    """One freeze of a document, from `frozen_at` until *make canonical* or *unfreeze* ends it."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        "documents.Document", on_delete=models.PROTECT, related_name="freezes"
    )
    reason = models.CharField(max_length=REASON_MAX, blank=True)
    frozen_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    frozen_at = models.DateTimeField()
    ended_by_kind = models.CharField(max_length=14, choices=FreezeEnd.choices, blank=True)
    # Who ended it; empty when an operator ended it from the command line.
    ended_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["document"],
                condition=Q(ended_at__isnull=True),
                name="editions_one_open_freeze_per_document",
            ),
            models.CheckConstraint(
                condition=(Q(ended_at__isnull=True) & Q(ended_by_kind=""))
                | (Q(ended_at__isnull=False) & ~Q(ended_by_kind="")),
                name="editions_freeze_ends_with_its_kind",
            ),
            models.CheckConstraint(
                condition=Q(ended_at__isnull=True) | Q(ended_at__gte=F("frozen_at")),
                name="editions_freeze_ends_after_it_begins",
            ),
        ]

    def __str__(self) -> str:
        return f"freeze of #{self.document_id}"


class Edition(models.Model):
    """One canonical edition, `N.0` (DL-0183): the accepted content version it made canonical and
    the tagged passport commit that records the approval."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # The accepted content version made canonical.
    version = models.OneToOneField(
        "documents.Version", on_delete=models.PROTECT, related_name="edition"
    )
    # The passport commit, kind `approval`, tagged with the number.
    approval_version = models.OneToOneField(
        "documents.Version", on_delete=models.PROTECT, related_name="approval"
    )
    freeze = models.OneToOneField(Freeze, on_delete=models.PROTECT, related_name="edition")
    number = models.CharField(max_length=21)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    approved_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(number__regex=r"^[1-9][0-9]{0,9}\.0$"),
                name="editions_edition_number_is_n_0",
            )
        ]

    def __str__(self) -> str:
        return f"edition {self.number}"


def open_freeze(document: Document) -> Freeze | None:
    """The document's freeze while it lasts, or `None`. A freeze an edition already records is
    over whatever its row says; the reconciler ends it (`edition_unfinished`)."""
    return (
        Freeze.objects.filter(document=document, ended_at__isnull=True, edition__isnull=True)
        .select_related("frozen_by")
        .first()
    )
