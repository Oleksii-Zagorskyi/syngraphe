"""The identity app's periodic tasks."""

from __future__ import annotations

from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from identity.models import SignInAttempt

KEEP = timedelta(days=1)


@shared_task(name="identity.sweep_sign_in_attempts")
def sweep_sign_in_attempts() -> int:
    """Remove throttling rows whose last failure is over a day old; returns how many."""
    removed, _ = SignInAttempt.objects.filter(last_failure_at__lt=timezone.now() - KEEP).delete()
    return removed
