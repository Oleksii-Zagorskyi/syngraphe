"""A return stopped between its passport commit and its rows is derived from the passport's
section — by the next writer under the lock, or by the reconciler — and a finish stopped under a
return is recognised and completed (DL-0111, DL-0114, DL-0318).

People, organisations, groups and texts are synthetic examples: every address ends in
`@example.test`, and every text is invented.
"""

from __future__ import annotations

from typing import Any

import pytest

from documents import reconcile
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.crash,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

REASON = "Synthetic reason: the time limits contradict the section on the register"
FIRST = (
    "# General provisions\n\n"
    "A request for approval is made in writing.\n"
    "A request is considered within ten days.\n"
)
SECOND = FIRST + "\nA copy of the decision goes to the applicant that day.\n"


def stopped_return(tenant: Any, cast: Any, commit_version: Any, repository: Any) -> Any:
    """`a` commits one version; `r` returns it, stopped right after the passport commit. The
    cast, with `.returned_sha` the return's commit and `.last` the run's last version."""
    from review import services

    people = cast(editors=("a",), reviewers=("r",))
    people.last = commit_version(people.document, people["a"], FIRST, "edit")
    with schema_context(tenant.number):
        with pytest.raises(services.InjectedFault):
            services.return_run(
                people.document,
                people["r"],
                REASON,
                confirmed=people.last.commit_sha,
                fault_at=1,
            )
    assert repository.kinds(people.document)[-1] == "return"
    people.returned_sha = repository.head(people.document)
    return people


def assert_derived(tenant: Any, people: Any) -> Any:
    """The `Return` row and its `return` version, as the section says; the row."""
    from documents.models import Version
    from review.models import Return

    with schema_context(tenant.number):
        created = Version.objects.get(document=people.document, kind="created")
        row = Version.objects.get(document=people.document, commit_sha=people.returned_sha)
        assert row.kind == "return"
        returned = Return.objects.get()
        assert returned.version_id == row.pk
        assert returned.returned_from_id == created.pk
        assert returned.reviewer_id == people["r"].pk
        assert returned.reason == REASON
        assert returned.at is not None
        return returned


def test_a_stopped_return_is_derived(
    migrated_tenant: Any, cast: Any, commit_version: Any, repository: Any
) -> None:
    from review import services
    from review.models import Return

    people = stopped_return(migrated_tenant, cast, commit_version, repository)
    with schema_context(migrated_tenant.number):
        assert not Return.objects.exists()

    found = {
        (f.kind, f.detail)
        for f in reconcile.run(
            tenant=migrated_tenant.number, document=people.document.number, repair=False
        )
    }

    assert ("commit_without_row", people.returned_sha) in found, found
    assert ("passport_entry_without_row", "return") in found, found
    with schema_context(migrated_tenant.number):
        assert not Return.objects.exists()

    with schema_context(migrated_tenant.number):
        acceptance = services.accept(people.document, people["r"])

    returned = assert_derived(migrated_tenant, people)
    with schema_context(migrated_tenant.number):
        assert acceptance.number == "0.1"
        assert returned.version.created_at <= acceptance.version.created_at
    assert repository.kinds(people.document) == ["created", "edit", "return", "acceptance"]


def test_the_reconciler_derives_a_stopped_return(
    migrated_tenant: Any, cast: Any, commit_version: Any, repository: Any
) -> None:
    people = stopped_return(migrated_tenant, cast, commit_version, repository)
    head = repository.head(people.document)

    reconcile.run(tenant=migrated_tenant.number, document=people.document.number, repair=True)

    assert_derived(migrated_tenant, people)
    assert repository.head(people.document) == head
    again = reconcile.run(tenant=migrated_tenant.number, document=people.document.number)
    # The head's authorship is the worker's, which the suite replaces: what concerns the return's
    # own rows is gone.
    assert not [
        f for f in again if f.detail == people.returned_sha and f.kind != "authorship_missing"
    ], again
    assert not [f for f in again if f.kind == "passport_entry_without_row"], again


def test_a_stopped_finish_under_a_return(
    migrated_tenant: Any, cast: Any, commit_version: Any, repository: Any
) -> None:
    """`b` sends a version; `a` takes the document, and their finish stops right after its
    commit with the hold still open; `r` returns the run. Sent again, `a`'s finish is the stopped
    one completed: no second content version, the hold released `finished`."""
    from documents.models import Version
    from editing import holds
    from editing import services as editing
    from editing.models import Draft, Hold
    from review import services

    people = cast(editors=("a", "b"), reviewers=("r",))
    document = people.document
    commit_version(document, people["b"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        hold = holds.take(document, people["a"])
        draft = Draft.objects.get(hold=hold)
        draft.content = {
            **draft.content,
            "document.md": draft.content["document.md"] + "\nA new synthetic sentence.\n",
        }
        draft.save()
        with pytest.raises(editing.InjectedFault):
            editing.commit_draft(hold, people["a"], "Synthetic edit", fault_at=1)
    stopped = repository.head(document)
    with schema_context(migrated_tenant.number):
        assert Hold.objects.get(pk=hold.pk).released_at is None
        services.return_run(document, people["r"], REASON)
    assert repository.kinds(document) == ["created", "edit", "edit", "return"]

    with schema_context(migrated_tenant.number):
        version = editing.commit_draft(Hold.objects.get(pk=hold.pk), people["a"], "Synthetic edit")

    assert version.commit_sha == stopped
    assert repository.kinds(document) == ["created", "edit", "edit", "return"]
    with schema_context(migrated_tenant.number):
        assert (
            Version.objects.filter(document=document, kind__in=["edit", "reviewer_edit"]).count()
            == 2
        )
        finished = Hold.objects.get(pk=hold.pk)
        assert finished.released_at is not None
        assert finished.release_kind == "finished"
        assert not Draft.objects.filter(hold=hold).exists()
