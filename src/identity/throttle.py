"""Sign-in throttling: a growing delay, never a lock (DL-0116, DL-0289, T-14).

Failures are counted twice — by the client, and by the pair of the email address typed and the
client — and the next attempt waits 1, 2, 4 … 60 seconds after the last failure. An attempt made
while either delay runs is refused and counted as a failure. A success resets the pair only, so
signing into one's own account does not clear the client's count, and nobody's failures delay the
owner of an address signing in from another client.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core import signing
from django.db import connection, transaction
from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from identity.models import SignInAttempt, User

FIRST_DELAY_SECONDS = 1
CEILING_SECONDS = 60
# Past this the doubling is at the ceiling already; it keeps the power small however many
# refused attempts arrive.
CEILING_EXPONENT = 6
DEVICE_COOKIE = "sign_in_device"
DEVICE_SALT = "identity.throttle.device"
DEVICE_SECONDS = 90 * 24 * 3600
# One IPv6 subscriber holds a /64: counting its addresses apart would give it endless clients.
IPV6_PREFIX = 64

Key = tuple[str, str]


def client_key(request: HttpRequest) -> str:
    """The client as the throttle counts it — its address, an IPv6 one by its /64; a trusted
    proxy's forwarded address is already in place (`syngraphe.proxy`)."""
    peer = str(request.META.get("REMOTE_ADDR", ""))
    try:
        address = ipaddress.ip_address(peer)
    except ValueError:
        return peer
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        # An IPv4 client a dual-stack listener reports in IPv6 form is still that IPv4 client.
        return str(address.ipv4_mapped)
    if address.version == 6:
        return str(ipaddress.ip_network(f"{address}/{IPV6_PREFIX}", strict=False))
    return str(address)


def keys(email: str | None, client: str, device: str | None = None) -> list[Key]:
    """The rows an attempt counts against: a device's alone when the browser shows it signed in
    with this address before (DL-0293); otherwise the client's, and the pair's when the form
    accepted the email address — hashed, so the address typed is never kept."""
    if device is not None:
        return [(device, SignInAttempt.KeyKind.DEVICE)]
    found: list[Key] = [(client, SignInAttempt.KeyKind.ADDRESS)]
    if email:
        found.append((pair_key(email, client), SignInAttempt.KeyKind.PAIR))
    return found


def _digest(text: str) -> str:
    """An HMAC under a key derived from the installation's secret: a copy of the table, or of a
    cookie, does not give the address back."""
    secret = hashlib.sha256(f"sign-in attempts\n{settings.SECRET_KEY}".encode()).digest()
    return hmac.new(secret, text.encode(), hashlib.sha256).hexdigest()


def pair_key(email: str, client: str) -> str:
    return _digest(f"{email}\n{client}")


@dataclass(frozen=True)
class Device:
    """A valid device cookie: the row it counts on, and the random value it carries."""

    key: str
    nonce: str


def device_cookie_name() -> str:
    """`__Host-` where cookies go over HTTPS only, so no sibling host can plant one that shadows
    it; browsers accept that prefix only on a secure cookie."""
    return f"__Host-{DEVICE_COOKIE}" if settings.SESSION_COOKIE_SECURE else DEVICE_COOKIE


def device(request: HttpRequest, email: str | None) -> Device | None:
    """The device a valid cookie names for this address and its current password, otherwise
    none — a missing, altered, expired or other-address cookie, or one issued before the password
    last changed, changes nothing."""
    value = request.COOKIES.get(device_cookie_name())
    if not value or not email:
        return None
    try:
        payload = signing.loads(value, salt=DEVICE_SALT, max_age=DEVICE_SECONDS)
    except signing.BadSignature:
        return None
    if not isinstance(payload, dict) or payload.get("who") != _digest(email):
        return None
    nonce = payload.get("nonce")
    person = User.objects.filter(email=email).first()
    if not isinstance(nonce, str) or person is None or payload.get("cred") != _credential(person):
        return None
    return Device(key=_digest(f"device\n{nonce}"), nonce=nonce)


def issue_device(response: HttpResponse, person: User, presented: Device | None) -> None:
    """Give the browser its cookie: a hash of the address and of the current password's hash,
    and a random value — the one it presented, if any, so one browser keeps one device and
    signing in again mints no new ones. Signed; never the address itself."""
    nonce = presented.nonce if presented is not None else secrets.token_urlsafe(16)
    value = signing.dumps(
        {"who": _digest(person.email), "cred": _credential(person), "nonce": nonce},
        salt=DEVICE_SALT,
    )
    response.set_cookie(
        device_cookie_name(),
        value,
        max_age=DEVICE_SECONDS,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="Lax",
    )


def _credential(person: User) -> str:
    """Changes whenever the password does, so a password change retires every cookie."""
    return _digest(f"credential\n{person.get_session_auth_hash()}")


def spend_a_hash(password: str) -> None:
    """The cost of a password check, for an attempt that is refused without one: a refused and a
    checked attempt take the same time, so the timing shows neither the delay nor the cookie."""
    make_password(password)


def _lock(keys: list[str]) -> None:
    """Serialise attempts on the same keys, a first attempt too — a row that does not exist yet
    cannot be locked. Taken in one order, so two attempts never wait on each other."""
    with connection.cursor() as cursor:
        for key in sorted(keys):
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", [key])


@dataclass(frozen=True)
class Before:
    """A row as it was before this attempt charged it, and the delay the charge set."""

    existed: bool
    failures: int
    next_allowed_at: datetime | None
    last_failure_at: datetime | None
    charged_until: datetime


@dataclass(frozen=True)
class Charge:
    allowed: bool
    keys: list[Key]
    before: dict[str, Before] = field(default_factory=dict)


def charge(attempt_keys: list[Key]) -> Charge:
    """Count the attempt as a failure before the password is checked, and say whether it may go
    ahead: it may not while either row's delay runs.

    Charging first, under the rows' locks, is what makes the delay hold against attempts sent in
    parallel — each waits for the one before it and then finds the delay already running. A
    refused attempt is counted only on rows that already exist, so refusals add no rows. A
    success settles the charge with `succeed()`.
    """
    now = timezone.now()
    names = [key for key, _ in attempt_keys]
    before: dict[str, Before] = {}
    with transaction.atomic():
        _lock(names)
        existing = {
            row.key: row for row in SignInAttempt.objects.select_for_update().filter(key__in=names)
        }
        waiting = any(
            row.next_allowed_at is not None and row.next_allowed_at > now
            for row in existing.values()
        )
        if waiting:
            rows = list(existing.values())
        else:
            rows = [
                existing.get(key)
                or SignInAttempt.objects.select_for_update().get_or_create(
                    key=key, defaults={"key_kind": kind}
                )[0]
                for key, kind in attempt_keys
            ]
        for row in rows:
            was = (row.consecutive_failures, row.next_allowed_at, row.last_failure_at)
            row.consecutive_failures += 1
            exponent = min(row.consecutive_failures - 1, CEILING_EXPONENT)
            row.next_allowed_at = now + timedelta(
                seconds=min(FIRST_DELAY_SECONDS * 2**exponent, CEILING_SECONDS)
            )
            row.last_failure_at = now
            row.save()
            before[row.key] = Before(row.key in existing, *was, charged_until=row.next_allowed_at)
    return Charge(allowed=not waiting, keys=attempt_keys, before=before)


def succeed(charged: Charge) -> None:
    """After a success: the pair's count is reset; the client's keeps its earlier failures and
    loses only this attempt's charge — unless another attempt has charged it since (DL-0289)."""
    with transaction.atomic():
        _lock([key for key, _ in charged.keys])
        for key, kind in charged.keys:
            was = charged.before.get(key)
            row = SignInAttempt.objects.select_for_update().filter(key=key).first()
            if row is None or was is None:
                continue
            if kind in (SignInAttempt.KeyKind.PAIR, SignInAttempt.KeyKind.DEVICE):
                row.consecutive_failures = 0
                row.next_allowed_at = None
                row.save()
            elif row.next_allowed_at != was.charged_until:
                row.consecutive_failures = max(row.consecutive_failures - 1, 0)
                row.save()
            elif not was.existed:
                row.delete()
            else:
                row.consecutive_failures = was.failures
                row.next_allowed_at = was.next_allowed_at
                row.last_failure_at = was.last_failure_at
                row.save()
