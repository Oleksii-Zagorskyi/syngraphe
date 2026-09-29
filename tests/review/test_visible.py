"""The visible version, the alpha's thin rule (DL-0348): *view pending* sees the
newest content version of the run, or the base when the run is empty; *view accepted* sees the
base — the latest accepted content version, or the `created` one before any acceptance; anything
less sees nothing. The label is the accepted number for the base, the pending number otherwise.

People and groups are synthetic examples; the text is invented.
"""

from __future__ import annotations

from typing import Any

import pytest

from access.rights import Right
from documents.models import Version
from review import visible
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

FIRST = "# Загальні положення\n\nЗаяву на погодження подають письмово.\n"
SECOND = FIRST + "\nКопію рішення надсилають заявникові того ж дня.\n"
THIRD = SECOND + "\nРеєстр заяв веде відповідальний виконавець.\n"


def _reader(
    member_of: Any, link_group: Any, document: Any, right: Right, by: Any, name: str
) -> Any:
    """A member whose only group linked to `document` holds `right` alone."""
    _, user, membership = member_of(f"{name}.synthetic@example.test")
    link_group(document, [right], [membership], by)
    return user


def test_pending_sees_the_newest_content_version(
    migrated_tenant: Any,
    cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    accepted_directly: Any,
) -> None:
    people = cast(editors=("a",), reviewers=("r",))
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    accepted_directly(document, people["r"])
    newest = commit_version(document, people["a"], SECOND, "edit")
    holder = _reader(member_of, link_group, document, Right.VIEW_PENDING, people["a"], "pending")

    with schema_context(migrated_tenant.number):
        shown = visible.latest_visible(holder, document)
        assert shown is not None
        assert shown.pk == newest.pk
        assert visible.label(holder, document, shown) == "0.1-1"


def test_pending_with_an_empty_run_sees_the_base(
    migrated_tenant: Any,
    cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    accepted_directly: Any,
) -> None:
    people = cast(editors=("a",), reviewers=("r",))
    document = people.document
    accepted_content = commit_version(document, people["a"], FIRST, "edit")
    accepted_directly(document, people["r"])
    holder = _reader(member_of, link_group, document, Right.VIEW_PENDING, people["a"], "pending")

    with schema_context(migrated_tenant.number):
        shown = visible.latest_visible(holder, document)
        assert shown is not None
        # The content version the acceptance decided on, not the acceptance's own commit.
        assert shown.pk == accepted_content.pk
        assert visible.label(holder, document, shown) == "0.1"


def test_accepted_sees_the_latest_accepted_content_version(
    migrated_tenant: Any,
    cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    accepted_directly: Any,
) -> None:
    people = cast(editors=("a",), reviewers=("r",))
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    accepted_directly(document, people["r"])
    second = commit_version(document, people["a"], SECOND, "edit")
    accepted_directly(document, people["r"])
    commit_version(document, people["a"], THIRD, "edit")
    reader = _reader(member_of, link_group, document, Right.VIEW_ACCEPTED, people["a"], "reader")

    with schema_context(migrated_tenant.number):
        shown = visible.latest_visible(reader, document)
        assert shown is not None
        # The later acceptance's base; the pending third version is not the reader's.
        assert shown.pk == second.pk
        assert visible.label(reader, document, shown) == "0.2"


def test_accepted_before_any_acceptance_sees_the_created_version(
    migrated_tenant: Any, cast: Any, member_of: Any, link_group: Any, commit_version: Any
) -> None:
    people = cast(editors=("a",), reviewers=("r",))
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    reader = _reader(member_of, link_group, document, Right.VIEW_ACCEPTED, people["a"], "reader")

    with schema_context(migrated_tenant.number):
        created = Version.objects.get(document=document, kind="created")
        shown = visible.latest_visible(reader, document)
        assert shown is not None
        assert shown.pk == created.pk
        # `0.0` names no version and is never shown alone (DL-0272): no number before any
        # acceptance.
        assert visible.label(reader, document, shown) == ""
        whole = visible.shown(reader, document)
        assert whole is not None and whole.version.pk == created.pk
        assert (whole.number, whole.accepted) == ("", False)


def test_view_canonical_alone_sees_nothing(
    migrated_tenant: Any,
    cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    accepted_directly: Any,
) -> None:
    people = cast(editors=("a",), reviewers=("r",))
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    accepted_directly(document, people["r"])
    reader = _reader(member_of, link_group, document, Right.VIEW_CANONICAL, people["a"], "canon")

    with schema_context(migrated_tenant.number):
        assert visible.latest_visible(reader, document) is None


def test_no_right_sees_nothing(
    migrated_tenant: Any, cast: Any, member_of: Any, commit_version: Any, accepted_directly: Any
) -> None:
    people = cast(editors=("a",), reviewers=("r",))
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    accepted_directly(document, people["r"])
    _, stranger, _ = member_of("stranger.synthetic@example.test")

    with schema_context(migrated_tenant.number):
        assert visible.latest_visible(stranger, document) is None
