"""Running an export job on the render worker: the content composed, the file written under the
exports root at `<job id>/<file name>` — one file, or one zip when attachments go with it — and the
row marked `done` with its file, or `failed` with the reason. A job that is not `queued` is left
alone, so a job queued twice runs once.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import uuid
import zipfile
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from django.utils.translation import pgettext

from documents import gitstore
from rendering.export import compose, docx, furniture, names, pdf
from rendering.models import REASON_MAX, ExportFormat, ExportJob, ExportState

logger = logging.getLogger(__name__)

# How long an export's file is kept: it is a download, not a record.
KEPT = timedelta(hours=24)
STYLESHEET = Path(__file__).resolve().parents[1] / "static" / "rendering" / "document.css"


def _write_document(
    composed: compose.Composed, fmt: str, path: Path, tenant: int, job: ExportJob
) -> None:
    repo = gitstore.open_repository(tenant, job.document.number)
    commit = job.version.commit_sha

    def read_image(image: str) -> bytes:
        return gitstore.read(repo, image, commit)

    if fmt == ExportFormat.MARKDOWN:
        path.write_text(composed.markdown, encoding="utf-8")
    elif fmt == ExportFormat.PDF:
        stylesheets = [STYLESHEET.read_text(encoding="utf-8"), furniture.pdf_css()]
        pdf.write(composed.html, path, stylesheets=stylesheets, read_image=read_image)
    else:
        docx.write(composed.html, path)


def _zip(
    composed: compose.Composed,
    document: Path | None,
    folder: Path,
    scratch: Path,
    tenant: int,
    job: ExportJob,
) -> Path:
    """The document, when chosen, and its attachments as stored, in one zip of the document's
    name."""
    repo = gitstore.open_repository(tenant, job.document.number)
    word = pgettext("a part in an exported file's name", "attachment")
    inner = _("Document").lower() + Path(composed.name).suffix
    target = folder / (Path(composed.name).stem + ".zip")
    partial = scratch / (target.name + ".part")
    with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as bundle:
        if document is not None:
            bundle.write(document, inner)
        for item in composed.attachments:
            number = int(item["number"])
            data = gitstore.read(repo, f"attachments/{number}", job.version.commit_sha)
            bundle.writestr(names.part_name(word, number, str(item.get("file_name", ""))), data)
    partial.replace(target)
    return target


def run(job_id: str | uuid.UUID, tenant: int) -> ExportState:
    """Run the job, in the tenant's schema the caller has set; its state after. The job's row is
    held for the whole run, so a second delivery — the queue's, or the reconciler's after the
    grace — finds it taken and leaves it; a run that dies leaves it queued for the next."""
    with transaction.atomic():
        job = (
            ExportJob.objects.select_for_update(of=("self",), skip_locked=True)
            .select_related("document", "version", "baseline_version", "requested_by")
            .filter(pk=job_id)
            .first()
        )
        if job is None:
            state = ExportJob.objects.filter(pk=job_id).values_list("state", flat=True).first()
            return ExportState(state or ExportState.FAILED)
        if job.state != ExportState.QUEUED:
            return ExportState(job.state)
        return _held(job, tenant)


def _held(job: ExportJob, tenant: int) -> ExportState:
    folder = Path(settings.EXPORT_ROOT) / str(job.pk)
    try:
        with translation.override(settings.LANGUAGE_CODE):
            if not compose.still_permitted(job):
                raise compose.Refused(_("The version asked for is no longer one you may export."))
            if job.at_version:
                # The number the version's page shows, from git and the passport (DL-0183, DL-0267).
                from editing import numbering

                number = numbering.number_of(job.document, job.version)
            else:
                number = compose.number_of(job.document, job.version, job.view)
            composed = compose.compose(job, tenant, number=number)
            folder.mkdir(parents=True, exist_ok=True)
            # Marked as fresh: the hourly sweep keys on the folder's age.
            os.utime(folder)
            with tempfile.TemporaryDirectory(dir=folder) as scratch:
                document: Path | None = None
                if job.include_document:
                    document = Path(scratch) / composed.name
                    _write_document(composed, job.format, document, tenant, job)
                if composed.attachments:
                    produced = _zip(composed, document, folder, Path(scratch), tenant, job)
                elif document is not None:
                    produced = folder / composed.name
                    document.replace(produced)
                else:
                    raise compose.Refused(_("The chosen version has no attachments to export."))
    except compose.Refused as refusal:
        return _failed(job, str(refusal), folder)
    except Exception:
        logger.exception("an export failed", extra={"export": str(job.pk)})
        return _failed(
            job, _("The file could not be made. Try again, or tell the operator."), folder
        )
    job.state = ExportState.DONE
    job.artifact_ref = f"{job.pk}/{produced.name}"
    job.save(update_fields=["state", "artifact_ref"])
    return ExportState.DONE


def _failed(job: ExportJob, reason: str, folder: Path) -> ExportState:
    shutil.rmtree(folder, ignore_errors=True)
    job.state = ExportState.FAILED
    job.failure_reason = reason[:REASON_MAX]
    job.save(update_fields=["state", "failure_reason"])
    return ExportState.FAILED


def artifact(job: ExportJob) -> Path | None:
    """The job's file, while it is kept."""
    if job.state != ExportState.DONE or not job.artifact_ref:
        return None
    root = Path(settings.EXPORT_ROOT).resolve()
    path = (root / job.artifact_ref).resolve()
    if root not in path.parents or not path.is_file():
        return None
    return path


def sweep(now: object | None = None) -> int:
    """Delete every job's files older than a day; the rows stay. How many folders went."""
    root = Path(settings.EXPORT_ROOT)
    if not root.is_dir():
        return 0
    cutoff = (now or timezone.now()).timestamp() - KEPT.total_seconds()  # type: ignore[attr-defined]
    gone = 0
    for folder in root.iterdir():
        if folder.is_dir() and folder.stat().st_mtime < cutoff:
            shutil.rmtree(folder, ignore_errors=True)
            gone += 1
    return gone
