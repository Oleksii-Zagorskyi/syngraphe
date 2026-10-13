"""`rotate_mail_key`: every stored sending password re-encrypted under the current key — the
platform's and each organisation's — so the previous key can be removed (DL-0202, DL-0372).
Run with the new key as `MAIL_PASSWORD_KEY` and the old one as `MAIL_PASSWORD_KEY_PREVIOUS`; run
again, it re-encrypts what is already under the new key and changes nothing a reader sees."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from audit.record import record
from mail import secrets
from mail.models import MailSender
from tenancy.models import Tenant, visited_by_background_work
from tenancy.schemas import schema_context


class Command(BaseCommand):
    help = (
        "Re-encrypt every sending password under MAIL_PASSWORD_KEY, the platform's and each "
        "organisation's, reading the old ones with MAIL_PASSWORD_KEY_PREVIOUS."
    )

    def handle(self, *args: Any, **options: Any) -> None:
        secrets.keys()
        tenants: list[Tenant | None] = [None, *visited_by_background_work()]
        for tenant in tenants:
            with schema_context(tenant.number if tenant else None), transaction.atomic():
                # A sender that signs in nowhere stores no password, and there is nothing to rotate.
                senders = list(
                    MailSender.objects.select_for_update().exclude(password_encrypted=b"")
                )
                for sender in senders:
                    sender.password_encrypted = secrets.rotated(bytes(sender.password_encrypted))
                    sender.save(update_fields=["password_encrypted"])
                record(
                    actor=None,
                    action="mail.key_rotated",
                    obj=None,
                    before=None,
                    after={"senders": len(senders)},
                    tenant=tenant,
                )
            where = f"organisation {tenant.number}" if tenant else "the platform"
            self.stdout.write(f"{where}: {len(senders)} re-encrypted")
