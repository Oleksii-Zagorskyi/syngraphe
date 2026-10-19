"""Administration › Platform › Audit log (ST-0050; DL-0082, DL-0392, DL-0393, DL-0434): the newest
200 audit events matching the filters, for a platform administrator on a platform host, each
person by address, each object and change drawn from the event's own payload.

People, organisations and events are synthetic examples; addresses end in `@example.test`."""

from __future__ import annotations

import html
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

PAGE = "/administration/platform/audit/"
DOMAIN = "audit.example.test"


@pytest.fixture(autouse=True)
def in_english(settings: Any) -> None:
    settings.LANGUAGE_CODE = "en"
    settings.DISPLAY_TIMEZONE = "UTC"


def _at(day: int, hour: int = 12, minute: int = 0) -> datetime:
    return datetime(2026, 3, day, hour, minute, tzinfo=UTC)


def _event(
    action: str, at: datetime, *, actor: Any = None, tenant: Any = None, **payload: Any
) -> Any:
    from audit.models import AuditEvent

    return AuditEvent.objects.create(
        tenant=tenant,
        actor=actor,
        actor_kind="system" if actor is None else "user",
        action=action,
        object_type=payload.pop("object_type", "document"),
        before=payload.pop("before", None),
        after=payload.pop("after", None),
        at=at,
    )


def _operator(signed_in_without_tenant: Any) -> Client:
    return signed_in_without_tenant("an.operator@example.test", is_platform_admin=True)


def _rows(response: Any) -> list[str]:
    body = response.content.decode()
    table = body.split('<tbody class="events">', 1)[1].split("</tbody>", 1)[0]
    rows = re.findall(r"<tr>(.*?)</tr>", table, re.S)
    return [
        re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", row))).strip() for row in rows
    ]


def _cells(response: Any) -> list[list[str]]:
    """Each row's cells, in the columns' order: When, Who, Kind, Organisation, Action, Object,
    Change."""
    body = response.content.decode()
    table = body.split('<tbody class="events">', 1)[1].split("</tbody>", 1)[0]
    return [
        [
            re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", cell))).strip()
            for cell in re.findall(r"<td>(.*?)</td>", row, re.S)
        ]
        for row in re.findall(r"<tr>(.*?)</tr>", table, re.S)
    ]


def _text(response: Any) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", response.content.decode())))


def test_the_newest_200(
    migrated_tenant: Any, make_tenant_schema: Any, signed_in_without_tenant: Any
) -> None:
    other = make_tenant_schema("Other Org")
    start = _at(1)
    for n in range(250):
        tenant = (migrated_tenant, other, None)[n % 3]
        _event(f"synthetic.act{n:03d}", start + timedelta(minutes=n), tenant=tenant)

    response = _operator(signed_in_without_tenant).get(PAGE)

    assert response.status_code == 200
    rows = _rows(response)
    assert len(rows) == 200
    assert "synthetic.act249" in rows[0] and "synthetic.act050" in rows[-1]
    assert "The newest 200 events matching." in _text(response)
    header = response.content.decode().split('<tbody class="events">', 1)[0]
    for column in ("When", "Who", "Kind", "Organisation", "Action", "Object", "Change"):
        assert f"<th>{column}</th>" in header


def test_fewer_than_the_bound_are_not_said_to_be_bounded(signed_in_without_tenant: Any) -> None:
    _event("synthetic.act", _at(1))

    response = _operator(signed_in_without_tenant).get(PAGE)

    assert len(_rows(response)) == 1
    assert "The newest 200" not in _text(response)


def test_filters(
    migrated_tenant: Any, make_tenant_schema: Any, signed_in_without_tenant: Any, member_of: Any
) -> None:
    other = make_tenant_schema("Other Org")
    _, person, _ = member_of("a.person@example.test")
    _event("document.archived", _at(1), tenant=migrated_tenant, actor=person)
    _event("document.restored", _at(2), tenant=migrated_tenant)
    _event("folder.created", _at(3), tenant=other, actor=person)
    _event("platform.administration_granted", _at(4), actor=person, object_type="user")
    client = _operator(signed_in_without_tenant)

    def actions(**query: Any) -> list[str]:
        response = client.get(PAGE, query)
        assert response.status_code == 200, query
        return [_action(row) for row in _rows(response)]

    assert actions(organisation=str(migrated_tenant.number)) == [
        "document.restored",
        "document.archived",
    ]
    assert actions(organisation="platform") == ["platform.administration_granted"]
    assert actions(kind="system") == ["document.restored"]
    assert actions(action="document.") == ["document.restored", "document.archived"]
    assert actions(since="2026-03-02", until="2026-03-03") == [
        "folder.created",
        "document.restored",
    ]
    assert actions(kind="user", action="document.") == ["document.archived"]


def _action(row: str) -> str:
    return next(word for word in row.split() if re.fullmatch(r"[a-z_]+\.[a-z_.]+", word))


def test_the_form_refuses_what_it_does_not_know(signed_in_without_tenant: Any) -> None:
    client = _operator(signed_in_without_tenant)

    for query in (
        {"organisation": "9999"},
        {"kind": "robot"},
        {"since": "2026-03-04", "until": "2026-03-03"},
        {"since": "yesterday"},
        {"action": "x" * 101},
    ):
        response = client.get(PAGE, query)
        assert response.status_code == 400, query
        assert '<tbody class="events">' not in response.content.decode(), query


def test_rows_are_presented_from_the_payload(signed_in_without_tenant: Any) -> None:
    _event(
        "membership.changed",
        _at(1),
        object_type="membership",
        before={"state": "active"},
        after={"state": "blocked", "number": 7},
    )
    _event("something.new", _at(2), after={"text": "x" * 300})

    rows = _rows(_operator(signed_in_without_tenant).get(PAGE))

    assert "something.new" in rows[0]
    assert "text: — → " + "x" * 120 + "…" in rows[0]
    assert "membership #7" in rows[1]
    assert "state: active → blocked" in rows[1]
    assert "number: — → 7" in rows[1]


def test_who_by_address(signed_in_without_tenant: Any, member_of: Any) -> None:
    from audit.models import AuditEvent
    from identity.models import User

    _, person, _ = member_of("named.admin@example.test")
    User.objects.filter(pk=person.pk).update(display_name="Synthetic Admin")
    _event("synthetic.by_person", _at(1), actor=person)
    _event("synthetic.by_system", _at(2))
    AuditEvent.objects.create(
        actor=None, actor_kind="agent", action="synthetic.by_agent", object_type="x", at=_at(3)
    )

    rows = _cells(_operator(signed_in_without_tenant).get(PAGE))

    assert [row[1:3] for row in rows] == [
        ["agent", "agent"],
        ["system", "system"],
        ["named.admin@example.test", "person"],
    ]


def test_platform_administrators_on_the_platform_host_only(
    migrated_tenant: Any, member_of: Any, signed_in_without_tenant: Any
) -> None:
    from identity.models import User
    from tenancy.middleware import invalidate_host_cache
    from tenancy.models import TenantDomain

    admin, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    member, _, _ = member_of("a.member@example.test")
    TenantDomain.objects.create(
        tenant=migrated_tenant, host=DOMAIN, is_default=True, actor_kind="system"
    )
    invalidate_host_cache()
    on_domain = Client(headers={"host": DOMAIN})
    on_domain.force_login(
        User.objects.create_user("p.admin@example.test", "Tr4vel-Plan-Ok", is_platform_admin=True)
    )

    for client in (admin, member, on_domain):
        response = client.get(PAGE)
        assert response.status_code == 404
        assert '<tbody class="events">' not in response.content.decode()
    assert _operator(signed_in_without_tenant).post(PAGE).status_code == 404


def test_reads_shared_tables_only(
    migrated_tenant: Any, member_of: Any, signed_in_without_tenant: Any
) -> None:
    """With an organisation chosen in the session, the page's own read of the events joins only
    the shared tables; the frame's reads are the frame's."""
    _, person, _ = member_of("a.person@example.test")
    _event("document.archived", _at(1), tenant=migrated_tenant, actor=person)
    client = _operator(signed_in_without_tenant)
    session = client.session
    session["tenant_number"] = migrated_tenant.number
    session.save()

    with CaptureQueriesContext(connection) as captured:
        response = client.get(PAGE, {"organisation": str(migrated_tenant.number)})

    assert response.status_code == 200
    assert "document.archived" in _text(response)
    [statement] = [q["sql"] for q in captured.captured_queries if '"audit_auditevent"' in q["sql"]]
    tables = set(re.findall(r'(?:FROM|JOIN) "([a-z_]+)"', statement))
    assert tables == {"audit_auditevent", "identity_user", "tenancy_tenant"}


def test_the_period_is_inclusive_in_the_display_timezone(
    signed_in_without_tenant: Any, settings: Any
) -> None:
    """Kyiv is two hours ahead of UTC in March: its 1 March begins at 22:00 UTC on 28 February."""
    settings.DISPLAY_TIMEZONE = "Europe/Kyiv"
    _event("synthetic.before", datetime(2026, 2, 28, 21, 59, tzinfo=UTC))
    _event("synthetic.first", datetime(2026, 2, 28, 22, 0, tzinfo=UTC))
    _event("synthetic.last", datetime(2026, 3, 2, 21, 59, 59, tzinfo=UTC))
    _event("synthetic.after", datetime(2026, 3, 2, 22, 0, tzinfo=UTC))
    client = _operator(signed_in_without_tenant)

    def actions(**query: Any) -> list[str]:
        return [row[4] for row in _cells(client.get(PAGE, query))]

    assert actions(since="2026-03-01", until="2026-03-02") == ["synthetic.last", "synthetic.first"]
    assert actions(since="2026-03-01") == ["synthetic.after", "synthetic.last", "synthetic.first"]
    assert actions(until="2026-03-02") == ["synthetic.last", "synthetic.first", "synthetic.before"]


def test_payloads_of_any_shape_are_drawn(signed_in_without_tenant: Any) -> None:
    """A payload the presenter did not expect — not a mapping, a boolean for a number, a value
    whose type changed, a long key, many keys — is drawn, never a failed page."""
    from audit.models import AuditEvent

    for n, (before, after) in enumerate(
        [
            ("a plain string", ["a", "list"]),
            (7, None),
            ({"number": True, "flag": 1}, {"number": True, "flag": True}),
            (None, {"k" * 300: 1}),
            (None, {f"key{i:03d}": i for i in range(30)}),
        ]
    ):
        AuditEvent.objects.create(
            actor=None,
            actor_kind="system",
            action=f"synthetic.shape{n}",
            object_type="thing",
            before=before,
            after=after,
            at=_at(1, 12, n),
        )

    response = _operator(signed_in_without_tenant).get(PAGE)

    assert response.status_code == 200
    rows = {row[4]: row for row in _cells(response)}
    assert "a plain string" in rows["synthetic.shape0"][6]
    assert '["a","list"]' in rows["synthetic.shape0"][6]
    assert "7" in rows["synthetic.shape1"][6]
    assert rows["synthetic.shape2"][5] == "thing"
    assert "flag: 1 → true" in rows["synthetic.shape2"][6]
    assert len(rows["synthetic.shape3"][6]) < 300
    assert "10 more" in rows["synthetic.shape4"][6]
