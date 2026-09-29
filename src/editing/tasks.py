"""The editing app's worker tasks: per-line authorship after each commit (DL-0135, ADR-0011), and
the sweep that closes editors whose page went away without closing them (ASR-22)."""

from __future__ import annotations

import logging

from celery import shared_task
from django.db import DatabaseError

from documents import gitstore
from documents.models import Document
from editing import authorship
from tenancy.schemas import schema_context

logger = logging.getLogger(__name__)


@shared_task(name="editing.compute_authorship")
def compute_authorship(tenant_number: int, document_number: int, commit_sha: str) -> int:
    """Write the authorship rows of the version at `commit_sha`; returns how many. A commit whose
    version row is not there yet is left to the reconciler, which derives the row and queues this
    again; a failure of git is raised, for the reconciler's next pass to retry."""
    with schema_context(tenant_number):
        document = Document.objects.get(number=document_number)
        try:
            result = authorship.compute(
                document,
                commit_sha,
                repository_path=gitstore.repository_path(tenant_number, document_number),
            )
        except authorship.VersionMissing:
            logger.warning(
                "authorship waits for a version row",
                extra={"tenant": tenant_number, "document": document_number},
            )
            return 0
    return result.rows


def queue_authorship(tenant_number: int, document_number: int, commit_sha: str) -> None:
    """Ask the worker for the authorship of one commit; the request path never computes it."""
    compute_authorship.delay(tenant_number, document_number, commit_sha)


@shared_task(name="editing.close_silent_editors")
def close_silent_editors() -> int:
    """Close every open editor whose heartbeat stopped — a tab closed without closing its editor —
    in every organisation background work visits (`visited_by_background_work`). Returns how many
    were closed."""
    from django.utils import timezone

    from editing.models import OpenEditor
    from editing.views.capture import SILENT_AFTER
    from tenancy.models import visited_by_background_work

    closed = 0
    cutoff = timezone.now() - SILENT_AFTER
    for number in visited_by_background_work().values_list("number", flat=True):
        # One organisation's failure leaves the others' editors to be closed all the same.
        try:
            with schema_context(number):
                closed += OpenEditor.objects.filter(
                    closed_at__isnull=True, last_seen_at__lt=cutoff
                ).update(closed_at=timezone.now())
        except DatabaseError:
            logger.exception("silent editors not closed", extra={"tenant": number})
    return closed
