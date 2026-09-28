"""Creating an organisation with its first administrator; a failed migration leaves it
unreachable until `migrate_schemas` completes it (ST-0001, ADR-0017, DL-0280, DL-0290)."""

from __future__ import annotations

from typing import Any

import pytest
from django.core.management import call_command
from django.db import connection
from django.test import Client

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

NEW = "/administration/platform/tenants/new/"
TENANTS = "/administration/platform/tenants/"


def registered(email: str) -> Any:
    from identity.models import User

    return User.objects.create_user(email, "Tr4vel-Plan-Ok")


def test_create_tenant_with_first_administrator(
    platform_admin: Any, make_tenant: Any, drop_tenant_schemas: None
) -> None:
    from audit.models import AuditEvent
    from identity.models import Membership
    from tenancy.models import Tenant, TenantStateHistory
    from tenancy.schemas import schema_exists

    earlier = make_tenant("Example Org")
    client, _ = platform_admin()
    first = registered("first.admin@example.test")

    response = client.post(
        NEW, {"name": "Example Branch", "first_administrator": "First.Admin@example.test"}
    )

    tenant = Tenant.objects.get(name="Example Branch")
    assert response.status_code == 302 and response["Location"] == TENANTS
    # The next number from the platform's sequence, which every organisation takes its own from.
    assert tenant.number == earlier.number + 1
    assert schema_exists(tenant.number)
    with connection_to(tenant.number) as cursor:
        cursor.execute("SELECT to_regclass('access_accessgroup') IS NOT NULL")
        assert cursor.fetchone()[0], "a tenant app's table exists in the new schema"
    assert tenant.state == "active"
    step = TenantStateHistory.objects.get(tenant=tenant)
    assert (step.before, step.after, step.by) == ("migrating", "active", None)
    membership = Membership.objects.get(tenant=tenant)
    assert membership.user == first and membership.is_tenant_admin and membership.state == "active"
    assert AuditEvent.objects.filter(action="tenant.created", object_id=tenant.id).count() == 1


def test_tenant_needs_an_administrator(platform_admin: Any) -> None:
    from tenancy.models import Tenant

    client, _ = platform_admin()

    missing = client.post(NEW, {"name": "Example Branch", "first_administrator": ""})
    unknown = client.post(
        NEW, {"name": "Example Branch", "first_administrator": "nobody@example.test"}
    )

    assert missing.status_code == unknown.status_code == 200
    assert missing.context["form"].errors["first_administrator"]
    assert unknown.context["form"].errors["first_administrator"]
    assert not Tenant.objects.filter(name="Example Branch").exists()


def test_tenants_listed(platform_admin: Any, make_tenant: Any) -> None:
    from identity.models import Membership

    one = make_tenant("Example Org")
    two = make_tenant("Sandbox", state="migrating")
    Membership.objects.create(
        tenant=one,
        user=registered("an.admin@example.test"),
        is_tenant_admin=True,
        actor_kind="system",
    )
    client, _ = platform_admin()

    response = client.get(TENANTS)

    rows = {row["tenant"].number: row for row in response.context["rows"]}
    assert response.status_code == 200
    assert rows[one.number]["administrators"] == 1 and rows[one.number]["tenant"].state == "active"
    assert (
        rows[two.number]["administrators"] == 0 and rows[two.number]["tenant"].state == "migrating"
    )


def test_failed_migration_leaves_tenant_unresolvable(
    platform_admin: Any, drop_tenant_schemas: None, monkeypatch: Any
) -> None:
    from audit.models import AuditEvent
    from identity.models import Membership
    from tenancy.management.commands import migrate_schemas
    from tenancy.models import Tenant, TenantStateHistory
    from tenancy.schemas import schema_exists

    def fails(label: str) -> None:
        raise RuntimeError("a migration failed")

    # A real run that fails part-way: the schema and its migration record exist, no app is in.
    monkeypatch.setattr(migrate_schemas, "_migrate", fails)
    client, admin = platform_admin()
    registered("first.admin@example.test")

    response = client.post(
        NEW, {"name": "Example Branch", "first_administrator": "first.admin@example.test"}
    )

    tenant = Tenant.objects.get(name="Example Branch")
    assert response.status_code == 302
    assert tenant.state == "migrating"
    assert Membership.objects.filter(tenant=tenant, is_tenant_admin=True).exists()
    assert AuditEvent.objects.filter(action="tenant.created", object_id=tenant.id).exists()
    assert AuditEvent.objects.filter(action="tenant.migration_failed", object_id=tenant.id).exists()
    assert schema_exists(tenant.number)
    session = client.session
    session["tenant_number"] = tenant.number
    session.save()
    seen = client.get("/")
    assert seen.wsgi_request.tenant is None

    with connection.cursor() as cursor:
        cursor.execute("SHOW search_path")
        assert cursor.fetchone()[0] == "public"
    monkeypatch.undo()
    call_command("migrate_schemas", "--tenant", str(tenant.number), verbosity=0)

    tenant.refresh_from_db()
    assert tenant.state == "active"
    step = TenantStateHistory.objects.get(tenant=tenant)
    assert (step.before, step.after, step.by) == ("migrating", "active", None)


def test_platform_pages_need_a_platform_administrator(make_tenant: Any) -> None:
    from identity.models import Membership, User

    tenant = make_tenant("Example Org")
    user = User.objects.create_user("t.admin@example.test", "Tr4vel-Plan-Ok")
    Membership.objects.create(tenant=tenant, user=user, is_tenant_admin=True, actor_kind="system")
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(user)

    assert client.post(NEW, {"name": "X", "first_administrator": user.email}).status_code == 404


class connection_to:
    """A cursor with the tenant's schema alone on the path, restored on leaving."""

    def __init__(self, number: int) -> None:
        self.number = number

    def __enter__(self) -> Any:
        from tenancy.schemas import schema_context

        self.context = schema_context(self.number, public=False)
        self.context.__enter__()
        from django.db import connection

        self.cursor = connection.cursor()
        return self.cursor

    def __exit__(self, *exc: Any) -> None:
        self.cursor.close()
        self.context.__exit__(*exc)


def test_a_person_who_blocked_themselves_is_no_first_administrator(platform_admin: Any) -> None:
    from identity.models import User
    from tenancy.models import Tenant

    User.objects.create_user("gone@example.test", "Tr4vel-Plan-Ok", self_blocked=True)
    client, _ = platform_admin()

    response = client.post(
        NEW, {"name": "Example Branch", "first_administrator": "gone@example.test"}
    )

    assert response.status_code == 200 and response.context["form"].errors["first_administrator"]
    assert not Tenant.objects.filter(name="Example Branch").exists()


def test_creation_with_an_organisation_chosen_restores_its_path(
    platform_admin: Any, make_tenant: Any, drop_tenant_schemas: None
) -> None:
    from tenancy import views
    from tenancy.models import Tenant

    chosen = make_tenant("Example Org")
    client, _ = platform_admin()
    registered("first.admin@example.test")
    session = client.session
    session["tenant_number"] = chosen.number
    session.save()
    seen: dict[str, str] = {}
    create = views.services.create_tenant

    def create_and_look(*args: Any, **kwargs: Any) -> Any:
        tenant = create(*args, **kwargs)
        with connection.cursor() as cursor:
            cursor.execute("SHOW search_path")
            seen["path"] = cursor.fetchone()[0]
        return tenant

    views.services.create_tenant = create_and_look  # type: ignore[assignment]
    try:
        client.post(
            NEW, {"name": "Example Branch", "first_administrator": "first.admin@example.test"}
        )
    finally:
        views.services.create_tenant = create  # type: ignore[assignment]

    assert Tenant.objects.get(name="Example Branch").state == "active"
    assert seen["path"] == f"tenant_{chosen.number}, public"
