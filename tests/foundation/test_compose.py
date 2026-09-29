"""Each container receives the secrets its job needs and no other (the backup's keys stay where
ADR-0019 and DL-0299 put them)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

pytestmark = pytest.mark.fast

COMPOSE = Path(__file__).resolve().parents[2] / "compose.yaml"
SECRETS = {
    "BACKUP_DB_CIPHER_PASS",
    "BACKUP_BUNDLE_CRYPT_PASSWORD",
    "BACKUP_S3_ACCESS_KEY",
    "BACKUP_S3_SECRET_KEY",
    "DJANGO_SECRET_KEY",
    "POSTGRES_PASSWORD",
}


def _services() -> dict[str, Any]:
    services: dict[str, Any] = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]
    return services


def _secrets(service: dict[str, Any]) -> set[str]:
    assert "env_file" not in service, "a service reads `.env` whole"
    return SECRETS & set(service.get("environment") or {})


def test_each_service_holds_its_own_secrets() -> None:
    services = _services()

    assert _secrets(services["web"]) == {"DJANGO_SECRET_KEY", "POSTGRES_PASSWORD"}
    assert _secrets(services["worker"]) == {
        "DJANGO_SECRET_KEY",
        "POSTGRES_PASSWORD",
        "BACKUP_BUNDLE_CRYPT_PASSWORD",
        "BACKUP_S3_ACCESS_KEY",
        "BACKUP_S3_SECRET_KEY",
    }
    for name in ("db", "backup"):
        assert _secrets(services[name]) == {
            "POSTGRES_PASSWORD",
            "BACKUP_DB_CIPHER_PASS",
            "BACKUP_S3_ACCESS_KEY",
            "BACKUP_S3_SECRET_KEY",
        }


def test_web_reads_the_backup_state_only() -> None:
    web = _services()["web"]

    assert "backup-state:/srv/backup-state:ro" in web["volumes"]
    assert not any("/run/backup" in volume for volume in web["volumes"])
