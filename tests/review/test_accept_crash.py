"""An acceptance stopped between its steps is finished by the reconciler from the passport, and a
row disagreeing with the passport is reported with the passport believed (DL-0111, ADR-0001).

People and groups are synthetic examples; the text is invented.
"""

from __future__ import annotations

from typing import Any

import pytest

from documents import reconcile
from documents.models import Version
from notifications.models import Notification
from review import services
from review.models import Acceptance, CorrectionLine, CorrectionNotice
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.crash,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

WRITTEN = (
    "# Загальні положення\n\n"
    "Заяву на погодження подають письмово.\n"
    "Строк розгляду заяви становить десять днів.\n"
)
CORRECTED = WRITTEN.replace(
    "Строк розгляду заяви становить десять днів.",
    "Заяву розглядають протягом п'яти робочих днів.",
)


@pytest.mark.parametrize("step", [1, 2])
def test_reconciler_derives_acceptance(
    step: int,
    migrated_tenant: Any,
    cast: Any,
    commit_version: Any,
    repository: Any,
    queued_authorship: list[Any],
) -> None:
    """Killed after the passport commit (1), or after the rows and before the notices (2)."""
    people = cast(editors=("a",), reviewers=("r",))
    document, author, reviewer = people.document, people["a"], people["r"]
    written = commit_version(document, author, WRITTEN, "edit")
    corrected = commit_version(document, reviewer, CORRECTED, "reviewer_edit")
    with schema_context(migrated_tenant.number):
        with pytest.raises(services.InjectedFault):
            services.accept(document, reviewer, fault_at=step)
        assert Acceptance.objects.exists() == (step == 2)
    head = repository.head(document)
    passport = repository.read(document, "passport.md", head)

    reconcile.run(tenant=migrated_tenant.number, document=document.number, repair=True)

    # The passport unchanged; the row derived from it; the notices computed for the row.
    assert repository.head(document) == head
    assert repository.read(document, "passport.md", head) == passport
    with schema_context(migrated_tenant.number):
        created = Version.objects.get(document=document, kind="created")
        acceptance = Acceptance.objects.get()
        assert acceptance.number == "0.1"
        assert acceptance.version.commit_sha == head and acceptance.version.kind == "acceptance"
        assert acceptance.reviewer_id == reviewer.pk
        assert acceptance.accepted_from_id == created.pk
        assert services.accepted_content_version(acceptance).pk == corrected.pk
        assert acceptance.notices_computed_at is not None
        notice = CorrectionNotice.objects.get(acceptance=acceptance)
        assert notice.author_id == author.pk
        line = CorrectionLine.objects.get(notice=notice)
        assert (line.changing_version_id, line.author_version_id) == (corrected.pk, written.pk)
        notification = Notification.objects.get(event="correction_notice")
        assert (notification.user_id, notification.correction_notice_id) == (author.pk, notice.pk)

    # Idempotent: a second repair writes nothing more.
    reconcile.run(tenant=migrated_tenant.number, document=document.number, repair=True)
    with schema_context(migrated_tenant.number):
        assert Acceptance.objects.count() == 1
        assert CorrectionNotice.objects.count() == 1
        assert CorrectionLine.objects.count() == 1
        assert Notification.objects.filter(event="correction_notice").count() == 1
        # The run's author told once that it was accepted, the reviewer not at all.
        assert list(
            Notification.objects.filter(event="accepted").values_list("user_id", flat=True)
        ) == [author.pk]
    assert repository.head(document) == head


def test_passport_wins(
    migrated_tenant: Any,
    cast: Any,
    commit_version: Any,
    repository: Any,
    queued_authorship: list[Any],
) -> None:
    people = cast(editors=("a",), reviewers=("r",))
    document = people.document
    commit_version(document, people["a"], WRITTEN, "edit")
    with schema_context(migrated_tenant.number):
        acceptance = services.accept(document, people["r"])
    head = repository.head(document)
    passport = repository.read(document, "passport.md", head)
    agreeing = {
        (f.kind, f.detail)
        for f in reconcile.run(tenant=migrated_tenant.number, document=document.number)
    }
    with schema_context(migrated_tenant.number):
        Acceptance.objects.filter(pk=acceptance.pk).update(number="0.7")

    findings = reconcile.run(tenant=migrated_tenant.number, document=document.number)

    assert not [f for f in findings if f.kind == "unreadable"], findings
    disagreement = [f for f in findings if (f.kind, f.detail) not in agreeing]
    assert disagreement, findings
    assert all(f.document == document.number and not f.repaired for f in disagreement)
    # The finding names the passport's number, the one believed.
    assert any("0.1" in f.detail for f in disagreement), disagreement
    # Report mode writes nothing: the row as it was, the passport as it was.
    with schema_context(migrated_tenant.number):
        assert Acceptance.objects.get(pk=acceptance.pk).number == "0.7"
    assert repository.head(document) == head
    assert repository.read(document, "passport.md", head) == passport


def test_the_accepted_version_without_rows_is_asked_for_again(
    migrated_tenant: Any, cast: Any, commit_version: Any, queued_authorship: list[Any]
) -> None:
    """The latest accepted version is kept beside the head (DL-0266); without its rows the
    reconciler asks the worker for them."""
    people = cast(editors=("a",), reviewers=("r",))
    written = commit_version(people.document, people["a"], WRITTEN, "edit")
    with schema_context(migrated_tenant.number):
        services.accept(people.document, people["r"])
    queued_authorship.clear()

    findings = reconcile.run(
        tenant=migrated_tenant.number, document=people.document.number, repair=True
    )

    assert ("authorship_missing", written.commit_sha) in {(f.kind, f.detail) for f in findings}
    assert (migrated_tenant.number, people.document.number, written.commit_sha) in queued_authorship


def test_an_acceptance_after_a_stop_settles_the_stopped_one_first(
    migrated_tenant: Any, cast: Any, commit_version: Any, repository: Any
) -> None:
    """A stop after the passport commit, then another *accept*: the stopped acceptance is
    derived first, so its run is not accepted twice and its number never given again."""
    people = cast(editors=("a",), reviewers=("r",))
    document, reviewer = people.document, people["r"]
    commit_version(document, people["a"], WRITTEN, "edit")
    with schema_context(migrated_tenant.number):
        with pytest.raises(services.InjectedFault):
            services.accept(document, reviewer, fault_at=1)
        with pytest.raises(services.AcceptRefused) as refused:
            services.accept(document, reviewer)
        assert refused.value.reason == "nothing_to_accept"
        assert list(Acceptance.objects.values_list("number", flat=True)) == ["0.1"]
        assert Acceptance.objects.get().notices_computed_at is not None
    assert repository.kinds(document).count("acceptance") == 1


def test_a_version_after_a_stop_settles_the_stopped_acceptance_first(
    migrated_tenant: Any, cast: Any, commit_version: Any, repository: Any
) -> None:
    """A stop after the passport commit, then an editor's *send for review*: the acceptance and
    its notices are derived before the version is written on top of them."""
    from editing import holds
    from editing import services as editing
    from editing.models import Draft

    people = cast(editors=("a",), reviewers=("r",))
    document, author, reviewer = people.document, people["a"], people["r"]
    commit_version(document, author, WRITTEN, "edit")
    commit_version(document, reviewer, CORRECTED, "reviewer_edit")
    with schema_context(migrated_tenant.number):
        with pytest.raises(services.InjectedFault):
            services.accept(document, reviewer, fault_at=1)
        hold = holds.take(document, author)
        draft = Draft.objects.get(hold=hold)
        draft.content = {**draft.content, "document.md": CORRECTED + "\nНове речення.\n"}
        draft.save()
        editing.commit_draft(hold, author, "Нове речення")
        acceptance = Acceptance.objects.get()
        assert acceptance.number == "0.1" and acceptance.notices_computed_at is not None
        assert CorrectionNotice.objects.get(acceptance=acceptance).author_id == author.pk
    assert repository.kinds(document) == ["created", "edit", "reviewer_edit", "acceptance", "edit"]


def test_a_second_acceptance_is_derived_after_the_first(
    migrated_tenant: Any, cast: Any, commit_version: Any
) -> None:
    people = cast(editors=("a",), reviewers=("r",))
    document, reviewer = people.document, people["r"]
    first = commit_version(document, people["a"], WRITTEN, "edit")
    with schema_context(migrated_tenant.number):
        services.accept(document, reviewer)
    commit_version(document, people["a"], CORRECTED, "edit")
    with schema_context(migrated_tenant.number):
        with pytest.raises(services.InjectedFault):
            services.accept(document, reviewer, fault_at=1)
    reconcile.run(tenant=migrated_tenant.number, document=document.number, repair=True)
    with schema_context(migrated_tenant.number):
        second = Acceptance.objects.get(number="0.2")
        assert second.accepted_from_id == first.pk


def test_an_acceptance_the_platform_would_not_write_is_not_derived(
    migrated_tenant: Any, cast: Any, commit_version: Any, repository: Any
) -> None:
    """A commit of kind `acceptance` that also changes the text, by someone without *accept*:
    reported, never derived."""
    from django.utils import timezone

    from documents import bundle, gitstore
    from documents.identity import identity_for
    from documents.locks import document_lock

    people = cast(editors=("a",), reviewers=("r",))
    document, author = people.document, people["a"]
    written = commit_version(document, author, WRITTEN, "edit")
    now = timezone.now().replace(microsecond=0)
    with schema_context(migrated_tenant.number):
        repo = gitstore.open_repository(migrated_tenant.number, document.number)
        head = gitstore.head(repo)
        assert head is not None
        passport = gitstore.read(repo, "passport.md", head).decode()
        entry = bundle.PassportEntry(
            kind="acceptance", number="0.1", at=now, by=str(author.pk), version=written.commit_sha
        )
        text = gitstore.read(repo, "document.md", head) + "Прихований рядок.\n".encode()
        with document_lock(migrated_tenant.number, document.number):
            forged = gitstore.commit(
                repo,
                {
                    "passport.md": bundle.append_passport(passport, entry).encode(),
                    "document.md": text,
                },
                identity_for(author, at=now),
                "Accepted as 0.1",
                gitstore.Kind.ACCEPTANCE,
            )
    findings = reconcile.run(tenant=migrated_tenant.number, document=document.number, repair=True)
    assert any(f.kind == "commit_without_row" and forged in f.detail for f in findings)
    with schema_context(migrated_tenant.number):
        assert not Acceptance.objects.exists()


def test_a_row_moved_off_its_section_is_reported_and_repaired(
    migrated_tenant: Any, cast: Any, commit_version: Any
) -> None:
    from datetime import UTC, datetime

    people = cast(editors=("a",), reviewers=("r",))
    document = people.document
    written = commit_version(document, people["a"], WRITTEN, "edit")
    with schema_context(migrated_tenant.number):
        acceptance = services.accept(document, people["r"])
        Acceptance.objects.filter(pk=acceptance.pk).update(
            accepted_from=written, at=datetime(2001, 1, 1, tzinfo=UTC)
        )
    found = reconcile.run(tenant=migrated_tenant.number, document=document.number)
    assert any(f.kind == "acceptance_differs" and "accepted_from" in f.detail for f in found)
    reconcile.run(tenant=migrated_tenant.number, document=document.number, repair=True)
    with schema_context(migrated_tenant.number):
        row = Acceptance.objects.get(pk=acceptance.pk)
        assert row.accepted_from.kind == "created" and row.at.year > 2001


def test_a_restore_before_an_acceptance_is_pruned_with_what_derived_from_it(
    migrated_tenant: Any, cast: Any, commit_version: Any, repository: Any
) -> None:
    """A repository restored to before an acceptance: pruning the lost rows takes the acceptance,
    its notices and their notifications with them, and the pending tab reads again (ADR-0018)."""
    from django.test import Client

    from documents import gitstore

    people = cast(editors=("a",), reviewers=("r",))
    document, author, reviewer = people.document, people["a"], people["r"]
    written = commit_version(document, author, WRITTEN, "edit")
    commit_version(document, reviewer, CORRECTED, "reviewer_edit")
    with schema_context(migrated_tenant.number):
        services.accept(document, reviewer)
        assert Notification.objects.filter(event="correction_notice").count() == 1
        repo = gitstore.open_repository(migrated_tenant.number, document.number)
        repo.references["refs/heads/main"].set_target(written.commit_sha)

    reconcile.run(
        tenant=migrated_tenant.number, document=document.number, repair=True, prune_rows=True
    )

    with schema_context(migrated_tenant.number):
        assert not Acceptance.objects.exists()
        assert (
            not CorrectionNotice.objects.exists()
            and not Notification.objects.filter(
                event__in=("correction_notice", "accepted")
            ).exists()
        )
        kept = set(Version.objects.filter(document=document).values_list("commit_sha", flat=True))
        assert written.commit_sha in kept and repository.head(document) in kept
        assert len(kept) == 2  # the `created` commit and the author's version
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(reviewer)
    session = client.session
    session["tenant_number"] = migrated_tenant.number
    session.save()
    assert client.get(f"/document/{document.number}/pending/").status_code == 200
