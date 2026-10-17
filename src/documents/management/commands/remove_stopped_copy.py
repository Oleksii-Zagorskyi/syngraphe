"""Remove a copy that stopped before it was made (DL-0455): the reconciler reports it
`copy_stopped` and never finishes it; this command removes its repository, then every row derived
for it and its own, and audits the removal. The copier copies again; its number is never given
again. Run again after a stop between the two, it finds no repository and removes the rows."""

from __future__ import annotations

import shutil
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction
from django.utils import timezone

from audit.record import record
from documents import gitstore
from documents.locks import document_lock
from documents.models import Document, DocumentState, Version
from documents.reconcile import CREATING_GRACE, is_a_copy
from tenancy.models import Tenant, TenantState
from tenancy.schemas import schema_context


class Command(BaseCommand):
    help = (
        "Remove a copy that stopped before it was made: its repository, its rows, its record of "
        "being created. Refused for anything but a copy still being created past the grace."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--tenant", type=int, required=True, help="the organisation's number")
        parser.add_argument("--document", type=int, required=True, help="the copy's number")

    def handle(self, *args: Any, tenant: int, document: int, **options: Any) -> None:
        organisation = Tenant.objects.filter(number=tenant, state=TenantState.ACTIVE).first()
        if organisation is None:
            raise CommandError(f"no active tenant numbered {tenant}")
        # Decided under the copy's writer lock, which its own process holds until it is finished:
        # a copy older than the grace may still be alive, and finish while this waits.
        with schema_context(tenant), document_lock(tenant, document):
            found = Document.objects.filter(number=document).first()
            if found is None:
                self.stdout.write(f"document {document}: nothing to remove")
                return
            if found.state != DocumentState.CREATING or not is_a_copy(found):
                raise CommandError(f"document {document} is not a stopped copy")
            if found.created_at > timezone.now() - CREATING_GRACE:
                raise CommandError(
                    f"document {document} may still be being copied; run the command again later"
                )
            # The repository first: a stop between the two leaves rows a second run removes.
            path = gitstore.repository_path(tenant, document)
            if path.exists():
                shutil.rmtree(path)
            with transaction.atomic():
                record(
                    actor=None,
                    action="document.stopped_copy_removed",
                    obj=found,
                    before=None,
                    after={"number": found.number},
                    tenant=organisation,
                )
                # Each version's caches go with it.
                Version.objects.filter(document=found).delete()
                found.delete()
        self.stdout.write(f"document {document} · stopped copy removed")
