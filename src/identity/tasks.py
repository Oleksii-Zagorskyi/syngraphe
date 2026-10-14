"""The identity app's periodic tasks."""

from __future__ import annotations

from datetime import timedelta

from celery import shared_task
from django.db.models import Q
from django.utils import timezone

from identity.models import PasswordReset, SignInAttempt

KEEP = timedelta(days=1)


@shared_task(name="identity.sweep_sign_in_attempts")
def sweep_sign_in_attempts() -> int:
    """Remove throttling rows whose last failure is over a day old, and resets used or expired
    over a day ago (DL-0413); returns how many."""
    before = timezone.now() - KEEP
    removed, _ = SignInAttempt.objects.filter(last_failure_at__lt=before).delete()
    spent, _ = PasswordReset.objects.filter(
        Q(used_at__lt=before) | Q(expires_at__lt=before)
    ).delete()
    return removed + spent
