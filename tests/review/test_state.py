"""The document's state, a function of the rows and the rights, never a column (ADR-0007, DL-0233).

Groups, people and texts are synthetic examples.
"""

from __future__ import annotations

from typing import Any

import pytest

from review.state import State
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

BODY = "# General provisions\n\nA request is made in writing.\n"


def test_state_from_rows_and_rights(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    accepted_directly: Any,
) -> None:
    from access.rights import Right
    from review.state import State, state

    _, author, author_membership = member_of("the.author@example.test")
    _, reviewer, reviewer_membership = member_of("the.reviewer@example.test")
    document = new_document(author)
    link_group(document, [Right.EDIT], [author_membership], author)
    commit_version(document, author, BODY, "edit")
    with schema_context(migrated_tenant.number):
        assert state(document) is State.NO_REVIEWER_ASSIGNED
    link_group(document, [Right.ACCEPT], [reviewer_membership], author)
    with schema_context(migrated_tenant.number):
        assert state(document) is State.AWAITING_REVIEW
    accepted_directly(document, reviewer)
    with schema_context(migrated_tenant.number):
        assert state(document) is State.ACCEPTED


def test_a_new_document_is_new_and_draws_no_tag(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    from access.rights import Right
    from review.state import State, state

    client, author, membership = member_of("the.author@example.test")
    document = new_document(author)
    link_group(document, [Right.ACCEPT], [membership], author)
    with schema_context(migrated_tenant.number):
        assert state(document) is State.NEW
    assert "data-state=" not in client.get(f"/document/{document.number}/").content.decode()


def test_state_tags_follow_view_pending(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    from access.rights import Right

    author_client, author, author_membership = member_of("the.author@example.test")
    reader_client, _, reader_membership = member_of("the.reader@example.test")
    document = new_document(author)
    link_group(document, [Right.ACCEPT], [author_membership], author)
    link_group(document, [Right.VIEW_ACCEPTED], [reader_membership], author)
    commit_version(document, author, BODY, "edit")
    tag = 'data-state="awaiting_review"'
    for path in ("/folder/1/", f"/document/{document.number}/"):
        assert tag in author_client.get(path).content.decode(), path
        reader_page = reader_client.get(path)
        assert reader_page.status_code == 200, path
        assert "data-state=" not in reader_page.content.decode(), path


def test_no_reviewer_assigned_shown_to_administrators(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    from access.rights import Right

    _, author, author_membership = member_of("the.author@example.test")
    admin_client, _, _ = member_of("the.admin@example.test", is_tenant_admin=True)
    document = new_document(author)
    link_group(document, [Right.EDIT], [author_membership], author)
    commit_version(document, author, BODY, "edit")
    page = admin_client.get(f"/document/{document.number}/").content.decode()
    assert 'data-state="no_reviewer_assigned"' in page


def test_the_lists_tags_cost_a_fixed_number_of_queries(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    django_assert_max_num_queries: Any,
) -> None:
    from access.rights import Right
    from review.state import tags

    _, author, membership = member_of("the.author@example.test")
    documents = []
    for n in range(5):
        document = new_document(author, f"Synthetic procedure {n}")
        link_group(document, [Right.ACCEPT], [membership], author)
        commit_version(document, author, BODY, "edit")
        documents.append(document)
    with schema_context(migrated_tenant.number):
        with django_assert_max_num_queries(12) as one:
            tags(author, documents[:1])
        with django_assert_max_num_queries(len(one.captured_queries)):
            found = tags(author, documents)
    assert all([tag.state for tag in shown] == [State.AWAITING_REVIEW] for shown in found.values())


def test_hold_tags_cost_one_query(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
) -> None:
    """Thirty documents, ten of them held: the folder list reads the holds in one query of its
    own, and costs the same with ten held as with none."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext
    from django.utils import timezone

    from editing.models import Draft, Hold
    from review.state import tags

    client, author, _ = member_of("the.author@example.test")
    documents = [new_document(author, f"Synthetic procedure {n}") for n in range(30)]

    def hold_reads(queries: list[dict[str, Any]]) -> int:
        return sum('"editing_hold"' in query["sql"] for query in queries)

    # The first request fills the caches every later one reads.
    assert client.get("/folder/1/").status_code == 200
    with CaptureQueriesContext(connection) as unheld:
        assert client.get("/folder/1/").status_code == 200
    with schema_context(migrated_tenant.number):
        now = timezone.now()
        for n, document in enumerate(documents[:10]):
            hold = Hold.objects.create(
                document=document,
                user=author,
                acquired_at=now,
                last_activity_at=now,
                reserved_at=now if n % 2 else None,
            )
            Draft.objects.create(hold=hold, base_commit="0" * 40, content={})
    with CaptureQueriesContext(connection) as held:
        assert client.get("/folder/1/").status_code == 200
    assert len(held.captured_queries) == len(unheld.captured_queries)
    with schema_context(migrated_tenant.number):
        with CaptureQueriesContext(connection) as tagged:
            found = tags(author, documents, administrator=True)
    assert hold_reads(tagged.captured_queries) == 1
    hold_states = [
        tag.state.value
        for document in documents
        for tag in found[document.pk]
        if tag.state.value in ("held", "reserved")
    ]
    assert sorted(hold_states) == ["held"] * 5 + ["reserved"] * 5


# Epic 10
def test_an_archived_document_is_tagged_archived_first(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    """Only administrators reach an archived document; its tags open with *archived*."""
    from access.rights import Right
    from documents import archive
    from review.state import tags

    _, author, author_membership = member_of("the.author@example.test")
    admin_client, admin, _ = member_of("the.admin@example.test", is_tenant_admin=True)
    document = new_document(author)
    link_group(document, [Right.EDIT], [author_membership], author)
    commit_version(document, author, BODY, "edit")
    with schema_context(migrated_tenant.number):
        before = tags(admin, [document], administrator=True)[document.pk]
        archive.archive(document, admin)
        document.refresh_from_db()
        after = tags(admin, [document], administrator=True)[document.pk]

    assert State.ARCHIVED not in [tag.state for tag in before]
    assert after[0].state is State.ARCHIVED
    assert [tag.state for tag in after[1:]] == [tag.state for tag in before]
    page = admin_client.get(f"/document/{document.number}/").content.decode()
    assert page.index('data-state="archived"') < page.index('data-state="no_reviewer_assigned"')
