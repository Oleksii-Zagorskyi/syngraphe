"""The content policy on every response (DL-0493, T-05): `syngraphe.content_policy` sets one
`Content-Security-Policy`, the decided string, on every answer the application gives, whatever
its class or status, before WhiteNoise answers a static file; the switch from an organisation's
domain answers with a page under it (DL-0497); the shell carries no inline sheet.

Fast rows run the middleware around a view with `RequestFactory`; integration rows fetch the
routes through `Client`. People and organisations are synthetic examples at `@example.test`."""

from __future__ import annotations

from typing import Any

import pytest
from django.conf import settings as django_settings
from django.http import (
    FileResponse,
    HttpRequest,
    HttpResponse,
    HttpResponseNotFound,
    JsonResponse,
    StreamingHttpResponse,
)
from django.test import Client, RequestFactory

HEADER = "Content-Security-Policy"
# The decided string, written out here so that the module is compared with the decision and not
# with itself (DL-0493).
POLICY = (
    "default-src 'none'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "style-src-attr 'unsafe-inline'; "
    "img-src 'self'; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'none'; "
    "object-src 'none'"
)
DIRECTIVES = {
    "default-src": "'none'",
    "script-src": "'self'",
    "style-src": "'self'",
    "style-src-attr": "'unsafe-inline'",
    "img-src": "'self'",
    "font-src": "'self'",
    "connect-src": "'self'",
    "form-action": "'self'",
    "frame-ancestors": "'none'",
    "base-uri": "'none'",
    "object-src": "'none'",
}
MIDDLEWARE = "syngraphe.content_policy.ContentSecurityPolicyMiddleware"
PROXY = "syngraphe.proxy.TrustedProxyMiddleware"
WHITENOISE = "whitenoise.middleware.WhiteNoiseMiddleware"
SWITCH = "/organisation/switch/"
# A password the validators accept, as `tests/identity/test_framework_admin.py` sets one.
PASSWORD = "Tr4vel-Plan-Ok"


def _through_the_middleware(view: Any) -> HttpResponse:
    from syngraphe.content_policy import ContentSecurityPolicyMiddleware

    request = RequestFactory().get("/signin/", headers={"host": "127.0.0.1"})
    return ContentSecurityPolicyMiddleware(view)(request)


def _policy_headers(response: Any) -> list[str]:
    return [k for k in response.headers if k.lower() == "content-security-policy"]


@pytest.mark.fast
def test_every_response_class_carries_the_policy(tmp_path: Any) -> None:
    file = tmp_path / "download.txt"
    file.write_text("invented text", encoding="utf-8")
    views = {
        "HttpResponse": lambda _r: HttpResponse("a page"),
        "JsonResponse": lambda _r: JsonResponse({"state": "ok"}),
        "FileResponse": lambda _r: FileResponse(file.open("rb")),
        "StreamingHttpResponse": lambda _r: StreamingHttpResponse(iter([b"a", b"b"])),
        "HttpResponseNotFound": lambda _r: HttpResponseNotFound("nothing to show here"),
    }

    carried = {name: _through_the_middleware(view) for name, view in views.items()}

    for name, response in carried.items():
        assert response.get(HEADER) == POLICY, name
        if hasattr(response, "close"):
            response.close()


@pytest.mark.fast
def test_a_view_cannot_relax_the_policy() -> None:
    def relaxing(_request: HttpRequest) -> HttpResponse:
        response = HttpResponse("a page")
        response[HEADER] = "default-src *"
        return response

    response = _through_the_middleware(relaxing)

    assert response[HEADER] == POLICY
    assert len(_policy_headers(response)) == 1


@pytest.mark.fast
def test_the_policy_is_the_decided_one() -> None:
    from syngraphe import content_policy

    assert content_policy.HEADER == HEADER
    assert content_policy.POLICY == POLICY

    parts = [part.strip() for part in content_policy.POLICY.split(";")]
    assert "" not in parts, "a trailing or doubled `;`"
    read = {}
    for part in parts:
        name, _, value = part.partition(" ")
        read[name] = value
    assert len(read) == len(parts) == 11, parts
    for name, value in DIRECTIVES.items():
        assert read.get(name) == value, name
    inline = [name for name, value in read.items() if "'unsafe-inline'" in value]
    assert inline == ["style-src-attr"]
    assert "'unsafe-eval'" not in content_policy.POLICY


@pytest.mark.fast
def test_the_policy_precedes_the_static_files() -> None:
    """WhiteNoise answers a static path with a response of its own and never calls the middleware
    after it, so the policy reaches static files only from before it; the proxy stays first, so
    the request it rewrites is the one every later middleware sees (DL-0493)."""
    middleware = list(django_settings.MIDDLEWARE)

    assert MIDDLEWARE in middleware, middleware
    assert middleware.index(MIDDLEWARE) == 1
    assert middleware.index(PROXY) == 0
    assert middleware.index(MIDDLEWARE) < middleware.index(WHITENOISE)


def _assert_one_policy(response: Any, route: str) -> None:
    found = _policy_headers(response)
    assert len(found) == 1, (route, response.status_code, dict(response.headers))
    assert response[HEADER] == POLICY, (route, response.status_code)


def _signed_in(user: Any, host: str = "127.0.0.1") -> Client:
    client = Client(headers={"host": host})
    client.force_login(user)
    return client


def _on_a_domain(migrated_tenant: Any, make_tenant_schema: Any) -> tuple[Client, Any]:
    """A person in two organisations, the first with its own default domain, and a signed-in
    client on that domain; the other organisation."""
    from identity.models import Membership, User
    from tenancy.middleware import invalidate_host_cache
    from tenancy.models import TenantDomain

    other = make_tenant_schema("Another synthetic organisation")
    person = User.objects.create_user("two.places@example.test", PASSWORD)
    for tenant in (migrated_tenant, other):
        Membership.objects.create(tenant=tenant, user=person, actor_kind="system")
    TenantDomain.objects.create(
        tenant=migrated_tenant, host="first.example.test", is_default=True, actor_kind="system"
    )
    invalidate_host_cache()
    return _signed_in(person, "first.example.test"), other


@pytest.mark.integration
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_the_routes_carry_the_policy(
    migrated_tenant: Any, make_tenant_schema: Any, member_of: Any
) -> None:
    from identity.models import User

    anonymous = Client(headers={"host": "127.0.0.1"})
    member, _, _ = member_of("a.member@example.test")
    administrator, _, _ = member_of("an.administrator@example.test", is_tenant_admin=True)
    operator = _signed_in(User.objects.create_superuser("an.operator@example.test", PASSWORD))
    admin_path = f"/{django_settings.DJANGO_ADMIN_PATH}"
    on_a_domain, other = _on_a_domain(migrated_tenant, make_tenant_schema)

    answers = {
        "/signin/": anonymous.get("/signin/"),
        "/health/": anonymous.get("/health/"),
        "/no-such-page/": anonymous.get("/no-such-page/"),
        "/folder/1/": member.get("/folder/1/"),
        "/administration/": administrator.get("/administration/"),
        admin_path: operator.get(admin_path),
        "/help/": member.get("/help/"),
        f"POST {SWITCH} on first.example.test": on_a_domain.post(
            SWITCH, {"organisation": other.number}
        ),
    }

    assert answers["/health/"].status_code in (200, 503)
    assert answers["/no-such-page/"].status_code == 404
    assert answers["/folder/1/"].status_code == 200
    assert answers["/administration/"].status_code == 200
    assert answers[admin_path].status_code == 200
    assert answers["/help/"].status_code == 200
    switched = answers[f"POST {SWITCH} on first.example.test"]
    assert switched.status_code == 200 and "Location" not in switched
    for route, response in answers.items():
        _assert_one_policy(response, route)


@pytest.mark.integration
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_a_static_file_carries_the_policy(settings: Any) -> None:
    """The settings go in before the client's first request: a client builds its middleware chain,
    WhiteNoise's file index with it, on that request; without the finders the suite has no
    collected file and the answer would be the not-found page."""
    settings.WHITENOISE_USE_FINDERS = True
    settings.WHITENOISE_AUTOREFRESH = True
    client = Client(headers={"host": "127.0.0.1"})

    response = client.get("/static/htmx.min.js")

    assert response.status_code == 200
    _assert_one_policy(response, "/static/htmx.min.js")
    if hasattr(response, "close"):
        response.close()


@pytest.mark.integration
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_no_inline_sheet() -> None:
    """The templates alone: htmx's own indicator sheet is inserted by script and is the browser
    sweep's to see."""
    response = Client(headers={"host": "127.0.0.1"}).get("/signin/")
    html = response.content.decode()

    assert response.status_code == 200
    meta = [line for line in html.splitlines() if 'name="htmx-config"' in line]
    assert len(meta) == 1, meta
    assert '"includeIndicatorStyles": false' in meta[0], meta[0]
    assert "<style" not in html.lower()
