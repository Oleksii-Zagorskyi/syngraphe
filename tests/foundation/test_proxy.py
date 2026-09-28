"""A trusted proxy's forwarded client, scheme and host; anyone else's headers ignored (DL-0283)."""

from __future__ import annotations

import ipaddress
from typing import Any

import pytest
from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory

pytestmark = pytest.mark.fast


def seen_through_the_proxy_step(peer: str, **headers: str) -> dict[str, Any]:
    from syngraphe.proxy import TrustedProxyMiddleware

    request = RequestFactory().post("/signin/", headers={"host": "127.0.0.1:8083", **headers})
    request.META["REMOTE_ADDR"] = peer
    seen: dict[str, Any] = {}

    def view(req: HttpRequest) -> HttpResponse:
        seen.update(host=req.get_host(), secure=req.is_secure(), client=req.META["REMOTE_ADDR"])
        return HttpResponse()

    TrustedProxyMiddleware(view)(request)
    return seen


FORWARDED = {
    "x-forwarded-host": "spoofed.example.test, docs.example.test",
    "x-forwarded-proto": "https",
    "x-forwarded-for": "198.51.100.9, 203.0.113.7",
}


def test_trusted_proxy_forwards_client_scheme_and_host(settings: Any) -> None:
    settings.TRUSTED_PROXIES = (ipaddress.ip_network("172.18.0.0/16"),)

    seen = seen_through_the_proxy_step("172.18.0.1", **FORWARDED)

    assert seen == {"host": "docs.example.test", "secure": True, "client": "203.0.113.7"}


def test_other_peers_headers_ignored(settings: Any) -> None:
    settings.TRUSTED_PROXIES = (ipaddress.ip_network("172.18.0.0/16"),)

    seen = seen_through_the_proxy_step("192.0.2.5", **FORWARDED)

    assert seen == {"host": "127.0.0.1:8083", "secure": False, "client": "192.0.2.5"}


def test_malformed_forwarded_values_leave_the_request_alone(settings: Any) -> None:
    settings.TRUSTED_PROXIES = (ipaddress.ip_network("172.18.0.0/16"),)

    seen = seen_through_the_proxy_step(
        "172.18.0.1", **{"x-forwarded-for": "not-an-address", "x-forwarded-proto": "gopher"}
    )

    assert seen == {"host": "127.0.0.1:8083", "secure": False, "client": "172.18.0.1"}


def test_an_ipv4_mapped_peer_is_trusted_as_itself(settings: Any) -> None:
    settings.TRUSTED_PROXIES = (ipaddress.ip_network("172.18.0.0/16"),)

    seen = seen_through_the_proxy_step("::ffff:172.18.0.1", **FORWARDED)

    assert seen["client"] == "203.0.113.7"
