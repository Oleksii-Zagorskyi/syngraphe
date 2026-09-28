"""The request as the client made it, when a trusted proxy forwarded it (DL-0283).

From a peer in `TRUSTED_PROXIES`, the client's address, the scheme and the host are taken from the
proxy's `X-Forwarded-For`, `X-Forwarded-Proto` and `X-Forwarded-Host` — the last entry of each,
the one the proxy wrote itself, whatever a client put before it. Every later layer — the host
check, CSRF, secure cookies, throttling, the logs — then reads the ordinary request attributes.
From any other peer the headers are ignored.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse


def _last(value: str) -> str:
    return value.rsplit(",", 1)[-1].strip()


def is_trusted(peer: str) -> bool:
    try:
        address: ipaddress.IPv4Address | ipaddress.IPv6Address = ipaddress.ip_address(peer)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return any(address in network for network in settings.TRUSTED_PROXIES)


class TrustedProxyMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        meta = request.META
        if is_trusted(str(meta.get("REMOTE_ADDR", ""))):
            host = _last(str(meta.get("HTTP_X_FORWARDED_HOST", "")))
            if host:
                meta["HTTP_HOST"] = host
            scheme = _last(str(meta.get("HTTP_X_FORWARDED_PROTO", ""))).lower()
            if scheme in ("http", "https"):
                meta["wsgi.url_scheme"] = scheme
            client = _last(str(meta.get("HTTP_X_FORWARDED_FOR", "")))
            try:
                meta["REMOTE_ADDR"] = str(ipaddress.ip_address(client))
            except ValueError:
                pass
        return self.get_response(request)
