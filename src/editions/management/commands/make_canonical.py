"""`make_canonical`: a document frozen and made canonical by a named member, through the services
the interface calls — how a loaded document reaches its first edition before its readers are
lowered to *view canonical* (DL-0350)."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from access.rights import Right, rights_on
from documents.locks import LockTimeout, document_lock
from documents.models import Document
from editions import services
from editions.models import Edition, open_freeze
from editions.visible import latest_edition
from identity.managers import fold_email
from identity.models import User
from review.services import RecordIncomplete, settle_head
from tenancy.models import Tenant, TenantState
from tenancy.schemas import schema_context

# The audit trail's mark on the acts this command performs as the member it names.
VIA = "make_canonical"


class Command(BaseCommand):
    help = (
        "Freeze the document, unless it is frozen already, and make its latest accepted version "
        "the next edition, as the member named with --as, who holds freeze and make canonical. "
        "A document that could not then be made canonical is reported and left as it is."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--tenant", type=int, required=True, help="the organisation's number")
        parser.add_argument("--document", type=int, required=True, help="the document's number")
        parser.add_argument("--as", dest="member", required=True, help="the member's address")
        parser.add_argument("--reason", default="", help="the freeze's reason, one line")

    def handle(
        self, *args: Any, tenant: int, document: int, member: str, reason: str, **options: Any
    ) -> None:
        if not Tenant.objects.filter(number=tenant, state=TenantState.ACTIVE).exists():
            raise CommandError(f"no active tenant numbered {tenant}")
        user = User.objects.filter(email=fold_email(member)).first()
        if user is None:
            raise CommandError(f"no person with the address {member}")
        with schema_context(tenant):
            found = Document.objects.filter(number=document).first()
            if found is None:
                raise CommandError(f"no document {document} in tenant {tenant}")
            try:
                edition = self._act(tenant, found, user, reason)
            except services.FreezeRefused as error:
                raise CommandError(f"not frozen: {error.reason}") from None
            except services.CanonicalRefused as error:
                raise CommandError(f"not made canonical: {error.reason}") from None
            except LockTimeout:
                raise CommandError("the document is busy; run the command again") from None
            except RecordIncomplete as error:
                raise CommandError(f"the document's record is incomplete: {error}") from None
            if edition is None:
                return
            self.stdout.write(f"document {found.number} · edition {edition.number}")

    def _act(self, tenant: int, document: Document, user: User, reason: str) -> Edition | None:
        """Freeze, unless frozen already, and make canonical, in one hold of the document's lock:
        nothing is frozen that the same hold could not then make canonical. `None` when the
        document is already at an edition with nothing accepted since — a re-run's answer."""
        with document_lock(tenant, document.number, timeout=services.LOCK_WAIT_SECONDS):
            settle_head(document)
            if Right.FREEZE not in rights_on(user, document):
                raise services.CanonicalRefused("not_permitted")
            if open_freeze(document) is None:
                refused = services.canonical_refusal(document, user, once_frozen=True)
                latest = latest_edition(document)
                if refused == "nothing_accepted" and latest is not None:
                    self.stdout.write(
                        f"document {document.number} · edition {latest.number} already made"
                        " — skipped"
                    )
                    return None
                if refused is not None:
                    raise services.CanonicalRefused(refused)
                if services.next_edition_tagged(document):
                    raise RecordIncomplete("a tag of the next edition's number exists already")
                services.freeze_locked(document, user, reason, via=VIA)
            return services.make_canonical_locked(document, user, via=VIA)
