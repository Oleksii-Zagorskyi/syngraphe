"""The documents' periodic tasks."""

from __future__ import annotations

import logging

from celery import shared_task

from documents import backup, backup_state, backup_watch, gitstore, housekeeping, reconcile
from documents.locks import LockTimeout

logger = logging.getLogger(__name__)

# A repository whose writer holds it longer than this is left for the next night.
REPACK_LOCK_SECONDS = 60.0


@shared_task(name="documents.reconcile_hourly")
def reconcile_hourly() -> int:
    """Repair what git implies, every hour, never deleting a row; log what is left unrepaired,
    by numbers and kind. Returns how much was found."""
    findings = reconcile.run(repair=True, prune_rows=False)
    for finding in findings:
        if not finding.repaired:
            logger.warning(
                "the reconciler left a finding unrepaired",
                extra={
                    "tenant": finding.tenant,
                    "document": finding.document,
                    "finding": finding.kind,
                },
            )
    return len(findings)


@shared_task(name="documents.repack_nightly")
def repack_nightly() -> int:
    """Repack and prune every repository under its lock. Pruning removes only debris from failed
    writes: an append-only linear history has no unreachable version (ASR-02). Returns how many
    repositories were done."""
    done = 0
    for tenant, document in gitstore.repositories():
        try:
            housekeeping.repack_and_prune(tenant, document, timeout=REPACK_LOCK_SECONDS)
        except (LockTimeout, OSError, housekeeping.HousekeepingFailure) as error:
            logger.error(
                "a repository was not repacked",
                extra={"tenant": tenant, "document": document, "error": str(error)},
            )
            continue
        done += 1
    return done


@shared_task(name="documents.backup_repositories")
def backup_repositories() -> int | None:
    """The ten-minute bundle run; the number of bundles written, `None` when a run was running."""
    result = backup.run(backup.store_from_environment())
    return None if result is None else len(result.bundled)


@shared_task(name="documents.backup_watch")
def watch_backup() -> None:
    """The backup's three conditions, every minute; nothing until the `backup` service has made
    the worker's state folder."""
    if not backup_state.folder_ready("run"):
        logger.warning("the backup's state folder is not there yet; this check is skipped")
        return
    backup_watch.check()
