"""What the platform tells a person, in the application (DL-0070, DL-0204). A notification holds
references and facts about an event, never text of a document (DL-0113, DL-0205).
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Category(models.TextChoices):
    DOCUMENT = "document", "document"
    ADMINISTRATIVE = "administrative", "administrative"


class Event(models.TextChoices):
    CORRECTION_NOTICE = "correction_notice", "correction_notice"


class Notification(models.Model):
    """One event for one person. The row carries its own facts — who, when, read, emailed — so it
    takes no provenance columns."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    document = models.ForeignKey("documents.Document", on_delete=models.PROTECT, related_name="+")
    category = models.CharField(max_length=14, choices=Category.choices)
    event = models.CharField(max_length=40, choices=Event.choices)
    version = models.ForeignKey(
        "documents.Version", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    # One notification per notice (ADR-0014).
    correction_notice = models.OneToOneField(
        "review.CorrectionNotice",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="notification",
    )
    created_at = models.DateTimeField(default=timezone.now)
    read_at = models.DateTimeField(null=True, blank=True)
    emailed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(event__in=Event.values), name="notifications_event_known"
            ),
            models.CheckConstraint(
                condition=Q(category__in=Category.values), name="notifications_category_known"
            ),
            models.CheckConstraint(
                condition=~Q(event=Event.CORRECTION_NOTICE) | Q(correction_notice__isnull=False),
                name="notifications_correction_notice_names_its_notice",
            ),
        ]

    def __str__(self) -> str:
        return f"notification {self.pk}"
