"""A correction notice opened by its author (ADR-0001, ADR-0014, DL-0113): for each change, what the
author wrote and what was accepted, both read from the repository at the two versions and marked
word by word, who changed it, and the way to the document. The text is rendered only while the
reader holds *view accepted* on the document — the right that reads accepted text, which *edit*
includes (ADR-0007); otherwise the notice shows that it exists, how many changes it lists and who
made them, and no text."""

from __future__ import annotations

import logging
import re
from typing import Any

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy

from access.rights import Right, rights_on
from documents import gitstore
from documents.parts import lists_at, part_operations
from editing import holds
from editing.authorship import DOCUMENT_FILE
from editing.diffview import render_changes
from identity.naming import person
from review import notices, services
from review.models import Acceptance
from shell.views import not_found

RANGE = re.compile(r"([1-9][0-9]{0,9})(?:-([1-9][0-9]{0,9}))?")

logger = logging.getLogger(__name__)


def _span(value: str) -> tuple[int, int] | None:
    """The first and last line a range names, `"n"` or `"n-m"` counted from 1; `None` for none or
    for a value that is not a range."""
    match = RANGE.fullmatch(value)
    if match is None:
        return None
    first, last = int(match.group(1)), int(match.group(2) or match.group(1))
    return (first, last) if first <= last else None


def _lines(text: bytes, value: str) -> bytes:
    """The lines a range names in `text`, or nothing."""
    span = _span(value)
    if span is None:
        return b""
    rows = text.split(b"\n")
    return b"\n".join(rows[span[0] - 1 : span[1]]) + b"\n"


def _numbers(acceptance: Any) -> dict[str, str]:
    """Each version of the accepted run by its number, `N.M-X`, as it waited: counted from the
    later of the acceptance and the edition before it, as the pending tab counts (DL-0267)."""
    from editions.models import Edition

    base = acceptance.accepted_from
    key = services.number_key(acceptance.number)
    earlier = [
        number
        for number in [
            *Acceptance.objects.filter(version__document=base.document).values_list(
                "number", flat=True
            ),
            *Edition.objects.filter(version__document=base.document).values_list(
                "number", flat=True
            ),
        ]
        if services.number_key(number) < key
    ]
    accepted = max(earlier, key=services.number_key, default="0.0")
    run = services.run(
        base.document, since=base, head=services.accepted_content_version(acceptance).commit_sha
    )
    return {version.commit_sha: f"{accepted}-{n}" for n, version in enumerate(run, 1)}


def _passage(text: bytes, line: int) -> str:
    """The reading view's anchor of the numbered heading `line` of `document.md` falls under, or
    `""` above the first (DL-0334)."""
    from documents import bundle
    from rendering.outline import anchor
    from rendering.renderer import labelled

    decoded = text.decode("utf-8")
    _frontmatter, body = bundle.parse(decoded)
    offset = decoded[: len(decoded) - len(body)].count("\n")
    tokens = labelled(body)
    found = ""
    for i, token in enumerate(tokens):
        if token.type != "heading_open" or token.map is None or token.map[0] + offset >= line:
            continue
        children = tokens[i + 1].children or []
        if children and (children[0].meta or {}).get("num"):
            found = anchor(children[0].meta["label"])
    return found


# A part entry's two halves (ADR-0014): what its author's version did, what the changing version
# did; each half a whole phrase, so a translation never makes a verb agree with a name.
AUTHOR_DID = {
    ("attachment", "added"): gettext_lazy("You added this attachment in %(version)s"),
    ("attachment", "replaced"): gettext_lazy("You replaced this attachment in %(version)s"),
    ("attachment", "renamed"): gettext_lazy("You renamed this attachment in %(version)s"),
    ("attachment", "removed"): gettext_lazy("You removed this attachment in %(version)s"),
    ("appendix", "added"): gettext_lazy("You added this appendix in %(version)s"),
    ("appendix", "renamed"): gettext_lazy("You renamed this appendix in %(version)s"),
    ("appendix", "removed"): gettext_lazy("You removed this appendix in %(version)s"),
}
CHANGER_DID = {
    "removed": gettext_lazy("%(changer)s removed it in %(changing)s."),
    "replaced": gettext_lazy("%(changer)s replaced it in %(changing)s."),
    "renamed": gettext_lazy("%(changer)s renamed it in %(changing)s."),
    "added": gettext_lazy("%(changer)s restored it in %(changing)s."),
}


def _parent(document: Any, repo: Any, version: Any) -> Any:
    """The version `version` was committed on, or `None` for the document's first."""
    from documents.models import Version

    parents = gitstore.commit_at(repo, version.commit_sha).parents
    if not parents:
        return None
    return Version.objects.filter(document=document, commit_sha=str(parents[0].id)).first()


ORDER = ("added", "removed", "replaced", "renamed")


def _changes(document: Any, repo: Any, version: Any, kind: str, number: int) -> list[str]:
    """What `version` did to part `number` against the version before it, in `ORDER`."""
    before = _parent(document, repo, version)
    older = lists_at(before) if before is not None else ([], [])
    done = {
        o.change
        for o in part_operations(older, lists_at(version))
        if o.kind == kind and o.number == number
    }
    return [change for change in ORDER if change in done]


def _part_entry(
    document: Any, accepted: tuple[str, Any], line: Any, numbers: dict[str, str], repo: Any
) -> dict[str, Any]:
    """A part entry as the page draws it: its sentence, the part by its title as its author left
    it, and *open* where the accepted version — `(number, version)`, the version `None` past the
    reader's ceiling — holds the part."""
    kind = "appendix" if line.part.startswith("appendices/") else "attachment"
    side = 0 if kind == "appendix" else 1
    number = int(
        line.part.removeprefix("appendices/").removeprefix("attachments/").removesuffix(".md")
    )
    changed = _changes(document, repo, line.changing_version, kind, number) or ["renamed"]
    # The author's half names what of theirs the change undid: of a version that both replaced
    # and renamed a part, the half the changing version touched.
    touched = {attribute for change in changed for attribute in notices.SETS[change]}
    own_changes = _changes(document, repo, line.author_version, kind, number)
    authored = next(
        (c for c in own_changes if touched & set(notices.SETS[c])),
        own_changes[0] if own_changes else "renamed",
    )
    title = next(
        (e["title"] for e in lists_at(line.author_version)[side] if int(e["number"]) == number), ""
    )
    if not title:
        # A part the author's version removed: its title in the version before it.
        before = _parent(document, repo, line.author_version)
        held = lists_at(before)[side] if before is not None else []
        title = next((e["title"] for e in held if int(e["number"]) == number), "")
    said = str(AUTHOR_DID.get((kind, authored), AUTHOR_DID[(kind, "renamed")])) % {
        "version": numbers.get(line.author_version.commit_sha, "")
    }
    said += "; " + str(CHANGER_DID[changed[0]]) % {
        "changer": person(line.changing_version.author),
        "changing": numbers.get(line.changing_version.commit_sha, ""),
    }
    link = ""
    at, version = accepted
    if version is not None and any(int(e["number"]) == number for e in lists_at(version)[side]):
        link = f"/document/{document.number}/version/{at}/{kind}/{number}/"
    return {
        "kind": "part_operation",
        "said": said,
        "icon": "▤" if kind == "appendix" else "📎",
        "title": title,
        "open": link,
    }


def _accepted(request: HttpRequest, document: Any, acceptance: Any) -> Any:
    """The accepted version as the reader may open it: `None` past their ceiling, or where the
    document's history does not read."""
    from rendering.views import UNREADABLE
    from review.history import version_for

    try:
        return version_for(request.user, document, acceptance.number)
    except UNREADABLE:
        # A record that does not read costs the links, never the notice; logged for the operator.
        logger.exception(
            "a document's history could not be read",
            extra={"document": f"/document/{document.number}/"},
        )
        return None


def _link(document: Any, accepted: tuple[str, Any], lines: list[Any], repo: Any) -> str:
    """Where *open the document* leads: the accepted version's historical page at the first
    passage of the body, where the reader's ceiling reaches it — or, where every line is an
    appendix's, the first such appendix at that version while it lists it; else the document
    (DL-0334)."""
    plain = f"/document/{document.number}/"
    at, version = accepted
    if version is None:
        return plain
    page = f"{plain}version/{at}/"
    body = [line for line in lines if line.file == DOCUMENT_FILE and line.entry != "part_operation"]
    first = next((_span(line.range_after) for line in body if line.range_after), None)
    if first is None:
        appendix = next((line.file for line in lines if line.file != DOCUMENT_FILE), None)
        if appendix is not None and body == []:
            number = int(appendix.removeprefix("appendices/").removesuffix(".md"))
            if any(int(e["number"]) == number for e in lists_at(version)[0]):
                return f"{page}appendix/{number}/"
        return page
    target = _passage(gitstore.read(repo, "document.md", version.commit_sha), first[0])
    return f"{page}#{target}" if target else page


def page(request: HttpRequest, notification: Any) -> HttpResponse:
    notice = notification.correction_notice
    acceptance = notice.acceptance
    document = notification.document
    if acceptance.version.document_id != document.pk or notice.author_id != notification.user_id:
        return not_found(request)
    from rendering import reading
    from review.views.notice_images import notice_lines, selected_lines

    # Only the lines of this document's notice, in the order the versions came and the lines
    # stand: the run's order, which commit times cannot give.
    numbers = _numbers(acceptance)
    lines = selected_lines(notice, document, numbers)
    readable = Right.VIEW_ACCEPTED in rights_on(request.user, document)
    changers = sorted({person(line.changing_version.author) for line in lines})
    entries: list[dict[str, Any]] = []
    if readable:
        # Read through `notice_lines`, as the notice's image route reads them, so every image
        # shown here is one that route serves.
        shown = notice_lines(notice, document)
        bodies = [part.decode("utf-8") for e in shown for part in (e.before, e.after)]
        reader = reading.context(
            request.user, document, *bodies, images=reading.notice_images(notification)
        )
        for entry in shown:
            line = entry.line
            entries.append(
                {
                    "kind": line.entry,
                    "changer": person(line.changing_version.author),
                    "changing": numbers.get(line.changing_version.commit_sha, ""),
                    "author_version": numbers.get(line.author_version.commit_sha, ""),
                    # Rendered from escaped text by the one diff presentation.
                    "changes": mark_safe(  # noqa: S308
                        render_changes(entry.before, entry.after, context=reader)
                    ),
                }
            )
    link = ""
    if readable:
        accepted = (acceptance.number, _accepted(request, document, acceptance))
        repo = gitstore.open_repository(holds.tenant_number(), document.number)
        entries += [
            _part_entry(document, accepted, line, numbers, repo)
            for line in lines
            if line.entry == "part_operation"
        ]
        link = _link(document, accepted, lines, repo)
    context = {
        "document": document,
        "acceptance": acceptance,
        "link": link,
        "count": len(lines),
        "counted": notices.counted(notice),
        "changers": changers,
        "readable": readable,
        "entries": entries,
    }
    return render(request, "review/notice.html", context)
