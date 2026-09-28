"""Row provenance: every table says who created it and whether the actor was a person or the system.

The abstract bases a model inherits unless its own columns already carry these facts under the
data model's names (DL-0082).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class ActorKind(models.TextChoices):
    USER = "user", "user"
    SYSTEM = "system", "system"
    AGENT = "agent", "agent"


class Provenanced(models.Model):
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        editable=False,
    )
    actor_kind = models.CharField(max_length=6, choices=ActorKind.choices)

    class Meta:
        abstract = True
        constraints = [
            # A system row has no creator and a user row has one; an agent row may have either.
            models.CheckConstraint(
                condition=(
                    Q(actor_kind=ActorKind.SYSTEM, created_by__isnull=True)
                    | Q(actor_kind=ActorKind.USER, created_by__isnull=False)
                    | Q(actor_kind=ActorKind.AGENT)
                ),
                name="%(app_label)s_%(class)s_actor_matches_creator",
            )
        ]


class Mutable(Provenanced):
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        editable=False,
    )

    class Meta(Provenanced.Meta):
        abstract = True
