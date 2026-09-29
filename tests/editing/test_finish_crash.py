"""A finish stopped after each of its steps ends, once the reconciler has repaired it, where an
uninterrupted finish ends: the version derived, the hold released as finished, the draft gone, the
authorship asked for. Invented text; people are synthetic examples."""

from __future__ import annotations

from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.crash,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]


@pytest.mark.parametrize("step", [1, 2, 3, 4])
def test_each_crash_state_repaired(
    step: int,
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    queued_authorship: list[Any],
) -> None:
    from documents import gitstore, reconcile
    from documents.models import Version
    from editing import services
    from editing.models import Draft, Hold

    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    client.post(f"/document/{document.number}/edit/take/")
    with schema_context(migrated_tenant.number):
        hold = Hold.objects.get(document=document)
        draft = Draft.objects.get(hold=hold)
        draft.content = {
            **draft.content,
            "document.md": draft.content["document.md"] + "\nНове речення.\n",
        }
        draft.save()
        with pytest.raises(services.InjectedFault):
            services.commit_draft(hold, author, "Доповнено", fault_at=step)

    reconcile.run(tenant=migrated_tenant.number, repair=True)

    with schema_context(migrated_tenant.number):
        repo = gitstore.open_repository(migrated_tenant.number, document.number)
        head = gitstore.head(repo)
        hold.refresh_from_db()
        assert Version.objects.filter(commit_sha=head, kind="edit").exists()
        assert hold.release_kind == "finished"
        assert not Draft.objects.filter(hold=hold).exists()
    assert (migrated_tenant.number, document.number, head) in queued_authorship
    assert [f.kind for f in reconcile.run(tenant=migrated_tenant.number)] in (
        [],
        ["authorship_missing"],
    )


def stopped_at_the_commit(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> tuple[Any, Any, Any]:
    """A finish stopped right after its git commit: the hold open, its draft behind the head."""
    from editing import services
    from editing.models import Draft, Hold

    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    client.post(f"/document/{document.number}/edit/take/")
    with schema_context(migrated_tenant.number):
        hold = Hold.objects.get(document=document)
        draft = Draft.objects.get(hold=hold)
        draft.content = {
            **draft.content,
            "document.md": draft.content["document.md"] + "\nНове речення.\n",
        }
        draft.save()
        with pytest.raises(services.InjectedFault):
            services.commit_draft(hold, author, "Доповнено", fault_at=1)
    return author, document, hold


def add_to_draft(migrated_tenant: Any, hold: Any, text: str) -> None:
    from editing.models import Draft

    with schema_context(migrated_tenant.number):
        draft = Draft.objects.get(hold=hold)
        draft.content = {**draft.content, "document.md": draft.content["document.md"] + text}
        draft.save()


def test_a_second_send_resumes_a_stopped_finish(
    migrated_tenant: Any, member_of: Any, new_document: Any, queued_authorship: list[Any]
) -> None:
    """Sent again with nothing typed since: the stopped version finished, not *nothing changed*."""
    from documents import gitstore
    from documents.models import Version
    from editing import services
    from editing.models import Draft

    author, document, hold = stopped_at_the_commit(migrated_tenant, member_of, new_document)
    with schema_context(migrated_tenant.number):
        version = services.commit_draft(hold, author, "Доповнено")
        head = gitstore.head(gitstore.open_repository(migrated_tenant.number, document.number))
        hold.refresh_from_db()
        assert version.commit_sha == head
        assert Version.objects.filter(document=document, kind="edit").count() == 1
        assert hold.release_kind == "finished"
        assert not Draft.objects.filter(hold=hold).exists()


def test_a_second_send_commits_what_was_typed_after_the_stop(
    migrated_tenant: Any, member_of: Any, new_document: Any, queued_authorship: list[Any]
) -> None:
    from documents import bundle, gitstore
    from documents.models import Version
    from editing import services

    author, document, hold = stopped_at_the_commit(migrated_tenant, member_of, new_document)
    add_to_draft(migrated_tenant, hold, "\nПізніше речення.\n")
    with schema_context(migrated_tenant.number):
        version = services.commit_draft(hold, author, "Ще доповнено")
        repo = gitstore.open_repository(migrated_tenant.number, document.number)
        _, body = bundle.parse(gitstore.read(repo, "document.md", version.commit_sha).decode())
        assert "Нове речення." in body and "Пізніше речення." in body
        assert Version.objects.filter(document=document, kind="edit").count() == 2


def test_the_repair_leaves_text_typed_after_the_stop(
    migrated_tenant: Any, member_of: Any, new_document: Any, queued_authorship: list[Any]
) -> None:
    from documents import reconcile
    from editing.models import Draft

    _, document, hold = stopped_at_the_commit(migrated_tenant, member_of, new_document)
    add_to_draft(migrated_tenant, hold, "\nПізніше речення.\n")

    findings = reconcile.run(tenant=migrated_tenant.number, repair=True)

    stopped = [f for f in findings if f.kind == "finish_stopped"]
    assert stopped and not stopped[0].repaired and "later text" in stopped[0].detail
    with schema_context(migrated_tenant.number):
        hold.refresh_from_db()
        assert hold.released_at is None
        assert "Пізніше речення." in Draft.objects.get(hold=hold).content["document.md"]


def test_the_repair_leaves_a_holder_no_longer_a_member(
    migrated_tenant: Any, member_of: Any, new_document: Any, queued_authorship: list[Any]
) -> None:
    from documents import reconcile
    from editing.models import Draft
    from identity.models import Membership

    author, _, hold = stopped_at_the_commit(migrated_tenant, member_of, new_document)
    with schema_context(migrated_tenant.number):
        Membership.objects.filter(user=author).delete()

    findings = reconcile.run(tenant=migrated_tenant.number, repair=True)

    stopped = [f for f in findings if f.kind == "finish_stopped"]
    assert stopped and not stopped[0].repaired
    with schema_context(migrated_tenant.number):
        hold.refresh_from_db()
        assert hold.released_at is None
        assert Draft.objects.filter(hold=hold).exists()
