"""Configuration, read once from the environment.

Every value an installation supplies comes from the environment; `.env` at the repository root is
loaded into it first, and a value already in the environment wins. `???` is the template's mark for
a value nobody supplied and is treated as absent, as is an empty value. Every missing or malformed
key is reported in one error, so an operator filling the template learns what is outstanding in one
pass.
"""

from __future__ import annotations

import ipaddress
import os
import re
import zoneinfo
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

UNSET = "???"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network


class ConfigurationError(Exception):
    """Raised with every missing and malformed key at once."""

    def __init__(self, missing: list[str], malformed: list[str]) -> None:
        self.missing = sorted(missing)
        self.malformed = sorted(malformed)
        parts = []
        if self.missing:
            parts.append("missing: " + ", ".join(self.missing))
        if self.malformed:
            parts.append("malformed: " + ", ".join(self.malformed))
        super().__init__("Configuration incomplete — " + "; ".join(parts))


@dataclass(frozen=True)
class Config:
    secret_key: str = field(repr=False)
    debug: bool
    admin_path: str
    site_https: bool
    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_user: str
    postgres_password: str = field(repr=False)
    redis_url: str = field(repr=False)
    celery_broker_url: str = field(repr=False)
    git_repo_root: Path
    trusted_proxies: tuple[IPNetwork, ...]
    display_timezone: str
    default_language: str
    backup_state_dir: Path
    backup_lock_timeout: float
    backup_wal_alert: int
    editing_conformance_page: bool
    help_work_in_progress: bool
    export_root: Path


class _Reader:
    def __init__(self, environ: Mapping[str, str]) -> None:
        self.environ = environ
        self.missing: list[str] = []
        self.malformed: list[str] = []

    def raw(self, key: str, default: str | None = None) -> str | None:
        value = self.environ.get(key)
        if value is None or value.strip() in (UNSET, ""):
            if default is None:
                self.missing.append(key)
            return default
        return value.strip()

    def string(self, key: str, default: str | None = None) -> str:
        return self.raw(key, default) or ""

    def boolean(self, key: str, default: str) -> bool:
        value = self.string(key, default).lower()
        if value in ("true", "1", "yes", "on"):
            return True
        if value in ("false", "0", "no", "off"):
            return False
        self.malformed.append(key)
        return False

    def integer(self, key: str, default: str) -> int:
        value = self.string(key, default)
        try:
            return int(value)
        except ValueError:
            self.malformed.append(key)
            return 0

    def networks(self, key: str) -> tuple[IPNetwork, ...]:
        """A comma-separated list of addresses or CIDR networks, or `none`.

        A bare address is a one-host network. The key has no default: the operator writes the
        proxy or `none`, so trusting nothing is a decision, never an omission (DL-0292).
        """
        value = self.string(key)
        if value.lower() == "none":
            return ()
        networks: list[IPNetwork] = []
        for item in filter(None, (part.strip() for part in value.split(","))):
            try:
                network = ipaddress.ip_network(item, strict=False)
            except ValueError:
                network = None
            # A network of every address trusts any client to name itself.
            if network is None or network.prefixlen == 0:
                if key not in self.malformed:
                    self.malformed.append(key)
                continue
            networks.append(network)
        return tuple(networks)

    def url_path(self, key: str) -> str:
        """A path segment under the root: no leading slash, a trailing one, never `admin/`."""
        value = self.string(key)
        if value and (value.startswith("/") or not value.endswith("/") or value == "admin/"):
            self.malformed.append(key)
        return value

    def timezone(self, key: str) -> str:
        value = self.string(key)
        if value:
            try:
                zoneinfo.ZoneInfo(value)
            except (zoneinfo.ZoneInfoNotFoundError, ValueError):
                self.malformed.append(key)
        return value

    def size(self, key: str, default: str) -> int:
        """A size in bytes, written plainly or with a suffix counted in powers of 1024, as
        pgBackRest counts them: `2GiB` and `2GB` are the same size."""
        value = self.string(key, default)
        match = re.fullmatch(r"([0-9]+)\s*(?:([KMGT])i?B)?", value)
        if match is None:
            self.malformed.append(key)
            return 0
        power = "KMGT".index(match.group(2)) + 1 if match.group(2) else 0
        return int(match.group(1)) * int(1024**power)

    def seconds(self, key: str, default: str) -> float:
        value = self.string(key, default)
        try:
            seconds = float(value)
        except ValueError:
            seconds = -1
        if seconds <= 0:
            self.malformed.append(key)
        return seconds

    def directory(self, key: str, default: str | None = None) -> Path:
        """A path; a relative one is taken from the repository root, not the working directory."""
        return REPOSITORY_ROOT / self.string(key, default)


def load(environ: Mapping[str, str] | None = None) -> Config:
    """Read the configuration from `environ`, or from the process environment after `.env`.

    Raises `ConfigurationError` naming every missing and malformed key.
    """
    if environ is None:
        load_dotenv(REPOSITORY_ROOT / ".env", override=False)
        environ = os.environ
    reader = _Reader(environ)
    config = Config(
        secret_key=reader.string("DJANGO_SECRET_KEY"),
        debug=reader.boolean("DJANGO_DEBUG", "false"),
        admin_path=reader.url_path("DJANGO_ADMIN_PATH"),
        site_https=reader.boolean("SITE_HTTPS", "true"),
        postgres_host=reader.string("POSTGRES_HOST"),
        postgres_port=reader.integer("POSTGRES_PORT", "5432"),
        postgres_db=reader.string("POSTGRES_DB"),
        postgres_user=reader.string("POSTGRES_USER"),
        postgres_password=reader.string("POSTGRES_PASSWORD"),
        redis_url=reader.string("REDIS_URL"),
        celery_broker_url=reader.string("CELERY_BROKER_URL"),
        git_repo_root=reader.directory("GIT_REPO_ROOT"),
        trusted_proxies=reader.networks("TRUSTED_PROXIES"),
        display_timezone=reader.timezone("DISPLAY_TIMEZONE"),
        default_language=reader.string("DEFAULT_LANGUAGE"),
        backup_state_dir=Path(reader.string("BACKUP_STATE_DIR", "/srv/backup-state")),
        backup_lock_timeout=reader.seconds("BACKUP_LOCK_TIMEOUT", "30"),
        backup_wal_alert=reader.size("BACKUP_WAL_ALERT", "2GiB"),
        editing_conformance_page=reader.boolean("EDITING_CONFORMANCE_PAGE", "false"),
        help_work_in_progress=reader.boolean("HELP_WORK_IN_PROGRESS", "false"),
        export_root=reader.directory("EXPORT_ROOT", "/srv/exports"),
    )
    if reader.missing or reader.malformed:
        raise ConfigurationError(reader.missing, reader.malformed)
    return config
