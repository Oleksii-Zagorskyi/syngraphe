"""Correcting as a reviewer (ST-0035, DL-0222, ADR-0014, DL-0521): the review page's *Edit* takes
the document with the reviewer's notice, a holder of *accept* commits `reviewer_edit`, and the
finishing screen offers *accept as N.M* and *create version N.M-X* where an editor sees *send for
review*.

People and groups are synthetic examples; the text is invented.
"""

from __future__ import annotations

import html
import re
from typing import Any

import pytest
from django.test import Client

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
CORRECTED = SECOND.replace("ten days", "five working days")


def signed_in(tenant: Any, user: Any) -> Client:
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(user)
    session = client.session
    session["tenant_number"] = tenant.number
    session.save()
    return client


def pending_with_two_versions(cast: Any, commit_version: Any) -> Any:
    people = cast(editors=("a", "b"), reviewers=("r",))
    commit_version(people.document, people["a"], FIRST, "edit")
    commit_version(people.document, people["b"], SECOND, "edit")
    return people


def take_and_change(tenant: Any, client: Client, document: Any, body: str) -> None:
    from editing.models import Draft

    assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
    with schema_context(tenant.number):
        draft = Draft.objects.get(hold__document=document, hold__released_at__isnull=True)
        draft.content = {**draft.content, "document.md": body}
        draft.save()


def test_correct_takes_the_hold_with_the_notice(
    migrated_tenant: Any, cast: Any, commit_version: Any
) -> None:
    from editing.models import Hold

    people = pending_with_two_versions(cast, commit_version)
    document, reviewer = people.document, people["r"]
    client = signed_in(migrated_tenant, reviewer)
    pending = client.get(f"/document/{document.number}/pending/").content.decode()
    # *Correct* is gone; a reviewer who changes the text uses *Edit* (DL-0521).
    assert 'data-command="correct"' not in pending
    assert f'href="/document/{document.number}/edit/" data-command="edit"' in pending
    tab = client.get(
        f"/document/{document.number}/edit/", headers={"Sec-Fetch-Site": "same-origin"}
    )
    page = tab.content.decode()
    assert 'data-take-on-mount="true"' in page and 'class="notice correcting"' in page
    assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
    with schema_context(migrated_tenant.number):
        hold = Hold.objects.get(document=document, released_at__isnull=True)
        assert hold.user_id == reviewer.pk
    # An editor opening the same tab reads no reviewer's notice.
    editor_page = signed_in(migrated_tenant, people["a"]).get(f"/document/{document.number}/edit/")
    assert 'class="notice correcting"' not in editor_page.content.decode()


def test_correct_is_disabled_while_someone_else_holds(
    migrated_tenant: Any, cast: Any, commit_version: Any
) -> None:
    people = pending_with_two_versions(cast, commit_version)
    document = people.document
    assert (
        signed_in(migrated_tenant, people["a"])
        .post(f"/document/{document.number}/edit/take/")
        .status_code
        == 200
    )
    pending = signed_in(migrated_tenant, people["r"]).get(f"/document/{document.number}/pending/")
    page = pending.content.decode()
    assert 'data-command="correct"' not in page and 'data-command="edit" disabled' in page
    # A holder of *accept* learns who holds it, on an ordinary hold too (DL-0516).
    from identity.naming import person

    with schema_context(migrated_tenant.number):
        name = person(people["a"])
    after = page.split('data-command="edit" disabled', 1)[1].split("</div>", 1)[0]
    assert html.escape(f"{name} is editing.") in after or f"Редагує {html.escape(name)}." in after


def test_create_version_is_a_reviewer_edit(
    migrated_tenant: Any, cast: Any, commit_version: Any, repository: Any
) -> None:
    from review.services import run
    from review.state import State, state

    people = pending_with_two_versions(cast, commit_version)
    document, reviewer = people.document, people["r"]
    client = signed_in(migrated_tenant, reviewer)
    take_and_change(migrated_tenant, client, document, CORRECTED)
    sent = client.post(
        f"/document/{document.number}/edit/send/", {"summary": "Terms", "choice": "create"}
    )
    assert sent.status_code == 302 and sent["Location"] == f"/document/{document.number}/"
    assert repository.kinds(document) == ["created", "edit", "edit", "reviewer_edit"]
    with schema_context(migrated_tenant.number):
        assert len(run(document)) == 3
        assert state(document) is State.AWAITING_REVIEW
    landing = client.get(sent["Location"]).content.decode()
    assert "0.0-3" in landing.split('<p class="notice" role="status">', 1)[1].split("</p>", 1)[0]


def test_accept_as_commits_and_accepts_in_one_act(
    migrated_tenant: Any, cast: Any, commit_version: Any, repository: Any
) -> None:
    from review.models import Acceptance
    from review.state import State, state

    people = pending_with_two_versions(cast, commit_version)
    document, reviewer = people.document, people["r"]
    client = signed_in(migrated_tenant, reviewer)
    take_and_change(migrated_tenant, client, document, CORRECTED)
    sent = client.post(
        f"/document/{document.number}/edit/send/", {"summary": "Terms", "choice": "accept"}
    )
    assert sent.status_code == 302 and sent["Location"] == f"/document/{document.number}/"
    assert repository.kinds(document) == ["created", "edit", "edit", "reviewer_edit", "acceptance"]
    head = repository.head(document)
    corrected = repository.parent(document, head)
    with schema_context(migrated_tenant.number):
        acceptance = Acceptance.objects.get()
        assert acceptance.number == "0.1"
        assert acceptance.version.commit_sha == head
        assert state(document) is State.ACCEPTED
        from review.services import accepted_content_version

        assert accepted_content_version(acceptance).commit_sha == corrected
    landing = client.get(sent["Location"]).content.decode()
    assert "0.1" in landing.split('<p class="notice" role="status">', 1)[1].split("</p>", 1)[0]


def test_editor_sees_send_for_review_only(
    migrated_tenant: Any, cast: Any, commit_version: Any
) -> None:
    people = pending_with_two_versions(cast, commit_version)
    document = people.document
    editor = signed_in(migrated_tenant, people["a"])
    take_and_change(migrated_tenant, editor, document, CORRECTED)
    screen = editor.get(f"/document/{document.number}/edit/finish/").content.decode()
    assert 'data-command="send"' in screen and "0.0-3" in screen
    assert 'data-command="create"' not in screen and 'data-command="accept"' not in screen
    # A choice the editor is not offered is not taken.
    refused = editor.post(
        f"/document/{document.number}/edit/send/", {"summary": "Terms", "choice": "accept"}
    )
    assert refused.status_code == 404


def test_reviewer_sees_both_choices_with_their_numbers(
    migrated_tenant: Any, cast: Any, commit_version: Any
) -> None:
    people = pending_with_two_versions(cast, commit_version)
    document = people.document
    reviewer = signed_in(migrated_tenant, people["r"])
    take_and_change(migrated_tenant, reviewer, document, CORRECTED)
    screen = reviewer.get(f"/document/{document.number}/edit/finish/").content.decode()
    assert 'data-command="accept"' in screen and 'data-command="create"' in screen
    assert 'data-command="send"' not in screen
    assert "0.1" in screen and "0.0-3" in screen
    # *Accept as* names the versions it accepts besides the reviewer's own (DL-0333).
    assert 'data-number="0.0-1"' in screen and 'data-number="0.0-2"' in screen


def stopped_after_the_commit(tenant: Any, people: Any) -> tuple[Any, Any]:
    """The reviewer's finish, stopped just after its `reviewer_edit` commit."""
    from editing import services
    from editing.models import Hold

    document, reviewer = people.document, people["r"]
    client = signed_in(tenant, reviewer)
    take_and_change(tenant, client, document, CORRECTED)
    with schema_context(tenant.number):
        hold = Hold.objects.get(document=document, released_at__isnull=True)
        with pytest.raises(services.InjectedFault):
            services.commit_draft(hold, reviewer, "Terms", fault_at=1)
    return client, hold


def test_a_reviewers_stopped_finish_is_finished_by_the_reconciler(
    migrated_tenant: Any, cast: Any, commit_version: Any, repository: Any
) -> None:
    from documents import reconcile
    from documents.models import Version
    from editing.models import Draft, Hold

    people = pending_with_two_versions(cast, commit_version)
    document = people.document
    _, hold = stopped_after_the_commit(migrated_tenant, people)
    head = repository.head(document)
    reconcile.run(tenant=migrated_tenant.number, document=document.number, repair=True)
    with schema_context(migrated_tenant.number):
        assert Version.objects.get(commit_sha=head).kind == "reviewer_edit"
        assert Hold.objects.get(pk=hold.pk).release_kind == "finished"
        assert not Draft.objects.filter(hold=hold).exists()


def test_a_reviewers_stopped_finish_is_resumed_by_the_next_send(
    migrated_tenant: Any, cast: Any, commit_version: Any, repository: Any
) -> None:
    from documents.models import Version

    people = pending_with_two_versions(cast, commit_version)
    document = people.document
    client, _ = stopped_after_the_commit(migrated_tenant, people)
    head = repository.head(document)
    sent = client.post(
        f"/document/{document.number}/edit/send/", {"summary": "Terms", "choice": "create"}
    )
    assert sent.status_code == 302
    assert repository.head(document) == head
    with schema_context(migrated_tenant.number):
        assert Version.objects.get(commit_sha=head).kind == "reviewer_edit"


def test_a_head_moved_back_by_a_restore_is_not_the_holders_finish(
    migrated_tenant: Any, cast: Any, commit_version: Any, repository: Any
) -> None:
    """The holder's own earlier version, made head again by a restore, is not a finish that
    stopped: the draft's base is not behind it (DL-0335)."""
    from documents import gitstore
    from editing.models import Draft

    people = cast(editors=("a",), reviewers=("r",))
    document, author = people.document, people["a"]
    earlier = commit_version(document, author, FIRST, "edit")
    commit_version(document, people["r"], SECOND, "reviewer_edit")
    client = signed_in(migrated_tenant, author)
    take_and_change(migrated_tenant, client, document, CORRECTED)
    with schema_context(migrated_tenant.number):
        repo = gitstore.open_repository(migrated_tenant.number, document.number)
        repo.references["refs/heads/main"].set_target(earlier.commit_sha)
        draft = Draft.objects.get(hold__document=document, hold__released_at__isnull=True)
        from editing.services import _stopped

        assert _stopped(repo, earlier.commit_sha, draft, author) is None
    # Sent after the restore, the draft is a new version on the restored head, not a resume.
    sent = client.post(f"/document/{document.number}/edit/send/", {"summary": "Terms"})
    assert sent.status_code == 302
    assert repository.kinds(document)[-1] == "edit"
    assert repository.parent(document, repository.head(document)) == earlier.commit_sha


def test_an_acceptance_after_a_stopped_finish_decides_on_the_finished_version(
    migrated_tenant: Any, cast: Any, commit_version: Any, repository: Any
) -> None:
    """A finish stopped after its commit and before its row, then *Accept the run*: the version is
    derived first and the acceptance decides on it, never on the one before."""
    from documents import gitstore
    from review import services

    people = pending_with_two_versions(cast, commit_version)
    document = people.document
    stopped_after_the_commit(migrated_tenant, people)
    corrected = repository.head(document)
    with schema_context(migrated_tenant.number):
        acceptance = services.accept(document, people["r"])
        assert services.accepted_content_version(acceptance).commit_sha == corrected
        repo = gitstore.open_repository(migrated_tenant.number, document.number)
        assert not isinstance(
            services.derivable(document, repo, acceptance.version.commit_sha), str
        )


def test_a_finish_stopped_under_an_acceptance_is_resumed(
    migrated_tenant: Any, cast: Any, commit_version: Any, repository: Any
) -> None:
    """Stopped after its row, then accepted by another: the holder's next send finishes it."""
    from editing import services as editing
    from editing.models import Draft, Hold
    from review import services

    people = pending_with_two_versions(cast, commit_version)
    document, reviewer = people.document, people["r"]
    client = signed_in(migrated_tenant, reviewer)
    take_and_change(migrated_tenant, client, document, CORRECTED)
    with schema_context(migrated_tenant.number):
        hold = Hold.objects.get(document=document, released_at__isnull=True)
        with pytest.raises(editing.InjectedFault):
            editing.commit_draft(hold, reviewer, "Terms", fault_at=2)
        services.accept(document, reviewer)
    sent = client.post(
        f"/document/{document.number}/edit/send/", {"summary": "Terms", "choice": "create"}
    )
    assert sent.status_code == 302
    with schema_context(migrated_tenant.number):
        assert Hold.objects.get(pk=hold.pk).release_kind == "finished"
        assert not Draft.objects.filter(hold=hold).exists()
    # The version was accepted meanwhile, and the holder is told so, never that it waits.
    landing = client.get(sent["Location"]).content.decode()
    notice = landing.split('<p class="notice" role="status">', 1)[1].split("</p>", 1)[0]
    assert "0.1" in notice and "0.1-" not in notice


def test_a_resumed_finish_ends_the_hold(
    migrated_tenant: Any, cast: Any, commit_version: Any, repository: Any
) -> None:
    from editing.models import Draft, Hold

    people = pending_with_two_versions(cast, commit_version)
    client, hold = stopped_after_the_commit(migrated_tenant, people)
    client.post(
        f"/document/{people.document.number}/edit/send/", {"summary": "Terms", "choice": "create"}
    )
    with schema_context(migrated_tenant.number):
        assert Hold.objects.get(pk=hold.pk).release_kind == "finished"
        assert not Draft.objects.filter(hold=hold).exists()


def test_a_head_moved_since_the_screen_is_not_accepted(
    migrated_tenant: Any, cast: Any, commit_version: Any, repository: Any
) -> None:
    from review.models import Acceptance

    people = pending_with_two_versions(cast, commit_version)
    document = people.document
    client = signed_in(migrated_tenant, people["r"])
    take_and_change(migrated_tenant, client, document, CORRECTED)
    stale = repository.parent(document, repository.head(document))
    refused = client.post(
        f"/document/{document.number}/edit/send/",
        {"summary": "Terms", "choice": "accept", "head": stale},
    )
    assert refused.status_code == 409
    assert repository.kinds(document) == ["created", "edit", "edit"]
    with schema_context(migrated_tenant.number):
        assert not Acceptance.objects.exists()


def test_a_refusal_after_the_versions_commit_leaves_it_pending(
    migrated_tenant: Any,
    cast: Any,
    commit_version: Any,
    repository: Any,
    monkeypatch: pytest.MonkeyPatch,
    queued_authorship: list[Any],
) -> None:
    """*Accept as* refused between its two commits — a right withdrawn in that instant: the version
    stands and waits, its authorship is asked for, and the holder lands on the document page."""
    from review import services

    people = pending_with_two_versions(cast, commit_version)
    document = people.document
    client = signed_in(migrated_tenant, people["r"])
    take_and_change(migrated_tenant, client, document, CORRECTED)

    def withdrawn(*_: Any, **__: Any) -> Any:
        raise services.AcceptRefused("not_a_reviewer")

    monkeypatch.setattr(services, "accept_locked", withdrawn)
    queued_authorship.clear()
    sent = client.post(
        f"/document/{document.number}/edit/send/", {"summary": "Terms", "choice": "accept"}
    )
    assert sent.status_code == 302 and sent["Location"] == f"/document/{document.number}/"
    head = repository.head(document)
    assert repository.kinds(document) == ["created", "edit", "edit", "reviewer_edit"]
    assert (migrated_tenant.number, document.number, head) in queued_authorship


def test_accept_as_takes_the_lock_once(
    migrated_tenant: Any, cast: Any, commit_version: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from documents import locks
    from review import services

    people = pending_with_two_versions(cast, commit_version)
    document = people.document
    client = signed_in(migrated_tenant, people["r"])
    take_and_change(migrated_tenant, client, document, CORRECTED)
    taken: list[int] = []
    real = locks.document_lock

    def counted(tenant: int, number: int, **kwargs: Any) -> Any:
        taken.append(number)
        return real(tenant, number, **kwargs)

    monkeypatch.setattr(services, "document_lock", counted)
    client.post(f"/document/{document.number}/edit/send/", {"summary": "Terms", "choice": "accept"})
    assert taken == [document.number]


def test_choices_not_offered_are_refused(
    migrated_tenant: Any, cast: Any, commit_version: Any
) -> None:
    people = pending_with_two_versions(cast, commit_version)
    document = people.document
    reviewer = signed_in(migrated_tenant, people["r"])
    take_and_change(migrated_tenant, reviewer, document, CORRECTED)
    for posted in ({"summary": "Terms", "choice": "send"}, {"summary": "Terms"}):
        assert reviewer.post(f"/document/{document.number}/edit/send/", posted).status_code == 404


def test_correct_is_disabled_while_reserved_and_with_nothing_pending(
    migrated_tenant: Any, cast: Any, commit_version: Any
) -> None:
    from django.utils import timezone

    from editing.models import Hold

    people = cast(editors=("a",), reviewers=("r",))
    document = people.document
    reviewer = signed_in(migrated_tenant, people["r"])
    page = reviewer.get(f"/document/{document.number}/pending/").content.decode()
    # Nothing pending: no act to accept and no *Correct*; the page says so.
    assert 'data-command="correct"' not in page and 'data-command="accept"' not in page
    assert 'class="nothing-pending"' in page
    # The disabled act still reads whole: the head's number and the one it would become.
    assert re.search(r'disabled title="[^"]*">\S+ 0\.0 — \S+ 0\.1</button>', page)
    commit_version(document, people["a"], FIRST, "edit")
    now = timezone.now()
    with schema_context(migrated_tenant.number):
        Hold.objects.create(
            document=document, user=people["r"], acquired_at=now, last_activity_at=now,
            reserved_at=now,
        )  # fmt: skip
    page = reviewer.get(f"/document/{document.number}/pending/").content.decode()
    # Held by the reviewer's own reservation: acceptance waits, its reason beside it.
    acts = page.split('class="acts phase-acts"', 1)[1].split("</div>", 1)[0]
    assert 'data-command="correct"' not in page and 'data-command="accept"' not in acts
    assert '<button class="btn primary" type="button" disabled title="' in acts
