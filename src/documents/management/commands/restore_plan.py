"""`manage.py restore_plan`: where a whole-host restore takes the database, from the markers in
the store and `pgbackrest verify`'s report read on standard input (DL-0314)."""

from __future__ import annotations

import sys
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from documents import backup, restore


class Command(BaseCommand):
    help = (
        "Print the three bounds of a whole-host restore — the newest clean marker, the last good "
        "moment and the end of the archive — and the one that governs. Reads `pgbackrest verify` "
        "from standard input. The last line is the recovery, as pgBackRest's own variables, "
        "each one word: a time target is written with a `T`, which `restore-database.sh` turns "
        "into the space pgBackRest reads."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--good", help="the last good moment, YYYYMMDDTHHMMSSZ, in UTC")
        parser.add_argument(
            "--marker",
            help="aim at this marker's start; the repositories it lists lose their commits since "
            "their last bundle",
        )
        parser.add_argument(
            "--end-of-archive",
            action="store_true",
            help="recover to the end of the archive, after a recovery to the target stopped "
            "because the archive ended before it",
        )
        parser.add_argument(
            "--database-only",
            action="store_true",
            help="the repositories are intact on the host: no marker bounds the restore",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            plan = restore.plan(
                [] if options["database_only"] else backup.markers(backup.store_from_environment()),
                verify=sys.stdin.read(),
                good=options["good"],
                marker=options["marker"],
                end_of_archive=options["end_of_archive"],
                database_only=options["database_only"],
            )
        except (restore.NoTarget, ValueError) as error:
            raise CommandError(str(error)) from error
        self.stdout.write(plan.describe())
