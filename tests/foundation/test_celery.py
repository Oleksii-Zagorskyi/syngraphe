"""The smoke task proves the broker, the result backend and the worker together."""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.integration


def test_smoke_task_round_trips(celery_worker: Any, test_queue: str) -> None:
    from syngraphe.celery import ping

    assert ping.apply_async(queue=test_queue).get(timeout=10) == "pong"


def test_a_task_sent_from_the_web_process_follows_the_routes() -> None:
    """In a process that sets Django up as the web server does and never imports the Celery
    module itself, a shared task is sent through the configured app: an export goes to the
    `render` queue, never the default one."""
    import subprocess
    import sys
    from pathlib import Path

    script = (
        "import django; django.setup()\n"
        "from rendering.tasks import render_export\n"
        "route = render_export.app.amqp.router.route({}, 'rendering.render_export', (), {})\n"
        "print(route['queue'].name)\n"
    )
    src = Path(__file__).resolve().parents[2] / "src"
    result = subprocess.run(  # noqa: S603 — this interpreter, a fixed script
        [sys.executable, "-c", script],
        cwd=src,
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "DJANGO_SETTINGS_MODULE": "syngraphe.settings"},
        check=True,
    )
    assert result.stdout.strip().splitlines()[-1] == "render"
