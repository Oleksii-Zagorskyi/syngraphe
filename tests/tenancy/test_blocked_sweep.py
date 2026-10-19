"""Every route of the resolver is closed to a blocked organisation's members (ST-0065, DL-0376):
each pattern, its arguments filled, first reached while the organisation is active — proof the fill
reaches the view — then answered *Nothing to show here*, by `GET` and by `POST`, on the
organisation's own domain and from the platform host with it chosen. The exempt routes read no
organisation's content and say why; a route no fill reaches while active says why too.

A route added later is swept as it stands: a new keyword joins `FILL`, or the route joins
`UNREACHED` or `EXEMPT` with its reason.

People, groups, documents and their text are synthetic examples."""

from __future__ import annotations

import hashlib
import importlib.util
import re
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from django.conf import settings as django_settings
from django.db import transaction
from django.test import Client
from django.urls import URLPattern, URLResolver, get_resolver

from tenancy.schemas import schema_context

_spec = importlib.util.spec_from_file_location(
    "blocked_sweep_editing_fixtures",
    Path(__file__).resolve().parents[1] / "editing" / "conftest.py",
)
assert _spec is not None and _spec.loader is not None
_editing = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _editing
_spec.loader.exec_module(_editing)

# The editing tests' fixtures: a document with its repository, a linked group, a committed version.
new_document = _editing.new_document
link_group = _editing.link_group
commit_version = _editing.commit_version

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

DOMAIN = "sweep.example.test"
TOKEN = re.compile(rb'name="csrfmiddlewaretoken" value="[^"]*"')

# Each (converter, keyword) a route takes, to the name of the value the sweep fills it with.
FILL: dict[tuple[str, str], str] = {
    ("int", "number"): "number",
    ("int", "part"): "part",
    ("str", "version_number"): "version_number",
    ("uuid", "group_id"): "group_id",
    ("uuid", "membership_id"): "membership_id",
    ("uuid", "user_id"): "user_id",
    ("uuid", "pk"): "notification",
    ("uuid", "sample_id"): "sample",
    ("str", "job_id"): "job",
    ("str", "name"): "image",
    ("str", "token"): "token",
    ("str", "digest_asked"): "digest",
    ("slug", "slug"): "help",
    ("path", "content_type_id"): "content_type",
    ("path", "object_id"): "object",
}

# Routes that read no organisation's content, each with its reason.
EXEMPT: dict[str, str] = {
    "health": "the service's own health, no organisation's content",
    "setup": "the installation's first run, before any organisation",
    "signin": "signing in reads no organisation's content",
    "signout": "signing out reads no organisation's content",
    "block_account": "a person's own account (its POST blocks the actor's own account)",
    "reset_request": "a person's own account",
    "reset_password": "a person's own account, reached by its token",
    "accept_invitation": "an invitation, reached by its token",
    "preference_show_author": "a person's own preference",
    "preference_outline_width": "a person's own preference",
    "preference_panel_width": "a person's own preference",
    "preference_folder_tree_width": "a person's own preference",
    "switch_organisation": "the organisation switcher: which organisations a person reaches",
    "choose_organisation": "the platform's organisation selector",
    "help": "the help pages are the product's, not an organisation's",
    "help_page": "the help pages are the product's, not an organisation's",
    "editing_conformance": "the editor's conformance page: test cases, no organisation's content",
    "tenants": "a platform page: platform administrators alone",
    "tenant_new": "a platform page: platform administrators alone",
    "hosts": "a platform page: platform administrators alone",
    "administrators": "a platform page: platform administrators alone",
    "administration_grant": "a platform page: platform administrators alone",
    "administration_revoke": "a platform page: platform administrators alone",
    "tenant_block": "a platform page: platform administrators alone",
    "tenant_lift": "a platform page: platform administrators alone",
    "tenant_appoint": "a platform page: platform administrators alone",
    "platform_mail": "a platform page: platform administrators alone",
    "platform_mail_test": "a platform page: platform administrators alone",
    "audit_log": "a platform page: platform administrators alone",
}
# The framework's administration, confined to the operator by its own middleware (DL-0210).
EXEMPT_PREFIXES = {django_settings.DJANGO_ADMIN_PATH: "the framework's administration"}

EDITOR = "needs an open editor of the actor's, which only the editor's own load opens"
KEPT = "needs a kept draft of the actor's, left by a hold ended elsewhere"
# Routes the fill cannot reach while the organisation is active, each with its reason.
UNREACHED: dict[str, str] = {
    "notification_image": "no notification of the sweep's carries an image",
    "document_edit_capture": EDITOR,
    "document_edit_heartbeat": EDITOR,
    "document_edit_close": EDITOR,
    "document_edit_changes": EDITOR,
    "document_edit_send": "needs a draft its holder has finished",
    "document_edit_end_reservation": "needs a reservation another person holds",
    "document_edit_take_back": KEPT,
    "document_edit_discard_draft": KEPT,
    "document_edit_force_release": "needs another person's hold",
    "document_edit_image_upload": "an upload without its file is answered as a missing page",
    "document_edit_image": "needs an image staged in the actor's draft",
    "document_parts_attachment": "needs an attachment staged in the actor's draft",
    "document_undo": "needs an edit of the actor's to undo, named in the request",
    "document_revert": "needs a part change in the pending run, named in the request",
    "export_download": "needs an export the worker has finished",
}

# The form a route answers only when given — an empty one is answered as a missing page — filled
# from the sweep's values; and the query a `GET` route needs.
BODIES: dict[str, dict[str, str]] = {
    "group_rights": {"right": "accept", "action": "grant"},
    "document_link": {"group": "{group_id}", "action": "link"},
    "folder_new": {"parent": "1", "name": "Synthetic folder"},
}
QUERIES: dict[str, str] = {
    "compare_start": "?first={number}&second={number}",
    "document_compare": "?from=0.0&to={version_number}",
    "document_compare_appendix": "?from={version_number}:1&to={version_number}:1",
}
# The routes of the actor's own editing, asked of a document of their own they hold, and the one
# that needs it reserved.
HELD = {
    "document_edit_load",
    "document_edit_capture",
    "document_edit_heartbeat",
    "document_edit_close",
    "document_edit_changes",
    "document_edit_finish",
    "document_edit_send",
    "document_edit_discard",
    "document_my_edits",
    "document_edit_reserve",
    "document_edit_cancel_reservation",
    "document_edit_image_upload",
    "document_edit_image",
    "document_edit_entities",
    "document_appendix_edit_load",
    "document_parts_attachment",
}
RESERVED = {"document_edit_cancel_reservation"}


@dataclass(frozen=True)
class Route:
    path: str
    name: str
    keys: tuple[tuple[str, str], ...]
    pattern: Any


def _converter(converter: Any) -> str:
    return type(converter).__name__.removesuffix("Converter").lower().replace("string", "str")


def routes(patterns: list[Any] | None = None, prefix: str = "") -> Iterator[Route]:
    """Every pattern of the resolver, with the (converter, keyword) keys its arguments take."""
    for pattern in get_resolver().url_patterns if patterns is None else patterns:
        if isinstance(pattern, URLResolver):
            yield from routes(pattern.url_patterns, prefix + str(pattern.pattern))
            continue
        assert isinstance(pattern, URLPattern)
        converters = getattr(pattern.pattern, "converters", {})
        keys = tuple((_converter(c), k) for k, c in converters.items())
        yield Route(prefix + str(pattern.pattern), pattern.name or "", keys, pattern)


def exempt(route: Route) -> str | None:
    if route.name in EXEMPT:
        return EXEMPT[route.name]
    for prefix, reason in EXEMPT_PREFIXES.items():
        if route.path.startswith(prefix):
            return reason
    return None


def fill(route: Route, values: dict[str, str]) -> str:
    """The route's address with each argument filled; `KeyError` naming the route and the key a
    `FILL` entry is missing for."""
    address = route.path
    for converter, keyword in route.keys:
        if (converter, keyword) not in FILL:
            raise KeyError(f"{route.path}: no FILL for ({converter!r}, {keyword!r})")
        address = re.sub(rf"<{converter}:{keyword}>", values[FILL[(converter, keyword)]], address)
    return "/" + address


def _tokenless(body: bytes) -> bytes:
    return TOKEN.sub(b"", body)


def _body(response: Any) -> bytes:
    """A response's body without its form token, a streamed file read whole (and so closed)."""
    if getattr(response, "streaming", False):
        return b"".join(response.streaming_content)
    return _tokenless(response.content)


def _client(user: Any, host: str, tenant: Any = None) -> Client:
    client = Client(headers={"host": host})
    client.force_login(user)
    if tenant is not None:
        session = client.session
        session["tenant_number"] = tenant.number
        session.save()
    return client


@pytest.fixture
def organisation(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    invented_image: Any,
) -> dict[str, Any]:
    """A synthetic organisation and the values the sweep fills its routes with: a document of
    number 1 — the root folder's number too — with a version, an appendix, an attachment and an
    image; a group linked to it holding every right; a notification, an export and a sample of
    the actor's; another member."""
    from access.rights import GRID
    from notifications.models import Notification
    from rendering.models import ExportJob, SampleExport
    from tenancy.models import TenantDomain

    TenantDomain.objects.create(
        tenant=migrated_tenant, host=DOMAIN, is_default=True, actor_kind="system"
    )
    client, actor, membership = member_of("the.actor@example.test", is_tenant_admin=True)
    _, other_admin, _ = member_of("another.admin@example.test", is_tenant_admin=True)
    _, _, other = member_of("another.member@example.test")
    document = new_document(actor)
    assert document.number == 1
    group = link_group(document, list(GRID), [membership], other_admin)
    image = invented_image()
    image_name = hashlib.sha256(image).hexdigest() + ".png"
    commit_version(
        document,
        actor,
        f"# Purpose\n\nThe first synthetic sentence.\n\n![A synthetic plan](images/{image_name})\n",
        appendices=[{"number": 1, "title": "Synthetic appendix"}],
        attachments=[
            {
                "number": 1,
                "title": "Synthetic form",
                "file_name": "form.txt",
                "sha256": hashlib.sha256(b"a synthetic form").hexdigest(),
                "bytes": len(b"a synthetic form"),
            }
        ],
        files={
            "appendices/1.md": b"# Synthetic appendix\n",
            "attachments/1": b"a synthetic form",
            f"images/{image_name}": image,
        },
    )
    assert client.post(
        f"/document/{document.number}/export/",
        {"document": "on", "format": "pdf", "view": "pending_edits"},
    ).status_code in (200, 302, 303)
    assert client.post("/administration/tenant/styles/sample/", {"text": "", "format": "pdf"})
    with schema_context(migrated_tenant.number):
        job = ExportJob.objects.order_by("-created_at").first()
        sample = SampleExport.objects.order_by("-created_at").first()
        if sample is not None:
            # Rendered, so its download has a file to give.
            from rendering import sample as samples

            samples.run(sample.pk, migrated_tenant.number)
        notification = Notification.objects.filter(user=actor).first()

    def fresh() -> str:
        """A document of the route's own for a `POST`, the actor holding every right on it."""
        made = new_document(actor)
        link_group(made, list(GRID), [membership], other_admin)
        return str(made.number)

    return {
        "tenant": migrated_tenant,
        "membership": membership,
        "document": document,
        "fresh": fresh,
        "actor": actor,
        "values": {
            "number": str(document.number),
            "part": "1",
            "version_number": "0.0-1",
            "group_id": str(group.pk),
            "membership_id": str(other.pk),
            "user_id": str(other.user_id),
            "notification": str(notification.pk) if notification else "0" * 32,
            "sample": str(sample.pk) if sample else "0" * 32,
            "job": str(job.pk) if job else "0",
            "image": image_name,
            "token": "x",
            "digest": "0" * 16,
            "help": "editing",
            "content_type": "1",
            "object": "1",
        },
    }


@dataclass(frozen=True)
class Asked:
    """How the control reached a route: the address of its `GET`, and of its `POST` with the
    body — the very requests the blocked organisation's member then makes."""

    get: str
    post: str
    body: dict[str, str]


def _asked(route: Route, values: dict[str, str], fresh: Callable[[], str], client: Client) -> Asked:
    """The route's requests: a document's route `POST`s on a document of its own, so no act it
    performs reaches the routes walked after it; a route of the actor's own editing asks both of
    a document of its own they hold — and have reserved, where the route needs it."""
    address = fill(route, values)
    post = address
    if route.name in HELD:
        number = fresh()
        assert client.post(f"/document/{number}/edit/take/").status_code == 200
        if route.name in RESERVED:
            assert client.post(f"/document/{number}/edit/reserve/").status_code in (200, 302, 303)
        address = post = fill(route, {**values, "number": number})
    elif route.path.startswith("document/<int:number>/"):
        post = fill(route, {**values, "number": fresh()})
    body = {key: value.format(**values) for key, value in BODIES.get(route.name, {}).items()}
    return Asked(address + QUERIES.get(route.name, "").format(**values), post, body)


def _nothing(client: Client) -> bytes:
    """The body an address that does not exist gets now: the frame around it carries the actor's
    unread count, which the walk's own acts change."""
    return _tokenless(client.get("/no-such-address/").content)


def _reached(client: Client, asked: Asked) -> bool:
    """Whether the route answers anything but the uniform not-found body — by `GET`, else by its
    `POST`; a route outside any document's in a savepoint rolled back."""
    if _body(client.get(asked.get)) != _nothing(client):
        return True
    if asked.post.startswith("/document/"):
        posted = client.post(asked.post, asked.body)
    else:
        with transaction.atomic():
            posted = client.post(asked.post, asked.body)
            transaction.set_rollback(True)
    return _body(posted) != _nothing(client)


def test_every_route_is_closed_to_a_blocked_organisation(organisation: dict[str, Any]) -> None:
    from documents.models import Document
    from identity.models import Membership, User
    from tenancy.middleware import invalidate_host_cache

    tenant, actor, values = organisation["tenant"], organisation["actor"], organisation["values"]
    swept = [r for r in routes() if exempt(r) is None]
    active = _client(actor, DOMAIN)

    asked = {r.name: _asked(r, values, organisation["fresh"], active) for r in swept}
    # Reached while active on both hosts the blocked phase asks from, so a not-found answer
    # there is the block's and not the host's.
    for client in (active, _client(actor, "127.0.0.1", tenant)):
        unreached = [
            r.name for r in swept if r.name not in UNREACHED and not _reached(client, asked[r.name])
        ]
        assert unreached == [], "not reached while active:\n" + "\n".join(unreached)
    print("reached only when blocked, by their reasons:", UNREACHED)
    # The walk changed nothing the blocked phase stands on: the actor, their membership and the
    # document the routes are filled with.
    assert Membership.objects.get(pk=organisation["membership"].pk).state == "active"
    assert not User.objects.get(pk=actor.pk).self_blocked
    with schema_context(tenant.number):
        assert Document.objects.get(pk=organisation["document"].pk).state == "active"

    tenant.state = "blocked"
    tenant.save(update_fields=["state"])
    invalidate_host_cache()
    open_routes = []
    for client in (_client(actor, DOMAIN), _client(actor, "127.0.0.1", tenant)):
        for route in swept:
            request = asked[route.name]
            for answer in (client.get(request.get), client.post(request.post, request.body)):
                if answer.status_code != 404 or _body(answer) != _nothing(client):
                    open_routes.append((route.name, answer.request["REQUEST_METHOD"]))
    assert open_routes == [], open_routes


def test_every_pattern_is_filled() -> None:
    """A route whose argument no `FILL` entry names fails, naming the route and the key — the
    sweep never skips what it cannot fill."""
    from django.urls import path

    planted = path("planted/<uuid:widget_id>/", lambda request, widget_id: None, name="planted")
    names = {r.name for r in routes()}
    for route in routes():
        fill(route, {value: "1" for value in FILL.values()})

    [route] = list(routes([planted]))
    with pytest.raises(KeyError, match=r"planted/<uuid:widget_id>/.*\('uuid', 'widget_id'\)"):
        fill(route, {})
    assert "planted" not in names


def test_exemptions_are_named() -> None:
    """Every exempt and every unreached entry names a route the resolver holds, with its reason."""
    names = {r.name for r in routes()}
    for listed in (EXEMPT, UNREACHED):
        for name, reason in listed.items():
            assert name in names, name
            assert reason.strip(), name
    assert all(any(r.path.startswith(p) for r in routes()) for p in EXEMPT_PREFIXES)
