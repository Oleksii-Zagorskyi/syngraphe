"""The sample a stylesheet is tried on (DL-0466): the built-in invented text, its title page in
the organisation's layout and an attachment list, rendered by the render worker through the
export's own functions with the stylesheet as it stood in the styles page's box.

The texts are plain Markdown, one a language, loaded by path from `samples/`, so whoever reads or
changes them need not read Python.
"""

from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import formats, timezone, translation
from django.utils.translation import gettext as _
from django.utils.translation import pgettext

from rendering.models import ExportFormat, ExportState, SampleExport

logger = logging.getLogger(__name__)

SAMPLES = Path(__file__).resolve().parent / "samples"


def text_for(language: str) -> str:
    """The sample's text in `language`, the English one for a language without its own."""
    # Chosen from the texts there are, never built from the stored value.
    written = {path.stem: path for path in SAMPLES.glob("*.md")}
    return written.get(language, written["en"]).read_text(encoding="utf-8")


def images() -> dict[str, bytes]:
    """The sample's images, by the path its text names them by."""
    folder = SAMPLES / "images"
    return {f"images/{path.name}": path.read_bytes() for path in sorted(folder.glob("*.png"))}


def run(sample_id: str | uuid.UUID, tenant: int) -> ExportState:
    """Make the sample, in the tenant's schema the caller has set; its state after. The row is
    held for the whole run, as an export's is, so a second delivery finds it taken."""
    with transaction.atomic():
        sample = (
            SampleExport.objects.select_for_update(of=("self",), skip_locked=True)
            .filter(pk=sample_id)
            .first()
        )
        if sample is None:
            state = (
                SampleExport.objects.filter(pk=sample_id).values_list("state", flat=True).first()
            )
            return ExportState(state or ExportState.FAILED)
        if sample.state != ExportState.QUEUED:
            return ExportState(sample.state)
        return _held(sample)


def _held(sample: SampleExport) -> ExportState:
    folder = Path(settings.EXPORT_ROOT) / str(sample.pk)
    try:
        with translation.override(sample.language):
            html = compose(sample.language)
            name = pgettext("a sample file's name", "sample") + (
                ".pdf" if sample.format == ExportFormat.PDF else ".docx"
            )
        folder.mkdir(parents=True, exist_ok=True)
        _write(sample, html, folder / name)
    except Exception:
        logger.exception("a sample failed", extra={"sample": str(sample.pk)})
        shutil.rmtree(folder, ignore_errors=True)
        sample.state = ExportState.FAILED
        sample.failure_reason = _("Try again, or tell the operator.")
        sample.save(update_fields=["state", "failure_reason"])
        return ExportState.FAILED
    sample.state = ExportState.DONE
    sample.artifact_ref = f"{sample.pk}/{name}"
    sample.save(update_fields=["state", "artifact_ref"])
    return ExportState.DONE


def compose(language: str) -> str:
    """The sample's page as an export composes one: the body rendered by the export's call and
    context — no reader, so the mention is its words alone (DL-0438) and the image its path —
    its title page in the organisation's layout, an attachment list of two invented rows."""
    from documents.models import DocumentTemplate
    from rendering import title_page
    from rendering.export.compose import EXPORT_CONTEXT, page_html
    from rendering.renderer import render

    today = formats.date_format(timezone.localdate(), "j E Y")
    edition = "2.0"
    approver = _("An example approver")
    facts = title_page.TitleFacts(
        title=_("An example policy"),
        number="#1",
        type_label=_("An example type"),
        edition=edition,
        approver=approver,
        approval_date=today,
        text=_("Register entry: EX-0 (example)") + "\n" + _("A second line of its own text"),
        approval=_("Approved: %(name)s, %(date)s; edition %(number)s")
        % {"name": approver, "date": today, "number": edition},
    )
    layout = title_page.layout_of(DocumentTemplate.objects.get().title_page_layout)
    attachments = [
        {"title": _("An example form"), "file_name": "example-form.pdf", "sha256": "0" * 64},
        {
            "title": _("An example schedule"),
            "file_name": "example-schedule.xlsx",
            "sha256": "1" * 64,
        },
    ]
    return page_html(
        language=language,
        header=_("An example policy"),
        title_page=title_page.html(facts, layout),
        text=render(text_for(language), context=EXPORT_CONTEXT),
        attachments=attachments,
    )


def _write(sample: SampleExport, html: str, path: Path) -> None:
    from rendering.export import docx, pdf
    from rendering.stylesheet import export_stylesheets

    pictures = images()
    if sample.format == ExportFormat.PDF:
        pdf.write(
            html,
            path,
            stylesheets=export_stylesheets(sample.stylesheet),
            read_image=pictures.__getitem__,
        )
    else:
        docx.write(html, path, images=pictures, stylesheet=sample.stylesheet)
