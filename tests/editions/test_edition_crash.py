"""An edition stopped between its steps is finished from the passport — by the reconciler, or by
the next writer under the lock — and a tag without its passport section is reported, never
repaired (DL-0111, DL-0260).

People and groups are synthetic examples; the text is invented.
"""

from __future__ import annotations

from typing import Any

import pygit2
import pytest

from audit.models import AuditEvent
from documents import bundle, gitstore, reconcile
from documents.identity import identity_for
from review import services as review
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.crash,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

WRITTEN = (
    "# General provisions\n\n"
    "A request for approval is made in writing.\n"
    "A request is considered within ten days.\n"
)
LATER = WRITTEN + "\nA copy of the decision goes to the applicant that day.\n"
REASON = "Synthetic reason: waiting for the committee to report"
# The worker does not run in the suite (`queued_authorship` records its jobs), so the authorship
# of the kept versions is always missing to a report; it is not what these tests are about.
NOT_OURS = {reconcile.AUTHORSHIP_MISSING}


def _tag(migrated_tenant: Any, document: Any, name: str) -> pygit2.Tag | None:
    repo = gitstore.open_repository(migrated_tenant.number, document.number)
    ref = repo.references.get(f"refs/tags/{name}")
    if ref is None:
        return None
    found = repo[ref.target]
    assert isinstance(found, pygit2.Tag), f"{name} is a lightweight tag"
    return found


def _frozen_and_accepted(migrated_tenant: Any, people: Any, commit_version: Any) -> tuple[Any, Any]:
    """`0.1` accepted and the document frozen by the approver: the accepted content version and
    the freeze."""
    from editions import services as editions

    accepted = commit_version(people.document, people["a"], WRITTEN, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(people.document, people["r"])
        freeze = editions.freeze(people.document, people["p"], REASON)
    return accepted, freeze


def _assert_edition_complete(
    migrated_tenant: Any, people: Any, repository: Any, accepted: Any, freeze: Any, head: str
) -> None:
    """The state a whole `make_canonical` leaves: one approval commit at `head`, tagged `1.0`, one
    `EDITION` recording it, the freeze ended as made canonical."""
    from editions.models import Edition, Freeze, open_freeze

    document, approver = people.document, people["p"]
    assert repository.head(document) == head
    assert repository.kinds(document).count("approval") == 1
    tag = _tag(migrated_tenant, document, "1.0")
    assert tag is not None
    assert str(tag.peel(pygit2.Commit).id) == head
    # The tag carries the approver's identity whoever writes it (DL-0260).
    assert tag.tagger.name == str(approver.pk)
    with schema_context(migrated_tenant.number):
        edition = Edition.objects.get()
        assert edition.number == "1.0"
        assert edition.version_id == accepted.pk
        assert edition.approval_version.commit_sha == head
        assert edition.approval_version.kind == "approval"
        assert edition.freeze_id == freeze.pk
        assert edition.approved_by_id == approver.pk
        ended = Freeze.objects.get(pk=freeze.pk)
        assert ended.ended_by_kind == "made_canonical"
        assert ended.ended_at is not None
        assert open_freeze(document) is None


@pytest.mark.parametrize("step", [1, 2, 3])
def test_reconciler_derives_edition(
    step: int,
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    repository: Any,
) -> None:
    """Killed after the passport commit (1), after the tag (2), after the `EDITION` row and the
    freeze's end, which are one transaction (3); `reconcile --repair` finishes what is left, and
    a report afterwards is empty."""
    from editions import services as editions
    from editions.models import Edition

    people = edition_cast()
    document = people.document
    accepted, freeze = _frozen_and_accepted(migrated_tenant, people, commit_version)

    with schema_context(migrated_tenant.number):
        with pytest.raises(review.InjectedFault):
            editions.make_canonical(document, people["p"], fault_at=step)
    head = repository.head(document)
    passport = repository.read(document, "passport.md", head)
    # The commit point was passed at every step: the approval is in the passport.
    assert repository.kinds(document)[-1] == "approval"
    last = bundle.passport_entries(passport)[-1]
    assert (last.kind, last.number, last.edition) == ("approval", "1.0", "1.0")
    if step == 1:
        assert _tag(migrated_tenant, document, "1.0") is None
    else:
        assert _tag(migrated_tenant, document, "1.0") is not None
    if step < 3:
        with schema_context(migrated_tenant.number):
            assert not Edition.objects.exists()

    reconcile.run(migrated_tenant.number, document.number, repair=True)

    # The passport unchanged, nothing committed on top; the rest derived from it.
    assert repository.read(document, "passport.md", head) == passport
    _assert_edition_complete(migrated_tenant, people, repository, accepted, freeze, head)

    report = reconcile.run(migrated_tenant.number, document.number)
    assert [f for f in report if f.kind not in NOT_OURS] == []

    # Idempotent: a second repair derives nothing more.
    reconcile.run(migrated_tenant.number, document.number, repair=True)
    _assert_edition_complete(migrated_tenant, people, repository, accepted, freeze, head)


def test_a_version_after_a_stop_settles_the_approval_first(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any, repository: Any
) -> None:
    """Stopped after the passport commit, then the reviewer — who may hold a frozen document —
    finishes a version: the approval is derived before the version is written on top of it, and
    the version is numbered from the edition."""
    from editing import holds, numbering
    from editing import services as editing
    from editing.models import Draft
    from editions import services as editions
    from editions.models import Edition

    people = edition_cast()
    document, reviewer = people.document, people["r"]
    _frozen_and_accepted(migrated_tenant, people, commit_version)
    with schema_context(migrated_tenant.number):
        with pytest.raises(review.InjectedFault):
            editions.make_canonical(document, people["p"], fault_at=1)
        hold = holds.take(document, reviewer)
        draft = Draft.objects.get(hold=hold)
        draft.content = {**draft.content, "document.md": LATER}
        draft.save()
        editing.commit_draft(hold, reviewer, "Synthetic edit")

        assert list(Edition.objects.values_list("number", flat=True)) == ["1.0"]
        assert numbering.latest(document) == "1.0-1"
    kinds = repository.kinds(document)
    assert kinds[-2] == "approval" and kinds.count("approval") == 1


def test_tag_without_passport_reported(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any, repository: Any
) -> None:
    """A tag `1.0` planted on an accepted document whose passport has no approval: reported, and
    nothing changed — in report mode and on repair alike, the passport being believed."""
    from editions.models import Edition

    people = edition_cast()
    document = people.document
    commit_version(document, people["a"], WRITTEN, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
    head = repository.head(document)
    passport = repository.read(document, "passport.md", head)
    repo = gitstore.open_repository(migrated_tenant.number, document.number)
    gitstore.tag(repo, "1.0", head, identity_for(people["p"]), "Synthetic tag without a section")

    findings = reconcile.run(migrated_tenant.number, document.number)

    planted = [f for f in findings if f.kind == reconcile.TAG_WITHOUT_SECTION]
    assert planted, findings
    assert all(f.document == document.number and not f.repaired for f in planted)

    repaired = reconcile.run(migrated_tenant.number, document.number, repair=True)
    assert [f for f in repaired if f.kind == reconcile.TAG_WITHOUT_SECTION and not f.repaired]

    # Nothing changed: no commit, the passport as it was, no edition, the tag left for a person.
    assert repository.head(document) == head
    assert repository.read(document, "passport.md", head) == passport
    assert repository.kinds(document).count("approval") == 0
    assert _tag(migrated_tenant, document, "1.0") is not None
    with schema_context(migrated_tenant.number):
        assert not Edition.objects.exists()


def _accepted_unfrozen(migrated_tenant: Any, people: Any, commit_version: Any) -> Any:
    """`0.1` accepted and no freeze open: the accepted content version."""
    from editions.models import open_freeze

    accepted = commit_version(people.document, people["a"], WRITTEN, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(people.document, people["r"])
        assert open_freeze(people.document) is None
    return accepted


# replaces tests/editions/test_edition_crash.py
#   ::test_the_next_act_after_a_stop_settles_the_approval_first
def test_the_next_act_after_a_stop_settles_the_approval_first(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any, repository: Any
) -> None:
    """Stopped after the passport commit of an unfrozen approval, then *make canonical*
    again: `settle_head` derives the stopped approval under the lock — no `RecordIncomplete`, no
    second approval commit, no second edition; its zero-length freeze is derived as a repair and
    `document.freeze_derived` audited; the retry meets `nothing_accepted`."""
    from editions import services as editions
    from editions.models import Edition, Freeze, open_freeze

    people = edition_cast()
    document, approver = people.document, people["p"]
    accepted = _accepted_unfrozen(migrated_tenant, people, commit_version)
    with schema_context(migrated_tenant.number):
        with pytest.raises(review.InjectedFault):
            editions.make_canonical(document, approver, fault_at=1)
        assert not Edition.objects.exists()
        assert not Freeze.objects.filter(document=document).exists()
    head = repository.head(document)

    with schema_context(migrated_tenant.number):
        try:
            editions.make_canonical(document, approver)
        except review.RecordIncomplete as incomplete:  # pragma: no cover — the failure reported
            pytest.fail(f"the stopped approval was not settled: {incomplete}")
        except editions.CanonicalRefused as refused:
            # The settled approval made the edition, so the retry meets the next refusal.
            assert refused.reason == "nothing_accepted"
        else:
            pytest.fail("a second edition was made over the stopped one")

        assert list(Edition.objects.values_list("number", flat=True)) == ["1.0"]
        edition = Edition.objects.get()
        assert edition.version_id == accepted.pk
        assert edition.approval_version.commit_sha == head
        assert edition.approval_version.kind == "approval"
        assert edition.approved_by_id == approver.pk
        freeze = Freeze.objects.get(pk=edition.freeze_id)
        assert Freeze.objects.filter(document=document).count() == 1
        assert freeze.frozen_at == freeze.ended_at == edition.approved_at
        assert freeze.frozen_by_id == freeze.ended_by_id == approver.pk
        assert (freeze.reason, freeze.ended_by_kind) == ("", "made_canonical")
        assert open_freeze(document) is None

    # The repository as a whole act leaves it: one approval at `head`, tagged by the approver.
    assert repository.head(document) == head
    assert repository.kinds(document).count("approval") == 1
    tag = _tag(migrated_tenant, document, "1.0")
    assert tag is not None
    assert str(tag.peel(pygit2.Commit).id) == head
    assert tag.tagger.name == str(approver.pk)

    # The settlement is a repair: the derived freeze is audited beside the approval's line.
    derived = AuditEvent.objects.filter(action="document.freeze_derived")
    assert derived.count() == 1
    assert (derived.get().after or {}).get("freeze") == str(freeze.pk)
    made = AuditEvent.objects.get(action="document.made_canonical")
    assert made.actor_id == approver.pk
    assert made.object_id == document.pk
