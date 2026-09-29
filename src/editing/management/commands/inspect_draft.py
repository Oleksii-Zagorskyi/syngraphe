"""`manage.py inspect_draft`: print a document's draft — the open hold's, or else the latest."""

from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db.models import F

from audit.record import record
from documents.models import Document
from documents.reconcile import tenant_exists
from editing.models import Draft
from tenancy.models import Tenant
from tenancy.schemas import schema_context


class Command(BaseCommand):
    help = (
        "Print a document's draft as JSON: the open hold's, or else the latest hold's. The read "
        "is recorded in the audit trail."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--tenant", type=int, required=True, help="the tenant, by its number")
        parser.add_argument("--document", type=int, required=True, help="the document, by number")

    def handle(self, *args: Any, **options: Any) -> None:
        if not tenant_exists(options["tenant"]):
            raise CommandError(f"no tenant {options['tenant']}")
        with schema_context(options["tenant"]):
            document = Document.objects.filter(number=options["document"]).first()
            if document is None:
                raise CommandError(f"no document {options['document']}")
            draft = (
                Draft.objects.filter(hold__document=document)
                .select_related("hold")
                .order_by(F("hold__released_at").desc(nulls_first=True), "-hold__acquired_at")
                .first()
            )
            if draft is None:
                raise CommandError(f"document {document.number} has no draft")
            hold = draft.hold
            record(
                actor=None,
                action="document.draft_inspected",
                obj=document,
                before=None,
                after={"number": document.number},
                tenant=Tenant.objects.get(number=options["tenant"]),
            )
            printed = {
                "document": document.number,
                "hold": {
                    "acquired_at": hold.acquired_at.isoformat(timespec="seconds"),
                    "released_at": hold.released_at.isoformat(timespec="seconds")
                    if hold.released_at
                    else None,
                    "release_kind": hold.release_kind or None,
                },
                "base_commit": draft.base_commit,
                "content": draft.content,
            }
        self.stdout.write(json.dumps(printed, ensure_ascii=False, indent=2))
