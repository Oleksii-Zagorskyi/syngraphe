"""Running an export job on the render worker: the content composed, the file written under the
exports root at `<job id>/<file name>` — one file, or one zip when attachments or separate
appendices go with it or a Markdown export's text shows images — and the row marked `done` with
its file, or `failed` with the reason. A job that is not `queued` is left alone, so a job queued
twice runs once.
"""

from __future__ import annotations

import hashlib
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
from rendering.export import compose, docx, names, pdf
from rendering.models import (
    REASON_MAX,
    ExportFormat,
    ExportJob,
    ExportState,
    SampleExport,
    Stylesheet,
)
from rendering.stylesheet import applied, export_stylesheets

logger = logging.getLogger(__name__)

# How long an export's file is kept: it is a download, not a record.
KEPT = timedelta(hours=24)
STYLESHEET = Path(__file__).resolve().parents[1] / "static" / "rendering" / "document.css"


def _images(composed: compose.Composed, tenant: int, job: ExportJob) -> dict[str, bytes]:
    """Every image the export shows, read before any writer runs: a *my edits* export's from the
    draft's staged rows first, then the version's tree, then a marked export's baseline. An image
    none of them holds — the draft discarded meanwhile — fails the job with its reason, which a
    writer's own fetch could not say."""
    if not composed.images:
        return {}
    from editing.models import DraftFile, DraftFileKind
    from rendering.models import ExportView

    repo = gitstore.open_repository(tenant, job.document.number)
    found: dict[str, bytes] = {}
    if job.view == ExportView.MY_EDITS:
        rows = DraftFile.objects.filter(
            draft__hold__document=job.document,
            draft__hold__user_id=job.requested_by_id,
            draft__hold__released_at__isnull=True,
            kind=DraftFileKind.IMAGE,
            path__in=composed.images,
            content__isnull=False,
        ).values_list("path", "content")
        found.update((path, bytes(content)) for path, content in rows if content is not None)
    commits = [job.version.commit_sha]
    if job.baseline_version is not None:
        commits.append(job.baseline_version.commit_sha)
    for path in composed.images:
        for commit in commits:
            if path in found:
                break
            try:
                found[path] = gitstore.read(repo, path, commit)
            except KeyError:
                continue
        if path not in found:
            raise compose.Refused(
                _("An image the text shows has gone since you asked; export again.")
            )
    return found


def _write_document(
    composed: compose.Composed,
    fmt: str,
    path: Path,
    pictures: dict[str, bytes],
    stylesheet: str = "",
) -> None:
    """One file of the export; `stylesheet` the organisation's, as `_held` read it once for the
    whole job, so no file of it goes unstyled or takes another look."""
    if fmt == ExportFormat.MARKDOWN:
        path.write_text(composed.markdown, encoding="utf-8")
    elif fmt == ExportFormat.PDF:
        stylesheets = export_stylesheets(stylesheet)
        pdf.write(composed.html, path, stylesheets=stylesheets, read_image=pictures.__getitem__)
    else:
        docx.write(composed.html, path, images=pictures, stylesheet=stylesheet)


def _zip(
    composed: compose.Composed,
    document: Path | None,
    folder: Path,
    scratch: Path,
    tenant: int,
    job: ExportJob,
    pictures: dict[str, bytes],
    stylesheet: str = "",
) -> Path:
    """The document, when chosen, each separate appendix, the images beside a Markdown text under
    the paths it names them by, and the attachments as stored, in one zip of the document's
    name. Every attachment is read as the download reads it, its hash checked: a file that does
    not match its entry fails the job."""
    word = pgettext("a part in an exported file's name", "attachment")
    inner = _("Document").lower() + Path(composed.name).suffix
    target = folder / (Path(composed.name).stem + ".zip")
    partial = scratch / (target.name + ".part")
    with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as bundle:
        if document is not None:
            bundle.write(document, inner)
        for part in composed.appendices:
            written = scratch / part.name
            _write_document(
                compose.Composed(name=part.name, header="", html=part.html, markdown=part.markdown),
                job.format,
                written,
                pictures,
                stylesheet,
            )
            bundle.write(written, part.name)
        if job.format == ExportFormat.MARKDOWN:
            for image, data in pictures.items():
                bundle.writestr(image, data)
        for item in composed.attachments:
            number = int(item["number"])
            data = _attachment(job, tenant, number)
            if hashlib.sha256(data).hexdigest() != item.get("sha256"):
                # A draft changed between the list composed above and this read: the file would
                # not be the one the export's list names.
                raise compose.Refused(
                    _("Your draft changed while the file was being made; export again.")
                )
            bundle.writestr(names.part_name(word, number, str(item.get("file_name", ""))), data)
    partial.replace(target)
    return target


def _attachment(job: ExportJob, tenant: int, number: int) -> bytes:
    """Attachment `number`'s bytes as the export lists it — the version's, or for *my edits* the
    draft's, staged or at the draft's base — hash checked; a mismatch is logged as a defect where
    it is read, and fails the job."""
    from documents.parts import read_attachment
    from rendering.models import ExportView

    try:
        if job.view == ExportView.MY_EDITS:
            from editing.holds import open_hold
            from editing.models import Draft
            from editing.parts import draft_attachment

            hold = open_hold(job.document)
            if hold is None or hold.user_id != job.requested_by_id:
                raise compose.Refused(
                    _("Your draft has been finished or discarded since you asked.")
                )
            return draft_attachment(Draft.objects.get(hold=hold), number)[1]
        return read_attachment(tenant, job.document, job.version, number)[1]
    except KeyError as missing:
        raise compose.Refused(
            _("An attachment has gone since you asked; export again.")
        ) from missing
    except ValueError as mismatch:
        raise compose.Refused(
            _("An attachment's file does not match its record; tell the operator.")
        ) from mismatch


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
            # The organisation's look as it stands when the job runs, read once (DL-0464).
            stylesheet = applied(Stylesheet.objects.get().text)
            folder.mkdir(parents=True, exist_ok=True)
            # Marked as fresh: the hourly sweep keys on the folder's age.
            os.utime(folder)
            with tempfile.TemporaryDirectory(dir=folder) as scratch:
                document: Path | None = None
                writes = job.include_document or bool(composed.appendices)
                pictures = _images(composed, tenant, job) if writes else {}
                if job.include_document:
                    document = Path(scratch) / composed.name
                    _write_document(composed, job.format, document, pictures, stylesheet)
                beside = job.format == ExportFormat.MARKDOWN and bool(pictures)
                if composed.attachments or composed.appendices or beside:
                    produced = _zip(
                        composed, document, folder, Path(scratch), tenant, job, pictures, stylesheet
                    )
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


def artifact(job: ExportJob | SampleExport) -> Path | None:
    """The job's file, or the sample's (DL-0466), while it is kept."""
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
