"""Shared fixtures: the database, a client on the platform host, the Celery worker."""

from __future__ import annotations

import os
import tempfile
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from django.db import connection
from django.test import Client

# The values a host-side run cannot take from `.env`: they describe the test process, not an
# installation. CI sets every one of them explicitly and wins.
_TEST_DEFAULTS = {
    "DJANGO_SECRET_KEY": "test-only-not-a-secret",
    "DJANGO_DEBUG": "false",
    "DJANGO_ADMIN_PATH": "operator/",
    "SITE_HTTPS": "false",
    "TRUSTED_PROXIES": "none",
    "DISPLAY_TIMEZONE": "UTC",
    "DEFAULT_LANGUAGE": "uk",
    "GIT_REPO_ROOT": str(Path(tempfile.gettempdir()) / "syngraphe-test-repos"),
}
for _key, _value in _TEST_DEFAULTS.items():
    os.environ.setdefault(_key, _value)

pytest_plugins = ("celery.contrib.pytest",)


@pytest.fixture(autouse=True)
def unhashed_static_files(settings: Any) -> None:
    """Static names as written: the suite renders pages without collecting the files first."""
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


@pytest.fixture(autouse=True)
def fresh_host_cache() -> None:
    """Each test sees the hosts it creates: the thirty-second cache never carries across tests."""
    from tenancy.middleware import invalidate_host_cache

    invalidate_host_cache()


# A queue of this run alone, so a worker container sharing the broker never takes the test's task.
TEST_QUEUE = f"test-{uuid.uuid4().hex}"


@pytest.fixture
def client() -> Client:
    """A client whose requests carry the host `127.0.0.1`."""
    return Client(headers={"host": "127.0.0.1"})


@pytest.fixture(scope="session")
def celery_app() -> Any:
    """The application's own Celery app, so its tasks are the ones the test worker runs."""
    from syngraphe.celery import app

    return app


@pytest.fixture(scope="session")
def celery_worker_parameters() -> dict[str, Any]:
    return {"queues": (TEST_QUEUE,), "perform_ping_check": False, "shutdown_timeout": 30}


@pytest.fixture(scope="session")
def test_queue() -> str:
    return TEST_QUEUE


@pytest.fixture
def repo_root(tmp_path: Path, settings: Any) -> Iterator[Path]:
    """An empty repository root for the test, in place of the configured one."""
    root = tmp_path / "repos"
    root.mkdir()
    settings.GIT_REPO_ROOT = root
    yield root


@pytest.fixture
def drop_tenant_schemas() -> Iterator[None]:
    """Drop every `tenant_N` schema the test created, since a schema outlives a rolled-back row."""
    yield
    with connection.cursor() as cursor:
        cursor.execute("SELECT nspname FROM pg_namespace WHERE nspname LIKE 'tenant\\_%'")
        for (name,) in cursor.fetchall():
            cursor.execute(f'DROP SCHEMA "{name}" CASCADE')
