"""A correction notice opened by its author (ADR-0001, ADR-0014, DL-0113): for each change, what the
author wrote and what was accepted, both read from the repository at the two versions and marked
word by word, who changed it, and the way to the document. The text is rendered only while the
reader holds *view accepted* on the document — the right that reads accepted text, which *edit*
includes (ADR-0007); otherwise the notice shows that it exists, how many changes it lists and who
made them, and no text."""

from __future__ import annotations

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
from review.models import Acceptance, CorrectionLine, Entry
from shell.views import not_found

RANGE = re.compile(r"([1-9][0-9]{0,9})(?:-([1-9][0-9]{0,9}))?")


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
    """Each version of the accepted run by its number, `N.M-X`, as it waited."""
    base = acceptance.accepted_from
    key = services.number_key(acceptance.number)
    earlier = [
        other.number
        for other in Acceptance.objects.filter(version__document=base.document)
        if services.number_key(other.number) < key
    ]
    accepted = max(earlier, key=services.number_key, default="0.0")
    run = services.run(
        base.document, since=base, head=services.accepted_content_version(acceptance).commit_sha
    )
    return {version.commit_sha: f"{accepted}-{n}" for n, version in enumerate(run, 1)}


def page(request: HttpRequest, notification: Any) -> HttpResponse:
    notice = notification.correction_notice
    acceptance = notice.acceptance
    document = notification.document
    if acceptance.version.document_id != document.pk or notice.author_id != notification.user_id:
        return not_found(request)
    # Only the lines of this document's notice, in the order the versions came and the lines stand.
    numbers = _numbers(acceptance)
    # The versions in the order the run has them, which commit times cannot give.
    order = {sha: n for n, sha in enumerate(numbers)}
    lines = sorted(
        (
            line
            for line in CorrectionLine.objects.filter(notice=notice).select_related(
                "changing_version__author", "author_version"
            )
            if line.changing_version.document_id == line.author_version.document_id == document.pk
        ),
        key=lambda line: (
            order.get(line.changing_version.commit_sha, len(order)),
            (_span(line.range_before) or (0,))[0],
        ),
    )
    readable = Right.VIEW_ACCEPTED in rights_on(request.user, document)
    changers = sorted({person(line.changing_version.author) for line in lines})
    entries: list[dict[str, Any]] = []
    if readable:
        repo = gitstore.open_repository(holds.tenant_number(), document.number)
        accepted = services.accepted_content_version(acceptance)
        texts: dict[str, bytes] = {}

        def text_at(sha: str) -> bytes:
            if sha not in texts:
                texts[sha] = gitstore.read(repo, "document.md", sha)
            return texts[sha]

        for line in lines:
            if line.entry == Entry.PART_OPERATION:
                # A part's operation is named, never read through the line path.
                continue
            if line.entry == Entry.RESTORED:
                parents = gitstore.commit_at(repo, line.author_version.commit_sha).parents
                if not parents:
                    continue
                before = _lines(text_at(str(parents[0].id)), line.range_before)
            else:
                before = _lines(text_at(line.author_version.commit_sha), line.range_before)
            after = _lines(text_at(accepted.commit_sha), line.range_after)
            entries.append(
                {
                    "kind": line.entry,
                    "changer": person(line.changing_version.author),
                    "changing": numbers.get(line.changing_version.commit_sha, ""),
                    "author_version": numbers.get(line.author_version.commit_sha, ""),
                    # Rendered from escaped text by the one diff presentation.
                    "changes": mark_safe(render_changes(before, after)),  # noqa: S308
                }
            )
    context = {
        "document": document,
        "acceptance": acceptance,
        "count": len(lines),
        "changers": changers,
        "readable": readable,
        "entries": entries,
    }
    return render(request, "review/notice.html", context)
