"""The render worker's tasks: an export, and the hourly sweep of kept files. Both run on the
`render` queue, whose worker has no way out of its network (ADR-0013)."""

from __future__ import annotations

from celery import shared_task

from rendering.export import job
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
