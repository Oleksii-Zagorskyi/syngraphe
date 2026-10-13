"""The mail pages render in Ukrainian from the one catalogue: the form with its rules, a stored
password, the last test's steps, the outbox and the frame's section.

People, addresses and texts are synthetic examples; every address ends in `@example.test`."""

from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path
from typing import Any

import pytest

from tenancy.schemas import schema_context

_spec = importlib.util.spec_from_file_location(
    "mail_catalogue", Path(__file__).resolve().parents[1] / "review" / "test_catalogue.py"
)
assert _spec is not None and _spec.loader is not None
_review = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_review)


@pytest.mark.integration
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_catalogue_covers_the_mail_pages(member_of: Any, sender: Any, settings: Any) -> None:
    from mail.models import EmailOutbox, MailSender

    settings.LANGUAGE_CODE = "uk"
    client, _, _ = member_of("o.synthetic@example.test", is_platform_admin=True)
    ids = _review.message_ids(_review.CATALOGUE.read_text(encoding="utf-8"))
    bodies = {"no sender": client.get("/administration/platform/mail/").content.decode()}
    invalid = client.post(
        "/administration/platform/mail/",
        {
            "host": "smtp://x",
            "port": "0",
            "address": "x",
            "display_name": "\x01",
            "username": "u",
            "password": "ключ",
            "security": "none",
        },
    )
    bodies["the rules"] = invalid.content.decode()
    saved = sender(None, username="u.synthetic@example.test")
    with schema_context(None):
        MailSender.objects.filter(pk=saved.pk).update(
            last_test_result=json.dumps(
                {"done": ["connected"], "failed": "signed_in", "error": "SMTPAuthenticationError"}
            )
        )
        for status in ("queued", "sent", "failed"):
            EmailOutbox.objects.create(
                sender=saved.address,
                recipient="r.synthetic@example.test",
                subject="Синтетична тема",
                body="Синтетичний лист.",
                status=status,
            )
    bodies["saved"] = client.get("/administration/platform/mail/").content.decode()
    bodies["waiting"] = client.get(
        f"/administration/platform/mail/?testing={int(time.time())}"
    ).content.decode()
    clear = client.post(
        "/administration/platform/mail/",
        {
            "host": "smtp.example.test",
            "port": "25",
            "address": "p.synthetic@example.test",
            "username": "u",
            "password": "p",
            "security": "none",
        },
    )
    bodies["in the clear"] = clear.content.decode()
    bodies["frame"] = client.get("/administration/").content.decode()
    admin, _, _ = member_of("t.synthetic@example.test", is_tenant_admin=True)
    bodies["the organisation's page"] = admin.get(
        "/administration/tenant/sending-address/"
    ).content.decode()
    for name, body in bodies.items():
        shown = _review.text_of(body)
        leaked = [message for message in ids if message in shown]
        assert leaked == [], (name, leaked)
