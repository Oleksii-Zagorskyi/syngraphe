"""Tenants, their domains, the platform's hosts and the state history (ADR-0008, ADR-0017)."""

from __future__ import annotations

import uuid
from typing import Any

from django.conf import settings
from django.db import connection, models
from django.db.models import Q
from django.utils import timezone

from syngraphe.provenance import Mutable, Provenanced
from tenancy.schemas import schema_name

NUMBER_SEQUENCE = "tenancy_tenant_number_seq"


class TenantState(models.TextChoices):
    MIGRATING = "migrating", "migrating"
    ACTIVE = "active", "active"
    BLOCKED = "blocked", "blocked"


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
    attachment_max_bytes = models.PositiveIntegerField(default=5 * 1024 * 1024)
    hold_inactivity_minutes = models.PositiveIntegerField(default=30)

    class Meta(Mutable.Meta):
        abstract = False
        ordering = ["number"]

    def __str__(self) -> str:
        return f"#{self.number} {self.name}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.number is None:
            with connection.cursor() as cursor:
                cursor.execute("SELECT nextval(%s)", [NUMBER_SEQUENCE])
                self.number = int(cursor.fetchone()[0])
        self.schema_name = schema_name(self.number)
        super().save(*args, **kwargs)


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
