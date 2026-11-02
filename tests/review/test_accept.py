"""Accepting the run (ST-0036, DL-0092, DL-0183, DL-0224): a passport commit of kind `acceptance`,
its `ACCEPTANCE` row numbered `N.M`, under the lock; refused with its reason; a reviewer may
accept a run they wrote, and the record shows it.

People and groups are synthetic examples; the text is invented.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from django.utils import timezone

from audit.models import AuditEvent
from documents.models import Version
from editing.models import Hold
from review import services
from review.models import Acceptance, CorrectionNotice
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

FIRST = (
    "# General provisions\n\n"
    "A request for approval is made in writing.\n"
    "A request is considered within ten days.\n"
)
SECOND = FIRST + "\nA copy of the decision goes to the applicant that day.\n"
THIRD = SECOND.replace("ten days", "five working days")


def test_acceptance_is_a_passport_commit(
    migrated_tenant: Any,
    cast: Any,
    commit_version: Any,
    repository: Any,
    queued_authorship: list[Any],
) -> None:
    people = cast(editors=("a", "b"), reviewers=("r",))
    document, reviewer = people.document, people["r"]
    commit_version(document, people["a"], FIRST, "edit")
    last = commit_version(document, people["b"], SECOND, "edit")
    passport_before = repository.read(document, "passport.md")

    with schema_context(migrated_tenant.number):
        acceptance = services.accept(document, reviewer)

    head = repository.head(document)
    # One commit of kind `acceptance`, on top of the run, that changes the passport alone.
    assert repository.kinds(document) == ["created", "edit", "edit", "acceptance"]
    assert repository.parent(document, head) == last.commit_sha
    assert repository.read(document, "document.md", head) == repository.read(
        document, "document.md", last.commit_sha
    )
    # The passport gains `## acceptance 0.1` with `at`, `by`, `version`; every earlier byte kept.
    passport = repository.read(document, "passport.md", head)
    assert passport.startswith(passport_before)
    appended = passport[len(passport_before) :]
    assert re.search(r"^## acceptance 0\.1$", appended, re.MULTILINE)
    section = appended.split("## acceptance 0.1", 1)[1]
    # Each field on a line of its own, its name first (`bundle.PassportEntry.section`).
    assert re.search(r"^\W*at\b", section, re.MULTILINE)
    assert re.search(rf"^\W*by\b.*{reviewer.pk}", section, re.MULTILINE)
    assert re.search(rf"^\W*version\b.*{last.commit_sha}", section, re.MULTILINE)
    assert reviewer.email not in passport

    with schema_context(migrated_tenant.number):
        created = Version.objects.get(document=document, kind="created")
        row = Acceptance.objects.get()
        assert row.pk == acceptance.pk
        assert row.number == "0.1"
        assert row.version.commit_sha == head and row.version.kind == "acceptance"
        assert row.accepted_from_id == created.pk
        assert row.reviewer_id == reviewer.pk
        assert row.at is not None
        assert row.notices_computed_at is not None
        assert services.accepted_content_version(row).pk == last.pk
    assert (migrated_tenant.number, document.number, last.commit_sha) in queued_authorship
    assert AuditEvent.objects.filter(action="document.accepted").count() == 1


def test_refused_without_a_reviewer(
    migrated_tenant: Any, cast: Any, member_of: Any, commit_version: Any, repository: Any
) -> None:
    people = cast(editors=("a",), reviewers=())
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    _, administrator, _ = member_of("platform.admin@example.test", is_platform_admin=True)
    head = repository.head(document)

    with schema_context(migrated_tenant.number):
        with pytest.raises(services.AcceptRefused) as refused:
            services.accept(document, administrator)
        assert refused.value.reason == "no_reviewer"
        assert not Acceptance.objects.exists()
    assert repository.head(document) == head


def test_refused_while_reserved(
    migrated_tenant: Any, cast: Any, commit_version: Any, repository: Any
) -> None:
    people = cast(editors=("a",), reviewers=("r",))
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    head = repository.head(document)
    now = timezone.now()
    with schema_context(migrated_tenant.number):
        Hold.objects.create(
            document=document,
            user=people["a"],
            acquired_at=now,
            last_activity_at=now,
            reserved_at=now,
        )

        with pytest.raises(services.AcceptRefused) as refused:
            services.accept(document, people["r"])
        assert refused.value.reason == "reserved"
        assert not Acceptance.objects.exists()
    assert repository.head(document) == head


def test_empty_run_refused(
    migrated_tenant: Any, cast: Any, commit_version: Any, repository: Any
) -> None:
    people = cast(editors=("a",), reviewers=("r",))
    document, reviewer = people.document, people["r"]
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        services.accept(document, reviewer)
    head = repository.head(document)

    with schema_context(migrated_tenant.number):
        with pytest.raises(services.AcceptRefused) as refused:
            services.accept(document, reviewer)
        assert refused.value.reason == "nothing_to_accept"
        assert Acceptance.objects.count() == 1
    assert repository.head(document) == head
    assert repository.kinds(document).count("acceptance") == 1


def test_self_acceptance_recorded(
    migrated_tenant: Any, cast: Any, commit_version: Any, repository: Any
) -> None:
    people = cast(editors=("a",), reviewers=("r",))
    document, reviewer = people.document, people["r"]
    run = [
        commit_version(document, reviewer, SECOND, "reviewer_edit"),
        commit_version(document, reviewer, THIRD, "reviewer_edit"),
    ]

    with schema_context(migrated_tenant.number):
        acceptance = services.accept(document, reviewer)
        row = Acceptance.objects.get(pk=acceptance.pk)
        assert row.number == "0.1"
        assert all(version.author_id == row.reviewer_id for version in run)
        assert row.reviewer_id == reviewer.pk
        # Nobody is told about their own lines (ADR-0014).
        assert not CorrectionNotice.objects.exists()
    event = AuditEvent.objects.get(action="document.accepted")
    assert event.actor_id == reviewer.pk


def test_refused_to_a_member_without_accept(
    migrated_tenant: Any, cast: Any, commit_version: Any
) -> None:
    people = cast(editors=("a",), reviewers=("r",))
    commit_version(people.document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        with pytest.raises(services.AcceptRefused) as refused:
            services.accept(people.document, people["a"])
        assert refused.value.reason == "not_a_reviewer"


def test_the_confirmation_names_the_run_and_a_grown_run_is_refused(
    migrated_tenant: Any, cast: Any, commit_version: Any, member_of: Any
) -> None:
    from django.test import Client

    people = cast(editors=("a",), reviewers=("r",))
    document, reviewer = people.document, people["r"]
    first = commit_version(document, people["a"], FIRST, "edit")
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(reviewer)
    session = client.session
    session["tenant_number"] = migrated_tenant.number
    session.save()
    address = f"/document/{document.number}/pending/accept/"
    page = client.get(address).content.decode()
    assert 'data-number="0.0-1"' in page and "0.1" in page
    assert f'name="confirmed" value="{first.commit_sha}"' in page
    # Another version lands before the click: refused, the confirmation shown again.
    second = commit_version(document, people["a"], SECOND, "edit")
    refused = client.post(address, {"confirmed": first.commit_sha})
    assert refused.status_code == 409
    assert f'name="confirmed" value="{second.commit_sha}"' in refused.content.decode()
    with schema_context(migrated_tenant.number):
        assert not Acceptance.objects.exists()
    accepted = client.post(address, {"confirmed": second.commit_sha})
    assert accepted.status_code == 302 and accepted["Location"] == f"/document/{document.number}/"
    landing = client.get(accepted["Location"]).content.decode()
    notice = landing.split('<p class="notice" role="status">', 1)[1].split("</p>", 1)[0]
    assert "0.1" in notice
    # An editor without *accept* reaches no confirmation.
    editor = Client(headers={"host": "127.0.0.1"})
    editor.force_login(people["a"])
    session = editor.session
    session["tenant_number"] = migrated_tenant.number
    session.save()
    assert editor.get(address).status_code == 404


def test_reservation_and_acceptance_never_interleave(
    migrated_tenant: Any, cast: Any, commit_version: Any, link_group: Any
) -> None:
    """Review waits for a reservation, never the reverse (DL-0224): a reservation attempted while
    an acceptance holds the document's lock waits and lands after its commit, both standing; an
    acceptance that finds the reservation refuses `reserved`, and the reservation stands."""
    import threading

    from django.db import connection

    from access.rights import Right
    from documents.locks import document_lock
    from editing import holds, reservations

    people = cast(editors=("a",), reviewers=("r",))
    document = people.document
    link_group(document, [Right.RESERVE_FOR_EDITING], [people.memberships["a"]], people["a"])
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        hold = holds.take(document, people["a"])
    reserved: list[Any] = []

    def reserve() -> None:
        try:
            with schema_context(migrated_tenant.number):
                reserved.append(reservations.reserve(hold, people["a"]))
        finally:
            connection.close()

    # The acceptance first: the reservation waits for its lock and lands after its commit.
    with schema_context(migrated_tenant.number):
        with document_lock(migrated_tenant.number, document.number):
            waiting = threading.Thread(target=reserve)
            waiting.start()
            waiting.join(timeout=1)
            still_waiting = waiting.is_alive()
            accepted = services.accept_locked(document, people["r"])
        waiting.join(timeout=30)
        assert still_waiting
        assert len(reserved) == 1
        hold.refresh_from_db()
        assert hold.reserved_at is not None and hold.reserved_at >= accepted.version.created_at

        # The reservation first: the next acceptance refuses, and the reservation stands.
        commit_version(document, people["a"], SECOND, "edit")
        with pytest.raises(services.AcceptRefused) as refused:
            services.accept(document, people["r"])
        assert refused.value.reason == "reserved"
        assert Acceptance.objects.count() == 1
        hold.refresh_from_db()
        assert hold.reserved_at is not None and hold.released_at is None


def test_the_reserved_refusal_dates_in_the_display_timezone(
    migrated_tenant: Any, cast: Any, commit_version: Any, settings: Any
) -> None:
    """The refusal names the reservation's date as the band beside it does, in the display
    timezone: late on the 13th in UTC is the 14th east of it."""
    from datetime import UTC, datetime

    from django.test import Client

    settings.LANGUAGE_CODE = "en"
    settings.DISPLAY_TIMEZONE = "Europe/Kyiv"
    people = cast(editors=("a",), reviewers=("r",))
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        Hold.objects.create(
            document=document,
            user=people["a"],
            acquired_at=timezone.now(),
            last_activity_at=timezone.now(),
            reserved_at=datetime(2026, 10, 13, 22, 30, tzinfo=UTC),
        )
    reviewer = Client(headers={"host": "127.0.0.1"})
    reviewer.force_login(people["r"])
    session = reviewer.session
    session["tenant_number"] = migrated_tenant.number
    session.save()
    page = reviewer.get(f"/document/{document.number}/pending/").content.decode()
    assert "14 October 2026" in page
    assert "13 October 2026" not in page
