"""`end_freeze`, the operator's way out of a freeze no holder of *freeze* is there to end: the
freeze ended `unfrozen` with an audit event carrying the reason; the numbering unchanged.

People and groups are synthetic examples; the text is invented.
"""

from __future__ import annotations

from io import StringIO
from typing import Any

import pytest
from django.core.management import CommandError, call_command

from audit.models import AuditEvent
from review import services as review
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

BODY = "A request for approval is made in writing.\n"


def test_end_freeze_ends_it_unfrozen(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any
) -> None:
    from editing import numbering
    from editions import services as editions
    from editions.models import Freeze, open_freeze

    people = edition_cast()
    commit_version(people.document, people["a"], BODY, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(people.document, people["r"])
        editions.freeze(people.document, people["p"], "Synthetic reason")
    out = StringIO()

    call_command(
        "end_freeze",
        tenant=migrated_tenant.number,
        document=people.document.number,
        reason="Synthetic decision of the operator",
        stdout=out,
    )

    assert out.getvalue().strip() == f"document {people.document.number} · freeze ended"
    with schema_context(migrated_tenant.number):
        freeze = Freeze.objects.get()
        assert freeze.ended_by_kind == "unfrozen" and freeze.ended_at is not None
        assert freeze.ended_by is None
        assert open_freeze(people.document) is None
        assert numbering.accepted(people.document) == "0.1"
    event = AuditEvent.objects.get(action="document.unfrozen")
    assert event.actor_id is None and event.after["reason"] == "Synthetic decision of the operator"
    # Ordinary editing resumes: an editor without *accept* takes the document.
    from editing import holds

    with schema_context(migrated_tenant.number):
        assert holds.take(people.document, people["a"]).user_id == people["a"].pk


def test_end_freeze_on_a_document_not_frozen(migrated_tenant: Any, edition_cast: Any) -> None:
    people = edition_cast()
    with pytest.raises(CommandError, match="not frozen"):
        call_command(
            "end_freeze",
            tenant=migrated_tenant.number,
            document=people.document.number,
            reason="Synthetic decision",
        )
    assert not AuditEvent.objects.filter(action="document.unfrozen").exists()


def test_end_freeze_needs_a_reason(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any
) -> None:
    from editions import services as editions
    from editions.models import open_freeze

    people = edition_cast()
    with schema_context(migrated_tenant.number):
        editions.freeze(people.document, people["p"])
    with pytest.raises(CommandError, match="reason"):
        call_command(
            "end_freeze",
            tenant=migrated_tenant.number,
            document=people.document.number,
            reason="  ",
        )
    with schema_context(migrated_tenant.number):
        assert open_freeze(people.document) is not None


def test_the_command_names_no_actor(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any
) -> None:
    """The operator's command ends a freeze as the platform's act: no actor, and the reason it must
    give."""
    from editions import services as editions
    from editions.models import Freeze

    people = edition_cast()
    commit_version(people.document, people["a"], BODY, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(people.document, people["r"])
        editions.freeze(people.document, people["p"], "Synthetic reason")
    call_command(
        "end_freeze",
        tenant=migrated_tenant.number,
        document=people.document.number,
        reason="Synthetic decision of the operator",
        stdout=StringIO(),
    )
    event = AuditEvent.objects.get(action="document.unfrozen")
    assert event.actor_kind == "system" and event.actor_id is None
    with schema_context(migrated_tenant.number):
        assert Freeze.objects.get().ended_by is None
        # A freeze still open: the operator's empty reason is refused, and the freeze stays.
        editions.freeze(people.document, people["p"], "Synthetic reason")
        with pytest.raises(ValueError, match="reason"):
            editions.end_freeze(people.document, "")
        assert Freeze.objects.filter(ended_at__isnull=True).count() == 1


def test_an_archived_document_is_refused(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any, member_of: Any
) -> None:
    from documents import archive
    from editions import services as editions
    from editions.models import open_freeze

    people = edition_cast()
    _, admin, _ = member_of("the.archiver@example.test", is_tenant_admin=True)
    commit_version(people.document, people["a"], BODY, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(people.document, people["r"])
        editions.freeze(people.document, people["p"], "Synthetic reason")
        archive.archive(people.document, admin)

    with pytest.raises(CommandError, match="archived; restore it first"):
        call_command(
            "end_freeze",
            tenant=migrated_tenant.number,
            document=people.document.number,
            reason="Synthetic decision of the operator",
        )
    with schema_context(migrated_tenant.number):
        assert open_freeze(people.document) is not None


def test_a_document_archived_while_the_command_waits_is_refused(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    member_of: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The command read the document active; an administrator archives it before the service
    takes its lock: the service, reading the locked row, refuses — the freeze stays, unaudited."""
    from documents import archive
    from editions import services as editions
    from editions.models import open_freeze

    people = edition_cast()
    _, admin, _ = member_of("the.archiver@example.test", is_tenant_admin=True)
    commit_version(people.document, people["a"], BODY, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(people.document, people["r"])
        editions.freeze(people.document, people["p"], "Synthetic reason")
    end_freeze = editions.end_freeze

    def archived_first(document: Any, *args: Any, **kwargs: Any) -> Any:
        archive.archive(document, admin)
        return end_freeze(document, *args, **kwargs)

    monkeypatch.setattr(editions, "end_freeze", archived_first)

    with pytest.raises(CommandError, match="archived; restore it first"):
        call_command(
            "end_freeze",
            tenant=migrated_tenant.number,
            document=people.document.number,
            reason="Synthetic decision of the operator",
        )
    with schema_context(migrated_tenant.number):
        assert open_freeze(people.document) is not None
    assert not AuditEvent.objects.filter(action="document.unfrozen").exists()
