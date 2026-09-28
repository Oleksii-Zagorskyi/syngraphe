"""`record()`: one audit event per act, the actor's kind derived from the actor."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from django.db.models import Model

from audit.models import AuditEvent
from syngraphe.provenance import ActorKind

if TYPE_CHECKING:
    from identity.models import User
    from tenancy.models import Tenant

# Values that never belong in the trail, whatever the caller passes.
SECRET_KEYS = frozenset({"password", "password_hash", "token_hash"})


def _checked(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is not None and SECRET_KEYS & payload.keys():
        raise ValueError(f"an audit payload never carries {', '.join(sorted(SECRET_KEYS))}")
    return payload


def record(
    *,
    actor: User | None,
    action: str,
    obj: Model | None,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    tenant: Tenant | None = None,
) -> AuditEvent:
    """Write one event; `actor_kind` is `system` when `actor` is `None`, `user` otherwise.

    `object_id` holds the object's uuid; an object keyed otherwise leaves it empty and the caller
    puts the natural key in `after`. `before` and `after` are what a presenter shows of the object,
    never a model instance's every field.
    """
    pk = obj.pk if obj is not None else None
    return AuditEvent.objects.create(
        tenant=tenant,
        actor=actor,
        actor_kind=ActorKind.SYSTEM if actor is None else ActorKind.USER,
        action=action,
        object_type=(obj._meta.model_name or "") if obj is not None else "",
        object_id=pk if isinstance(pk, uuid.UUID) else None,
        before=_checked(before),
        after=_checked(after),
    )
