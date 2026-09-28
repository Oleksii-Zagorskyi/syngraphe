"""`setup_token`: the one-time token for the first-run page (DL-0231, T-19)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction
from django.utils import timezone

from identity.models import SetupToken, User
from identity.tokens import hash_token, new_token
from tenancy import services
from tenancy.middleware import invalidate_host_cache
from tenancy.models import PlatformHost, TenantDomain

TOKEN_MINUTES = 60


class AdministratorExists(Exception):
    pass


class Command(BaseCommand):
    help = (
        "Print a token for the first-run page, valid once for sixty minutes; a second run "
        "replaces it. --host makes that host the default platform host."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--host", help="the installation's public host, made the default")

    def handle(self, *args: Any, host: str | None = None, **options: Any) -> None:
        if host is not None:
            host = _checked_host(host)
        token = new_token()
        try:
            with transaction.atomic():
                SetupToken.lock_first_run()
                if User.objects.filter(is_platform_admin=True).exists():
                    raise AdministratorExists
                if host is not None:
                    _make_default(host)
                SetupToken.objects.all().delete()
                SetupToken.objects.create(
                    token_hash=hash_token(token),
                    expires_at=timezone.now() + timedelta(minutes=TOKEN_MINUTES),
                )
        except AdministratorExists:
            self.stderr.write("A platform administrator already exists.")
            raise SystemExit(1) from None
        # Clears this process's copy only; a running web process sees the new default host
        # within the middleware's thirty-second cache.
        invalidate_host_cache()
        self.stdout.write(token)


def _checked_host(host: str) -> str:
    try:
        host = services.checked_host(host)
    except services.Refused:
        raise CommandError(f"Not a host name: {host!r}") from None
    if TenantDomain.objects.filter(host=host).exists():
        raise CommandError(f"{host!r} is an organisation's domain, not a platform host")
    return host


def _make_default(host: str) -> None:
    """The host becomes the one default platform host, added if absent; each change audited."""
    row = PlatformHost.objects.filter(host=host).first()
    if row is None:
        added = services.add_host(host, None, by=None)
        assert isinstance(added, PlatformHost)
        row = added
    services.make_default(row, by=None)
