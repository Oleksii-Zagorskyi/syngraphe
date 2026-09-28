"""The audit event: shared, with a nullable tenant, reachable only by administrators (DL-0082).

Rows are appended and never changed: the migration installs a trigger that refuses an update or a
delete, so the trail is what happened, not what someone later preferred.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models import Q
from django.utils import timezone

from syngraphe.provenance import ActorKind


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenancy.Tenant", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    actor_kind = models.CharField(max_length=6, choices=ActorKind.choices)
    action = models.CharField(max_length=100)
    object_type = models.CharField(max_length=50)
    object_id = models.UUIDField(null=True, blank=True)
    before = models.JSONField(null=True, blank=True, encoder=DjangoJSONEncoder)
    after = models.JSONField(null=True, blank=True, encoder=DjangoJSONEncoder)
    at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["at"]
        indexes = [models.Index(fields=["object_type", "object_id"])]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(actor_kind=ActorKind.SYSTEM, actor__isnull=True)
                    | Q(actor_kind=ActorKind.USER, actor__isnull=False)
                    | Q(actor_kind=ActorKind.AGENT)
                ),
                name="audit_auditevent_actor_matches_kind",
            )
        ]

    def __str__(self) -> str:
        return f"{self.action} {self.object_type} {self.object_id}"
