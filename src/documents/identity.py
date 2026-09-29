"""The identity a commit or a tag carries: the user's id and a non-routable address, never a name
(DL-0088, DL-0093; `technical-design.md § Who performs git operations` fixes the domain)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pygit2

if TYPE_CHECKING:
    from identity.models import User

# Baked into every commit ever written: changing it would split one author into two.
DOMAIN = "users.noreply.syngraphe.local"


def identity_for(user: User, *, at: datetime | None = None) -> pygit2.Signature:
    """The signature for `user`, at `at` or now, in UTC. A naive `at` is refused."""
    if at is not None and at.tzinfo is None:
        raise ValueError("a commit's time carries its zone")
    moment = at if at is not None else datetime.now(UTC)
    return pygit2.Signature(str(user.id), f"{user.id}@{DOMAIN}", int(moment.timestamp()), 0)
