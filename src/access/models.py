"""Groups, their rights and their members, in the tenant's schema; every change is history
(ADR-0007, ASR-08).

The rows reference people through `public.identity_membership` across the schema boundary; a
membership or a user is never deleted (state and tombstone instead), so the PROTECT relations
are never walked.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.conf import settings
from django.db import connection, models, transaction
from django.db.models import Q
from django.utils import timezone

from access.rights import Right, implied
from syngraphe.provenance import ActorKind, Mutable, Provenanced
from tenancy.schemas import current_tenant


class AccessGroup(Mutable):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)

    class Meta(Mutable.Meta):
        abstract = False
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def rights(self) -> set[Right]:
        """The rights granted, as stored."""
        return {Right(r) for r in self.granted.values_list("right", flat=True)}

    def implied_rights(self) -> frozenset[Right]:
        return implied(self.rights())

    def grant(self, right: Right, *, by: Any) -> None:
        with transaction.atomic():
            _, created = GroupRight.objects.get_or_create(
                group=self, right=right, defaults=_provenance(by)
            )
            if created:
                AccessChange.objects.create(
                    kind=AccessChange.Kind.RIGHT,
                    group=self,
                    right=right,
                    action=AccessChange.Action.ADDED,
                    **_actor(by),
                )

    def revoke(self, right: Right, *, by: Any) -> None:
        with transaction.atomic():
            deleted, _ = GroupRight.objects.filter(group=self, right=right).delete()
            if deleted:
                AccessChange.objects.create(
                    kind=AccessChange.Kind.RIGHT,
                    group=self,
                    right=right,
                    action=AccessChange.Action.REMOVED,
                    **_actor(by),
                )

    def add_member(self, membership: Any, *, by: Any) -> None:
        """Add a member of this organisation; the database cannot check that boundary, this does."""
        if membership.tenant.number != current_tenant(connection):
            raise ValueError("the membership belongs to another organisation")
        with transaction.atomic():
            _, created = GroupMember.objects.get_or_create(
                group=self, membership=membership, defaults=_provenance(by)
            )
            if created:
                AccessChange.objects.create(
                    kind=AccessChange.Kind.MEMBER,
                    group=self,
                    membership=membership,
                    action=AccessChange.Action.ADDED,
                    **_actor(by),
                )

    def remove_member(self, membership: Any, *, by: Any) -> None:
        with transaction.atomic():
            deleted, _ = GroupMember.objects.filter(group=self, membership=membership).delete()
            if deleted:
                AccessChange.objects.create(
                    kind=AccessChange.Kind.MEMBER,
                    group=self,
                    membership=membership,
                    action=AccessChange.Action.REMOVED,
                    **_actor(by),
                )


def _actor(by: Any) -> dict[str, Any]:
    return {"by": by, "actor_kind": ActorKind.SYSTEM if by is None else ActorKind.USER}


def _provenance(by: Any) -> dict[str, Any]:
    return {"created_by": by, "actor_kind": ActorKind.SYSTEM if by is None else ActorKind.USER}


class GroupRight(Provenanced):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    group = models.ForeignKey(AccessGroup, on_delete=models.PROTECT, related_name="granted")
    right = models.CharField(max_length=32, choices=[(r.value, r.value) for r in Right])

    class Meta(Provenanced.Meta):
        abstract = False
        constraints = [
            *Provenanced.Meta.constraints,
            models.UniqueConstraint(fields=["group", "right"], name="one_row_per_group_right"),
        ]

    def __str__(self) -> str:
        return f"{self.group_id}: {self.right}"


class GroupMember(Provenanced):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    group = models.ForeignKey(AccessGroup, on_delete=models.PROTECT, related_name="members")
    membership = models.ForeignKey(
        "identity.Membership", on_delete=models.PROTECT, related_name="groups"
    )

    class Meta(Provenanced.Meta):
        abstract = False
        constraints = [
            *Provenanced.Meta.constraints,
            models.UniqueConstraint(
                fields=["group", "membership"], name="one_row_per_group_member"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.group_id}: {self.membership_id}"


class AccessChange(models.Model):
    """The append-only history of every change to access: who could reach what, on any date."""

    class Kind(models.TextChoices):
        MEMBER = "member", "member"
        RIGHT = "right", "right"
        LINK = "link", "link"

    class Action(models.TextChoices):
        ADDED = "added", "added"
        REMOVED = "removed", "removed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=6, choices=Kind.choices)
    group = models.ForeignKey(AccessGroup, on_delete=models.PROTECT, related_name="changes")
    membership = models.ForeignKey(
        "identity.Membership", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    right = models.CharField(max_length=32, blank=True)
    action = models.CharField(max_length=7, choices=Action.choices)
    at = models.DateTimeField(default=timezone.now, editable=False)
    by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    actor_kind = models.CharField(max_length=6, choices=ActorKind.choices)

    class Meta:
        ordering = ["at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(actor_kind=ActorKind.SYSTEM, by__isnull=True)
                    | Q(actor_kind=ActorKind.USER, by__isnull=False)
                    | Q(actor_kind=ActorKind.AGENT)
                ),
                name="access_accesschange_actor_matches_by",
            )
        ]

    def __str__(self) -> str:
        return f"{self.kind} {self.action} on {self.group_id}"
