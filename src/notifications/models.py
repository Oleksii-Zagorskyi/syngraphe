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
    """Every event a notification can record; an act that adds one adds its value here and
    rebuilds the constraints in a migration of its own."""

    CORRECTION_NOTICE = "correction_notice", "correction_notice"
    VERSION_COMMITTED = "version_committed", "version_committed"
    ACCEPTED = "accepted", "accepted"
    FROZEN = "frozen", "frozen"
    UNFROZEN = "unfrozen", "unfrozen"
    MADE_CANONICAL = "made_canonical", "made_canonical"
    ACCESS_GRANTED = "access_granted", "access_granted"
    DOCUMENT_CREATED = "document_created", "document_created"
    DOCUMENT_COPIED = "document_copied", "document_copied"
    BACKUP_CONDITION = "backup_condition", "backup_condition"
    EMAIL_FAILED = "email_failed", "email_failed"
    USER_PARTIALLY_BLOCKED = "user_partially_blocked", "user_partially_blocked"
    TENANT_WITHOUT_ADMIN = "tenant_without_admin", "tenant_without_admin"
    RESERVATION_STARTED = "reservation_started", "reservation_started"
    RESERVATION_ENDED_BY_ADMIN = "reservation_ended_by_admin", "reservation_ended_by_admin"
    HOLD_EXPIRING = "hold_expiring", "hold_expiring"
    RETURNED = "returned", "returned"
    # Epic 10: the holder of a hold or reservation archiving ended (DL-0471).
    DOCUMENT_ARCHIVED = "document_archived", "document_archived"


# What platform administrators are told in the shared schema (DL-0382); `email_failed` also
# reaches an organisation's administrators in its own.
PLATFORM_EVENTS = (
    Event.BACKUP_CONDITION,
    Event.EMAIL_FAILED,
    Event.USER_PARTIALLY_BLOCKED,
    Event.TENANT_WITHOUT_ADMIN,
)


class Notification(models.Model):
    """One event for one person. The row carries its own facts — who, when, read, emailed — so it
    takes no provenance columns."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    # Empty where the event concerns no document: a failed email, a group, the backup (DL-0367).
    document = models.ForeignKey(
        "documents.Document", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
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
    # Ids and numbers only — never an address, a title or a line of text (DL-0370).
    facts = models.JSONField(default=dict, blank=True)
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
            # Epic 10: the archived holder's notice names no document they may no longer open,
            # only its number in the facts (DL-0471).
            models.CheckConstraint(
                condition=Q(category=Category.ADMINISTRATIVE)
                | Q(document__isnull=False)
                | Q(event=Event.DOCUMENT_ARCHIVED),
                name="notifications_document_event_names_its_document",
            ),
        ]

    def __str__(self) -> str:
        return f"notification {self.pk}"
