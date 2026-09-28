"""The host step: an unknown host is refused before any tenant lookup."""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import pytest
from django.test import Client

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_unknown_host_refused_first(
    make_tenant: Any, run_request: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_tenant("Example Org", domain="docs.example.test")
    lookup = Mock(side_effect=AssertionError("the tenant lookup ran"))
    monkeypatch.setattr("tenancy.middleware.resolve_tenant", lookup)

    response, _ = run_request("other.example.test")

    assert response.status_code == 400
    lookup.assert_not_called()


def test_platform_host_is_seeded(run_request: Any) -> None:
    response, seen = run_request("127.0.0.1")

    assert response.status_code == 200
    assert seen["tenant"] is None


def test_row_without_port_matches_any_port(make_tenant: Any, run_request: Any) -> None:
    tenant = make_tenant("Example Org", domain="docs.example.test")

    response, seen = run_request("docs.example.test:8443")

    assert response.status_code == 200
    assert seen["tenant"] == tenant


def test_row_with_port_matches_that_port_only(make_tenant: Any, run_request: Any) -> None:
    make_tenant("Example Org", domain="docs.example.test:8443")

    with_port, _ = run_request("docs.example.test:8443")
    without_port, _ = run_request("docs.example.test")
    other_port, _ = run_request("docs.example.test:9000")

    assert with_port.status_code == 200
    assert without_port.status_code == 400
    assert other_port.status_code == 400


def test_forwarded_host_counts_only_from_a_trusted_proxy(
    make_tenant: Any, run_request: Any, settings: Any
) -> None:
    import ipaddress

    tenant = make_tenant("Example Org", domain="docs.example.test")

    untrusted, _ = run_request("127.0.0.1", forwarded_host="docs.example.test", peer="10.9.8.7")
    settings.TRUSTED_PROXIES = (ipaddress.ip_network("10.9.8.0/24"),)
    trusted, seen = run_request(
        "127.0.0.1", forwarded_host="evil.example.test, docs.example.test", peer="10.9.8.7"
    )

    assert untrusted.status_code == 200
    assert trusted.status_code == 200
    assert seen["tenant"] == tenant


def test_health_answers_on_any_host() -> None:
    response = Client(headers={"host": "nowhere.example.test"}).get("/health/")

    assert response.status_code == 200
