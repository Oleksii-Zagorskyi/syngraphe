"""`manage.py restore_repositories`: every repository, or one, from its bundles in the store."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from documents import backup


class Command(BaseCommand):
    help = (
        "Restore each repository from its newest full bundle and every bundle after it, in "
        "order. A repository already on disk is left alone; move a damaged one aside first."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--tenant", type=int)
        parser.add_argument("--document", type=int)

    def handle(self, *args: Any, **options: Any) -> None:
        if options["document"] is not None and options["tenant"] is None:
            raise CommandError("--document requires --tenant")
        store = backup.store_from_environment()
        chains = backup.chains_in(store)
        wanted = [
            key
            for key in sorted(chains)
            if options["tenant"] in (None, key[0]) and options["document"] in (None, key[1])
        ]
        if not wanted:
            raise CommandError("no bundle in the store for what was asked")
        for tenant, document in wanted:
            outcome = backup.restore_repository(store, tenant, document, chains[(tenant, document)])
            self.stdout.write(f"tenant {tenant} document {document}: {outcome}")
