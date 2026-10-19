"""The distinct-approver check (DL-0092, DL-0101, DL-0115): with the tenant's check on, the
approver may have performed none of the acceptances between the previous edition and this one —
not merely not the last; with it off, a reviewer may approve their own acceptance.

People and groups are synthetic examples; the text is invented.
"""

from __future__ import annotations

from typing import Any

import pytest

from review import services as review
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

WRITTEN = (
    "# General provisions\n\n"
    "A request for approval is made in writing.\n"
    "A request is considered within ten days, unless set otherwise.\n"
)
# A comma: the run a colleague accepts after the substantive one (DL-0115's case).
COMMA = WRITTEN.replace("ten days, unless", "ten days unless")
LATER = COMMA + "\nA copy of the decision goes to the applicant that day.\n"
REASON = "Synthetic reason: agreeing it with the legal department"


def _check(tenant: Any, on: bool) -> None:
    tenant.require_distinct_approver = on
    tenant.save()


def test_any_acceptance_since_the_previous_edition(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any, repository: Any
) -> None:
    """R accepts the substantive run as `0.1`, C accepts a comma as `0.2`: R is not the last
    acceptor, and is refused all the same; T, who accepted nothing, is allowed."""
    from editions import services as editions
    from editions.models import Edition

    _check(migrated_tenant, True)
    people = edition_cast(editors=("a",), reviewers=("r", "c"), approvers=("r", "c", "t"))
    document = people.document
    commit_version(document, people["a"], WRITTEN, "edit")
    with schema_context(migrated_tenant.number):
        assert review.accept(document, people["r"]).number == "0.1"
    commit_version(document, people["a"], COMMA, "edit")
    with schema_context(migrated_tenant.number):
        assert review.accept(document, people["c"]).number == "0.2"
        editions.freeze(document, people["t"], REASON)
    head = repository.head(document)

    with schema_context(migrated_tenant.number):
        assert editions.canonical_refusal(document, people["r"]) == "distinct_approver"
        with pytest.raises(editions.CanonicalRefused) as refused:
            editions.make_canonical(document, people["r"])
        assert refused.value.reason == "distinct_approver"
        assert not Edition.objects.exists()
    assert repository.head(document) == head

    with schema_context(migrated_tenant.number):
        # C, who accepted the last run and holds *make canonical*: refused too.
        assert editions.canonical_refusal(document, people["c"]) == "distinct_approver"
        assert editions.canonical_refusal(document, people["t"]) is None
        edition = editions.make_canonical(document, people["t"])
        assert edition.number == "1.0"
        assert edition.approved_by_id == people["t"].pk
    assert repository.kinds(document)[-1] == "approval"


def test_acceptances_before_the_previous_edition_do_not_count(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any
) -> None:
    """R accepted `0.1`, which became edition `1.0`; C accepted `1.1` since. R may make `2.0`:
    the window is *since the previous edition* (DL-0115)."""
    from editions import services as editions

    _check(migrated_tenant, True)
    people = edition_cast(editors=("a",), reviewers=("r", "c"), approvers=("r", "c", "t"))
    document = people.document
    commit_version(document, people["a"], WRITTEN, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
        editions.freeze(document, people["t"], REASON)
        assert editions.make_canonical(document, people["t"]).number == "1.0"
    commit_version(document, people["a"], LATER, "edit")
    with schema_context(migrated_tenant.number):
        assert review.accept(document, people["c"]).number == "1.1"
        editions.freeze(document, people["t"], REASON)

        assert editions.canonical_refusal(document, people["r"]) is None
        edition = editions.make_canonical(document, people["r"])
        assert edition.number == "2.0"
        assert edition.approved_by_id == people["r"].pk


def test_self_approval_allowed_when_off(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any
) -> None:
    """The check off (the default, DL-0092): R accepts, freezes and makes canonical alone."""
    from editions import services as editions
    from review.models import Acceptance

    _check(migrated_tenant, False)
    people = edition_cast(editors=("a",), reviewers=("r",), approvers=("r",))
    document, reviewer = people.document, people["r"]
    commit_version(document, people["a"], WRITTEN, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, reviewer)
        editions.freeze(document, reviewer, REASON)

        assert editions.canonical_refusal(document, reviewer) is None
        edition = editions.make_canonical(document, reviewer)

        assert edition.number == "1.0"
        assert edition.approved_by_id == Acceptance.objects.get().reviewer_id == reviewer.pk


def test_the_check_switched_from_the_settings_page(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any, member_of: Any
) -> None:
    """The check as an administrator sets it on Administration › Settings: on, an approver who
    accepted the run since the previous edition is refused; off again, they make it canonical."""
    from editions import services as editions

    admin, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    people = edition_cast(editors=("a",), reviewers=("r",), approvers=("r",))
    document, reviewer = people.document, people["r"]
    commit_version(document, people["a"], WRITTEN, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, reviewer)
        editions.freeze(document, reviewer, REASON)

    page = "/administration/tenant/settings/"
    on = {
        "attachment_max_mb": "5",
        "hold_inactivity_minutes": "30",
        "require_distinct_approver": "on",
    }
    assert admin.post(page, on).status_code == 303
    with schema_context(migrated_tenant.number):
        assert editions.canonical_refusal(document, reviewer) == "distinct_approver"

    off = {"attachment_max_mb": "5", "hold_inactivity_minutes": "30"}
    assert admin.post(page, off).status_code == 303
    with schema_context(migrated_tenant.number):
        assert editions.canonical_refusal(document, reviewer) is None
        assert editions.make_canonical(document, reviewer).number == "1.0"
