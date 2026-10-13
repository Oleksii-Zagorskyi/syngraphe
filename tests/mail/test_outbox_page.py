"""The platform's outbox, on its mail page (DL-0203): every email the platform sent or tried to,
newest first, with its status and attempts — the shared schema's rows alone, never an
organisation's.

People, addresses and texts are synthetic examples; every address ends in `@example.test`.
"""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

ROW = re.compile(r'data-outbox="([0-9a-f-]+)"')


def test_the_platform_outbox_lists_platform_mail_only(member_of: Any, migrated_tenant: Any) -> None:
    from mail.models import EmailOutbox, Status

    client, _, _ = member_of("o.synthetic@example.test", is_platform_admin=True)
    now = timezone.now()
    with schema_context(None):
        older = EmailOutbox.objects.create(
            sender="platform.sender@example.test",
            recipient="first.synthetic@example.test",
            subject="Синтетична тема перша",
            body="Синтетичний лист.",
            status=Status.SENT,
            created_at=now - timedelta(minutes=2),
            sent_at=now - timedelta(minutes=2),
        )
        newer = EmailOutbox.objects.create(
            sender="platform.sender@example.test",
            recipient="second.synthetic@example.test",
            subject="Синтетична тема друга",
            body="Синтетичний лист.",
            status=Status.QUEUED,
            attempts=2,
            last_error="smtp:451 4.3.0 Synthetic refusal",
            created_at=now,
        )
    with schema_context(migrated_tenant.number):
        EmailOutbox.objects.create(
            tenant=migrated_tenant,
            sender="tenant.sender@example.test",
            recipient="tenant.reader@example.test",
            subject="Синтетична тема організації",
            body="Синтетичний лист.",
        )

    page = client.get("/administration/platform/mail/").content.decode()
    assert ROW.findall(page) == [str(newer.pk), str(older.pk)]
    assert "tenant.reader@example.test" not in page
    assert 'data-status="queued"' in page and 'data-attempts="2"' in page
    assert "4.3.0 Synthetic refusal" in page and 'data-error-code="smtp:451' in page
