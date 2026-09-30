"""The cases the review of freezing and making canonical found: an edition's freeze left open, an
operator's end over a stopped approval, a tag in the way, an approval over unaccepted work, the
confirmation outrun by an acceptance, a right lost mid-hold during a freeze, a reason that reorders
the band, a reservation's holder named, the edition's authorship asked for, and the list's cost.

People and groups are synthetic examples; the text is invented.
"""

from __future__ import annotations

import html
from typing import Any

import pytest
from django.utils import timezone

from access.rights import Right
from documents import bundle, gitstore, reconcile
from documents.identity import identity_for
from documents.locks import document_lock
from review import services as review
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

FIRST = "Заяву на погодження подають письмово.\n"
SECOND = FIRST + "\nКопію рішення надсилають заявникові того ж дня.\n"
THIRD = SECOND + "\nРеєстр заяв веде відповідальний виконавець.\n"
REASON = "Синтетична причина: чекаємо рішення ради"


def _accepted_and_frozen(migrated_tenant: Any, people: Any, commit_version: Any) -> Any:
    from editions import services as editions

    version = commit_version(people.document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(people.document, people["r"])
        editions.freeze(people.document, people["p"], REASON)
    return version


def test_an_unfinished_edition_is_finished_by_the_reconciler(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any
) -> None:
    """An edition whose tag is gone and whose freeze a hand reopened: reported as
    `edition_unfinished`, finished on repair, and reported by nothing afterwards; meanwhile the
    reopened freeze counts as over, so the document is not held frozen by it."""
    from editions import services as editions
    from editions.models import Freeze, open_freeze

    people = edition_cast()
    _accepted_and_frozen(migrated_tenant, people, commit_version)
    number = migrated_tenant.number
    with schema_context(number):
        edition = editions.make_canonical(people.document, people["p"])
        Freeze.objects.filter(pk=edition.freeze_id).update(
            ended_by_kind="", ended_by=None, ended_at=None
        )
        assert open_freeze(people.document) is None
    repo = gitstore.open_repository(number, people.document.number)
    repo.references.delete("refs/tags/1.0")

    found = reconcile.run(number, people.document.number)
    assert [f.kind for f in found if f.kind != reconcile.AUTHORSHIP_MISSING] == [
        reconcile.EDITION_UNFINISHED
    ]
    reconcile.run(number, people.document.number, repair=True)

    assert editions.tagged(repo, "1.0") is not None
    with schema_context(number):
        assert Freeze.objects.get(pk=edition.freeze_id).ended_by_kind == "made_canonical"
    again = reconcile.run(number, people.document.number)
    assert [f for f in again if f.kind != reconcile.AUTHORSHIP_MISSING] == []


def test_an_edition_row_that_differs_is_reported(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any
) -> None:
    from datetime import timedelta

    from editions import services as editions
    from editions.models import Edition

    people = edition_cast()
    _accepted_and_frozen(migrated_tenant, people, commit_version)
    number = migrated_tenant.number
    with schema_context(number):
        edition = editions.make_canonical(people.document, people["p"])
        moved = edition.approved_at - timedelta(days=1)
        Edition.objects.filter(pk=edition.pk).update(approved_at=moved)

    found = reconcile.run(number, people.document.number, repair=True)

    assert [f.kind for f in found if f.kind == reconcile.EDITION_DIFFERS] == [
        reconcile.EDITION_DIFFERS
    ]
    with schema_context(number):
        assert Edition.objects.get(pk=edition.pk).approved_at == moved


def test_a_freeze_the_rows_lost_is_derived_from_the_approval(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any
) -> None:
    """A restore that returns the approval's commit with rows from before its freeze (DL-0355):
    the next writer derives the freeze the section proves, and the edition with it."""
    from audit.models import AuditEvent
    from editions import services as editions
    from editions.models import Edition, Freeze

    people = edition_cast()
    _accepted_and_frozen(migrated_tenant, people, commit_version)
    with schema_context(migrated_tenant.number):
        with pytest.raises(review.InjectedFault):
            editions.make_canonical(people.document, people["p"], fault_at=1)
        Freeze.objects.all().delete()
        review.settle_head(people.document)

        edition = Edition.objects.get()
        freeze = edition.freeze
        assert (freeze.reason, freeze.ended_by_kind) == ("", "made_canonical")
        assert freeze.frozen_at == freeze.ended_at == edition.approved_at
        assert freeze.frozen_by_id == people["p"].pk
    assert AuditEvent.objects.filter(action="document.freeze_derived").exists()


def test_a_freeze_ends_no_earlier_than_it_began(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any
) -> None:
    """A freeze and its approval in one second, as the command makes them: the freeze is taken
    in whole seconds, and ends at or after its start."""
    from editions.models import Edition

    people = edition_cast()
    _accepted_and_frozen(migrated_tenant, people, commit_version)
    from editions import services as editions

    with schema_context(migrated_tenant.number):
        edition = editions.make_canonical(people.document, people["p"])
        freeze = Edition.objects.get(pk=edition.pk).freeze
        assert freeze.frozen_at.microsecond == 0
        assert freeze.ended_at is not None and freeze.ended_at >= freeze.frozen_at
        assert edition.approved_at >= freeze.frozen_at


def test_end_freeze_after_a_stopped_approval_finishes_the_approval(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any
) -> None:
    from editions import services as editions
    from editions.models import Edition, Freeze

    people = edition_cast()
    _accepted_and_frozen(migrated_tenant, people, commit_version)
    with schema_context(migrated_tenant.number):
        with pytest.raises(review.InjectedFault):
            editions.make_canonical(people.document, people["p"], fault_at=1)
        # The operator's end meets the approval settled first: the freeze it ended is not open.
        with pytest.raises(ValueError, match="not frozen"):
            editions.end_freeze(people.document, "Синтетичне рішення оператора")
        assert list(Edition.objects.values_list("number", flat=True)) == ["1.0"]
        assert Freeze.objects.get().ended_by_kind == "made_canonical"


def test_a_tag_in_the_way_stops_before_the_commit(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any, repository: Any
) -> None:
    from editions import services as editions
    from editions.models import Edition

    people = edition_cast()
    _accepted_and_frozen(migrated_tenant, people, commit_version)
    head = repository.head(people.document)
    repo = gitstore.open_repository(migrated_tenant.number, people.document.number)
    gitstore.tag(repo, "1.0", head, identity_for(people["p"]), "Синтетична мітка")

    with schema_context(migrated_tenant.number):
        with pytest.raises(review.RecordIncomplete):
            editions.make_canonical(people.document, people["p"])
        assert not Edition.objects.exists()
    assert repository.head(people.document) == head


def test_an_approval_over_unaccepted_work_is_not_derived(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any, repository: Any
) -> None:
    """An approval section written by hand over a version nobody accepted: neither the next
    writer nor the reconciler records it as an edition (DL-0267)."""
    from editions import services as editions
    from editions.models import Edition

    people = edition_cast()
    accepted = _accepted_and_frozen(migrated_tenant, people, commit_version)
    commit_version(people.document, people["r"], SECOND, "reviewer_edit")
    number = migrated_tenant.number
    repo = gitstore.open_repository(number, people.document.number)
    now = timezone.now().replace(microsecond=0)
    entry = bundle.PassportEntry(
        kind="approval",
        number="1.0",
        at=now,
        by=str(people["p"].pk),
        version=accepted.commit_sha,
        edition="1.0",
    )
    with schema_context(number), document_lock(number, people.document.number):
        head = repository.head(people.document)
        passport = gitstore.read(repo, "passport.md", head).decode()
        sha = gitstore.commit(
            repo,
            {"passport.md": bundle.append_passport(passport, entry).encode()},
            identity_for(people["p"], at=now),
            "Made canonical as 1.0",
            gitstore.Kind.APPROVAL,
        )
        found = editions.derivable_approval(people.document, repo, sha)
        assert found == "a version waits for review before it"
        with pytest.raises(review.RecordIncomplete):
            review.settle_head(people.document)
    reconcile.run(number, people.document.number, repair=True)
    with schema_context(number):
        assert not Edition.objects.exists()


def test_the_confirmation_is_the_edition(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any, settings: Any
) -> None:
    """An acceptance between the confirmation and the click: refused, and the confirmation shown
    again naming the new version (as DL-0333 for accepting)."""
    from editions.models import Edition

    settings.LANGUAGE_CODE = "en"
    people = edition_cast()
    first = _accepted_and_frozen(migrated_tenant, people, commit_version)
    approver = people.clients["p"]
    confirmation = approver.get(f"/document/{people.document.number}/make-canonical/")
    assert f'value="{first.commit_sha}"' in confirmation.content.decode()
    assert "Version 0.1 becomes edition 1.0" in confirmation.content.decode()
    commit_version(people.document, people["r"], SECOND, "reviewer_edit")
    with schema_context(migrated_tenant.number):
        assert review.accept(people.document, people["r"]).number == "0.2"

    stale = approver.post(
        f"/document/{people.document.number}/make-canonical/", {"confirmed": first.commit_sha}
    )

    assert stale.status_code == 409
    body = stale.content.decode()
    assert "What is accepted changed while you were confirming" in body
    assert "Version 0.2 becomes edition 1.0" in body
    with schema_context(migrated_tenant.number):
        assert not Edition.objects.exists()


def test_a_right_lost_mid_hold_during_a_freeze(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any
) -> None:
    """A reviewer holds the document during the freeze; *accept* is taken from their group; their
    finish is refused under the lock, and the draft stays."""
    from editing import holds
    from editing import services as editing
    from editing.models import Draft

    people = edition_cast()
    _accepted_and_frozen(migrated_tenant, people, commit_version)
    with schema_context(migrated_tenant.number):
        hold = holds.take(people.document, people["r"])
        draft = Draft.objects.get(hold=hold)
        draft.content = {**draft.content, "document.md": SECOND}
        draft.save()
        group = people.groups["reviewers"]
        group.revoke(Right.ACCEPT, by=people["a"])
        group.grant(Right.EDIT, by=people["a"])
        with pytest.raises(holds.Frozen):
            editing.commit_draft(hold, people["r"], "Синтетична правка")
        assert Draft.objects.filter(hold=hold).exists()


def test_a_reason_that_reorders_the_band_is_refused(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any
) -> None:
    from editions import services as editions

    people = edition_cast()
    commit_version(people.document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        with pytest.raises(editions.FreezeRefused) as refused:
            editions.freeze(people.document, people["p"], "причина ‮дзеркально")
        assert refused.value.reason == "reason_invalid"


def test_a_reservations_holder_is_named_to_who_may_freeze(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any
) -> None:
    """A reservation's holder is named to anyone who may edit (ADR-0009); *freeze* includes
    *edit*."""
    from editing import holds

    people = edition_cast()
    commit_version(people.document, people["a"], FIRST, "edit")
    people["a"].display_name = "Синтетична редакторка"
    people["a"].save(update_fields=["display_name"])
    with schema_context(migrated_tenant.number):
        hold = holds.take(people.document, people["a"])
        hold.reserved_at = timezone.now()
        hold.save(update_fields=["reserved_at"])

    page = people.clients["p"].get(f"/document/{people.document.number}/").content.decode()

    assert "Синтетична редакторка" in page


def test_make_canonical_asks_for_the_new_heads_authorship(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    repository: Any,
    queued_authorship: list[Any],
) -> None:
    from editions import services as editions

    people = edition_cast()
    accepted = _accepted_and_frozen(migrated_tenant, people, commit_version)
    queued_authorship.clear()
    with schema_context(migrated_tenant.number):
        editions.make_canonical(people.document, people["p"])
    head = repository.head(people.document)
    shas = {job[2] for job in queued_authorship}
    assert {accepted.commit_sha, head} <= shas
    report = reconcile.run(migrated_tenant.number, people.document.number)
    assert [f for f in report if f.kind != reconcile.AUTHORSHIP_MISSING] == []


def test_the_list_costs_a_fixed_number_of_queries(
    migrated_tenant: Any,
    edition_cast: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    django_assert_max_num_queries: Any,
) -> None:
    """The version columns read rights, editions and acceptances once, whatever the documents'
    number; only each repository is read per document."""
    from documents.models import Document
    from editions.visible import visible_many

    people = edition_cast()
    documents = [people.document]
    for n in range(4):
        document = new_document(people["a"], f"Синтетичний порядок {n}")
        link_group(document, [Right.VIEW_PENDING], [people.memberships["p"]], people["a"])
        documents.append(document)
    for document in documents:
        commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        rows = list(Document.objects.filter(pk__in=[d.pk for d in documents]))
        with django_assert_max_num_queries(40) as one:
            visible_many(people["p"], rows[:1])
        with django_assert_max_num_queries(len(one.captured_queries) + 4 * 3):
            visible_many(people["p"], rows)


def test_the_command_is_marked_in_the_audit(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any
) -> None:
    from django.core.management import call_command

    from audit.models import AuditEvent

    people = edition_cast()
    commit_version(people.document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(people.document, people["r"])
    call_command(
        "make_canonical",
        tenant=migrated_tenant.number,
        document=people.document.number,
        member=people["p"].email,
        reason="",
    )
    for action in ("document.frozen", "document.made_canonical"):
        event = AuditEvent.objects.get(action=action)
        assert event.after["via"] == "make_canonical", action


def test_a_reviewer_commits_through_the_service_while_frozen(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any
) -> None:
    from editing import holds
    from editing import services as editing
    from editing.models import Draft

    people = edition_cast()
    _accepted_and_frozen(migrated_tenant, people, commit_version)
    with schema_context(migrated_tenant.number):
        hold = holds.take(people.document, people["r"])
        draft = Draft.objects.get(hold=hold)
        draft.content = {**draft.content, "document.md": SECOND}
        draft.save()
        version = editing.commit_draft(hold, people["r"], "Синтетична правка")
        assert version.kind == "reviewer_edit"
        assert review.accept(people.document, people["r"]).number == "0.2"


def test_an_approver_without_view_pending_makes_it_canonical(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any, member_of: Any, link_group: Any
) -> None:
    """*Make canonical* includes *view accepted*, never *view pending* (DL-0234), and is enough."""
    from access.rights import rights_on
    from editions import services as editions

    people = edition_cast()
    _accepted_and_frozen(migrated_tenant, people, commit_version)
    _, approver, membership = member_of("q.synthetic@example.test")
    link_group(people.document, [Right.MAKE_CANONICAL], [membership], people["a"])
    with schema_context(migrated_tenant.number):
        assert Right.VIEW_PENDING not in rights_on(approver, people.document)
        assert editions.make_canonical(people.document, approver).number == "1.0"


def test_the_confirmation_refuses_after_a_stopped_approval(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any, settings: Any
) -> None:
    """Stopped after the passport commit: the page names no edition it cannot make."""
    from editions import services as editions

    settings.LANGUAGE_CODE = "en"
    people = edition_cast()
    _accepted_and_frozen(migrated_tenant, people, commit_version)
    with schema_context(migrated_tenant.number):
        with pytest.raises(review.InjectedFault):
            editions.make_canonical(people.document, people["p"], fault_at=1)
    client = people.clients["p"]

    answer = client.get(f"/document/{people.document.number}/make-canonical/", follow=True)

    body = html.unescape(answer.content.decode())
    assert "The document's record is incomplete" in body
    assert "becomes edition" not in body


def test_the_refusals_are_drawn_with_their_reasons(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any, settings: Any
) -> None:
    from editions import services as editions

    settings.LANGUAGE_CODE = "en"
    people = edition_cast()
    commit_version(people.document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(people.document, people["r"])
    page = people.clients["p"].get(f"/document/{people.document.number}/").content.decode()
    assert "Freeze the document first." in page
    commit_version(people.document, people["a"], SECOND, "edit")
    with schema_context(migrated_tenant.number):
        editions.freeze(people.document, people["p"], REASON)
    page = people.clients["p"].get(f"/document/{people.document.number}/").content.decode()
    assert "Changes are waiting for review; they must be accepted first." in page
