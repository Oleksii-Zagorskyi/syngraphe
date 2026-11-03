"""Every page and email the people pages add renders in Ukrainian from the one catalogue: the users
list, *invite by email* with each of its sentences, the invitation's email, the page its link opens,
the organisation form's note, the sign-in page's link, the reset's request, email and page,
blocking a membership and one's own account, the platform's entries, and the platform's pages for
organisations and their administrators.

People, organisations and groups are synthetic examples; every address ends in `@example.test`."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Any

import pytest
from django.test import Client

from tenancy.schemas import schema_context

_spec = importlib.util.spec_from_file_location(
    "identity_catalogue", Path(__file__).resolve().parents[1] / "review" / "test_catalogue.py"
)
assert _spec is not None and _spec.loader is not None
_review = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_review)

TOKEN = re.compile(r"/invitation/([A-Za-z0-9_-]{43})/")
RESET = re.compile(r"/reset/([A-Za-z0-9_-]{43})/")


@pytest.mark.integration
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_catalogue_covers_people_pages(
    migrated_tenant: Any, member_of: Any, make_document: Any, settings: Any, monkeypatch: Any
) -> None:
    from access.models import AccessGroup
    from identity.models import User
    from mail.models import EmailOutbox, MailSender

    settings.LANGUAGE_CODE = "uk"
    ids = _review.message_ids(_review.CATALOGUE.read_text(encoding="utf-8"))
    admin, admin_user, _ = member_of("t.synthetic@example.test", is_tenant_admin=True)
    _, _, blocked = member_of("b.synthetic@example.test")
    blocked.change("state", "blocked", by=admin_user)
    with schema_context(migrated_tenant.number):
        MailSender.objects.create(
            host="127.0.0.1", port=2525, address="mail@example.test", security="none"
        )
        group = AccessGroup.objects.create(
            name="Синтетична група", created_by=admin_user, actor_kind="user"
        )

    bodies = {
        "users": admin.get("/administration/tenant/users/").content.decode(),
        "invite": admin.get("/administration/tenant/users/invite/").content.decode(),
        "sent": admin.post(
            "/administration/tenant/users/invite/",
            {"email": "n.synthetic@example.test", "groups": [str(group.pk)]},
        ).content.decode(),
        "refused": admin.post(
            "/administration/tenant/users/invite/", {"email": "b.synthetic@example.test"}
        ).content.decode(),
        "malformed": admin.post(
            "/administration/tenant/users/invite/", {"email": "not-an-address"}
        ).content.decode(),
    }
    with schema_context(migrated_tenant.number):
        email = EmailOutbox.objects.get(recipient="n.synthetic@example.test")
    bodies["the email"] = f"{email.subject}\n{email.body}"
    match = TOKEN.search(email.body)
    assert match is not None
    stranger = Client(headers={"host": "127.0.0.1"})
    link = f"/invitation/{match.group(1)}/"
    bodies["the link"] = stranger.get(link).content.decode()
    bodies["a weak password"] = stranger.post(
        link, {"password": "short", "password_again": "other"}
    ).content.decode()
    platform, _, _ = member_of("p.synthetic@example.test", is_platform_admin=True)
    bodies["the organisation form"] = platform.get(
        "/administration/platform/tenants/new/"
    ).content.decode()
    _, _, member = member_of("m.synthetic@example.test")
    confirmation = f"/administration/tenant/users/{member.pk}/block/"
    bodies["block"] = admin.get(confirmation).content.decode()
    # The links page with a document held, and one reserved: each names its holder.
    from datetime import timedelta

    from django.utils import timezone

    from editing.models import Hold

    with schema_context(migrated_tenant.number):
        now = timezone.now()
        for title, reserved in (
            ("Синтетичний утримуваний", None),
            ("Синтетичний відкладений", now),
        ):
            Hold.objects.create(
                document=make_document(title=title, created_by=admin_user),
                user=member.user,
                acquired_at=now - timedelta(hours=1),
                last_activity_at=now,
                reserved_at=reserved,
            )
    bodies["the links page, held"] = admin.get(
        "/administration/tenant/document-links/"
    ).content.decode()
    from django.utils.translation import gettext, override

    with override("uk"):
        locked = gettext("Locked while the document is held.")
    assert bodies["the links page, held"].count(locked) == 2
    # A document busy at the moment of a block: each of the three block pages says so.
    from identity import blocking

    def busy(*args: Any, **kwargs: Any) -> int:
        raise blocking.BlockRefused("busy")

    monkeypatch.setattr("identity.blocking.end_holds", busy)
    bodies["block, busy"] = admin.post(
        confirmation, {"organisations": [str(migrated_tenant.number)]}
    ).content.decode()
    busy_client, _, _ = member_of("r.synthetic@example.test")
    bodies["block my account, busy"] = busy_client.post("/account/block/").content.decode()
    bodies["block the organisation, busy"] = platform.post(
        f"/administration/platform/tenants/{migrated_tenant.number}/block/"
    ).content.decode()
    monkeypatch.undo()
    for name in ("block, busy", "block my account, busy", "block the organisation, busy"):
        assert 'role="alert"' in bodies[name], name
    bodies["the last administrator"] = admin.post(
        f"/administration/tenant/users/{admin_user_membership(admin_user).pk}/block/",
        {"organisations": [str(migrated_tenant.number)]},
    ).content.decode()
    from notifications.models import Event
    from notifications.services import notify_platform

    watcher = User.objects.get(email="p.synthetic@example.test")
    notify_platform(
        event=Event.USER_PARTIALLY_BLOCKED,
        users=[watcher],
        facts={"user": str(member.user_id), "tenant": migrated_tenant.number},
    )
    notify_platform(
        event=Event.TENANT_WITHOUT_ADMIN, users=[watcher], facts={"tenant": migrated_tenant.number}
    )
    bodies["the platform's entries"] = platform.get(
        "/notifications/?tab=administrative"
    ).content.decode()
    member_client, _, _ = member_of("q.synthetic@example.test")
    bodies["block my account"] = member_client.get("/account/block/").content.decode()
    bodies["the last platform administrator's own block"] = platform.get(
        "/account/block/"
    ).content.decode()
    # A member's page: an ordinary member, an administrator, a blocked membership (DL-0505).
    from identity.models import Membership

    for label, membership in (
        ("a member's page", Membership.objects.get(user__email="q.synthetic@example.test")),
        ("an administrator's page", Membership.objects.get(user=admin_user)),
        ("a blocked member's page", blocked),
    ):
        page = admin.get(f"/administration/tenant/users/{membership.pk}/")
        assert page.status_code == 200, label
        bodies[label] = page.content.decode()
    # The account page: a member's, the last platform administrator's, a refused value, applied.
    bodies["my account"] = member_client.get("/account/").content.decode()
    bodies["the last platform administrator's account"] = platform.get("/account/").content.decode()
    bodies["my account, refused"] = member_client.post(
        "/account/", {"language": "xx"}
    ).content.decode()
    applied = member_client.post("/account/", {"language": "uk"})
    assert applied.status_code == 303
    bodies["my account, applied"] = member_client.get(applied["Location"]).content.decode()
    # The display name: refused empty, too long and taken; applied (DL-0523).
    bodies["my name, empty"] = member_client.post(
        "/account/", {"display_name": " "}
    ).content.decode()
    bodies["my name, long"] = member_client.post(
        "/account/", {"display_name": "и" * 201}
    ).content.decode()
    bodies["my name, unshowable"] = member_client.post(
        "/account/", {"display_name": "Ім'я\x00"}
    ).content.decode()
    User.objects.filter(email="b.synthetic@example.test").update(display_name="Синтетичне ім'я")
    bodies["my name, taken"] = member_client.post(
        "/account/", {"display_name": "Синтетичне ім'я"}
    ).content.decode()
    from identity.models import Membership
    from tenancy.models import Tenant

    joining = User.objects.create_user(
        "j.synthetic@example.test", "test-only-not-a-password", display_name="Синтетичне ім'я"
    )
    Membership.objects.create(
        tenant=Tenant.objects.create(name="Синтетична інша", actor_kind="system"),
        user=joining,
        actor_kind="system",
    )
    bodies["invite, name taken"] = admin.post(
        "/administration/tenant/users/invite/", {"email": "j.synthetic@example.test"}
    ).content.decode()
    named = member_client.post("/account/", {"display_name": "Інше синтетичне ім'я"})
    assert named.status_code == 303
    bodies["my name, applied"] = member_client.get(named["Location"]).content.decode()
    session = platform.session
    session.pop("tenant_number", None)
    session.save()
    platform_pages = (
        "/administration/platform/tenants/",
        f"/administration/platform/tenants/{migrated_tenant.number}/block/",
        f"/administration/platform/tenants/{migrated_tenant.number}/appoint/",
        "/administration/platform/administrators/",
    )
    from tenancy.models import Tenant

    # A blocked organisation too: its row's *lift the block*, its state, the selector's mark.
    Tenant.objects.create(name="Синтетична заблокована", state="blocked", actor_kind="system")
    # A holder who blocked their own account, marked on the administrators page.
    User.objects.create_user(
        "s.synthetic@example.test", "test-only-not-a-password", is_platform_admin=True
    )
    User.objects.filter(email="s.synthetic@example.test").update(self_blocked=True)
    for page in (*platform_pages, "/administration/"):
        bodies[page] = platform.get(page, follow=True).content.decode()
        assert "<html" in bodies[page], page
    bodies["appoint refused"] = platform.post(
        f"/administration/platform/tenants/{migrated_tenant.number}/appoint/",
        {"email": "nobody.here@example.test"},
    ).content.decode()
    bodies["grant refused"] = platform.post(
        "/administration/platform/administrators/grant/", {"email": "nobody.here@example.test"}
    ).content.decode()
    bodies["grant refused, blocked"] = platform.post(
        "/administration/platform/administrators/grant/", {"email": "s.synthetic@example.test"}
    ).content.decode()
    assert 'class="err"' in bodies["grant refused, blocked"]
    bodies["sign in"] = stranger.get("/signin/").content.decode()

    bodies["reset"] = stranger.get("/reset/").content.decode()
    bodies["reset asked"] = stranger.post(
        "/reset/", {"email": "t.synthetic@example.test"}
    ).content.decode()
    with schema_context(migrated_tenant.number):
        reset = EmailOutbox.objects.get(recipient="t.synthetic@example.test")
    bodies["the reset email"] = f"{reset.subject}\n{reset.body}"
    found = RESET.search(reset.body)
    assert found is not None
    bodies["the reset link"] = stranger.get(f"/reset/{found.group(1)}/").content.decode()

    for name, body in bodies.items():
        shown = _review.text_of(body)
        leaked = [message for message in ids if message in shown]
        assert leaked == [], (name, leaked)


def admin_user_membership(user: Any) -> Any:
    from identity.models import Membership

    return Membership.objects.get(user=user)
