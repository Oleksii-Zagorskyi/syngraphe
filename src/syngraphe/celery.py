"""The Celery application, configured from the Django settings, and the smoke task."""

from __future__ import annotations

import logging.config
import os
from typing import Any

from celery import Celery
from celery.signals import setup_logging

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "syngraphe.settings")

app = Celery("syngraphe")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@setup_logging.connect
def _use_the_platforms_logging(**kwargs: Any) -> None:
    """Every worker line, task loggers included, goes through the settings' JSON handler."""
    from django.conf import settings

    logging.config.dictConfig(settings.LOGGING)


@app.task(name="syngraphe.ping")
def ping() -> str:
    """Write nothing and answer; proves the broker, the result backend and the worker."""
    return "pong"
