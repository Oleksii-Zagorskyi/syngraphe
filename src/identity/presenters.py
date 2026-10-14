"""What a page shows of a person, kept to what its reader may learn (ASR-17)."""

from __future__ import annotations

from typing import Any

from identity.models import Membership


def membership_for_administrator(membership: Membership) -> dict[str, Any]:
    """A membership as a tenant administrator sees it.

    `granted_at` is the only date: when the person joined this organisation, never when their
    account was created, which would tell the administrator about a life elsewhere. The address
    alone names the person — a display name set elsewhere would say they existed (DL-0403). A page
    over many memberships loads them with `select_related("user")`.
    """
    user = membership.user
    return {
        "email": user.email,
        "is_tenant_admin": membership.is_tenant_admin,
        "state": membership.state,
        "granted_at": membership.granted_at,
    }
