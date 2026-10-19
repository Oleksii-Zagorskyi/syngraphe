"""The browser tests' teardown waits for the live server's own requests alone: a request the test
client began on the test's own thread and never finished — an unread download — is not one."""

from __future__ import annotations

from typing import Any

import pytest
from django.core.signals import request_started

pytestmark = pytest.mark.browser


def test_the_test_clients_unfinished_request_is_not_waited_for(
    browser_server: str, page: Any
) -> None:
    # What the test client does for a streamed response whose body is never read.
    request_started.send(sender=None, environ={})
