"""`load_document`: prepared folders loaded as documents, each accepted as `0.1` by a named member
of a named group (ST-0074, DL-0341, DL-0348)."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from access.models import AccessGroup
from documents import loading
from documents.parts import attachments
from identity.managers import fold_email
from identity.models import User
from review.services import accepted_content_version, latest_acceptance
from tenancy.models import Tenant, TenantState
from tenancy.schemas import schema_context


class Command(BaseCommand):
    help = (
        "Load each folder as a document: its text and attachments committed as one version and "
        "accepted, by the member named with --as through the group named with --group. The "
        "first folder refused stops the run; those loaded before it stand."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--tenant", type=int, required=True, help="the organisation's number")
        parser.add_argument(
            "--as", dest="loader", required=True, help="the loading member's address"
        )
        parser.add_argument(
            "--group", required=True, help="the group's id, from its page's address"
        )
        parser.add_argument("folders", nargs="+", help="one folder per document")

    def handle(
        self, *args: Any, tenant: int, loader: str, group: str, folders: list[str], **options: Any
    ) -> None:
        if not Tenant.objects.filter(number=tenant, state=TenantState.ACTIVE).exists():
            raise CommandError(f"no active tenant numbered {tenant}")
        user = User.objects.filter(email=fold_email(loader)).first()
        if user is None:
            raise CommandError(f"no person with the address {loader}")
        try:
            group_id = uuid.UUID(group)
        except ValueError:
            raise CommandError(f"not a group id: {group!r}") from None
        with schema_context(tenant):
            access_group = AccessGroup.objects.filter(pk=group_id).first()
            if access_group is None:
                raise CommandError(f"no group {group} in tenant {tenant}")
            for folder in folders:
                try:
                    document = loading.load(Path(folder), user, access_group)
                except loading.AlreadyLoaded as skipped:
                    self.stdout.write(str(skipped))
                    continue
                except loading.Refused as error:
                    raise CommandError(f"refused, nothing written: {error}") from None
                except loading.Stopped as error:
                    raise CommandError(str(error)) from None
                acceptance = latest_acceptance(document)
                assert acceptance is not None
                shown = accepted_content_version(acceptance)
                self.stdout.write(
                    f"document {document.number} · version {acceptance.number} · "
                    f"attachments: {len(attachments(shown))}"
                )
