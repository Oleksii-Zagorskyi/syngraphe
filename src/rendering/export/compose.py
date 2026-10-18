"""What an export is made of (DL-0172, DL-0193, DL-0209, DL-0241): the views a reader may export
with the version each shows and the baseline its marks would be measured against, and — for a
job — the text, the document's HTML page, the Markdown, the header and the file's name.

The text is validated before any renderer sees it: a construct the platform refuses fails the job
by name. The images the text shows go with it: embedded in PDF and DOCX — a marked export's
changed image as its pair — beside the Markdown in one zip; a mention is its words alone in PDF and
DOCX (DL-0438).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from typing import TYPE_CHECKING, Any

import pygit2
from django.utils.translation import gettext as _
from django.utils.translation import pgettext

from access.rights import Right, rights_on
from documents import bundle, gitstore, images
from documents.models import Document, Version, VersionKind
from editing.markdown.validator import validate
from editing.numbering import BEFORE_ANY_ACCEPTANCE
from editions.models import Edition
from rendering.export import furniture, names
from rendering.export.markdown import join_paragraphs, number_headings
from rendering.models import ExportChanges, ExportFormat, ExportView
from rendering.renderer import RenderContext, render
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
    # Whether its body, and whether the appendices it lists, show images: a Markdown export of
    # those that show them is then one zip.
    images: bool = False
    appendix_images: bool = False


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
    against an earlier edition, a history right; for a job asked at a version, whether their
    ceiling still reaches it. A right lost after asking fails the job and
    serves nothing; a run accepted or a draft sent for review since does not, the job being of
    its stated version."""
    if job.at_version:
        # Reached through the reader's ceiling, a history right included: what the job asks again
        # is that ceiling, for its version and its baseline (DL-0423).
        from review.history import ceiling

        past = ceiling(job.requested_by, job.document)
        baseline = job.baseline_version
        return past.reaches(job.version) and (baseline is None or past.reaches(baseline))
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


def offers(
    user: Any, document: Document, *, version: Version | None = None, past: Any = None
) -> list[Offer]:
    """The views `user` may export of `document`, in the dialog's order (DL-0209, DL-0241): the
    latest edition to every reader, marked against the previous one only with a history right;
    the latest acceptance beyond it to a reader of accepted text, against the edition; the pending
    run to a holder of *view pending*, against the last acceptance; the holder's draft, against
    the current text. With `version` — one the caller resolved for `user` on a historical page —
    the one offer at that version (DL-0195, DL-0208): its view by the stance it reached, marked by
    the same chain (DL-0426) — `past`, the reader's ceiling when the caller has read it."""
    if version is not None:
        from review.history import ceiling

        return _offer_at(document, version, past or ceiling(user, document))
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


def _mine(document: Document, user: Any) -> Any:
    """`user`'s draft of `document` while they hold it, or `None`."""
    from editing.holds import open_hold
    from editing.models import Draft

    hold = open_hold(document)
    if hold is None or hold.user_id != getattr(user, "pk", None):
        return None
    return Draft.objects.filter(hold=hold).first()


def offer_lists(
    offer: Offer, document: Document, user: Any
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The appendices and the attachments the offer's export would hold: its version's, or for
    *my edits* the draft's (DL-0193)."""
    from documents.parts import lists_at
    from editing.holds import FRONTMATTER

    if offer.view == ExportView.MY_EDITS:
        draft = _mine(document, user)
        held = draft.content.get(FRONTMATTER, {}) if draft is not None else {}
        return list(held.get("appendices", [])), list(held.get("attachments", []))
    return lists_at(offer.version)


def with_images(offers: list[Offer], document: Document, user: Any) -> list[Offer]:
    """Each offer marked by whether the texts its export writes show images — a version's body,
    and apart from it the appendices it lists, or the holder's draft's, whose first image may be
    in no commit yet — as the job decides it."""
    from dataclasses import replace

    from editing.holds import BODY
    from editing.services import draft_texts

    marked = []
    for offer in offers:
        body: str | None = None
        appendices: list[str] = []
        if offer.view == ExportView.MY_EDITS:
            draft = _mine(document, user)
            if draft is not None:
                repo = gitstore.open_repository(_tenant(), document.number)
                texts = draft_texts(draft, repo)
                body = texts.pop(BODY)
                appendices = list(texts.values())
        else:
            frontmatter, body = _body(_tenant(), document, offer.version)
            appendices = list(_appendix_texts(document, offer.version, frontmatter).values())
        marked.append(
            replace(
                offer,
                images=bool(shown_images(body)),
                appendix_images=bool(shown_images(*appendices)),
            )
        )
    return marked


def _appendix_texts(
    document: Document, version: Version, frontmatter: bundle.Frontmatter
) -> dict[int, str]:
    """Each appendix `version` lists, its text by number in the list's order."""
    repo = gitstore.open_repository(_tenant(), document.number)
    found = {}
    for entry in frontmatter.appendices:
        number = int(entry["number"])
        try:
            found[number] = gitstore.read(repo, f"appendices/{number}.md", version.commit_sha)
        except KeyError:
            # A listed appendix without its file: the reconciler's `part_missing`.
            found[number] = b""
    return {number: text.decode("utf-8") for number, text in found.items()}


def _offer_at(document: Document, version: Version, past: Any) -> list[Offer]:
    """The one offer at `version`, marked by DL-0241's chain for the stance it reached
    (DL-0426): an edition against the previous edition, accepted text against the edition before
    it, pending work against the acceptance or edition it counts from — each only where `past`
    reaches it, and marked by default where the dialog marks the same view by default."""
    history = past.history
    number = past.number(version)
    order = {c.sha: i for i, c in enumerate(history.commits)}
    # Content versions that became editions, in the order of their text.
    editions = sorted(
        (c.decides for c in history.commits if c.kind == VersionKind.APPROVAL and c.decides),
        key=order.__getitem__,
    )
    sha = version.commit_sha
    baseline_sha: str | None
    if sha in editions:
        view, by_default = ExportView.CANONICAL, False
        earlier = editions[: editions.index(sha)]
        baseline_sha = earlier[-1] if earlier else None
    elif "-" not in number:
        view, by_default = ExportView.ACCEPTED, True
        earlier = [e for e in editions if order[e] < order[sha]]
        baseline_sha = earlier[-1] if earlier else None
    else:
        view, by_default = ExportView.PENDING_EDITS, True
        baseline_sha = history.aliases.get(number.split("-")[0])
    baseline = (
        Version.objects.filter(document=document, commit_sha=baseline_sha).first()
        if baseline_sha is not None
        else None
    )
    if baseline is None or not past.reaches(baseline):
        return [Offer(view, version, number, None, "", False)]
    baseline_number = number.split("-")[0] if view == ExportView.PENDING_EDITS else ""
    return [
        Offer(
            view,
            version,
            number,
            baseline,
            baseline_number or past.number(baseline),
            by_default,
        )
    ]


def _body(
    tenant_number: int, document: Document, version: Version
) -> tuple[bundle.Frontmatter, str]:
    repo = gitstore.open_repository(tenant_number, document.number)
    text = gitstore.read(repo, "document.md", version.commit_sha).decode("utf-8")
    return bundle.parse(text)


@dataclass
class ComposedPart:
    """One appendix exported as a file of its own, ready for a writer."""

    name: str
    html: str = ""
    markdown: str = ""


@dataclass
class Composed:
    """One export's content, ready for a writer."""

    name: str
    header: str
    html: str = ""
    markdown: str = ""
    attachments: list[dict[str, Any]] = field(default_factory=list)
    # The images the texts show — and, marked, the baseline's — by their paths.
    images: list[str] = field(default_factory=list)
    # The appendices as files of their own, when they go separate.
    appendices: list[ComposedPart] = field(default_factory=list)


@dataclass
class _Texts:
    """What a job exports: the frontmatter, the body, each appendix `(number, title, text)`, and
    when marked the baseline's body and its appendices' texts by number."""

    frontmatter: bundle.Frontmatter
    body: str
    baseline: str | None
    appendices: list[tuple[int, str, str]]
    baseline_appendices: dict[int, str]


# An export's text names its images by their paths: PDF reads them through its fetcher, DOCX from
# its scratch folder. No mention links in a file that leaves the platform (DL-0438).
EXPORT_CONTEXT = RenderContext(image_url=str, full_size=False)


def shown_images(*texts: str | None) -> list[str]:
    """The images the platform names that `texts` show, each once, in order."""
    found = images.referenced({str(n): t for n, t in enumerate(texts) if t is not None})
    return list(dict.fromkeys(r.src for r in found if images.is_image_path(r.src)))


def _refusal(refusals: list[Any]) -> str:
    """What the platform refuses in the text, by construct, as the editor names them."""
    from editing.messages import CONSTRUCTS, DRAFT_LIMITS

    names = {**CONSTRUCTS, **DRAFT_LIMITS}
    # The construct as the editor names it, its code after it for whoever reports the fault.
    named = ", ".join(dict.fromkeys(f"{names.get(r.code, r.code)} ({r.code})" for r in refusals))
    return _(
        "The text holds what the platform does not accept: %(constructs)s. Correct it in the "
        "editor and export again."
    ) % {"constructs": named}


def _checked(text: str) -> str:
    refusals = validate(text)
    if refusals:
        raise Refused(_refusal(refusals))
    return text


def _texts(job: ExportJob, tenant_number: int) -> _Texts:
    """The texts the job exports: a version's, or for *my edits* the draft's state throughout —
    its frontmatter and lists, its body and its appendices (DL-0193, DL-0209)."""
    from rendering.models import ExportAppendices

    document = job.document
    frontmatter, body = _body(tenant_number, document, job.version)
    wanted = job.appendices != ExportAppendices.NONE
    if job.view == ExportView.MY_EDITS:
        from editing.holds import open_hold
        from editing.services import DraftRefused, draft_export

        hold = open_hold(document)
        if hold is None or hold.user_id != job.requested_by_id:
            raise Refused(_("Your draft has been finished or discarded since you asked."))
        try:
            held, body, appendices = draft_export(hold)
        except DraftRefused as refused:
            raise Refused(_refusal(refused.refusals)) from refused
        frontmatter = bundle.Frontmatter(**held)
    else:
        appendices = [
            (number, _title_of(frontmatter, number), text)
            for number, text in _appendix_texts(document, job.version, frontmatter).items()
        ]
    baseline = None
    baseline_appendices: dict[int, str] = {}
    if job.changes == ExportChanges.MARKED and job.baseline_version is not None:
        before, baseline = _body(tenant_number, document, job.baseline_version)
        if wanted:
            baseline_appendices = _appendix_texts(document, job.baseline_version, before)
    # Checked even when only attachments go: an export is of a text that stands.
    return _Texts(
        frontmatter,
        _checked(body),
        baseline,
        [(n, title, _checked(text)) for n, title, text in appendices] if wanted else [],
        baseline_appendices,
    )


def _title_of(frontmatter: bundle.Frontmatter, number: int) -> str:
    return next(
        (str(e.get("title", "")) for e in frontmatter.appendices if int(e["number"]) == number), ""
    )


def _title_page(job: ExportJob, title: str, number: str, text: str = "") -> str:
    """The title page as the organisation's template lays it out (DL-0462), its default form
    DL-0360's: the details, the document's own text, and the approval as the exported text
    stands."""
    from documents.models import DocumentTemplate
    from rendering import title_page

    layout = title_page.layout_of(DocumentTemplate.objects.get().title_page_layout)
    return title_page.html(title_page.facts_for(job, title, number, text), layout)


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
    job: ExportJob,
    frontmatter: bundle.Frontmatter,
    text: str,
    header: str,
    number: str,
    appendices: tuple[str, ...] = (),
) -> str:
    """The HTML page a writer converts: the title page when the document has one, the body, each
    embedded appendix in a section of its own — a new page in PDF — and the attachment list."""
    title_page = (
        _title_page(job, frontmatter.title, number, frontmatter.title_page_text)
        if frontmatter.title_page
        else ""
    )
    return page_html(
        language=job.document.language_id or "",
        header=header,
        title_page=title_page,
        text=text,
        attachments=frontmatter.attachments,
        appendices=appendices,
    )


def page_html(
    *,
    language: str,
    header: str,
    title_page: str,
    text: str,
    attachments: list[dict[str, Any]],
    appendices: tuple[str, ...] = (),
) -> str:
    """The page's HTML from its parts, already rendered: the export's and the sample's (DL-0466)
    one assembly."""
    hashes = "; ".join(
        f"{item.get('file_name', '')} {item.get('sha256', '')}" for item in attachments
    )
    meta = f'<meta name="description" content="{escape(hashes)}">' if hashes else ""
    parts = [
        f'<!doctype html><html lang="{escape(language)}"><head><meta charset="utf-8">'
        f"<title>{escape(header)}</title>{meta}</head><body>"
    ]
    if title_page:
        parts.append(title_page)
    parts.append(f'<article class="document-text">{text}</article>')
    parts += [
        f'<section class="appendix"><article class="document-text">{html}</article></section>'
        for html in appendices
    ]
    if attachments:
        parts.append(_attachment_list(attachments))
    parts.append("</body></html>")
    return "".join(parts)


def _cell(value: object) -> str:
    """A table cell's text in Markdown: a pipe escaped, so it never ends the cell."""
    return str(value).replace("|", "\\|")


def _rendered(job: ExportJob, text: str, baseline: str | None, number: str) -> str:
    """`text` rendered alone, its numbers from 1; marked against `baseline` when it is given."""
    from editing.diffview import render_changes

    if baseline is None or job.baseline_version is None:
        return render(text, context=EXPORT_CONTEXT)
    from dataclasses import replace

    from editing.numbering import number_of as shown_number

    try:
        baseline_number = shown_number(job.document, job.baseline_version)
    except LookupError:
        # A baseline the numbering does not reach: its side is named without a number.
        baseline_number = ""
    marked = replace(EXPORT_CONTEXT, sides=(baseline_number, number))
    return render_changes(baseline.encode(), text.encode(), context=marked)


def _markdown(text: str) -> str:
    return number_headings(join_paragraphs(text))


def compose(job: ExportJob, tenant_number: int, *, number: str) -> Composed:
    """The job's content: its file name, its header, the HTML page or the Markdown, and its
    appendices — embedded after the body, or each a file of its own (DL-0193, DL-0444). An
    appendix is rendered alone, its title never printed (DL-0165); marked, against the baseline's
    text of it, an appendix the baseline lacks wholly inserted."""
    from rendering.models import ExportAppendices

    texts = _texts(job, tenant_number)
    frontmatter, body, baseline = texts.frontmatter, texts.body, texts.baseline
    shown = stance(job.view)
    header = furniture.header_text(frontmatter.title, number, shown)
    marks = pgettext("marks in a file name", "marked") if baseline is not None else ""
    ext = EXTENSIONS[ExportFormat(job.format)]
    composed = Composed(
        name=names.file_name(frontmatter.title, number, shown, ext, marks=marks),
        header=header,
        attachments=list(frontmatter.attachments) if job.include_attachments else [],
        # The images of the texts that go: the body's only with the document.
        images=shown_images(
            *((body, baseline) if job.include_document else ()),
            *(text for _n, _t, text in texts.appendices),
            *texts.baseline_appendices.values(),
        ),
    )
    marked = baseline is not None
    separate = job.appendices == ExportAppendices.SEPARATE
    markdown = job.format == ExportFormat.MARKDOWN
    shown_parts: list[str] = []
    word = pgettext("a part in an exported file's name", "appendix")
    for n, title, text in texts.appendices:
        against = texts.baseline_appendices.get(n, "") if marked else None
        part = _markdown(text) if markdown else _rendered(job, text, against, number)
        if not separate:
            shown_parts.append(part)
            continue
        named = names.part_name(word, n, title[: names.TITLE_MOST]) + f".{ext}"
        page = bundle.Frontmatter(title=title, language=frontmatter.language)
        composed.appendices.append(
            ComposedPart(named, markdown=part)
            if markdown
            else ComposedPart(named, html=_page(job, page, part, header, number))
        )
    if markdown:
        text = _markdown(body)
        for part in shown_parts:
            text += "\n" + part
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
    rendered = _rendered(job, body, baseline, number)
    composed.html = _page(job, frontmatter, rendered, header, number, tuple(shown_parts))
    return composed
