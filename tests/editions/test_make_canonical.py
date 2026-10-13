"""Making canonical (ST-0039, DL-0183, DL-0234, DL-0260, DL-0267): refused until the document is
frozen and every content version since the latest acceptance is accepted; then the approval is a
passport commit of kind `approval`, tagged with the edition's number by the approver, recorded as
an `EDITION`, the freeze ended and the act audited; the numbering continues from the edition.

People and groups are synthetic examples; the text is invented.
"""

from __future__ import annotations

from typing import Any

import pygit2
import pytest

from access.rights import Right
from audit.models import AuditEvent
from documents import bundle, gitstore
from documents.identity import DOMAIN
from review import services as review
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

FIRST = "# Загальні положення\n\nЗаяву на погодження подають письмово.\n"
SECOND = FIRST + "\nСтрок розгляду заяви становить десять днів.\n"
THIRD = SECOND.replace("десять днів", "п'ять робочих днів")
FOURTH = THIRD + "\nКопію рішення надсилають заявникові того ж дня.\n"
REASON = "Синтетична причина: чекаємо рішення ради"


def _tag(migrated_tenant: Any, document: Any, name: str) -> pygit2.Tag | None:
    """The annotated tag `name` of the document's repository, or `None`."""
    repo = gitstore.open_repository(migrated_tenant.number, document.number)
    ref = repo.references.get(f"refs/tags/{name}")
    if ref is None:
        return None
    found = repo[ref.target]
    assert isinstance(found, pygit2.Tag), f"{name} is a lightweight tag"
    return found


def _passport(repository: Any, document: Any) -> list[bundle.PassportEntry]:
    return bundle.passport_entries(repository.read(document, "passport.md"))


def test_edition_is_a_tagged_passport_commit(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    repository: Any,
) -> None:
    from editing import numbering
    from editions import services as editions
    from editions.models import Edition, Freeze, open_freeze
    from review.state import state

    people = edition_cast()
    document, approver = people.document, people["p"]
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
    approved = commit_version(document, people["a"], SECOND, "edit")
    with schema_context(migrated_tenant.number):
        assert review.accept(document, people["r"]).number == "0.2"
        freeze = editions.freeze(document, approver, REASON)
    before = repository.head(document)
    passport_before = repository.read(document, "passport.md")

    with schema_context(migrated_tenant.number):
        edition = editions.make_canonical(document, approver)

    head = repository.head(document)
    # One commit of kind `approval` on top of the `0.2` acceptance, the text unchanged.
    assert repository.kinds(document) == [
        "created",
        "edit",
        "acceptance",
        "edit",
        "acceptance",
        "approval",
    ]
    assert repository.parent(document, head) == before
    assert repository.read(document, "document.md", head) == repository.read(
        document, "document.md", approved.commit_sha
    )
    # The passport gains `## approval 1.0`, every earlier byte kept.
    passport = repository.read(document, "passport.md", head)
    assert passport.startswith(passport_before)
    last = _passport(repository, document)[-1]
    assert last.kind == "approval"
    assert last.number == "1.0"
    assert last.edition == "1.0"
    assert last.version == approved.commit_sha
    assert last.by == str(approver.pk)
    assert approver.email not in passport

    # An annotated tag `1.0` on the approval commit, by the approver's identity (DL-0260).
    tag = _tag(migrated_tenant, document, "1.0")
    assert tag is not None
    assert str(tag.peel(pygit2.Commit).id) == head
    assert tag.tagger.name == str(approver.pk)
    assert tag.tagger.email == f"{approver.pk}@{DOMAIN}"

    with schema_context(migrated_tenant.number):
        row = Edition.objects.get()
        assert row.pk == edition.pk
        assert row.number == "1.0"
        assert row.version_id == approved.pk
        assert row.approval_version.commit_sha == head
        assert row.approval_version.kind == "approval"
        assert row.freeze_id == freeze.pk
        assert row.approved_by_id == approver.pk
        assert row.approved_at is not None

        ended = Freeze.objects.get(pk=freeze.pk)
        assert ended.ended_by_kind == "made_canonical"
        assert ended.ended_at is not None
        assert open_freeze(document) is None

        assert state(document) == "canonical"
        assert numbering.edition(document) == "1.0"
        assert numbering.accepted(document) == "1.0"
        # No longer frozen: the control's reason is the first refusal again.
        assert editions.canonical_refusal(document, approver) == "not_frozen"

    event = AuditEvent.objects.get(action="document.made_canonical")
    assert event.actor_id == approver.pk
    assert event.object_id == document.pk


def test_needs_a_freeze(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any, repository: Any
) -> None:
    from editions import services as editions
    from editions.models import Edition

    people = edition_cast()
    document, approver = people.document, people["p"]
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
    head = repository.head(document)

    with schema_context(migrated_tenant.number):
        assert editions.canonical_refusal(document, approver) == "not_frozen"
        with pytest.raises(editions.CanonicalRefused) as refused:
            editions.make_canonical(document, approver)
        assert refused.value.reason == "not_frozen"
        assert not Edition.objects.exists()

    # Nothing written: no commit, no tag, no audit.
    assert repository.head(document) == head
    assert _tag(migrated_tenant, document, "1.0") is None
    assert not AuditEvent.objects.filter(action="document.made_canonical").exists()
    # The control is drawn disabled with its reason.
    page = people.clients["p"].get(f"/document/{document.number}/").content.decode()
    control = page.split('data-command="make-canonical"')[1].split(">")[0]
    assert "disabled" in control


def test_refused_over_unaccepted_versions_without_the_number(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    repository: Any,
) -> None:
    """An approver holding *make canonical* alone — which includes *view accepted*, never *view
    pending* (DL-0234) — is refused while `0.2-1` waits, and never shown that number."""
    from editions import services as editions
    from editions.models import Edition

    people = edition_cast()
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
    commit_version(document, people["a"], SECOND, "edit")
    with schema_context(migrated_tenant.number):
        assert review.accept(document, people["r"]).number == "0.2"
    commit_version(document, people["a"], THIRD, "edit")
    with schema_context(migrated_tenant.number):
        editions.freeze(document, people["p"], REASON)
    approver_client, approver, membership = member_of("q.synthetic@example.test")
    link_group(document, [Right.MAKE_CANONICAL], [membership], people["a"])
    head = repository.head(document)

    with schema_context(migrated_tenant.number):
        from editing import numbering

        # The version the refusal must not name.
        assert numbering.latest(document) == "0.2-1"
        reason = editions.canonical_refusal(document, approver)
        assert reason == "unaccepted_changes"
        with pytest.raises(editions.CanonicalRefused) as refused:
            editions.make_canonical(document, approver)
        assert refused.value.reason == "unaccepted_changes"
        assert not Edition.objects.exists()
    assert repository.head(document) == head

    # The document page, control and all, names no pending number to this approver.
    response = approver_client.get(f"/document/{document.number}/")
    assert response.status_code == 200
    assert "0.2-1" not in response.content.decode()


def test_refused_when_nothing_accepted(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any, repository: Any
) -> None:
    """No acceptance at all; then, after an edition, none since it."""
    from editions import services as editions
    from editions.models import Edition

    people = edition_cast()
    document, approver = people.document, people["p"]
    with schema_context(migrated_tenant.number):
        editions.freeze(document, approver, REASON)
        assert editions.canonical_refusal(document, approver) == "nothing_accepted"
        with pytest.raises(editions.CanonicalRefused) as refused:
            editions.make_canonical(document, approver)
        assert refused.value.reason == "nothing_accepted"
        assert not Edition.objects.exists()

    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
        editions.make_canonical(document, approver)
        editions.freeze(document, approver, REASON)
        with pytest.raises(editions.CanonicalRefused) as refused:
            editions.make_canonical(document, approver)
        assert refused.value.reason == "nothing_accepted"
        assert list(Edition.objects.values_list("number", flat=True)) == ["1.0"]
    assert repository.kinds(document).count("approval") == 1


def test_refused_without_the_right(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any, repository: Any
) -> None:
    """A reviewer holding *accept* — and so *edit* and *view pending* — but not *make canonical*."""
    from editions import services as editions
    from editions.models import Edition

    people = edition_cast()
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
        editions.freeze(document, people["p"], REASON)
        for outsider in (people["r"], people["a"]):
            assert editions.canonical_refusal(document, outsider) == "not_permitted"
            with pytest.raises(editions.CanonicalRefused) as refused:
                editions.make_canonical(document, outsider)
            assert refused.value.reason == "not_permitted"
        assert not Edition.objects.exists()
    assert _tag(migrated_tenant, document, "1.0") is None


def test_numbering_after_an_edition(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any, repository: Any
) -> None:
    """`pending()` is the number the next content version will carry; `latest()` the number of
    the newest one (`editing.numbering`). After edition `1.0`: the first version is `1.0-1`
    (DL-0267), the next acceptance `1.1` (DL-0183), and the first version after it `1.1-1`."""
    from editing import numbering
    from editions import services as editions

    people = edition_cast()
    document, approver = people.document, people["p"]
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
        editions.freeze(document, approver, REASON)
        editions.make_canonical(document, approver)

        assert numbering.edition(document) == "1.0"
        assert numbering.accepted(document) == "1.0"
        assert numbering.pending(document) == "1.0-1"
        assert numbering.next_accepted(document) == "1.1"

    commit_version(document, people["a"], SECOND, "edit")
    with schema_context(migrated_tenant.number):
        assert numbering.latest(document) == "1.0-1"
        assert numbering.pending(document) == "1.0-2"

        acceptance = review.accept(document, people["r"])
        assert acceptance.number == "1.1"
        assert numbering.accepted(document) == "1.1"
        assert numbering.edition(document) == "1.0"
        assert numbering.pending(document) == "1.1-1"

    commit_version(document, people["a"], THIRD, "edit")
    with schema_context(migrated_tenant.number):
        assert numbering.latest(document) == "1.1-1"

    # The passport records the sequence the numbers are counted from.
    sections = [(e.kind, e.number) for e in _passport(repository, document)]
    assert sections == [("acceptance", "0.1"), ("approval", "1.0"), ("acceptance", "1.1")]


def test_second_edition_is_two(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any, repository: Any
) -> None:
    """`N+1.0`, N the editions made (DL-0183): the next edition after `1.0` is `2.0`, tagged so."""
    from editions import services as editions
    from editions.models import Edition

    people = edition_cast()
    document, approver = people.document, people["p"]
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
        editions.freeze(document, approver, REASON)
        editions.make_canonical(document, approver)
    second = commit_version(document, people["a"], FOURTH, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
        editions.freeze(document, approver, REASON)
        edition = editions.make_canonical(document, approver)
        assert edition.number == "2.0"
        assert edition.version_id == second.pk
        assert sorted(Edition.objects.values_list("number", flat=True)) == ["1.0", "2.0"]
    last = _passport(repository, document)[-1]
    assert (last.kind, last.number, last.edition) == ("approval", "2.0", "2.0")
    tag = _tag(migrated_tenant, document, "2.0")
    assert tag is not None and str(tag.peel(pygit2.Commit).id) == repository.head(document)
    assert _tag(migrated_tenant, document, "1.0") is not None


def test_the_pending_tab_numbers_from_the_edition(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any
) -> None:
    """After edition `1.0` — whose version was accepted as `0.1` — the first version waiting for
    review reads `1.0-1` on the pending tab, as it does everywhere else (DL-0267), never `0.1-1`."""
    from editions import services as editions

    people = edition_cast()
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
        editions.freeze(document, people["p"], REASON)
        editions.make_canonical(document, people["p"])
    commit_version(document, people["a"], SECOND, "edit")

    body = people.clients["r"].get(f"/document/{document.number}/pending/").content.decode()

    assert "1.0-1" in body
    assert "0.1-1" not in body


def test_a_notice_after_an_edition_numbers_its_versions_from_it(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any
) -> None:
    """A run accepted after an edition counts from the edition, as the pending tab does
    (DL-0267): the correction notice names `1.0-1` and `1.0-2`, never the acceptance before it."""
    from django.test import Client

    from editions import services as editions
    from notifications.models import Notification

    people = edition_cast()
    document, approver = people.document, people["p"]
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
        editions.freeze(document, approver, REASON)
        editions.make_canonical(document, approver)
    commit_version(document, people["a"], SECOND, "edit")
    commit_version(document, people["r"], THIRD, "reviewer_edit")
    with schema_context(migrated_tenant.number):
        assert review.accept(document, people["r"]).number == "1.1"
        notification = Notification.objects.get(user=people["a"], event="correction_notice")
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(people["a"])
    session = client.session
    session["tenant_number"] = migrated_tenant.number
    session.save()
    body = client.get(f"/notifications/{notification.pk}/").content.decode()
    assert "1.0-1" in body and "1.0-2" in body
    assert "0.1-" not in body
