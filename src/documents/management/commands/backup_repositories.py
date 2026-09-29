"""`manage.py backup_repositories`: one bundle run now, as the ten-minute task runs it."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from documents import backup
from documents.restore import shown


class Command(BaseCommand):
    help = (
        "Bundle every repository whose refs moved, copy the bundles to the backup store and write "
        "the run's marker; exit 1 when a repository failed or another run was running."
    )

    def handle(self, *args: Any, **options: Any) -> None:
        result = backup.run(backup.store_from_environment())
        if result is None:
            raise CommandError("another bundle run is running")
        self.stdout.write(f"marker {shown(result.start)}: {len(result.bundled)} bundled")
        for failure in result.failures:
            self.stdout.write(
                f"tenant {failure['tenant']} document {failure['document']}: "
                f"failed at {failure['stage']} since {shown(failure['since'])}"
            )
        if result.failures:
            count = len(result.failures)
            raise CommandError(f"{count} {'repository' if count == 1 else 'repositories'} failed")
