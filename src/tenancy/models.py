"""Tenants, their domains, the platform's hosts and the state history (ADR-0008, ADR-0017)."""

from __future__ import annotations

import uuid
from typing import Any

from django.conf import settings
from django.db import connection, models
from django.db.models import F, Q
from django.db.models.functions import Mod
from django.db.models.lookups import Exact
from django.utils import timezone

from notifications.models import PLATFORM_EVENTS
from syngraphe.provenance import Mutable, Provenanced
from tenancy.schemas import schema_name

NUMBER_SEQUENCE = "tenancy_tenant_number_seq"


class TenantState(models.TextChoices):
    MIGRATING = "migrating", "migrating"
    ACTIVE = "active", "active"
    BLOCKED = "blocked", "blocked"


# A megabyte as the settings count it, and the inactivity timeout's bounds in minutes (DL-0458).
MB = 1024 * 1024
INACTIVITY_LEAST = 5
INACTIVITY_MOST = 480
# The largest cap the column holds (PostgreSQL's `integer`), below a platform maximum set past it.
CAP_STORED_MOST = 2**31 - 1


class Tenant(Mutable):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Platform-wide, in creation order, never reused: it names the schema and the directory
    # (ADR-0008).
    number = models.IntegerField(unique=True, editable=False)
    name = models.CharField(max_length=200)
    schema_name = models.CharField(max_length=63, unique=True, editable=False)
    state = models.CharField(
        max_length=9, choices=TenantState.choices, default=TenantState.MIGRATING
    )
    require_distinct_approver = models.BooleanField(default=False)
    attachment_max_bytes = models.PositiveIntegerField(default=5 * MB)
    hold_inactivity_minutes = models.PositiveIntegerField(default=30)

    class Meta(Mutable.Meta):
        abstract = False
        ordering = ["number"]
        # The settings' stored bounds (DL-0458); the cap's upper bound is the platform's configured
        # upload maximum, which a stored constraint cannot follow, held by the form and the service
        # that save it (DL-0469).
        constraints = [
            *Mutable.Meta.constraints,
            models.CheckConstraint(
                condition=Q(hold_inactivity_minutes__gte=INACTIVITY_LEAST)
                & Q(hold_inactivity_minutes__lte=INACTIVITY_MOST),
                name="tenancy_tenant_inactivity_5_to_480",
            ),
            models.CheckConstraint(
                condition=Q(attachment_max_bytes__gte=MB)
                & Q(Exact(Mod(F("attachment_max_bytes"), MB), 0)),
                name="tenancy_tenant_attachment_cap_whole_mb",
            ),
        ]

    def __str__(self) -> str:
        return f"#{self.number} {self.name}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.number is None:
            with connection.cursor() as cursor:
                cursor.execute("SELECT nextval(%s)", [NUMBER_SEQUENCE])
                self.number = int(cursor.fetchone()[0])
        self.schema_name = schema_name(self.number)
        super().save(*args, **kwargs)


def visited_by_background_work() -> models.QuerySet[Tenant]:
    """The tenants the worker's periodic tasks and the reconciler visit, in number order: every one
    but a tenant still `migrating`, whose schema is not ready to be read."""
    return Tenant.objects.exclude(state=TenantState.MIGRATING).order_by("number")


class TenantDomain(Provenanced):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="domains")
    host = models.CharField(max_length=253, unique=True)
    is_default = models.BooleanField(default=False)

    class Meta(Provenanced.Meta):
        abstract = False
        constraints = [
            *Provenanced.Meta.constraints,
            models.UniqueConstraint(
                fields=["tenant"],
                condition=Q(is_default=True),
                name="one_default_domain_per_tenant",
            ),
        ]

    def __str__(self) -> str:
        return self.host

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.host = self.host.strip().lower()
        super().save(*args, **kwargs)


class PlatformHost(Provenanced):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    host = models.CharField(max_length=253, unique=True)
    is_default = models.BooleanField(default=False)

    class Meta(Provenanced.Meta):
        abstract = False
        constraints = [
            *Provenanced.Meta.constraints,
            models.UniqueConstraint(
                fields=["is_default"],
                condition=Q(is_default=True),
                name="one_default_platform_host",
            ),
        ]

    def __str__(self) -> str:
        return self.host

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.host = self.host.strip().lower()
        super().save(*args, **kwargs)


class TenantStateHistory(models.Model):
    """One row per change of a tenant's state; `by` is empty when `migrate_schemas` activated it."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="state_history")
    before = models.CharField(max_length=9, choices=TenantState.choices)
    after = models.CharField(max_length=9, choices=TenantState.choices)
    at = models.DateTimeField(default=timezone.now, editable=False)
    by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )

    class Meta:
        ordering = ["at"]

    def __str__(self) -> str:
        return f"{self.tenant_id}: {self.before} → {self.after}"


class PlatformNotification(models.Model):
    """What a platform administrator is told, in the shared schema (DL-0382): platform
    administrators may belong to no organisation, and an entry here names no document. Read
    and written only through `notifications.services`."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    event = models.CharField(max_length=40)
    # Ids and numbers only — never an address, a title or a line of text (DL-0370).
    facts = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    read_at = models.DateTimeField(null=True, blank=True)
    emailed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(event__in=[event.value for event in PLATFORM_EVENTS]),
                name="tenancy_platform_notification_event_known",
            ),
        ]

    def __str__(self) -> str:
        return f"platform notification {self.pk}"
