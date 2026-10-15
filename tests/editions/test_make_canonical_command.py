"""`make_canonical`, the operator's command (DL-0350): a named member freezes the document and
makes it canonical through the services; the distinct-approver check applies unchanged, and
nothing is frozen that could not then be made canonical.

People and groups are synthetic examples; the text is invented.
"""

from __future__ import annotations

from io import StringIO
from typing import Any

import pytest
from django.core.management import CommandError, call_command

from review import services as review
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

BODY = "A request for approval is made in writing.\n"


def _run(tenant: int, document: int, member: Any, reason: str = "") -> str:
    out = StringIO()
    call_command(
        "make_canonical",
        tenant=tenant,
        document=document,
        member=member.email,
        reason=reason,
        stdout=out,
    )
    return out.getvalue()


def test_command_freezes_and_makes_canonical(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any
) -> None:
    from editions.models import Edition, Freeze, open_freeze

    people = edition_cast()
    commit_version(people.document, people["a"], BODY, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(people.document, people["r"])

    out = _run(migrated_tenant.number, people.document.number, people["p"], "Synthetic board")

    assert out.strip() == f"document {people.document.number} · edition 1.0"
    with schema_context(migrated_tenant.number):
        assert list(Edition.objects.values_list("number", flat=True)) == ["1.0"]
        freeze = Freeze.objects.get()
        assert freeze.reason == "Synthetic board" and freeze.ended_by_kind == "made_canonical"
        assert open_freeze(people.document) is None


def test_command_keeps_the_distinct_approver_check(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any
) -> None:
    from editions.models import Edition, Freeze

    # One person who accepted and holds *freeze* and *make canonical*, as a lone operator would.
    people = edition_cast(editors=("a",), reviewers=("o",), approvers=("o",))
    commit_version(people.document, people["a"], BODY, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(people.document, people["o"])
    migrated_tenant.require_distinct_approver = True
    migrated_tenant.save(update_fields=["require_distinct_approver"])

    with pytest.raises(CommandError, match="distinct_approver"):
        _run(migrated_tenant.number, people.document.number, people["o"])
    with schema_context(migrated_tenant.number):
        assert not Freeze.objects.exists() and not Edition.objects.exists()

    migrated_tenant.require_distinct_approver = False
    migrated_tenant.save(update_fields=["require_distinct_approver"])
    assert "edition 1.0" in _run(migrated_tenant.number, people.document.number, people["o"])


def test_command_freezes_nothing_it_cannot_make_canonical(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any
) -> None:
    from editions.models import Freeze

    people = edition_cast()
    commit_version(people.document, people["a"], BODY, "edit")

    with pytest.raises(CommandError, match="nothing_accepted"):
        _run(migrated_tenant.number, people.document.number, people["p"])
    with schema_context(migrated_tenant.number):
        review.accept(people.document, people["r"])
    commit_version(
        people.document, people["a"], BODY + "\nThe second synthetic sentence.\n", "edit"
    )
    with pytest.raises(CommandError, match="unaccepted_changes"):
        _run(migrated_tenant.number, people.document.number, people["p"])
    with pytest.raises(CommandError, match="not_permitted"):
        _run(migrated_tenant.number, people.document.number, people["a"])
    with schema_context(migrated_tenant.number):
        assert not Freeze.objects.exists()


def test_command_run_again_skips_what_is_made(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any
) -> None:
    from editions.models import Edition

    people = edition_cast()
    commit_version(people.document, people["a"], BODY, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(people.document, people["r"])
    _run(migrated_tenant.number, people.document.number, people["p"])

    again = _run(migrated_tenant.number, people.document.number, people["p"])

    assert again.strip() == (
        f"document {people.document.number} · edition 1.0 already made — skipped"
    )
    with schema_context(migrated_tenant.number):
        assert list(Edition.objects.values_list("number", flat=True)) == ["1.0"]


def test_command_on_a_frozen_document_keeps_its_freeze(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any
) -> None:
    from editions import services as editions
    from editions.models import Freeze

    people = edition_cast()
    commit_version(people.document, people["a"], BODY, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(people.document, people["r"])
        editions.freeze(people.document, people["p"], "Synthetic first reason")

    _run(migrated_tenant.number, people.document.number, people["p"], "Synthetic second reason")

    with schema_context(migrated_tenant.number):
        freeze = Freeze.objects.get()
        assert freeze.reason == "Synthetic first reason"
        assert freeze.ended_by_kind == "made_canonical"
