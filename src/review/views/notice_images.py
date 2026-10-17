"""The images of a correction notice's passages (DL-0439): the page shows its recipient the lines a
reviewer changed, before and after, and this route serves the images those lines show — read at
the commit each passage was read at — to that recipient alone, whatever their history right
reaches, while they may read the document's accepted text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.views.decorators.cache import never_cache

from access.rights import Right, rights_on
from documents import gitstore, images
from documents.views import readable_document
from editing import holds
from identity.models import User
from shell.views import not_found


@dataclass(frozen=True)
class NoticeLine:
    """One line of a notice as its page shows it: the line, and its passage before the reviewer's
    change and after, each with the commit it was read at."""

    line: Any
    before: bytes
    before_sha: str
    after: bytes
    after_sha: str


def selected_lines(notice: Any, document: Any, numbers: dict[str, str] | None = None) -> list[Any]:
    """The notice's lines of `document` — every entry, a part's operation included — in the order
    the run's versions came, then the order the lines stand, when `numbers` gives the run's
    order; as stored otherwise."""
    from review.models import CorrectionLine
    from review.views.notice import _span

    lines = [
        line
        for line in CorrectionLine.objects.filter(notice=notice).select_related(
            "changing_version__author", "author_version"
        )
        if line.changing_version.document_id == line.author_version.document_id == document.pk
    ]
    if numbers is None:
        return lines
    order = {sha: n for n, sha in enumerate(numbers)}
    return sorted(
        lines,
        key=lambda line: (
            order.get(line.changing_version.commit_sha, len(order)),
            (_span(line.range_before) or (0,))[0],
        ),
    )


def notice_lines(notice: Any, document: Any, *, ordered: bool = True) -> list[NoticeLine]:
    """The notice's lines of `document`, each with its two passages — in the run's order unless
    `ordered` is false; a part's operation, which is named and never read, left out; a restored
    line read from the commit before its author's version."""
    from review import services
    from review.models import Entry
    from review.views.notice import _lines, _numbers

    acceptance = notice.acceptance
    lines = selected_lines(notice, document, _numbers(acceptance) if ordered else None)
    repo = gitstore.open_repository(holds.tenant_number(), document.number)
    accepted = services.accepted_content_version(acceptance).commit_sha
    texts: dict[str, bytes] = {}

    def text_at(sha: str) -> bytes:
        if sha not in texts:
            texts[sha] = gitstore.read(repo, "document.md", sha)
        return texts[sha]

    found = []
    for line in lines:
        if line.entry == Entry.PART_OPERATION:
            continue
        if line.entry == Entry.RESTORED:
            parents = gitstore.commit_at(repo, line.author_version.commit_sha).parents
            if not parents:
                continue
            before_sha = str(parents[0].id)
        else:
            before_sha = line.author_version.commit_sha
        found.append(
            NoticeLine(
                line,
                _lines(text_at(before_sha), line.range_before),
                before_sha,
                _lines(text_at(accepted), line.range_after),
                accepted,
            )
        )
    return found


def passages(notice: Any, document: Any = None) -> dict[str, str]:
    """Each image name the notice's passages show, mapped to the commit its passage was read at;
    `document` the notice's own when not given."""
    if document is None:
        document = notice.acceptance.version.document
    found: dict[str, str] = {}
    for entry in notice_lines(notice, document, ordered=False):
        for text, sha in ((entry.before, entry.before_sha), (entry.after, entry.after_sha)):
            for reference in images.referenced({"passage": text.decode("utf-8")}):
                if images.is_image_path(reference.src):
                    found.setdefault(reference.src.removeprefix(f"{images.FOLDER}/"), sha)
    return found


@never_cache
@login_required
def image(request: HttpRequest, pk: Any, name: str) -> HttpResponse:
    """An image of the requester's own correction notice: only the images its passages show,
    only while the document is active and they may read its accepted text. Not audited, as
    reading the text is not; opening the notice is what marks it read."""
    from notifications.models import Event, Notification
    from notifications.services import openable
    from notifications.views.detail import _in_organisation
    from rendering.views import UNREADABLE

    user = cast(User, request.user)
    if request.method != "GET" or user.pk is None or not _in_organisation(request):
        return not_found(request)
    if not images.NAME.fullmatch(name):
        return not_found(request)
    row = (
        Notification.objects.filter(pk=pk, user_id=user.pk, event=Event.CORRECTION_NOTICE)
        .select_related("document", "correction_notice__acceptance__version")
        .first()
    )
    if row is None or row.correction_notice is None or row.document is None:
        return not_found(request)
    if not openable(user, [row]):
        return not_found(request)
    notice = row.correction_notice
    document = readable_document(request, row.document.number)
    if (
        document is None
        or notice.acceptance.version.document_id != document.pk
        or notice.author_id != user.pk
        or Right.VIEW_ACCEPTED not in rights_on(user, document)
    ):
        return not_found(request)
    try:
        sha = passages(notice, document).get(name)
        if sha is None:
            return not_found(request)
        repo = gitstore.open_repository(holds.tenant_number(), document.number)
        data = gitstore.read(repo, f"{images.FOLDER}/{name}", sha)
    except UNREADABLE:
        # A record that does not read is answered as every page answers it.
        return not_found(request)
    return images.served(data, name)
