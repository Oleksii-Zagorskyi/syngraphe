"""`manage.py reconcile`: where the repositories and their rows disagree; repaired on request."""

from __future__ import annotations

import sys
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from documents import reconcile


class Command(BaseCommand):
    help = (
        "Report where the document repositories and their rows disagree, and exit 1 when "
        "anything is found. With --repair, make the rows what git implies, and exit 1 when "
        "anything is left unrepaired."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--repair", action="store_true", help="repair mode: make the rows what git implies"
        )
        parser.add_argument(
            "--prune-rows",
            action="store_true",
            help="with --repair: delete a version row whose commit its repository no longer holds",
        )
        parser.add_argument("--tenant", type=int, help="one tenant, by its number")
        parser.add_argument("--document", type=int, help="one document of the tenant, by number")

    def handle(self, *args: Any, **options: Any) -> None:
        if options["prune_rows"] and not options["repair"]:
            raise CommandError("--prune-rows requires --repair")
        if options["document"] is not None and options["tenant"] is None:
            raise CommandError("--document requires --tenant")
        if options["tenant"] is not None and not reconcile.tenant_exists(options["tenant"]):
            raise CommandError(f"no tenant {options['tenant']} to reconcile")
        findings = reconcile.run(
            tenant=options["tenant"],
            document=options["document"],
            repair=options["repair"],
            prune_rows=options["prune_rows"],
        )
        if not findings:
            self.stdout.write("nothing to report")
            return
        for finding in findings:
            line = f"tenant {finding.tenant} document {finding.document}: {finding.kind}"
            if finding.detail:
                line += f" {finding.detail}"
            if finding.repaired:
                line += " — repaired"
            self.stdout.write(line)
        if not all(finding.repaired for finding in findings):
            sys.exit(1)
