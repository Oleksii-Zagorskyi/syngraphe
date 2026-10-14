"""The sending address and the outbox (DL-0202, DL-0203, DL-0368, DL-0371). The app is on both
schema lists (ADR-0017): a tenant's own sender and its mail live in its schema, the platform's in
the shared one, and the shared rows are reached only with the shared schema alone (DL-0367)."""

from __future__ import annotations

import uuid

from django.db import models
from django.db.models import Q
from django.utils import timezone


class Security(models.TextChoices):
    """How the connection to the sending server is made (DL-0371)."""

    STARTTLS = "starttls", "starttls"
    TLS = "tls", "tls"
    NONE = "none", "none"


class Status(models.TextChoices):
    QUEUED = "queued", "queued"
    SENT = "sent", "sent"
    FAILED = "failed", "failed"


class Kind(models.TextChoices):
    """What an email carries: a notification's, an invitation's link, or a reset's link — the last
    left out of an organisation's own outbox page (DL-0410)."""

    NOTIFICATION = "notification", "notification"
    INVITATION = "invitation", "invitation"
    RESET = "reset", "reset"


class MailSender(models.Model):
    """The schema's one sending address, or none. The password is held only encrypted, under a
    key the environment supplies (`mail.secrets`); it is never read back into a page."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    host = models.CharField(max_length=253)
    port = models.PositiveIntegerField()
    address = models.EmailField(max_length=254)
    display_name = models.CharField(max_length=100, blank=True)
    username = models.CharField(max_length=254, blank=True)
    password_encrypted = models.BinaryField(blank=True)
    security = models.CharField(max_length=8, choices=Security.choices, default=Security.STARTTLS)
    # One test at a time (DL-0392): when the last was asked for, when it answered, and what.
    last_test_requested_at = models.DateTimeField(null=True, blank=True)
    last_test_at = models.DateTimeField(null=True, blank=True)
    last_test_result = models.TextField(blank=True)
    # One row at most per schema: every row holds the same value of a unique column.
    one = models.BooleanField(default=True, editable=False, unique=True)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(one=True), name="mail_one_sender_per_schema"),
            models.CheckConstraint(
                condition=Q(security__in=Security.values), name="mail_sender_security_known"
            ),
            models.CheckConstraint(
                condition=Q(port__gte=1) & Q(port__lte=65535), name="mail_sender_port_in_range"
            ),
        ]

    def __str__(self) -> str:
        return f"sender {self.pk}"


class EmailOutbox(models.Model):
    """Every email, written before any attempt to send it, and the log of what was sent
    (DL-0203). `notification_id` names the notification of the same schema it carries — a
    `Notification` in a tenant's, a `PlatformNotification` in the shared one — without a
    constraint, since neither notification table is in both schemas."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenancy.Tenant", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    sender = models.EmailField(max_length=254)
    recipient = models.EmailField(max_length=254)
    subject = models.CharField(max_length=255)
    body = models.TextField()
    status = models.CharField(max_length=6, choices=Status.choices, default=Status.QUEUED)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    notification_id = models.UUIDField(null=True, blank=True)
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.NOTIFICATION)

    class Meta:
        indexes = [models.Index(fields=["status", "next_attempt_at"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=Status.values), name="mail_outbox_status_known"
            ),
            models.CheckConstraint(
                condition=Q(kind__in=Kind.values), name="mail_outbox_kind_known"
            ),
        ]

    def __str__(self) -> str:
        return f"email {self.pk}"
