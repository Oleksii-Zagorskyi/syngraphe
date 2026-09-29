"""`manage.py release_hold`: an operator ends a hold that will not release; the draft is kept."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction

from documents.locks import document_lock
from documents.models import Document
from documents.reconcile import tenant_exists
from editing import holds
from editing.models import ReleaseKind
from tenancy.schemas import schema_context

REASON_MAX = 500


class Command(BaseCommand):
    help = (
        "Release the open hold on one document as forced, keeping its draft, and record the "
        "reason in the audit trail. The reason names neither the document nor a person."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--tenant", type=int, required=True, help="the tenant, by its number")
        parser.add_argument("--document", type=int, required=True, help="the document, by number")
        parser.add_argument("--reason", required=True, help="why the hold is released")

    def handle(self, *args: Any, **options: Any) -> None:
        reason = options["reason"].strip()
        if not reason or len(reason) > REASON_MAX:
            raise CommandError(f"--reason is required, at most {REASON_MAX} characters")
        if not tenant_exists(options["tenant"]):
            raise CommandError(f"no tenant {options['tenant']}")
        with schema_context(options["tenant"]):
            document = Document.objects.filter(number=options["document"]).first()
            if document is None:
                raise CommandError(f"no document {options['document']}")
            with document_lock(options["tenant"], document.number), transaction.atomic():
                Document.objects.select_for_update().get(pk=document.pk)
                hold = holds.open_hold(document)
                released = hold is not None and holds.release(
                    hold, ReleaseKind.FORCED, reason=reason
                )
        if released:
            self.stdout.write(f"released: document {document.number}; the draft is kept")
        else:
            self.stdout.write("nothing to release: the document is not held")
