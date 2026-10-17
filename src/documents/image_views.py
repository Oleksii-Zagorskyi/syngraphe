"""A document's committed images (DL-0439): an image is served to a reader whose ceiling reaches a
version holding it, and to nobody else; reading an image is reading the text, which is not audited.
"""

from __future__ import annotations

import logging

import pygit2
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.views.decorators.cache import never_cache

from documents import gitstore, images
from documents.views import readable_document
from shell.views import not_found

logger = logging.getLogger(__name__)


@never_cache
@login_required
def image(request: HttpRequest, number: int, name: str) -> HttpResponse:
    """The image `name` from the newest version the reader's ceiling reaches that holds it."""
    from rendering.views import UNREADABLE
    from review.history import ceiling

    document = readable_document(request, number)
    if document is None or not images.NAME.fullmatch(name):
        return not_found(request)
    path = f"{images.FOLDER}/{name}"
    try:
        reached = ceiling(request.user, document).reachable()
        repo = gitstore.open_repository(request.tenant.number, document.number)  # type: ignore[attr-defined]
    except UNREADABLE:
        # A record that does not read is answered as every page answers it, and logged.
        logger.exception("a document's history could not be read", extra={"document": number})
        return not_found(request)
    for _number, version in reversed(reached):
        try:
            return images.served(gitstore.read(repo, path, version.commit_sha), name)
        except (KeyError, ValueError, pygit2.GitError):
            continue
    return not_found(request)
