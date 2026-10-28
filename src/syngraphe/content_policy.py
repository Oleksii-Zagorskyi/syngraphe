"""One `Content-Security-Policy` on every response the application sends (DL-0493; T-05).

The platform's own scripts, styles, images and fonts only; scripts never evaluated; no plugin, no
framing by another site, forms posted to the platform alone. Nothing inline but `style` attributes,
which the pages use for their panes' widths, a folder's depth and a table cell's alignment.

The policy is the same on every installation and is not configuration: a page that needs more is a
change here, with the test that shows why. It is set rather than defaulted, so no view can relax it.
The middleware sits before WhiteNoise, which answers static files without calling the layers after
it.
"""

from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

HEADER = "Content-Security-Policy"
POLICY = "; ".join(
    (
        "default-src 'none'",
        "script-src 'self'",
        "style-src 'self'",
        "style-src-attr 'unsafe-inline'",
        "img-src 'self'",
        "font-src 'self'",
        "connect-src 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
        "base-uri 'none'",
        "object-src 'none'",
    )
)


class ContentSecurityPolicyMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        response[HEADER] = POLICY
        return response
