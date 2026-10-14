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


def test_the_outbox_task_runs_on_the_worker() -> None:
    """The outbox is sent every minute by beat, on the default queue the `worker` consumes — the
    one container that sends mail — never on `render`, which has no way out."""
    from celery.schedules import crontab
    from django.conf import settings

    from syngraphe.celery import app

    entry = settings.CELERY_BEAT_SCHEDULE["send-outbox"]
    assert entry["task"] == "mail.send_outbox"
    assert entry["schedule"] == crontab(minute="*")
    route = app.amqp.router.route({}, "mail.send_outbox", (), {})
    assert route["queue"].name == app.conf.task_default_queue


def test_idle_holds_are_visited_by_beat() -> None:
    """Idle holds are visited every minute by beat, on the default queue, each minute's visit
    expiring rather than queueing behind an outage."""
    from celery.schedules import crontab
    from django.conf import settings

    from syngraphe.celery import app

    entry = settings.CELERY_BEAT_SCHEDULE["release-inactive-holds"]
    assert entry["task"] == "editing.release_inactive_holds"
    assert entry["schedule"] == crontab(minute="*")
    assert entry["options"] == {"expires": 50}
    route = app.amqp.router.route({}, "editing.release_inactive_holds", (), {})
    assert route["queue"].name == app.conf.task_default_queue
