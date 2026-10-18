"""Export jobs (DL-0172, DL-0193, DL-0241): one requested export of a stated version, rendered by
the render worker. The row is written before the job is queued and names what was asked; the file
it produces lives on the exports volume for a day and is not a record.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from syngraphe.provenance import Mutable

# A failure's reason: the constructs the validator refused, or the renderer's error, one line.
REASON_MAX = 500


class ExportFormat(models.TextChoices):
    PDF = "pdf", "pdf"
    DOCX = "docx", "docx"
    MARKDOWN = "markdown", "markdown"


class ExportView(models.TextChoices):
    CANONICAL = "canonical", "canonical"
    ACCEPTED = "accepted", "accepted"
    PENDING_EDITS = "pending_edits", "pending_edits"
    MY_EDITS = "my_edits", "my_edits"


class ExportChanges(models.TextChoices):
    MARKED = "marked", "marked"
    CLEAN = "clean", "clean"


class ExportAppendices(models.TextChoices):
    NONE = "none", "none"
    EMBEDDED = "embedded", "embedded"
    SEPARATE = "separate", "separate"


class ExportState(models.TextChoices):
    QUEUED = "queued", "queued"
    DONE = "done", "done"
    FAILED = "failed", "failed"


class ExportJob(models.Model):
    """One export: what, format, view and changes as the dialog composed them, the version they
    are of, and the job's outcome."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        "documents.Document", on_delete=models.PROTECT, related_name="exports"
    )
    # Required: an export is of a stated version, never whatever the head is when it runs.
    version = models.ForeignKey("documents.Version", on_delete=models.PROTECT, related_name="+")
    include_document = models.BooleanField(default=True)
    appendices = models.CharField(
        max_length=8, choices=ExportAppendices.choices, default=ExportAppendices.NONE
    )
    include_attachments = models.BooleanField(default=False)
    format = models.CharField(max_length=8, choices=ExportFormat.choices)
    view = models.CharField(max_length=13, choices=ExportView.choices)
    changes = models.CharField(
        max_length=6, choices=ExportChanges.choices, default=ExportChanges.CLEAN
    )
    # The version the marks are measured against (DL-0241); set exactly when they are marked.
    baseline_version = models.ForeignKey(
        "documents.Version", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    # Asked from a version's historical page: re-checked against the reader's ceiling when it runs,
    # not against the view's rights (DL-0423).
    at_version = models.BooleanField(default=False)
    state = models.CharField(max_length=6, choices=ExportState.choices, default=ExportState.QUEUED)
    # The produced file's path under the exports root, `<job id>/<file name>`.
    artifact_ref = models.CharField(max_length=400, blank=True)
    failure_reason = models.CharField(max_length=REASON_MAX, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(changes=ExportChanges.CLEAN, baseline_version__isnull=True)
                | Q(changes=ExportChanges.MARKED, baseline_version__isnull=False),
                name="rendering_exportjob_baseline_when_marked",
            ),
            models.CheckConstraint(
                condition=Q(state=ExportState.DONE, artifact_ref__gt="")
                | ~Q(state=ExportState.DONE),
                name="rendering_exportjob_done_has_its_file",
            ),
            models.CheckConstraint(
                condition=~Q(format=ExportFormat.MARKDOWN, changes=ExportChanges.MARKED),
                name="rendering_exportjob_markdown_is_clean",
            ),
        ]

    def __str__(self) -> str:
        return f"export {self.pk}"


class Stylesheet(Mutable):
    """The organisation's stylesheet (DL-0464, DL-0465): one row per organisation, empty for the
    platform's default; read only through `rendering.stylesheet.applied`."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    text = models.TextField(blank=True)

    class Meta(Mutable.Meta):
        abstract = False


class SampleExport(models.Model):
    """A sample PDF or Word file of the built-in invented text, rendered with a stylesheet as it
    stood in the styles page's box (DL-0466): written before it is queued, and done only when the
    worker says so. Its file is kept for a day, as an export's is; the row stays with the text it
    was asked with."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    format = models.CharField(max_length=8, choices=ExportFormat.choices)
    stylesheet = models.TextField(blank=True)
    language = models.CharField(max_length=8)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    state = models.CharField(max_length=6, choices=ExportState.choices, default=ExportState.QUEUED)
    artifact_ref = models.CharField(max_length=400, blank=True)
    failure_reason = models.CharField(max_length=REASON_MAX, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(format__in=[ExportFormat.PDF, ExportFormat.DOCX]),
                name="rendering_sampleexport_format_pdf_or_docx",
            ),
            models.CheckConstraint(
                condition=Q(state=ExportState.DONE, artifact_ref__gt="")
                | ~Q(state=ExportState.DONE),
                name="rendering_sampleexport_done_has_its_file",
            ),
        ]

    def __str__(self) -> str:
        return f"sample {self.pk}"
