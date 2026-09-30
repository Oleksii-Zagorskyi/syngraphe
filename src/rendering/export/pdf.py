"""PDF by weasyprint (ADR-0013): the document's HTML and its stylesheets, every fetch through one
fetcher that serves only the document's own image files and fails the render on anything else —
a remote reference, a missing file, any other address. The file is written only when the render
succeeds.
"""

from __future__ import annotations

import mimetypes
import re
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from weasyprint import CSS, HTML
from weasyprint.urls import URLFetcherResponse

# The address the page is rendered under; it names nothing, so no relative reference can reach
# anything but what the fetcher serves from it.
BASE = "https://document.invalid/"
IMAGE = re.compile(r"images/[A-Za-z0-9][A-Za-z0-9._-]{0,199}")


class FetchRefused(Exception):
    """An address the export may not fetch."""


def fetcher(read_image: Callable[[str], bytes]) -> Callable[..., URLFetcherResponse]:
    """A weasyprint fetcher serving `images/<name>` under `BASE` by `read_image(path)`, and
    refusing every other address; its failures stop the render."""

    def fetch(url: str, *_: Any, **__: Any) -> URLFetcherResponse:
        if not url.startswith(BASE) or not IMAGE.fullmatch(url[len(BASE) :]):
            raise FetchRefused(url)
        path = url[len(BASE) :]
        kind = mimetypes.guess_type(path)[0] or "application/octet-stream"
        return URLFetcherResponse(url, body=read_image(path), headers={"Content-Type": kind})

    fetch._fail_on_errors = True  # type: ignore[attr-defined]
    return fetch


def write(
    html: str, path: Path, *, stylesheets: Sequence[str], read_image: Callable[[str], bytes]
) -> None:
    """Render `html` with `stylesheets` (CSS text) to `path`; raises, and writes nothing, when any
    reference cannot be fetched."""
    fetch = fetcher(read_image)
    partial = path.with_name(path.name + ".part")
    try:
        HTML(string=html, base_url=BASE, url_fetcher=fetch).write_pdf(
            partial,
            stylesheets=[CSS(string=css, base_url=BASE, url_fetcher=fetch) for css in stylesheets],
        )
        partial.replace(path)
    finally:
        partial.unlink(missing_ok=True)
