"""The smoke task proves the broker, the result backend and the worker together."""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.integration


def test_smoke_task_round_trips(celery_worker: Any, test_queue: str) -> None:
    from syngraphe.celery import ping

    assert ping.apply_async(queue=test_queue).get(timeout=10) == "pong"
