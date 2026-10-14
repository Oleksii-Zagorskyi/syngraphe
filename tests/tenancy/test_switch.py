"""Switching organisation (ST-0007, ADR-0008, ASR-17): a person with two or more active memberships
switches from the shell; on the platform host the session's organisation changes and the list is
that organisation's alone; on an organisation's domain the browser is sent to the other's default
domain, or to the platform's default host when it has none, where the choice is confirmed; an
organisation the person does not reach answers as a missing page, and the session keeps its choice.

People, organisations and documents are synthetic examples; every address ends in
`@example.test`."""

from __future__ import annotations

import re
from typing import Any

import pytest
from django.test import Client

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

SWITCH = "/organisation/switch/"
NAMED = re.compile(r'<span class="organisation">([^<]*)</span>')


def _member_of_both(first: Any, second: Any, email: str = "two.places@example.test") -> Any:
    from identity.models import Membership, User

    person = User.objects.create_user(email, "test-only-not-a-password")
    for tenant in (first, second):
        Membership.objects.create(tenant=tenant, user=person, actor_kind="system")
    return person


def _domain(tenant: Any, host: str) -> None:
    from tenancy.middleware import invalidate_host_cache
    from tenancy.models import TenantDomain

    TenantDomain.objects.create(tenant=tenant, host=host, is_default=True, actor_kind="system")
    invalidate_host_cache()


def _document(tenant: Any, author: Any, title: str) -> None:
    from documents import services
    from documents.models import DocumentType, Folder
    from identity.models import Language

    Language.objects.get_or_create(code="uk", defaults={"label": "uk", "actor_kind": "system"})
    with schema_context(tenant.number):
        services.create_document(
            author,
            title,
            "uk",
            DocumentType.objects.get(code="document"),
            Folder.objects.get(number=1),
        )


def _platform_host() -> str:
    from tenancy.models import PlatformHost

    host = PlatformHost.objects.filter(is_default=True).values_list("host", flat=True).first()
    if host is None:
        PlatformHost.objects.create(
            host="platform.example.test", is_default=True, actor_kind="system"
        )
        host = "platform.example.test"
    return str(host)


def test_switch_on_the_platform_host(
    migrated_tenant: Any, make_tenant_schema: Any, repo_root: Any
) -> None:
    other = make_tenant_schema("Інша синтетична організація")
    person = _member_of_both(migrated_tenant, other)
    _document(migrated_tenant, person, "Синтетичний документ першої")
    _document(other, person, "Синтетичний документ другої")
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(person)

    first = client.post(SWITCH, {"organisation": migrated_tenant.number})
    first_page = client.get("/folder/1/").content.decode()
    second = client.post(SWITCH, {"organisation": other.number})
    second_page = client.get("/folder/1/").content.decode()

    assert 'class="switcher"' in first_page and 'name="organisation"' in first_page
    assert first.status_code == 302 and first["Location"] == "/"
    assert second.status_code == 302 and second["Location"] == "/"
    assert NAMED.findall(first_page) == [migrated_tenant.name]
    assert NAMED.findall(second_page) == [other.name]
    assert "Синтетичний документ першої" in first_page
    assert "Синтетичний документ другої" not in first_page
    assert "Синтетичний документ другої" in second_page
    assert "Синтетичний документ першої" not in second_page
    assert client.session["tenant_number"] == other.number


def test_switch_on_a_domain_redirects(
    migrated_tenant: Any, make_tenant_schema: Any, settings: Any
) -> None:
    from identity.models import Membership

    with_domain = make_tenant_schema("Синтетична з адресою")
    without = make_tenant_schema("Синтетична без адреси")
    person = _member_of_both(migrated_tenant, with_domain)
    Membership.objects.create(tenant=without, user=person, actor_kind="system")
    _domain(migrated_tenant, "first.example.test")
    _domain(with_domain, "second.example.test")
    platform = _platform_host()
    client = Client(headers={"host": "first.example.test"})
    client.force_login(person)
    scheme = "https" if settings.SITE_HTTPS else "http"

    to_domain = client.post(SWITCH, {"organisation": with_domain.number})
    to_platform = client.post(SWITCH, {"organisation": without.number})

    assert to_domain.status_code == 302
    assert to_domain["Location"] == f"{scheme}://second.example.test/"
    assert to_platform.status_code == 302
    # The platform host carries its own session: the choice goes with the address, and is made
    # there by the person's own POST — a GET never writes a session.
    assert to_platform["Location"] == f"{scheme}://{platform}{SWITCH}?to={without.number}"
    assert client.session.get("tenant_number") is None


def test_the_choice_is_confirmed_on_the_platform_host(
    migrated_tenant: Any, make_tenant_schema: Any
) -> None:
    other = make_tenant_schema("Інша синтетична організація")
    person = _member_of_both(migrated_tenant, other)
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(person)
    client.post(SWITCH, {"organisation": migrated_tenant.number})

    confirmation = client.get(f"{SWITCH}?to={other.number}")

    body = confirmation.content.decode()
    assert confirmation.status_code == 200
    assert other.name in body and f'value="{other.number}"' in body
    # Opening the page changes nothing: the session still names the organisation it named.
    assert client.session["tenant_number"] == migrated_tenant.number
    anonymous = Client(headers={"host": "127.0.0.1"}).get(f"{SWITCH}?to={other.number}")
    assert anonymous.status_code == 302 and anonymous["Location"].startswith("/signin/")


@pytest.mark.parametrize(
    "case",
    [
        "blocked membership",
        "blocked organisation",
        "migrating organisation",
        "self-blocked",
        "platform administrator without membership",
        "stranger",
        "not a number",
        "out of range",
        "get",
    ],
)
def test_only_active_memberships(migrated_tenant: Any, make_tenant_schema: Any, case: str) -> None:
    from identity.models import Membership, User
    from tenancy.models import Tenant

    other = make_tenant_schema("Інша синтетична організація")
    person = _member_of_both(migrated_tenant, other)
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(person)
    assert client.post(SWITCH, {"organisation": migrated_tenant.number}).status_code == 302
    target: Any = other.number
    if case == "blocked membership":
        Membership.objects.get(tenant=other, user=person).change("state", "blocked", by=None)
    elif case == "blocked organisation":
        Tenant.objects.filter(pk=other.pk).update(state="blocked")
    elif case == "migrating organisation":
        Tenant.objects.filter(pk=other.pk).update(state="migrating")
    elif case == "self-blocked":
        User.objects.filter(pk=person.pk).update(self_blocked=True)
    elif case == "platform administrator without membership":
        User.objects.filter(pk=person.pk).update(is_platform_admin=True)
        target = make_tenant_schema("Третя синтетична організація").number
    elif case == "stranger":
        target = make_tenant_schema("Третя синтетична організація").number
    elif case == "not a number":
        target = "not-a-number"
    elif case == "out of range":
        target = "99999999999999999999"

    if case == "get":
        answer = client.get(SWITCH)
    else:
        answer = client.post(SWITCH, {"organisation": target})

    assert answer.status_code == 404
    if case != "self-blocked":
        assert client.session["tenant_number"] == migrated_tenant.number


def test_switch_needs_its_csrf_token(migrated_tenant: Any, make_tenant_schema: Any) -> None:
    other = make_tenant_schema("Інша синтетична організація")
    client = Client(headers={"host": "127.0.0.1"}, enforce_csrf_checks=True)
    client.force_login(_member_of_both(migrated_tenant, other))

    assert client.post(SWITCH, {"organisation": other.number}).status_code == 403


def test_the_switcher_never_names_another_organisation(
    migrated_tenant: Any, make_tenant_schema: Any
) -> None:
    """A platform administrator who chose, through the selector, an organisation they are no member
    of: the switcher shows that organisation as current, never one of their own."""
    from identity.models import User

    first = make_tenant_schema("Перша синтетична")
    second = make_tenant_schema("Друга синтетична")
    person = _member_of_both(first, second)
    User.objects.filter(pk=person.pk).update(is_platform_admin=True)
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(person)
    client.post("/administration/organisation/", {"organisation": migrated_tenant.number})

    page = client.get("/administration/").content.decode()

    switcher = page.split('class="switcher"', 1)[1].split("</form>", 1)[0]
    selected = re.findall(r"<option[^>]*selected[^>]*>([^<]*)<", switcher)
    assert selected == [migrated_tenant.name]


def test_one_membership_draws_no_switcher(migrated_tenant: Any) -> None:
    from identity.models import Membership, User

    person = User.objects.create_user("one.place@example.test", "test-only-not-a-password")
    Membership.objects.create(tenant=migrated_tenant, user=person, actor_kind="system")
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(person)
    client.post(SWITCH, {"organisation": migrated_tenant.number})

    page = client.get("/folder/1/").content.decode()

    assert 'class="switcher"' not in page and NAMED.findall(page) == [migrated_tenant.name]


def test_the_switcher_reads_in_ukrainian(
    migrated_tenant: Any, make_tenant_schema: Any, settings: Any
) -> None:
    settings.LANGUAGE_CODE = "uk"
    other = make_tenant_schema("Інша синтетична організація")
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(_member_of_both(migrated_tenant, other))
    client.post(SWITCH, {"organisation": migrated_tenant.number})

    page = client.get("/folder/1/").content.decode()
    confirmation = client.get(f"{SWITCH}?to={other.number}").content.decode()

    switcher = page.split('class="switcher"', 1)[1].split("</form>", 1)[0]
    assert "Перейти" in switcher and "Switch" not in switcher
    assert "Switch" not in confirmation
    assert other.name in confirmation and "Work in" not in confirmation
