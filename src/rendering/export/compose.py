"""What an export is made of (DL-0172, DL-0193, DL-0209, DL-0241): the views a reader may export
with the version each shows and the baseline its marks would be measured against, and — for a
job — the text, the document's HTML page, the Markdown, the header and the file's name.

The text is validated before any renderer sees it: a construct the platform refuses fails the job
by name. Images reach an export as their descriptions, as they reach the reading view.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from typing import TYPE_CHECKING, Any

import pygit2
from django.utils import formats, timezone
from django.utils.translation import gettext as _
from django.utils.translation import pgettext

from access.rights import Right, rights_on
from documents import bundle, gitstore
from documents.models import Document, Version, VersionKind
from editing.markdown.validator import validate
from editing.numbering import BEFORE_ANY_ACCEPTANCE
from editions.models import Edition
from rendering.export import furniture, names
from rendering.export.markdown import join_paragraphs
from rendering.models import ExportChanges, ExportFormat, ExportView
from rendering.renderer import render
from review.services import accepted_content_version, latest_acceptance, number_key, run

if TYPE_CHECKING:
    from rendering.models import ExportJob

# The shortened hash an attachment list shows; a PDF or DOCX carries the full value in its
# metadata, a Markdown export in the list itself.
HASH_SHOWN = 16
CONTENT = (gitstore.Kind.EDIT, gitstore.Kind.REVIEWER_EDIT)
EXTENSIONS = {ExportFormat.PDF: "pdf", ExportFormat.DOCX: "docx", ExportFormat.MARKDOWN: "md"}


class Refused(Exception):
    """The text holds constructs the platform refuses; the reason names each with its line."""


def stance(view: str) -> str:
    """The stance a view shows, in the glossary's words (DL-0182, DL-0275)."""
    return {
        ExportView.CANONICAL: pgettext("stance", "canonical version"),
        ExportView.ACCEPTED: pgettext("stance", "accepted edits"),
        ExportView.PENDING_EDITS: pgettext("stance", "pending edits"),
        ExportView.MY_EDITS: pgettext("stance", "my edits"),
    }[ExportView(view)]


@dataclass(frozen=True)
class Offer:
    """One view the dialog offers: the version it shows and its number, and the baseline its
    marks are measured against — `None` where marks are not offered."""

    view: ExportView
    version: Version
    number: str
    baseline: Version | None
    baseline_number: str
    marked_by_default: bool


@dataclass(frozen=True)
class _Chain:
    """Where a document's versions stand: its editions, oldest first; the latest acceptance beyond
    the latest edition and its content version; and where the pending run starts, with the
    number it counts from."""

    editions: list[Edition]
    acceptance_content: Version | None
    acceptance_number: str
    start: Version
    base_number: str


def _chain(document: Document) -> _Chain:
    editions = sorted(
        Edition.objects.filter(version__document=document).select_related("version"),
        key=lambda e: number_key(e.number),
    )
    edition = editions[-1] if editions else None
    acceptance = latest_acceptance(document)
    if acceptance is not None and (
        edition is None or number_key(acceptance.number) > number_key(edition.number)
    ):
        content = accepted_content_version(acceptance)
        return _Chain(editions, content, acceptance.number, content, acceptance.number)
    if edition is not None:
        return _Chain(editions, None, "", edition.version, edition.number)
    created = Version.objects.get(document=document, kind=VersionKind.CREATED)
    return _Chain(editions, None, "", created, BEFORE_ANY_ACCEPTANCE)


def number_of(document: Document, version: Version, view: str) -> str:
    """The number `version` carries in `view`, from its history — so a job run after the chain
    moved on names the version it was asked for as it was then: an edition's number; the
    acceptance's that decided on it; else the last acceptance or edition behind it and how many
    content versions follow that up to it, the draft counting one more (DL-0183, DL-0272)."""
    from review.models import Acceptance
    from review.services import accepted_sha

    editions = {
        e.version.commit_sha: e.number
        for e in Edition.objects.filter(version__document=document).select_related("version")
    }
    if view == ExportView.CANONICAL:
        return editions.get(version.commit_sha, "")
    accepted: dict[str, str] = {}
    for acceptance in Acceptance.objects.filter(version__document=document).select_related(
        "version"
    ):
        accepted[accepted_sha(acceptance, document.number)] = acceptance.number
    created = Version.objects.get(document=document, kind=VersionKind.CREATED)
    if view == ExportView.ACCEPTED:
        return accepted.get(version.commit_sha, BEFORE_ANY_ACCEPTANCE)
    bases = {created.commit_sha: BEFORE_ANY_ACCEPTANCE, **accepted}
    for sha, number in editions.items():
        if sha not in bases or number_key(number) > number_key(bases[sha]):
            bases[sha] = number
    repo = gitstore.open_repository(_tenant(), document.number)
    count, base = 0, BEFORE_ANY_ACCEPTANCE
    for commit in repo.walk(version.commit_sha, pygit2.enums.SortMode.TOPOLOGICAL):
        sha = str(commit.id)
        if sha in bases:
            base = bases[sha]
            break
        if gitstore.kind_of(commit.message) in CONTENT:
            count += 1
    if view == ExportView.MY_EDITS:
        count += 1
    return f"{base}-{count}" if count else base


# The right each view needs, and the rights marks against an earlier edition need.
VIEW_RIGHTS = {
    ExportView.CANONICAL: {Right.VIEW_CANONICAL, Right.VIEW_ACCEPTED, Right.VIEW_PENDING},
    ExportView.ACCEPTED: {Right.VIEW_ACCEPTED, Right.VIEW_PENDING},
    ExportView.PENDING_EDITS: {Right.VIEW_PENDING},
    ExportView.MY_EDITS: {Right.EDIT},
}
HISTORY = {Right.VIEW_ALL_HISTORY, Right.VIEW_PREVIOUS_CANONICAL}


def still_permitted(job: ExportJob) -> bool:
    """Whether the person who asked still holds the rights the job's view needs — and, for marks
    against an earlier edition, a history right. A right lost after asking fails the job and
    serves nothing; a run accepted or a draft sent for review since does not, the job being of
    its stated version."""
    rights = rights_on(job.requested_by, job.document)
    if not rights & VIEW_RIGHTS[ExportView(job.view)]:
        return False
    marked_history = job.view == ExportView.CANONICAL and job.changes == ExportChanges.MARKED
    return not marked_history or bool(rights & HISTORY)


def _tenant() -> int:
    from django.db import connection

    from tenancy.schemas import current_tenant

    number = current_tenant(connection)
    if number is None:
        raise RuntimeError("an export is composed inside a tenant's schema")
    return number


def offers(user: Any, document: Document) -> list[Offer]:
    """The views `user` may export of `document`, in the dialog's order (DL-0209, DL-0241): the
    latest edition to every reader, marked against the previous one only with a history right;
    the latest acceptance beyond it to a reader of accepted text, against the edition; the pending
    run to a holder of *view pending*, against the last acceptance; the holder's draft, against
    the current text."""
    rights = rights_on(user, document)
    if not rights & {Right.VIEW_CANONICAL, Right.VIEW_ACCEPTED, Right.VIEW_PENDING}:
        return []
    chain = _chain(document)
    edition = chain.editions[-1] if chain.editions else None
    history = bool(rights & {Right.VIEW_ALL_HISTORY, Right.VIEW_PREVIOUS_CANONICAL})
    found: list[Offer] = []
    if edition is not None:
        previous = chain.editions[-2] if len(chain.editions) > 1 and history else None
        found.append(
            Offer(
                ExportView.CANONICAL,
                edition.version,
                edition.number,
                previous.version if previous else None,
                previous.number if previous else "",
                False,
            )
        )
    if chain.acceptance_content is not None and Right.VIEW_ACCEPTED in rights:
        found.append(
            Offer(
                ExportView.ACCEPTED,
                chain.acceptance_content,
                chain.acceptance_number,
                edition.version if edition else None,
                edition.number if edition else "",
                True,
            )
        )
    first = chain.acceptance_content is None and not chain.editions
    if first and Right.VIEW_ACCEPTED in rights:
        # Before any acceptance the created text, version 0.0, is the accepted one (DL-0358).
        found.append(
            Offer(ExportView.ACCEPTED, chain.start, BEFORE_ANY_ACCEPTANCE, None, "", False)
        )
    start, base_number = chain.start, chain.base_number
    if Right.VIEW_PENDING not in rights:
        return found
    pending = run(document, since=start)
    current, current_number = start, base_number
    if pending:
        current, current_number = pending[-1], f"{base_number}-{len(pending)}"
        found.append(
            Offer(ExportView.PENDING_EDITS, current, current_number, start, base_number, True)
        )
    from editing.holds import open_hold

    hold = open_hold(document)
    if hold is not None and hold.user_id == getattr(user, "pk", None):
        draft_number = f"{base_number}-{len(pending) + 1}"
        found.append(
            Offer(ExportView.MY_EDITS, current, draft_number, current, current_number, True)
        )
    return found


def _body(
    tenant_number: int, document: Document, version: Version
) -> tuple[bundle.Frontmatter, str]:
    repo = gitstore.open_repository(tenant_number, document.number)
    text = gitstore.read(repo, "document.md", version.commit_sha).decode("utf-8")
    return bundle.parse(text)


@dataclass
class Composed:
    """One export's content, ready for a writer."""

    name: str
    header: str
    html: str = ""
    markdown: str = ""
    attachments: list[dict[str, Any]] = field(default_factory=list)


def _refusal(refusals: list[Any]) -> str:
    """What the platform refuses in the text, by construct, as the editor names them."""
    from editing.messages import CONSTRUCTS

    # The construct as the editor names it, its code after it for whoever reports the fault.
    named = ", ".join(
        dict.fromkeys(f"{CONSTRUCTS.get(r.code, r.code)} ({r.code})" for r in refusals)
    )
    return _(
        "The text holds what the platform does not accept: %(constructs)s. Correct it in the "
        "editor and export again."
    ) % {"constructs": named}


def _checked(text: str) -> str:
    refusals = validate(text)
    if refusals:
        raise Refused(_refusal(refusals))
    return text


def _texts(job: ExportJob, tenant_number: int) -> tuple[bundle.Frontmatter, str, str | None]:
    """The frontmatter and the body the job exports, and the baseline's body when marked."""
    document = job.document
    frontmatter, body = _body(tenant_number, document, job.version)
    if job.view == ExportView.MY_EDITS:
        from editing.holds import open_hold
        from editing.services import DraftRefused, draft_text

        hold = open_hold(document)
        if hold is None or hold.user_id != job.requested_by_id:
            raise Refused(_("Your draft has been finished or discarded since you asked."))
        try:
            _head, _head_body, body = draft_text(hold)
        except DraftRefused as refused:
            raise Refused(_refusal(refused.refusals)) from refused
    baseline = None
    if job.changes == ExportChanges.MARKED and job.baseline_version is not None:
        baseline = _body(tenant_number, document, job.baseline_version)[1]
    # Checked even when only attachments go: an export is of a text that stands.
    return frontmatter, _checked(body), baseline


def _title_page(job: ExportJob, title: str, number: str) -> str:
    """The title page's default form, until a tenant configures its own (DL-0164, DL-0360): the
    title, the number, and the approval as the exported text stands — the approver, the date and
    the edition on the canonical view; elsewhere what the text is, to the edition it departs
    from, or that nothing is approved yet."""
    from zoneinfo import ZoneInfo

    from django.conf import settings

    from identity.naming import person

    # The edition behind the exported version, from its own number: `N.M` and `N.M-X` stand on
    # edition `N.0` (DL-0183), so a job run after a newer edition still names the one it exports.
    major = int(number.split(".", 1)[0])
    edition = (
        Edition.objects.filter(version__document=job.document, number=f"{major}.0")
        .select_related("approved_by")
        .first()
        if major
        else None
    )
    if edition is None:
        approval = _("Not yet approved")
    elif job.view == ExportView.CANONICAL:
        approved_at = timezone.localtime(edition.approved_at, ZoneInfo(settings.DISPLAY_TIMEZONE))
        approval = _("Approved: %(name)s, %(date)s; edition %(number)s") % {
            "name": person(edition.approved_by),
            "date": formats.date_format(approved_at, "j E Y"),
            "number": edition.number,
        }
    else:
        approval = _("Not approved — %(stance)s to edition %(number)s") % {
            "stance": stance(job.view),
            "number": edition.number,
        }
    return (
        '<section class="title-page">'
        f'<h1 class="document-title">{escape(title)}</h1>'
        f'<p class="document-number">#{job.document.number}</p>'
        f'<p class="approval">{escape(approval)}</p></section>'
    )


def _attachment_list(items: list[dict[str, Any]]) -> str:
    rows = "".join(
        f"<tr><td>{escape(str(item.get('title', '')))}</td>"
        f"<td>{escape(str(item.get('file_name', '')))}</td>"
        f"<td><code>{escape(str(item.get('sha256', ''))[:HASH_SHOWN])}</code></td></tr>"
        for item in items
    )
    return (
        f'<section class="attachment-list"><h1>{escape(_("Attachment list"))}</h1>'
        f"<table><thead><tr><th>{escape(_('Title'))}</th><th>{escape(_('File name'))}</th>"
        f"<th>SHA-256</th></tr></thead><tbody>{rows}</tbody></table></section>"
    )


def _page(
    job: ExportJob, frontmatter: bundle.Frontmatter, text: str, header: str, number: str
) -> str:
    language = escape(job.document.language_id or "")
    hashes = "; ".join(
        f"{item.get('file_name', '')} {item.get('sha256', '')}" for item in frontmatter.attachments
    )
    meta = f'<meta name="description" content="{escape(hashes)}">' if hashes else ""
    parts = [
        f'<!doctype html><html lang="{language}"><head><meta charset="utf-8">'
        f"<title>{escape(header)}</title>{meta}</head><body>"
    ]
    if frontmatter.title_page:
        parts.append(_title_page(job, frontmatter.title, number))
    parts.append(f'<article class="document-text">{text}</article>')
    if frontmatter.attachments:
        parts.append(_attachment_list(frontmatter.attachments))
    parts.append("</body></html>")
    return "".join(parts)


def _cell(value: object) -> str:
    """A table cell's text in Markdown: a pipe escaped, so it never ends the cell."""
    return str(value).replace("|", "\\|")


def compose(job: ExportJob, tenant_number: int, *, number: str) -> Composed:
    """The job's content: its file name, its header, and the HTML page or the Markdown."""
    from editing.diffview import render_changes

    frontmatter, body, baseline = _texts(job, tenant_number)
    shown = stance(job.view)
    header = furniture.header_text(frontmatter.title, number, shown)
    marks = pgettext("marks in a file name", "marked") if baseline is not None else ""
    ext = EXTENSIONS[ExportFormat(job.format)]
    composed = Composed(
        name=names.file_name(frontmatter.title, number, shown, ext, marks=marks),
        header=header,
        attachments=list(frontmatter.attachments) if job.include_attachments else [],
    )
    if job.format == ExportFormat.MARKDOWN:
        text = join_paragraphs(body)
        if frontmatter.attachments:
            rows = "\n".join(
                f"| {_cell(item.get('title', ''))} | {_cell(item.get('file_name', ''))} | "
                f"{item.get('sha256', '')} |"
                for item in frontmatter.attachments
            )
            heading = _("Attachment list")
            text += (
                f"\n# {heading}\n\n| {_('Title')} | {_('File name')} | SHA-256 |\n"
                f"| --- | --- | --- |\n{rows}\n"
            )
        composed.markdown = text
        return composed
    if baseline is not None:
        rendered = render_changes(baseline.encode(), body.encode())
    else:
        rendered = render(body)
    composed.html = _page(job, frontmatter, rendered, header, number)
    return composed
