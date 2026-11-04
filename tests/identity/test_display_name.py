"""A person's own display name (DL-0523, DL-0537): set on their account page, unique within each
organisation they belong to — compared without case and with runs of spaces as one — refused
without naming the organisation, and kept unique when a person joins one, by invitation or by
`create_member`. People and organisations are synthetic examples."""

from __future__ import annotations

import re
import threading
import time
from io import StringIO
from typing import Any

import pytest
from django.core.management import CommandError, call_command

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db,
    pytest.mark.usefixtures("in_english"),
]

ACCOUNT = "/account/"
NAME = "Синтетична Особа"
SAME = "синтетична  особа"


def _member(tenant: Any, email: str, name: str = "") -> Any:
    from identity.models import Membership, User

    user = User.objects.create_user(email, "test-only-not-a-password", display_name=name)
    Membership.objects.create(tenant=tenant, user=user, actor_kind="system")
    return user


def _refused(body: str) -> bool:
    """The name field's own error, which names no organisation (DL-0537)."""
    found = re.search(r'id="display-name-error"[^>]*>(.*?)</p>', body, re.DOTALL)
    return (
        found is not None
        and "Another member already uses this name." in found.group(1)
        and "Org" not in found.group(1)
    )


def _elsewhere(name: str) -> Any:
    from tenancy.models import Tenant

    return Tenant.objects.create(name=name, actor_kind="system")


def test_a_person_names_themselves(member_of: Any) -> None:
    from identity.models import User
    from identity.naming import person

    client, user, _ = member_of("the.member@example.test")

    response = client.post(ACCOUNT, {"display_name": f"  {NAME} "})

    assert response.status_code == 303
    user = User.objects.get(pk=user.pk)
    assert user.display_name == NAME
    assert person(user) == NAME
    assert NAME in client.get(ACCOUNT).content.decode()


def test_a_name_taken_in_an_organisation_is_refused(member_of: Any, migrated_tenant: Any) -> None:
    from identity.models import User

    client, user, _ = member_of("the.member@example.test")
    _member(migrated_tenant, "another.member@example.test", NAME)

    response = client.post(ACCOUNT, {"display_name": SAME})

    assert response.status_code == 400
    body = response.content.decode()
    assert 'name="display_name"' in body and 'aria-invalid="true"' in body
    assert _refused(body)
    assert User.objects.get(pk=user.pk).display_name == ""


def test_a_blocked_members_name_is_taken(member_of: Any, migrated_tenant: Any) -> None:
    from identity.models import Membership, MembershipState

    client, _, _ = member_of("the.member@example.test")
    other = _member(migrated_tenant, "another.member@example.test", NAME)
    Membership.objects.filter(user=other).update(state=MembershipState.BLOCKED)

    response = client.post(ACCOUNT, {"display_name": NAME})

    assert response.status_code == 400
    assert _refused(response.content.decode())


def test_a_name_elsewhere_is_free(member_of: Any) -> None:
    from identity.models import User

    client, user, _ = member_of("the.member@example.test")
    _member(_elsewhere("Another Org"), "another.member@example.test", NAME)

    assert client.post(ACCOUNT, {"display_name": NAME}).status_code == 303
    assert User.objects.get(pk=user.pk).display_name == NAME


def test_a_name_taken_in_another_of_ones_organisations_is_refused(member_of: Any) -> None:
    from identity.models import Membership

    client, user, _ = member_of("the.member@example.test")
    second = _elsewhere("Another Org")
    Membership.objects.create(tenant=second, user=user, actor_kind="system")
    _member(second, "another.member@example.test", NAME)

    response = client.post(ACCOUNT, {"display_name": NAME})

    assert response.status_code == 400
    assert _refused(response.content.decode())


def test_keeping_ones_own_name_is_not_a_clash(member_of: Any) -> None:
    client, _, _ = member_of("the.member@example.test")

    assert client.post(ACCOUNT, {"display_name": NAME}).status_code == 303
    assert client.post(ACCOUNT, {"display_name": SAME}).status_code == 303


@pytest.mark.parametrize("name", ["", "   ", "x" * 201])
def test_an_empty_or_long_name_is_refused(member_of: Any, name: str) -> None:
    client, _, _ = member_of("the.member@example.test")

    response = client.post(ACCOUNT, {"display_name": name})

    assert response.status_code == 400
    expected = (
        "at most 200 characters" if name.strip() else "Write the name your colleagues will see."
    )
    assert expected in response.content.decode()


def test_a_change_of_name_is_audited_without_the_name(member_of: Any) -> None:
    from audit.models import AuditEvent

    client, user, _ = member_of("the.member@example.test")

    client.post(ACCOUNT, {"display_name": NAME})

    event = AuditEvent.objects.filter(action="user.renamed").get()
    assert str(user.pk) in str(event.after)
    assert NAME not in str(event.before) + str(event.after)


def test_create_member_checks_it(migrated_tenant: Any) -> None:
    from identity.models import User

    _member(migrated_tenant, "another.member@example.test", NAME)

    with pytest.raises(CommandError, match=migrated_tenant.name):
        call_command(
            "create_member",
            f"--tenant={migrated_tenant.number}",
            "--email=the.member@example.test",
            f"--name={SAME}",
            stdout=StringIO(),
        )
    assert not User.objects.filter(email="the.member@example.test").exists()


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_two_saves_of_one_name(migrated_tenant: Any) -> None:
    """The first save holds the name's lock until it commits; the second waits, then sees it."""
    from django.db import connection, transaction

    from identity import names
    from identity.models import User

    first = _member(migrated_tenant, "the.first@example.test")
    second = _member(migrated_tenant, "the.second@example.test")
    outcome: list[Any] = []
    backend: list[int] = []
    entered = threading.Event()

    def save_second() -> None:
        try:
            backend.append(_backend())
            entered.set()
            outcome.append(names.rename(User.objects.get(pk=second.pk), NAME))
        finally:
            connection.close()

    with transaction.atomic():
        assert names.rename(first, NAME) is None
        other = threading.Thread(target=save_second)
        other.start()
        assert entered.wait(timeout=10)
        _wait_for_a_lock_wait(backend[0])
    other.join(timeout=30)

    assert outcome and outcome[0] is not None, outcome
    assert User.objects.get(pk=first.pk).display_name == NAME
    assert User.objects.get(pk=second.pk).display_name == ""


def test_create_member_refuses_a_join_whose_name_is_taken(migrated_tenant: Any) -> None:
    from identity.models import Membership

    _member(migrated_tenant, "another.member@example.test", NAME)
    joining = _member(_elsewhere("Another Org"), "the.member@example.test", SAME)

    with pytest.raises(CommandError, match="display name"):
        call_command(
            "create_member",
            f"--tenant={migrated_tenant.number}",
            "--email=the.member@example.test",
            stdout=StringIO(),
        )
    assert not Membership.objects.filter(tenant=migrated_tenant, user=joining).exists()


def test_an_invitation_refuses_a_join_whose_name_is_taken(
    migrated_tenant: Any, member_of: Any, sending_address: Any
) -> None:
    from identity.models import Invitation, Membership

    admin, _, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    sending_address(migrated_tenant.number)
    _member(migrated_tenant, "another.member@example.test", NAME)
    joining = _member(_elsewhere("Another Org"), "the.member@example.test", SAME)

    response = admin.post("/administration/tenant/users/invite/", {"email": joining.email})

    body = response.content.decode()
    assert "display name is already used by a member of this organisation" in body
    assert NAME not in body and SAME not in body
    assert not Membership.objects.filter(tenant=migrated_tenant, user=joining).exists()
    assert not Invitation.objects.filter(email=joining.email).exists()


@pytest.mark.parametrize(
    "lookalike",
    [
        "Синтетична Особа",  # the same letters, typed again
        "Синтетична Особа".replace("й", "й"),
        "Синтетична Особа",
        "Синтетична Особа​",
        "Синтетична​ Особа",
    ],
)
def test_a_name_drawn_alike_is_one_name(
    member_of: Any, migrated_tenant: Any, lookalike: str
) -> None:
    """Composed and decomposed letters, a non-breaking space and a zero-width character draw one
    name: refused when the other is taken."""
    client, _, _ = member_of("the.member@example.test")
    _member(migrated_tenant, "another.member@example.test", "Синтетична Особа")

    assert _refused(client.post(ACCOUNT, {"display_name": lookalike}).content.decode())


def test_a_name_of_decomposed_letters_matches_its_composed_twin(
    member_of: Any, migrated_tenant: Any
) -> None:
    client, _, _ = member_of("the.member@example.test")
    _member(migrated_tenant, "another.member@example.test", "Синтетичний Йосип")

    decomposed = "Синтетичний Йосип".replace("Й", "Й")
    assert _refused(client.post(ACCOUNT, {"display_name": decomposed}).content.decode())


@pytest.mark.parametrize("name", ["​​", "Ім’я\x00", "Ім’я\tдругий"])
def test_a_name_of_invisible_or_control_characters_is_refused(member_of: Any, name: str) -> None:
    from identity.models import User

    client, user, _ = member_of("the.member@example.test")

    response = client.post(ACCOUNT, {"display_name": name})

    assert response.status_code == 400
    assert 'id="display-name-error"' in response.content.decode()
    assert User.objects.get(pk=user.pk).display_name == ""


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_a_rename_waits_for_a_join_in_progress(migrated_tenant: Any) -> None:
    """A join holds the person's row until it commits; a rename taking that name waits for it,
    then sees the organisation it joined."""
    from django.db import connection, transaction

    from identity import names
    from identity.models import Membership, User

    _member(migrated_tenant, "another.member@example.test", NAME)
    joining = _member(_elsewhere("Another Org"), "the.member@example.test")
    outcome: list[Any] = []
    entered = threading.Event()

    backend: list[int] = []

    def rename() -> None:
        try:
            backend.append(_backend())
            entered.set()
            outcome.append(names.rename(User.objects.get(pk=joining.pk), NAME))
        finally:
            connection.close()

    with transaction.atomic():
        User.objects.select_for_update().get(pk=joining.pk)
        Membership.objects.create(tenant=migrated_tenant, user=joining, actor_kind="system")
        other = threading.Thread(target=rename)
        other.start()
        assert entered.wait(timeout=10)
        _wait_for_a_lock_wait(backend[0])
    other.join(timeout=30)

    assert outcome and outcome[0] is not None, outcome
    assert User.objects.get(pk=joining.pk).display_name == ""


def _backend() -> int:
    """The process id of this thread's own database connection."""
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_backend_pid()")
        return int(cursor.fetchone()[0])


def _wait_for_a_lock_wait(backend: int) -> None:
    """Until the second writer's own connection waits on a lock — it has reached the lock, and no
    other session's wait on the shared test server stands in for it."""
    from django.db import connection

    for _ in range(200):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pg_locks WHERE pid = %s AND NOT granted", [backend]
            )
            if cursor.fetchone()[0]:
                return
        time.sleep(0.05)
    pytest.fail("the second writer never waited on a lock")
