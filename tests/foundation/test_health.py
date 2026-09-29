"""`GET /health/` names what answers and what does not, and the backup's state, and nothing
else."""

from __future__ import annotations

from typing import Any

import pytest
from django.test import Client

pytestmark = pytest.mark.integration


@pytest.mark.django_db
def test_health_ok(client: Client) -> None:
    response = client.get("/health/")

    body = response.json()
    assert response.status_code == 200
    assert set(body) == {"database", "redis", "backup"}
    assert (body["database"], body["redis"]) == ("ok", "ok")


@pytest.mark.django_db
def test_health_names_the_failing_service(client: Client, settings: Any) -> None:
    settings.REDIS_URL = "redis://127.0.0.1:9/0"

    response = client.get("/health/")

    body = response.json()
    assert response.status_code == 503
    assert (body["database"], body["redis"]) == ("ok", "unreachable")
