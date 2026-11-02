"""Administration › users (ST-0003, ASR-17): a person invited at a new address and one already
registered elsewhere are drawn as the same row, by the address alone (DL-0403) — on the users page
and in a group's members; the page and its invitation form are closed to everyone but the
organisation's administrators.

People, organisations, groups and texts are synthetic examples; every address ends in
`@example.test`.
"""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
    pytest.mark.usefixtures("in_english"),
]

USERS = "/administration/tenant/users/"
INVITE = "/administration/tenant/users/invite/"
# Of one length, as in `test_invitation.py`.
NEW = "new.person@example.test"
KNOWN = "old.person@example.test"
ROW = re.compile(r'<tr data-row="member"[^>]*>.*?</tr>', re.DOTALL)


def test_invited_and_added_rows_alike(
    migrated_tenant: Any, member_of: Any, person: Any, sending_address: Any, masked_text: Any
) -> None:
    from access.models import AccessGroup
    from identity.models import Membership

    admin, admin_user, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    sending_address(migrated_tenant.number)
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(
            name="Synthetic readers", created_by=admin_user, actor_kind="user"
        )
    # A name set elsewhere, and an account a year old, would each say the address existed.
    known = person(KNOWN, "Another Synthetic Org", display_name="Synthetic Elsewhere")
    type(known).objects.filter(pk=known.pk).update(
        created_at=known.created_at - timedelta(days=365)
    )
    for email in (NEW, KNOWN):
        assert admin.post(INVITE, {"email": email, "groups": [str(group.id)]}).status_code == 200
    # `test_new_and_existing_addresses_are_indistinguishable` holds the two within a second;
    # here they are put in one minute, so the cell drawn to the minute cannot differ by a
    # minute's boundary falling between the two invitations.
    invited = Membership.objects.filter(tenant=migrated_tenant, user__email__in=(NEW, KNOWN))
    assert invited.count() == 2
    invited.update(granted_at=invited.order_by("granted_at").first().granted_at)

    response = admin.get(USERS)

    assert response.status_code == 200
    rows = ROW.findall(response.content.decode())
    [new_row] = [row for row in rows if NEW in row]
    [known_row] = [row for row in rows if KNOWN in row]
    # A row's acts name its membership by its random id.
    ids = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    assert re.sub(ids, "ID", masked_text(new_row, NEW)) == re.sub(
        ids, "ID", masked_text(known_row, KNOWN)
    )
    assert "Synthetic Elsewhere" not in response.content.decode()
    members = admin.get(f"/administration/tenant/groups/{group.id}/members/").content.decode()
    assert NEW in members and KNOWN in members
    assert "Synthetic Elsewhere" not in members


def test_closed_to_members(
    migrated_tenant: Any, member_of: Any, signed_in_without_tenant: Any
) -> None:
    from identity.models import Invitation

    member, _, _ = member_of("a.member@example.test")
    outsider = signed_in_without_tenant("no.member@example.test")

    for client in (member, outsider):
        for page in (USERS, INVITE):
            assert client.get(page).status_code == 404, page
            posted = client.post(page, {"email": "someone.new@example.test"})
            assert posted.status_code == 404, page
    assert not Invitation.objects.exists()


def test_the_address_opens_the_members_page(migrated_tenant: Any, member_of: Any) -> None:
    """Every row's address is a link to `/administration/tenant/users/<id>/`, and the link
    opens the page. `test_invited_and_added_rows_alike` keeps passing: its uuid mask strips the
    href's id as it strips the acts'."""
    admin, _, admin_membership = member_of("t.admin@example.test", is_tenant_admin=True)
    _, _, membership = member_of("a.member@example.test")

    response = admin.get("/administration/tenant/users/")

    assert response.status_code == 200
    body = response.content.decode()
    for row, email in (
        (membership, "a.member@example.test"),
        (admin_membership, "t.admin@example.test"),
    ):
        href = f"/administration/tenant/users/{row.id}/"
        assert f'<a href="{href}">{email}</a>' in body
        assert admin.get(href).status_code == 200
