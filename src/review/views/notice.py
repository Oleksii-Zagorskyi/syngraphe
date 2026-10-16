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

from access.rights import Right, rights_on
from documents import gitstore
from editing import holds
from editing.diffview import render_changes
from identity.naming import person
from review import services
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


def _link(request: HttpRequest, document: Any, acceptance: Any, lines: list[Any]) -> str:
    """Where *open the document* leads: the accepted version's historical page at the first
    passage, where the reader's ceiling reaches it; else the document (DL-0334)."""
    from rendering.views import UNREADABLE
    from review.history import version_for

    plain = f"/document/{document.number}/"
    try:
        version = version_for(request.user, document, acceptance.number)
    except UNREADABLE:
        # A record that does not read costs the passage, never the notice; logged for the operator.
        logger.exception("a document's history could not be read", extra={"document": plain})
        return plain
    if version is None:
        return plain
    page = f"{plain}version/{acceptance.number}/"
    first = next((_span(line.range_after) for line in lines if line.range_after), None)
    if first is None:
        return page
    repo = gitstore.open_repository(holds.tenant_number(), document.number)
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
    context = {
        "document": document,
        "acceptance": acceptance,
        "link": _link(request, document, acceptance, lines) if readable else "",
        "count": len(lines),
        "changers": changers,
        "readable": readable,
        "entries": entries,
    }
    return render(request, "review/notice.html", context)
