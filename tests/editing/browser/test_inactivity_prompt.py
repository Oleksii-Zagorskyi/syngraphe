"""The inactivity prompt in Chromium (DL-0377): a hold idle past its organisation's timeout is
asked *are you still working?*; answering it, with nothing typed, restarts the clock and puts the
prompt away. People and texts are synthetic examples; the text is invented."""

from __future__ import annotations

import time
from datetime import timedelta
from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = pytest.mark.browser

PROMPT = '[data-prompt="inactivity"]'
START = "The first synthetic sentence.\n"


def test_the_prompt_restarts_the_clock(
    editing: Any, page: Any, migrated_tenant: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from django.utils import timezone

    from editing.models import Hold
    from editing.views import capture

    monkeypatch.setattr(capture, "HEARTBEAT_SECONDS", 1)
    document = editing(START)
    with schema_context(migrated_tenant.number):
        Hold.objects.filter(document=document, released_at__isnull=True).update(
            last_activity_at=timezone.now() - timedelta(minutes=31)
        )

    page.wait_for_selector(PROMPT, state="visible", timeout=10_000)
    page.click(f"{PROMPT} button")

    page.wait_for_selector(PROMPT, state="hidden", timeout=5_000)
    deadline = time.monotonic() + 5
    while True:
        with schema_context(migrated_tenant.number):
            last = Hold.objects.get(document=document, released_at__isnull=True).last_activity_at
        if timezone.now() - last < timedelta(seconds=10):
            break
        assert time.monotonic() < deadline, f"the clock was not restarted: {last}"
        page.wait_for_timeout(200)
