"""The correction notice's page (ADR-0014, DL-0113, DL-0334): each line's two wordings rendered from
git and marked, who changed it, a way to the document — under the reader's current rights, and
only to the notice's author.

People and groups are synthetic examples; the text is invented.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.test import Client

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

WRITTEN = (
    "# General provisions\n\n"
    "A request for approval is made in writing.\n"
    "A request is considered within ten days.\n"
)
CORRECTED = WRITTEN.replace(
    "A request is considered within ten days.",
    "A request is considered within five working days.",
)


def signed_in(tenant: Any, user: Any) -> Client:
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(user)
    session = client.session
    session["tenant_number"] = tenant.number
    session.save()
    return client


def a_notice(tenant: Any, cast: Any, commit_version: Any) -> tuple[Any, Any]:
    from notifications.models import Notification
    from review import services

    people = cast(editors=("a",), reviewers=("r",))
    people["r"].display_name = "Synthetic Approver R"
    people["r"].save(update_fields=["display_name"])
    commit_version(people.document, people["a"], WRITTEN, "edit")
    commit_version(people.document, people["r"], CORRECTED, "reviewer_edit")
    with schema_context(tenant.number):
        services.accept(people.document, people["r"])
        notification = Notification.objects.get(user=people["a"], event="correction_notice")
    return people, notification


def test_notice_for_its_author(migrated_tenant: Any, cast: Any, commit_version: Any) -> None:
    people, notification = a_notice(migrated_tenant, cast, commit_version)
    address = f"/notifications/{notification.pk}/"
    page = signed_in(migrated_tenant, people["a"]).get(address)
    assert page.status_code == 200
    body = page.content.decode()
    assert "<del>ten</del>" in body and "<ins>five working</ins>" in body
    assert "Synthetic Approver R" in body
    # The accepted version's page at the numbered heading the passage falls under, which the
    # author's ceiling reaches (DL-0334).
    assert f'href="/document/{people.document.number}/version/0.1/#h-1"' in body
    assert 'data-lines="1"' in body
    with schema_context(migrated_tenant.number):
        notification.refresh_from_db()
        assert notification.read_at is not None
    # Anyone else — the reviewer included — reaches nothing.
    assert signed_in(migrated_tenant, people["r"]).get(address).status_code == 404
    assert signed_in(migrated_tenant, people["a"]).get("/notifications/0/").status_code == 404


def test_text_follows_current_rights(
    migrated_tenant: Any, cast: Any, commit_version: Any, link_group: Any
) -> None:
    """DL-0337 under DL-0396: with every right gone the notice is missing and stays unread; with
    canonical text alone, once an edition exists, it shows that it exists, its lines and who
    changed them, no text; with *view accepted*, the text."""
    from access.models import DocumentGroup
    from access.rights import Right
    from editions import services as editions

    people, notification = a_notice(migrated_tenant, cast, commit_version)
    address = f"/notifications/{notification.pk}/"
    client = signed_in(migrated_tenant, people["a"])
    editors = people.groups["editors"]
    with schema_context(migrated_tenant.number):
        DocumentGroup.unlink(people.document, editors, by=people["r"])
    assert client.get(address).status_code == 404
    with schema_context(migrated_tenant.number):
        notification.refresh_from_db()
    assert notification.read_at is None

    link_group(
        people.document,
        [Right.FREEZE, Right.MAKE_CANONICAL],
        [people.memberships["r"]],
        people["r"],
    )
    link_group(people.document, [Right.VIEW_CANONICAL], [people.memberships["a"]], people["r"])
    with schema_context(migrated_tenant.number):
        editions.freeze(people.document, people["r"], "Synthetic reason")
        editions.make_canonical(people.document, people["r"])
    body = client.get(address).content.decode()
    assert 'data-lines="1"' in body and "Synthetic Approver R" in body
    assert "within" not in body and "five working" not in body and "A request" not in body

    with schema_context(migrated_tenant.number):
        DocumentGroup.link(people.document, editors, by=people["r"])
    body = client.get(address).content.decode()
    assert "<del>ten</del>" in body


@pytest.mark.parametrize("blocked", ["membership", "account"])
def test_a_blocked_author_reaches_nothing(
    migrated_tenant: Any, cast: Any, commit_version: Any, blocked: str
) -> None:
    """On the organisation's own address, where the organisation is known whoever asks: a blocked
    membership or a self-blocked account opens no notice, and it stays unread (DL-0308)."""
    from identity.models import Membership
    from tenancy.middleware import invalidate_host_cache
    from tenancy.models import TenantDomain

    TenantDomain.objects.create(
        tenant=migrated_tenant, host="docs.example.test", is_default=True, actor_kind="system"
    )
    invalidate_host_cache()
    people, notification = a_notice(migrated_tenant, cast, commit_version)
    author = people["a"]
    client = Client(headers={"host": "docs.example.test"})
    client.force_login(author)
    if blocked == "membership":
        Membership.objects.get(user=author, tenant=migrated_tenant).change(
            "state", "blocked", by=people["r"]
        )
    else:
        author.self_blocked = True
        author.save(update_fields=["self_blocked"])
    assert client.get(f"/notifications/{notification.pk}/").status_code == 404
    with schema_context(migrated_tenant.number):
        notification.refresh_from_db()
        assert notification.read_at is None


def test_a_range_that_does_not_read_names_no_line() -> None:
    from review.views.notice import _lines, _span

    for value in ("", "-3", "abc", "-1--1", "0", "0-9", "3-1"):
        assert _span(value) is None, value
    assert _lines(b"a\nb\nc\n", "2-3") == b"b\nc\n"


def test_notices_are_computed_once(migrated_tenant: Any, cast: Any, commit_version: Any) -> None:
    from review import notices
    from review.models import Acceptance, CorrectionLine, CorrectionNotice

    a_notice(migrated_tenant, cast, commit_version)
    with schema_context(migrated_tenant.number):
        acceptance = Acceptance.objects.get()
        counts = (CorrectionNotice.objects.count(), CorrectionLine.objects.count())
        # Asked again — by the reconciler, or a second call racing the first — nothing more.
        again = notices.compute(Acceptance.objects.get(pk=acceptance.pk))
        assert len(again) == counts[0]
        assert (CorrectionNotice.objects.count(), CorrectionLine.objects.count()) == counts
