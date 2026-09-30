"""The project package. The Celery app is imported with it, so every process that sets Django up —
the web server included — sends shared tasks through the configured app and its routes."""

from syngraphe.celery import app as celery_app

__all__ = ("celery_app",)
