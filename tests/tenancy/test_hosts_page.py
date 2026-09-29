"""Administration › hosts: the platform's hosts and each organisation's domains, one default per
set, every change audited (ADR-0008)."""

from __future__ import annotations

from typing import Any

import pytest
from django.test import Client
from django.utils.translation import gettext

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

HOSTS = "/administration/platform/hosts/"


def test_hosts_edited_and_audited(platform_admin: Any) -> None:
    from audit.models import AuditEvent
    from tenancy.models import PlatformHost

    client, _ = platform_admin()
    before = AuditEvent.objects.count()

    added = client.post(
        HOSTS, {"action": "add", "host": "Platform.Example.test", "belongs_to": "platform"}
    )
    row = PlatformHost.objects.get(host="platform.example.test")
    defaulted = client.post(HOSTS, {"action": "default", "id": str(row.id)})

    assert added.status_code == defaulted.status_code == 302
    assert list(PlatformHost.objects.filter(is_default=True).values_list("host", flat=True)) == [
        "platform.example.test"
    ]
    assert AuditEvent.objects.count() == before + 2
    assert Client(headers={"host": "platform.example.test"}).get("/signin/").status_code == 200


def test_organisation_domain_added_as_its_default(platform_admin: Any, make_tenant: Any) -> None:
    from tenancy.models import TenantDomain

    tenant = make_tenant("Example Org")
    client, _ = platform_admin()

    client.post(
        HOSTS, {"action": "add", "host": "docs.example.test", "belongs_to": str(tenant.number)}
    )

    domain = TenantDomain.objects.get(host="docs.example.test")
    assert domain.tenant == tenant and domain.is_default


def test_last_platform_host_kept(platform_admin: Any) -> None:
    from tenancy.models import PlatformHost

    client, _ = platform_admin()
    PlatformHost.objects.exclude(host="127.0.0.1").delete()
    only = PlatformHost.objects.get()

    response = client.post(HOSTS, {"action": "remove", "id": str(only.id)})

    assert response.status_code == 200
    assert response.context["refusal"] == gettext("The platform keeps at least one host.")
    assert PlatformHost.objects.filter(id=only.id).exists()


def test_default_host_kept_until_another_is_default(platform_admin: Any) -> None:
    from tenancy.models import PlatformHost

    client, _ = platform_admin()
    default = PlatformHost.objects.get(is_default=True)

    client.post(HOSTS, {"action": "remove", "id": str(default.id)})

    assert PlatformHost.objects.filter(id=default.id).exists()


def test_a_host_belongs_to_one_set(platform_admin: Any, make_tenant: Any) -> None:
    from tenancy.models import PlatformHost

    make_tenant("Example Org", domain="docs.example.test")
    client, _ = platform_admin()

    taken = client.post(
        HOSTS, {"action": "add", "host": "docs.example.test", "belongs_to": "platform"}
    )
    malformed = client.post(HOSTS, {"action": "add", "host": "http://x", "belongs_to": "platform"})

    assert taken.status_code == malformed.status_code == 200
    assert not PlatformHost.objects.filter(host__in=["docs.example.test", "http://x"]).exists()


def test_a_new_host_answers_once_the_cache_expires(monkeypatch: Any) -> None:
    import time

    from tenancy import middleware
    from tenancy.models import PlatformHost

    assert Client(headers={"host": "later.example.test"}).get("/signin/").status_code == 400
    # Another process added it: nothing here cleared the cache.
    PlatformHost.objects.create(host="later.example.test", actor_kind="system")
    started = time.monotonic()
    monkeypatch.setattr(
        middleware.time, "monotonic", lambda: started + middleware.HOST_CACHE_SECONDS + 1
    )

    assert Client(headers={"host": "later.example.test"}).get("/signin/").status_code == 200


def test_one_name_belongs_to_one_set_whatever_its_port(
    platform_admin: Any, make_tenant: Any
) -> None:
    from tenancy.models import PlatformHost

    make_tenant("Example Org", domain="docs.example.test")
    client, _ = platform_admin()

    client.post(
        HOSTS, {"action": "add", "host": "docs.example.test:8443", "belongs_to": "platform"}
    )

    assert not PlatformHost.objects.filter(host="docs.example.test:8443").exists()


def test_an_organisations_only_domain_can_go(platform_admin: Any, make_tenant: Any) -> None:
    from tenancy.models import TenantDomain

    make_tenant("Example Org", domain="docs.example.test")
    client, _ = platform_admin()
    only = TenantDomain.objects.get(host="docs.example.test")

    response = client.post(HOSTS, {"action": "remove", "id": str(only.id)})

    assert response.status_code == 302
    assert not TenantDomain.objects.filter(id=only.id).exists()


def test_no_domain_for_an_organisation_being_set_up(platform_admin: Any, make_tenant: Any) -> None:
    from tenancy.models import TenantDomain

    tenant = make_tenant("Example Branch", state="migrating")
    client, _ = platform_admin()

    response = client.post(
        HOSTS, {"action": "add", "host": "branch.example.test", "belongs_to": str(tenant.number)}
    )

    assert response.status_code == 404
    assert not TenantDomain.objects.exists()


def test_remove_offered_where_the_service_allows_it(platform_admin: Any, make_tenant: Any) -> None:
    """A sole domain is removable, so its row offers *Remove*; a default among siblings is not."""
    from tenancy.models import PlatformHost

    make_tenant("Example Org", domain="docs.example.test")
    PlatformHost.objects.create(host="platform.example.test", is_default=False, actor_kind="system")
    client, _ = platform_admin()

    body = client.get(HOSTS).content.decode()

    assert f"{gettext('Remove')} — docs.example.test" in body
    assert f"{gettext('Remove')} — platform.example.test" in body
    assert f"{gettext('Remove')} — 127.0.0.1" not in body
