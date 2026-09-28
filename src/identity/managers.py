"""The user manager: addresses folded on the way in; operators come from the command line."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib.auth.base_user import BaseUserManager

from syngraphe.provenance import ActorKind

if TYPE_CHECKING:
    from identity.models import User


def fold_email(email: str) -> str:
    """The stored form of an address: stripped and case-folded, so one person has one row."""
    return email.strip().casefold()


class UserManager(BaseUserManager["User"]):
    def get_by_natural_key(self, username: str | None) -> User:
        return self.get(email=fold_email(username or ""))

    def create_user(self, email: str, password: str | None = None, **fields: Any) -> User:
        fields.setdefault(
            "actor_kind", ActorKind.USER if fields.get("created_by") else ActorKind.SYSTEM
        )
        user = self.model(email=fold_email(email), **fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str | None = None, **fields: Any) -> User:
        """An operator account for the framework's own administration interface (DL-0210)."""
        fields.setdefault("is_superuser", True)
        return self.create_user(email, password, **fields)
