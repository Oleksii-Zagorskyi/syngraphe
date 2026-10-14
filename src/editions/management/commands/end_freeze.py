"""`end_freeze`: an operator ends a freeze no holder of *freeze* is there to end — *unfreeze* with
no actor — with a reason recorded in the audit trail."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from documents.locks import LockTimeout
from documents.models import Document
from editions import services
from review.services import RecordIncomplete
from tenancy.models import Tenant, TenantState
from tenancy.schemas import schema_context


class Command(BaseCommand):
    help = (
        "End the document's freeze as unfrozen, writing an audit event with the reason given. "
        "A document that is not frozen is reported and left as it is."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--tenant", type=int, required=True, help="the organisation's number")
        parser.add_argument("--document", type=int, required=True, help="the document's number")
        parser.add_argument("--reason", required=True, help="why the operator ends it, one line")

    def handle(self, *args: Any, tenant: int, document: int, reason: str, **options: Any) -> None:
        if not Tenant.objects.filter(number=tenant, state=TenantState.ACTIVE).exists():
            raise CommandError(f"no active tenant numbered {tenant}")
        with schema_context(tenant):
            found = Document.objects.filter(number=document).first()
            if found is None:
                raise CommandError(f"no document {document} in tenant {tenant}")
            try:
                services.end_freeze(found, reason)
            except ValueError as error:
                raise CommandError(str(error)) from None
            except LockTimeout:
                raise CommandError("the document is busy; run the command again") from None
            except RecordIncomplete as error:
                raise CommandError(f"the document's record is incomplete: {error}") from None
            self.stdout.write(f"document {found.number} · freeze ended")
