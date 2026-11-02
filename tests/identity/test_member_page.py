"""Administration › users › a member's page (DL-0505, ST-0077): the membership's state, its groups
with *Remove* and *Add* posting to a route of their own, and the rights table computed from the
membership's groups and the documents' links — never through the person's own block (DL-0398); an
administrator's membership draws one line instead; the page and its route are closed to everyone
but the organisation's administrators.

People, organisations, groups, folders and titles are synthetic examples; every address ends in
`@example.test`.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from django.test import Client

from access.rights import GRID, Right
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
    pytest.mark.usefixtures("in_english"),
]

USERS = "/administration/tenant/users/"
MEMBER = "a.member@example.test"
NOBODY = "00000000-0000-4000-8000-000000000000"
VIEWS = {Right.VIEW_CANONICAL, Right.VIEW_ACCEPTED, Right.VIEW_PENDING}
AUTHOR_ONLY = VIEWS | {Right.EDIT, Right.UPLOAD_ATTACHMENT, Right.REPLACE_ATTACHMENT}
FOLDER_ROW = re.compile(r'<tr class="folder"[^>]*>(.*?)</tr>', re.DOTALL)
CELL = re.compile(r'<td data-right="([a-z_]+)"[^>]*>(.*?)</td>', re.DOTALL)
REMOVE = re.compile(r'name="action"[^>]*value="remove"|value="remove"[^>]*name="action"')
TAGS = re.compile(r"<[^>]+>")


def _page_of(membership: Any) -> str:
    return f"{USERS}{membership.id}/"


def _groups_of(membership: Any) -> str:
    return f"{USERS}{membership.id}/groups/"


def _group(name: str, rights: list[Right], members: list[Any], admin: Any) -> Any:
    """A group holding `rights` with `members` in it, in the current schema (synthetic)."""
    from access.models import AccessGroup

    group = AccessGroup.objects.create(name=name, created_by=admin, actor_kind="user")
    for right in rights:
        group.grant(right, by=admin)
    for membership in members:
        group.add_member(membership, by=admin)
    return group


def _block(body: str, element_id: str) -> str:
    """The `<div>` with `element_id`, to its own closing tag — nested divs counted."""
    start = body.rindex("<div", 0, body.index(f'id="{element_id}"'))
    depth = 0
    for found in re.finditer(r"<div\b|</div>", body[start:]):
        depth += 1 if found.group().startswith("<div") else -1
        if depth == 0:
            return body[start : start + found.end()]
    raise AssertionError(f"#{element_id} is not closed")


def _document_row(body: str, document: Any) -> str:
    found = re.search(rf'<tr data-document="{document.number}"[^>]*>(.*?)</tr>', body, re.DOTALL)
    assert found is not None, f"no row for #{document.number}"
    return found.group(1)


def _ticks(row: str) -> set[Right]:
    cells = CELL.findall(row)
    assert {name for name, _ in cells} == {r.value for r in GRID}, "a cell per right"
    return {Right(name) for name, text in cells if "✓" in text}


def _select_options(body: str) -> list[str]:
    found = re.search(r'<select[^>]*name="group"[^>]*>(.*?)</select>', body, re.DOTALL)
    assert found is not None, "no select of groups"
    return re.findall(r'<option value="([^"]+)"', found.group(1))


def _other_tenants_administrator(make_tenant_schema: Any) -> tuple[Client, Any]:
    """An administrator of another organisation, that organisation chosen in the session."""
    from identity.models import Membership, User

    other = make_tenant_schema("Other Synthetic Org")
    outsider = User.objects.create_user("o.admin@example.test", "test-only-not-a-password")
    membership = Membership.objects.create(
        tenant=other, user=outsider, is_tenant_admin=True, actor_kind="system"
    )
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(outsider)
    session = client.session
    session["tenant_number"] = other.number
    session.save()
    return client, membership


def test_the_page_lists_groups_and_rights_per_folder(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    """Row 2: the address as heading; the state; the member's groups with *Remove*; *Add* of the
    other groups; folders in tree order; a row per active document ticked from `implied()`; the
    unlinked author-only document noted *author*; the archived document absent."""
    from access.models import DocumentGroup
    from documents.models import Folder, next_folder_number

    admin, admin_user, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    _, user, membership = member_of(MEMBER)
    with schema_context(migrated_tenant.number):
        root = Folder.objects.get(number=1)
        procedures = Folder.objects.create(
            number=next_folder_number(), parent=root, name="Procedures", actor_kind="system"
        )
    in_root = make_document(title="Synthetic rules", created_by=admin_user, author_only=False)
    in_sub = make_document(
        title="Synthetic procedure", created_by=admin_user, author_only=False, folder=procedures
    )
    own = make_document(title="Synthetic draft", created_by=user, author_only=True)
    archived = make_document(
        title="Synthetic archive", created_by=admin_user, author_only=False, state="archived"
    )
    with schema_context(migrated_tenant.number):
        editors = _group("Editors", [Right.EDIT], [membership], admin_user)
        readers = _group("Readers", [Right.VIEW_CANONICAL], [membership], admin_user)
        reviewers = _group("Reviewers", [Right.ACCEPT], [], admin_user)
        DocumentGroup.link(in_root, editors, by=admin_user)
        DocumentGroup.link(in_sub, readers, by=admin_user)
        DocumentGroup.link(archived, editors, by=admin_user)

    response = admin.get(_page_of(membership))

    assert response.status_code == 200
    body = response.content.decode()
    assert re.search(rf"<h1>\s*{re.escape(MEMBER)}\s*</h1>", body)
    assert 'data-state="active"' in body

    groups = _block(body, "member-groups")
    assert f'data-group="{editors.id}"' in groups and "Editors" in groups
    assert f'data-group="{readers.id}"' in groups and "Readers" in groups
    assert f'data-group="{reviewers.id}"' not in groups
    assert groups.count(f'action="{_groups_of(membership)}"') >= 3  # two removes and the add
    assert groups.count(f'hx-post="{_groups_of(membership)}"') >= 3
    assert 'hx-target="#member-groups"' in groups and 'hx-swap="outerHTML"' in groups
    assert len(REMOVE.findall(groups)) == 2
    assert 'data-act="add"' in groups
    assert _select_options(groups) == [str(reviewers.id)]

    assert '<table class="grid member-rights">' in body
    assert [r.value for r in GRID] == re.findall(r'<th data-right="([a-z_]+)"', body)
    headings = [TAGS.sub("", text).strip() for text in FOLDER_ROW.findall(body)]
    assert headings == [migrated_tenant.name, "Procedures"]
    rows = [int(n) for n in re.findall(r'<tr data-document="(\d+)"', body)]
    assert set(rows) == {in_root.number, in_sub.number, own.number}
    assert archived.number not in rows
    # Tree order: the root's documents before the subfolder's.
    assert rows.index(in_sub.number) > max(rows.index(in_root.number), rows.index(own.number))
    assert body.index("Procedures</") > body.index(f'data-document="{in_root.number}"')

    row = _document_row(body, in_root)
    assert f"#{in_root.number}" in row
    assert f'<a href="/document/{in_root.number}/">Synthetic rules</a>' in row
    assert _ticks(row) == VIEWS | {Right.EDIT}
    assert '<span class="note">(author)</span>' not in row
    assert _ticks(_document_row(body, in_sub)) == {Right.VIEW_CANONICAL}
    own_row = _document_row(body, own)
    assert '<span class="note">(author)</span>' in own_row
    assert _ticks(own_row) == AUTHOR_ONLY


def test_add_and_remove_post_to_the_members_route(migrated_tenant: Any, member_of: Any) -> None:
    """Rows 3 and 4: an *add* under `HX-Request` answers the fragment alone and writes the row,
    audited as `add_member` audits; a *remove* without it answers the whole page, the row gone."""
    from access.models import AccessChange, GroupMember

    admin, admin_user, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    _, _, membership = member_of(MEMBER)
    with schema_context(migrated_tenant.number):
        editors = _group("Editors", [Right.EDIT], [membership], admin_user)
        reviewers = _group("Reviewers", [Right.ACCEPT], [], admin_user)
        before = AccessChange.objects.count()

    added = admin.post(
        _groups_of(membership),
        {"group": str(reviewers.id), "action": "add"},
        headers={"HX-Request": "true"},
    )

    assert added.status_code == 200
    fragment = added.content.decode()
    assert "<html" not in fragment
    assert '<div id="member-groups"' in fragment
    assert f'data-group="{reviewers.id}"' in fragment and "Reviewers" in fragment
    assert f'data-group="{editors.id}"' in fragment
    with schema_context(migrated_tenant.number):
        assert GroupMember.objects.filter(group=reviewers, membership=membership).exists()
        change = AccessChange.objects.order_by("at").last()
        assert AccessChange.objects.count() == before + 1
        assert (change.kind, change.action) == ("member", "added")
        assert (change.group_id, change.membership_id, change.by_id) == (
            reviewers.id,
            membership.id,
            admin_user.id,
        )

    removed = admin.post(_groups_of(membership), {"group": str(editors.id), "action": "remove"})

    assert removed.status_code == 200
    whole = removed.content.decode()
    assert "<html" in whole
    assert 'id="member-groups"' in whole
    assert f'data-group="{editors.id}"' not in whole
    assert f'data-group="{reviewers.id}"' in whole
    with schema_context(migrated_tenant.number):
        assert not GroupMember.objects.filter(group=editors, membership=membership).exists()
        change = AccessChange.objects.order_by("at").last()
        assert AccessChange.objects.count() == before + 2
        assert (change.kind, change.action, change.group_id) == ("member", "removed", editors.id)


def test_a_blocked_members_page(migrated_tenant: Any, member_of: Any, make_document: Any) -> None:
    """Rows 5 and 6: the state line says blocked; *Remove* offered and no *Add*; the table stands
    under *blocked: none of this applies now*; an *add* is refused as `group_members` refuses it."""
    from access.models import DocumentGroup, GroupMember
    from identity.models import MembershipState

    admin, admin_user, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    _, _, membership = member_of(MEMBER)
    document = make_document(title="Synthetic rules", created_by=admin_user, author_only=False)
    with schema_context(migrated_tenant.number):
        editors = _group("Editors", [Right.EDIT], [membership], admin_user)
        reviewers = _group("Reviewers", [Right.ACCEPT], [], admin_user)
        DocumentGroup.link(document, editors, by=admin_user)
    membership.change("state", MembershipState.BLOCKED, by=admin_user)

    response = admin.get(_page_of(membership))

    assert response.status_code == 200
    body = response.content.decode()
    assert 'data-state="blocked"' in body
    groups = _block(body, "member-groups")
    assert f'data-group="{editors.id}"' in groups
    assert len(REMOVE.findall(groups)) == 1
    assert 'data-act="add"' not in groups
    assert "blocked: none of this applies now" in body
    assert body.index("blocked: none of this applies now") < body.index(
        '<table class="grid member-rights">'
    )
    assert _ticks(_document_row(body, document)) == VIEWS | {Right.EDIT}

    for headers in ({}, {"HX-Request": "true"}):
        refused = admin.post(
            _groups_of(membership), {"group": str(reviewers.id), "action": "add"}, headers=headers
        )
        assert refused.status_code == 404
        assert 'class="content empty"' in refused.content.decode()
    with schema_context(migrated_tenant.number):
        assert not GroupMember.objects.filter(group=reviewers).exists()

    # A blocked membership is still taken out of a group.
    removed = admin.post(_groups_of(membership), {"group": str(editors.id), "action": "remove"})
    assert removed.status_code == 200
    with schema_context(migrated_tenant.number):
        assert not GroupMember.objects.filter(group=editors, membership=membership).exists()


def test_a_persons_own_block_shows_through_nothing(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    """Row 7: a self-blocked person's active membership reads *active*, and the groups' rights are
    ticked — the table never reads the person's own block (DL-0398)."""
    from access.models import DocumentGroup
    from identity.models import User

    admin, admin_user, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    _, user, membership = member_of(MEMBER)
    document = make_document(title="Synthetic rules", created_by=admin_user, author_only=False)
    with schema_context(migrated_tenant.number):
        editors = _group("Editors", [Right.EDIT], [membership], admin_user)
        DocumentGroup.link(document, editors, by=admin_user)
        # A group left to join, so the *Add* form has something to offer.
        _group("Readers", [Right.VIEW_CANONICAL], [], admin_user)
    User.objects.filter(pk=user.pk).update(self_blocked=True)

    response = admin.get(_page_of(membership))

    assert response.status_code == 200
    body = response.content.decode()
    assert 'data-state="active"' in body
    assert 'data-state="blocked"' not in body
    assert "blocked: none of this applies now" not in body
    assert 'data-act="add"' in body
    assert _ticks(_document_row(body, document)) == VIEWS | {Right.EDIT}


def test_an_administrators_page_is_one_line(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    """Row 8: a tenant administrator's own membership draws *Administrator: reads every document
    in the organisation* and no rights table; the groups block is drawn."""
    from access.models import DocumentGroup

    admin, admin_user, admin_membership = member_of("t.admin@example.test", is_tenant_admin=True)
    document = make_document(title="Synthetic rules", created_by=admin_user, author_only=False)
    with schema_context(migrated_tenant.number):
        editors = _group("Editors", [Right.EDIT], [admin_membership], admin_user)
        DocumentGroup.link(document, editors, by=admin_user)

    response = admin.get(_page_of(admin_membership))

    assert response.status_code == 200
    body = response.content.decode()
    assert "data-administrator" in body
    assert "Administrator: reads every document in the organisation" in body
    assert "member-rights" not in body
    assert "data-document=" not in body
    assert "data-right=" not in body
    groups = _block(body, "member-groups")
    assert f'data-group="{editors.id}"' in groups
    assert len(REMOVE.findall(groups)) == 1


def test_closed_to_members_and_other_tenants(
    migrated_tenant: Any, member_of: Any, make_tenant_schema: Any
) -> None:
    """Rows 6a and 9: an ordinary member, another organisation's administrator and an unknown
    uuid each meet the not-found answer, on the page and on the route; a GET to the route and a
    POST to the page likewise; no row is written by any of them."""
    from access.models import GroupMember

    admin, admin_user, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    member, _, membership = member_of(MEMBER)
    with schema_context(migrated_tenant.number):
        reviewers = _group("Reviewers", [Right.ACCEPT], [], admin_user)
    outsider, foreign_membership = _other_tenants_administrator(make_tenant_schema)
    body = {"group": str(reviewers.id), "action": "add"}
    # The control: the organisation's administrator reaches the page, so the refusals below are
    # the gate's and not an absent route's.
    assert admin.get(_page_of(membership)).status_code == 200

    refused: list[tuple[str, int]] = []
    for who, client in (("member", member), ("outsider", outsider)):
        refused.append((f"{who} page", client.get(_page_of(membership)).status_code))
        refused.append((f"{who} route", client.post(_groups_of(membership), body).status_code))
    refused.append(("foreign page", admin.get(_page_of(foreign_membership)).status_code))
    refused.append(("foreign route", admin.post(_groups_of(foreign_membership), body).status_code))
    refused.append(("unknown page", admin.get(f"{USERS}{NOBODY}/").status_code))
    refused.append(("unknown route", admin.post(f"{USERS}{NOBODY}/groups/", body).status_code))
    refused.append(("GET the route", admin.get(_groups_of(membership)).status_code))
    refused.append(("POST the page", admin.post(_page_of(membership), body).status_code))

    assert refused == [(what, 404) for what, _ in refused]
    answer = member.get(_page_of(membership))
    assert 'class="content empty"' in answer.content.decode()
    with schema_context(migrated_tenant.number):
        assert not GroupMember.objects.filter(group=reviewers).exists()
    # The route's own control: the same body posted by the administrator is answered and acted on.
    assert admin.post(_groups_of(membership), body).status_code == 200
    with schema_context(migrated_tenant.number):
        assert GroupMember.objects.filter(group=reviewers, membership=membership).exists()


def test_a_blocked_administrators_page_says_none_of_it_applies(
    migrated_tenant: Any, member_of: Any
) -> None:
    """An administrator's membership, blocked, reads nothing: the one line stands under the
    blocked note as a member's table does."""
    admin, admin_user, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    _, _, other = member_of("o.admin@example.test", is_tenant_admin=True)
    other.change("state", "blocked", by=admin_user)

    body = admin.get(_page_of(other)).content.decode()

    assert 'data-state="blocked"' in body
    assert body.index("blocked: none of this applies now") < body.index("data-administrator")


def test_a_platform_administrator_sees_the_frame(migrated_tenant: Any, member_of: Any) -> None:
    """The page stands in Administration's frame as every section does: a platform
    administrator acting in the organisation keeps the platform's pane."""
    platform, _, _ = member_of("p.admin@example.test", is_tenant_admin=True, is_platform_admin=True)
    _, _, membership = member_of(MEMBER)

    body = platform.get(_page_of(membership)).content.decode()

    assert 'href="/administration/platform/hosts/"' in body


def test_a_link_granting_nothing_draws_no_row(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    """A group linked to a document but holding no right that reaches it — a new group's
    attachment rights without *edit* — gives the member nothing there: no row is drawn."""
    from access.models import DocumentGroup

    admin, admin_user, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    _, _, membership = member_of(MEMBER)
    document = make_document(title="Synthetic rules", created_by=admin_user, author_only=False)
    with schema_context(migrated_tenant.number):
        parts = _group("Parts", [Right.UPLOAD_ATTACHMENT], [membership], admin_user)
        DocumentGroup.link(document, parts, by=admin_user)

    body = admin.get(_page_of(membership)).content.decode()

    assert f'data-document="{document.number}"' not in body
