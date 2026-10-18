"""The render worker's tasks: an export, and the hourly sweep of kept files. Both run on the
`render` queue, whose worker has no way out of its network (ADR-0013)."""

from __future__ import annotations

from typing import Any

from celery import shared_task

from rendering import sample
from rendering.export import job
from rendering.models import ExportState
from tenancy.schemas import schema_context

# A render past this is stopped and its job failed with the reason; the hard limit, a minute on,
# ends a render that ignores the soft one.
SOFT_LIMIT = 540
HARD_LIMIT = 600


@shared_task(name="rendering.render_export", soft_time_limit=SOFT_LIMIT, time_limit=HARD_LIMIT)
def render_export(tenant: int, job_id: str) -> str:
    """Run one export job in its tenant's schema; its state after."""
    with schema_context(tenant):
        return str(job.run(job_id, tenant))


@shared_task(name="rendering.sweep_exports")
def sweep_exports() -> int:
    """Delete the exported files older than a day; the job rows stay."""
    return job.sweep()


# A sample found held when its delivery arrives — by a request reading the queue for a moment —
# is tried again shortly, never dropped with nothing left to make it.
SAMPLE_RETRIES = 6
SAMPLE_RETRY_SECONDS = 5


@shared_task(
    bind=True,
    name="rendering.render_sample",
    soft_time_limit=SOFT_LIMIT,
    time_limit=HARD_LIMIT,
    max_retries=SAMPLE_RETRIES,
)
def render_sample(self: Any, tenant: int, sample_id: str) -> str:
    """Make one sample in its tenant's schema (DL-0466); its state after."""
    with schema_context(tenant):
        state = sample.run(sample_id, tenant)
    if state == ExportState.QUEUED:
        raise self.retry(countdown=SAMPLE_RETRY_SECONDS)
    return str(state)
