"""People and what belongs to them: users, memberships, their histories, invitations, sign-in
attempts, preferences, the language lists and the first-run token (ADR-0008, DL-0210, DL-0231).
"""

from __future__ import annotations

import uuid
from typing import Any, ClassVar

from django.contrib.auth.base_user import AbstractBaseUser
from django.db import models, transaction
from django.utils import timezone

from identity.managers import UserManager, fold_email
from syngraphe.provenance import ActorKind, Mutable, Provenanced

__all__ = [
    "AccountBlockHistory",
    "Invitation",
    "Language",
    "Membership",
    "MembershipHistory",
    "MembershipState",
    "SetupToken",
    "SignInAttempt",
    "User",
    "UserPreference",
    "fold_email",
]


class User(AbstractBaseUser, Provenanced):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, max_length=254)
    display_name = models.CharField(max_length=200, blank=True)
    password = models.CharField(max_length=128, db_column="password_hash")
    is_platform_admin = models.BooleanField(default=False)
    is_tombstoned = models.BooleanField(default=False)
    self_blocked = models.BooleanField(default=False)
    last_login_at = models.DateTimeField(null=True, blank=True)
    # The operator flag of DL-0210: set from the command line, never by the application.
    is_superuser = models.BooleanField(default=False)

    last_login = None

    objects: ClassVar[UserManager] = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    class Meta(Provenanced.Meta):
        abstract = False

    def __str__(self) -> str:
        return f"user {self.id}"

    @property
    def is_staff(self) -> bool:
        return self.is_superuser

    @property
    def is_active(self) -> bool:  # type: ignore[override]
        """Only a tombstoned account cannot sign in.

        A self-blocked person still signs in: the block closes every membership, not the account,
        and nothing ever locks an account by an action its owner did not take (DL-0116).
        """
        return not self.is_tombstoned

    def has_perm(self, perm: str, obj: Any = None) -> bool:
        return self.is_active and self.is_superuser

    def has_module_perms(self, app_label: str) -> bool:
        return self.is_active and self.is_superuser

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.email = fold_email(self.email)
        super().save(*args, **kwargs)


class MembershipState(models.TextChoices):
    ACTIVE = "active", "active"
    BLOCKED = "blocked", "blocked"


class Membership(Mutable):
    """A person's place in one organisation; `granted_at` is what a tenant administrator sees."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenancy.Tenant", on_delete=models.PROTECT, related_name="memberships"
    )
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="memberships")
    is_tenant_admin = models.BooleanField(default=False)
    state = models.CharField(
        max_length=7, choices=MembershipState.choices, default=MembershipState.ACTIVE
    )
    granted_at = models.DateTimeField(default=timezone.now, editable=False)
    granted_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta(Mutable.Meta):
        abstract = False
        constraints = [
            *Mutable.Meta.constraints,
            models.UniqueConstraint(fields=["tenant", "user"], name="one_membership_per_person"),
        ]

    TRACKED_FIELDS = ("is_tenant_admin", "state")

    def __str__(self) -> str:
        return f"{self.user_id} in tenant {self.tenant_id}"

    def change(self, field: str, value: Any, *, by: User | None) -> MembershipHistory:
        """Change the administrator flag or the state, writing the history row in the same act.

        The only way those two fields change (ASR-18): `save()` refuses a change made otherwise.
        """
        if field not in self.TRACKED_FIELDS:
            raise ValueError(f"{field} is not a tracked membership field")
        before = getattr(self, field)
        with transaction.atomic():
            setattr(self, field, value)
            self._history_written = True
            try:
                self.save(update_fields=[field, "updated_at"])
            finally:
                self._history_written = False
            return MembershipHistory.objects.create(
                membership=self,
                field=field,
                before=str(before),
                after=str(value),
                by=by,
                actor_kind=ActorKind.SYSTEM if by is None else ActorKind.USER,
            )

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding and not getattr(self, "_history_written", False):
            stored = Membership.objects.filter(pk=self.pk).values(*self.TRACKED_FIELDS).first()
            if stored is not None:
                changed = [f for f in self.TRACKED_FIELDS if stored[f] != getattr(self, f)]
                if changed:
                    raise RuntimeError(
                        f"{', '.join(changed)} changes only through Membership.change()"
                    )
        super().save(*args, **kwargs)


class MembershipHistory(models.Model):
    """One row per change of a membership's administrator flag or state."""

    class Field(models.TextChoices):
        IS_TENANT_ADMIN = "is_tenant_admin", "is_tenant_admin"
        STATE = "state", "state"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    membership = models.ForeignKey(Membership, on_delete=models.PROTECT, related_name="history")
    field = models.CharField(max_length=15, choices=Field.choices)
    before = models.CharField(max_length=20)
    after = models.CharField(max_length=20)
    at = models.DateTimeField(default=timezone.now, editable=False)
    by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    actor_kind = models.CharField(max_length=6, choices=ActorKind.choices)

    class Meta:
        ordering = ["at"]

    def __str__(self) -> str:
        return f"{self.membership_id}: {self.field} {self.before} → {self.after}"


class AccountBlockHistory(models.Model):
    """A person's own block and its lifting by a platform administrator."""

    class Action(models.TextChoices):
        SELF_BLOCKED = "self_blocked", "self_blocked"
        BLOCK_LIFTED = "block_lifted", "block_lifted"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="block_history")
    action = models.CharField(max_length=12, choices=Action.choices)
    at = models.DateTimeField(default=timezone.now, editable=False)
    by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["at"]

    def __str__(self) -> str:
        return f"{self.user_id}: {self.action}"


class Invitation(Provenanced):
    """A hashed, single-use, expiring invitation to join one organisation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenancy.Tenant", on_delete=models.PROTECT, related_name="invitations"
    )
    email = models.EmailField(max_length=254)
    token_hash = models.CharField(max_length=128, unique=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    invited_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")

    class Meta(Provenanced.Meta):
        abstract = False

    def __str__(self) -> str:
        return f"invitation {self.id}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.email = fold_email(self.email)
        super().save(*args, **kwargs)


class SignInAttempt(models.Model):
    """Throttling state per submitted address and per client address; no reference to a user."""

    class KeyKind(models.TextChoices):
        EMAIL = "email", "email"
        ADDRESS = "address", "address"

    key = models.CharField(primary_key=True, max_length=254)
    key_kind = models.CharField(max_length=7, choices=KeyKind.choices)
    consecutive_failures = models.PositiveIntegerField(default=0)
    next_allowed_at = models.DateTimeField(null=True, blank=True)
    last_failure_at = models.DateTimeField(null=True, blank=True, db_index=True)

    def __str__(self) -> str:
        return f"{self.key_kind} attempt"


class UserPreference(Mutable):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="preferences")
    key = models.CharField(max_length=50)
    value = models.CharField(max_length=200)

    class Meta(Mutable.Meta):
        abstract = False
        constraints = [
            *Mutable.Meta.constraints,
            models.UniqueConstraint(fields=["user", "key"], name="one_value_per_preference"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}: {self.key}"


class Language(Mutable):
    """A document language and the splitter's abbreviation lists, one item per line (ADR-0012)."""

    code = models.CharField(primary_key=True, max_length=8)
    label = models.CharField(max_length=50)
    never_final = models.TextField(blank=True)
    may_be_final = models.TextField(blank=True)

    class Meta(Mutable.Meta):
        abstract = False
        ordering = ["code"]

    def __str__(self) -> str:
        return self.code

    def never_final_list(self) -> list[str]:
        return _lines(self.never_final)

    def may_be_final_list(self) -> list[str]:
        return _lines(self.may_be_final)


def _lines(text: str) -> list[str]:
    return [line for line in (part.strip() for part in text.splitlines()) if line]


class SetupToken(models.Model):
    """The first-run token's hash and expiry: deleted when used, ignored once expired (DL-0231)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    token_hash = models.CharField(max_length=128, unique=True)
    expires_at = models.DateTimeField()

    def __str__(self) -> str:
        return f"setup token until {self.expires_at:%Y-%m-%d %H:%M} UTC"
