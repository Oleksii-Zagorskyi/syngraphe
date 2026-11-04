"""Administration › Access history (ST-0006; DL-0434, DL-0457, DL-0460, DL-0461): a document and
a day, or one of its editions, answered as the groups linked then with their rights and members
and the changes that led there; *any document*, the changes alone; every person by address.

People, groups, documents and their histories are synthetic examples; addresses end in
`@example.test`."""

from __future__ import annotations

import html
import importlib.util
import re
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from django.utils import timezone

from tenancy.schemas import schema_context

_spec = importlib.util.spec_from_file_location(
    "access_history_helpers", Path(__file__).resolve().parent / "test_access_history.py"
)
assert _spec is not None and _spec.loader is not None
_history = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _history
_spec.loader.exec_module(_history)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

PAGE = "/administration/tenant/access-history/"
_at, _end = _history._at, _history._end


@pytest.fixture(autouse=True)
def in_english(settings: Any) -> None:
    settings.LANGUAGE_CODE = "en"
    settings.DISPLAY_TIMEZONE = "UTC"


def _tokenless(body: bytes) -> bytes:
    return re.sub(rb'name="csrfmiddlewaretoken" value="[^"]*"', b"", body)


def _text(response: Any) -> str:
    body = response.content.decode()
    body = re.sub(r"<[^>]+>", " ", body)
    return re.sub(r"\s+", " ", html.unescape(body))


def _story(migrated_tenant: Any, member_of: Any, make_document: Any) -> dict[str, Any]:
    """*Readers* linked to the document on day 1 with *view canonical*, three members — one of
    them blocked on day 2 — and *Editors* linked on day 3 with *edit*, one member named."""
    from identity.models import User

    admin_client, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    _, first, first_membership = member_of("first.reader@example.test")
    _, second, second_membership = member_of("second.reader@example.test")
    _, named, named_membership = member_of("named.editor@example.test")
    User.objects.filter(pk=named.pk).update(display_name="Synthetic Person")
    with schema_context(migrated_tenant.number):
        document = _history._dated(make_document(created_by=admin), _history._at(1, 0))
        readers = _history._group("Readers", admin)
        editors = _history._group("Editors", admin)
        _history._right(readers, "view_canonical", admin, _at(1, 9))
        _history._link(readers, document, admin, _at(1, 10))
        _history._member(readers, first_membership, admin, _at(1, 11))
        _history._member(readers, second_membership, admin, _at(1, 11, 30))
        _history._state(second_membership, "active", "blocked", admin, _at(2, 9))
        _history._right(editors, "edit", None, _at(3, 9))
        _history._link(editors, document, admin, _at(3, 10))
        _history._member(editors, named_membership, admin, _at(3, 11))
        _history._edition(document, admin, _at(3, 12))
    return {
        "client": admin_client,
        "admin": admin,
        "document": document,
        "readers": readers,
        "editors": editors,
    }


def test_a_document_on_a_day(migrated_tenant: Any, member_of: Any, make_document: Any) -> None:
    story = _story(migrated_tenant, member_of, make_document)
    number = story["document"].number

    page = _text(story["client"].get(PAGE, {"document": number, "on": "2026-03-03"}))

    assert f"#{number} on 3 March 2026 — readable by 2 groups, 2 people" in page
    assert "Readers linked 1 March 2026 by an.admin@example.test" in page
    assert "view canonical (granted 1 March 2026 by an.admin@example.test)" in page
    assert "Editors linked 3 March 2026 by an.admin@example.test" in page
    assert "edit (granted 3 March 2026 by system)" in page
    assert "first.reader@example.test added 1 March 2026 by an.admin@example.test" in page
    assert "second.reader@example.test blocked added 1 March 2026" in page
    changes = page[page.index("When Who Change") :]
    order = [
        "Editors linked to #",
        "Editors granted edit",
        "second.reader@example.test's membership blocked",
        "Readers linked to #",
        "Readers granted view canonical",
    ]
    assert [changes.index(c) for c in order] == sorted(changes.index(c) for c in order)


def test_a_document_at_an_edition(migrated_tenant: Any, member_of: Any, make_document: Any) -> None:
    story = _story(migrated_tenant, member_of, make_document)
    number = story["document"].number

    with schema_context(migrated_tenant.number):
        # After the approval, the same day: the edition's answer stands before it.
        _history._link(story["editors"], story["document"], story["admin"], _at(3, 13), "removed")

    response = story["client"].get(PAGE, {"document": number, "edition": "1.0"})
    page = _text(response)
    day = _text(story["client"].get(PAGE, {"document": number, "on": "2026-03-03"}))

    assert f"#{number} at 1.0, approved 3 March 2026 — readable by 2 groups, 2 people" in page
    assert "No canonical edition existed then" not in page
    assert f"#{number} on 3 March 2026 — readable by 1 group, 1 person" in day
    # The editions offered are the document's own, as a choice.
    assert '<option value="1.0" selected>1.0</option>' in response.content.decode()


def test_the_state_lines(migrated_tenant: Any, member_of: Any, make_document: Any) -> None:
    story = _story(migrated_tenant, member_of, make_document)
    client, document, admin = story["client"], story["document"], story["admin"]
    number = document.number
    with schema_context(migrated_tenant.number):
        _history._organisation(migrated_tenant, "active", "blocked", admin, _at(4, 9))
        _history._organisation(migrated_tenant, "blocked", "active", admin, _at(5, 9))

    before = _text(client.get(PAGE, {"document": number, "on": "2026-02-28"}))
    assert f"#{number} did not exist then." in before
    assert "readable by" not in before

    early = _text(client.get(PAGE, {"document": number, "on": "2026-03-02"}))
    assert "No canonical edition existed then: view canonical reached nothing." in early
    assert "The organisation was blocked then" not in early

    blocked = _text(client.get(PAGE, {"document": number, "on": "2026-03-04"}))
    assert blocked.count("The organisation was blocked then: none of its members could read.") == 1
    assert "readable by 0 groups, 0 people" in blocked

    from audit.models import AuditEvent

    AuditEvent.objects.create(
        tenant=migrated_tenant,
        actor=admin,
        actor_kind="user",
        action="document.archived",
        object_type="document",
        object_id=document.pk,
        after={"number": number},
        at=_at(6, 9),
    )
    archived = _text(client.get(PAGE, {"document": number, "on": "2026-03-06"}))
    assert archived.count(f"#{number} was archived then: no group could read it.") == 1


def test_any_document(migrated_tenant: Any, member_of: Any, make_document: Any) -> None:
    client, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    _, _, membership = member_of("a.reader@example.test")
    with schema_context(migrated_tenant.number):
        group = _history._group("Readers", admin)
        for n in range(125):
            _history._member(group, membership, admin, _at(1, 0, 0, 0, n))
            _history._member(group, membership, admin, _at(1, 0, 1, 0, n), "removed")

    page = _text(client.get(PAGE, {"document": "any", "on": "2026-03-01"}))

    assert (
        page.count("a.reader@example.test added to Readers")
        + page.count("a.reader@example.test removed from Readers")
        == 200
    )
    assert "The newest 200 changes up to then." in page
    assert "Members that day" not in page


def test_people_by_address(migrated_tenant: Any, member_of: Any, make_document: Any) -> None:
    from identity.models import User

    story = _story(migrated_tenant, member_of, make_document)
    User.objects.filter(pk=story["admin"].pk).update(display_name="Synthetic Admin")

    body = story["client"].get(PAGE, {"document": story["document"].number, "on": "2026-03-03"})
    page = _text(body)

    assert "named.editor@example.test" in page
    assert "linked 1 March 2026 by an.admin@example.test" in page
    # The reader's own name is the menu icon's label alone (DL-0541); the page names nobody by it.
    assert "Synthetic Person" not in page and "Synthetic Admin" not in page
    assert 'aria-label="Synthetic Admin"' in body.content.decode()


def test_refusals(migrated_tenant: Any, member_of: Any, make_document: Any) -> None:
    story = _story(migrated_tenant, member_of, make_document)
    client, number = story["client"], story["document"].number
    with schema_context(migrated_tenant.number):
        other = make_document(created_by=story["admin"], title="Synthetic other document")
    tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()

    for asked in (
        {"document": number, "on": tomorrow},
        {"document": "99999", "on": "2026-03-03"},
        {"document": other.number, "edition": "1.0"},
        {"document": number, "edition": "1.1"},
        {"document": "any", "edition": "1.0"},
    ):
        response = client.get(PAGE, asked)
        assert response.status_code == 400, asked
        page = _text(response)
        assert "readable by" not in page and "When Who Change" not in page, asked


def test_the_form_alone_without_a_question(migrated_tenant: Any, member_of: Any) -> None:
    client, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)

    response = client.get(PAGE)

    assert response.status_code == 200
    body = response.content.decode()
    assert 'name="document"' in body and 'name="on"' in body
    page = _text(response)
    assert "readable by" not in page and "When Who Change" not in page


def test_who_reaches_the_page(
    migrated_tenant: Any, member_of: Any, signed_in_without_tenant: Any
) -> None:
    member, _, _ = member_of("a.member@example.test")
    answer = member.get(PAGE)
    assert answer.status_code == 404
    assert _tokenless(answer.content) == _tokenless(member.get("/no-such-address/").content)

    chosen = signed_in_without_tenant("p.admin@example.test", is_platform_admin=True)
    session = chosen.session
    session["tenant_number"] = migrated_tenant.number
    session.save()
    assert chosen.get(PAGE).status_code == 200

    admin, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    assert admin.post(PAGE).status_code == 404


def test_today_is_the_display_timezones(
    migrated_tenant: Any, member_of: Any, make_document: Any, settings: Any
) -> None:
    """Fourteen hours east of UTC, the administrator's today is often the server's tomorrow."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    settings.DISPLAY_TIMEZONE = "Pacific/Kiritimati"
    story = _story(migrated_tenant, member_of, make_document)
    today = datetime.now(ZoneInfo("Pacific/Kiritimati")).date()

    asked = story["client"].get(PAGE, {"document": story["document"].number, "on": str(today)})
    form = story["client"].get(PAGE)

    assert asked.status_code == 200
    assert f'name="on" id="id_on" value="{today.isoformat()}"' in form.content.decode()


def test_a_refused_edition_keeps_its_field(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    story = _story(migrated_tenant, member_of, make_document)

    refused = story["client"].get(PAGE, {"document": story["document"].number, "edition": "2.0"})

    assert refused.status_code == 400
    assert 'name="edition"' in refused.content.decode()
