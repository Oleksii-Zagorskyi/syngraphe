"""A change summary of several lines (DL-0532, DL-0535): its first line is the commit's subject and
the line every list reads, the rest the commit's body; `VERSION.summary` holds the whole, drawn
whole on the version's page and in the review page's panel. Each line is checked on its own.
People and texts are synthetic examples."""

from __future__ import annotations

import re
from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

BODY = "# Terms\n\nThe first term.\nThe second term.\n"
FIRST = "Terms clarified"
SECOND = "The first term now names its owner."
THIRD = "The second term is unchanged in substance."
TYPED = f"{FIRST}\r\n{SECOND}\r\n{THIRD}"


@pytest.fixture(autouse=True)
def in_english(settings: Any) -> None:
    settings.LANGUAGE_CODE = "en"


@pytest.fixture
def editing_holder(migrated_tenant: Any, member_of: Any, new_document: Any) -> tuple[Any, Any]:
    """A document taken by its author, its draft changed: ready to finish."""
    from editing.models import Draft

    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
    with schema_context(migrated_tenant.number):
        draft = Draft.objects.get(hold__document=document)
        draft.content = {**draft.content, "document.md": BODY}
        draft.save()
    return client, document


def test_the_rules_by_line() -> None:
    from editing.summary import problem

    assert problem(f"{FIRST}\n{SECOND}") is None
    assert problem(TYPED) is None
    assert problem("") is not None
    assert problem("x" * 501) is not None
    assert problem(f"{FIRST}\n" + "y" * 499) is None
    assert problem(f"{FIRST}\n" + "y" * 5000) is not None
    assert problem(f"Refs: x\n{SECOND}") is not None
    assert problem(f"{FIRST}\nRefs: x") is not None
    assert problem(f"{FIRST}\nline\x0bwith a control") is not None
    assert problem(f"{FIRST}\nfirst second") is not None
    for separator in ("\u2028", "\u2029", "\x85"):
        # At the end of an inner line: one at the summary's end is stripped with its spaces.
        assert problem(f"{FIRST}\nline{separator}\nmore") is not None, repr(separator)


def test_a_trailer_in_the_body_is_refused(migrated_tenant: Any, editing_holder: Any) -> None:
    client, document = editing_holder
    sent = client.post(
        f"/document/{document.number}/edit/send/", {"summary": f"{FIRST}\r\nRefs: x"}
    )

    assert sent.status_code == 400
    assert "Line 2" in sent.content.decode()


def test_a_long_summary(
    migrated_tenant: Any, editing_holder: Any, member_of: Any, link_group: Any
) -> None:
    from access.rights import Right
    from documents import gitstore
    from documents.models import Version

    client, document = editing_holder
    n = document.number

    sent = client.post(f"/document/{n}/edit/send/", {"summary": TYPED})

    assert sent.status_code == 302, sent.content.decode()[:500]
    with schema_context(migrated_tenant.number):
        version = Version.objects.get(document=document, kind="edit")
        repo = gitstore.open_repository(migrated_tenant.number, n)
        message = gitstore.commit_at(repo, version.commit_sha).message
    assert message.startswith(f"{FIRST}\n\n{SECOND}\n{THIRD}\n\n"), message
    assert version.summary == f"{FIRST}\n\n{SECOND}\n{THIRD}"
    # The version's page, under its band, and the review page's panel: the whole.
    reviewer, _, reviewer_membership = member_of("the.reviewer@example.test")
    link_group(
        document, [Right.ACCEPT, Right.VIEW_ALL_HISTORY], [reviewer_membership], version.author
    )
    number = re.search(
        r'data-number="([0-9.\-]+)"', reviewer.get(f"/document/{n}/pending/").content.decode()
    )
    assert number is not None
    for path in (f"/document/{n}/version/{number.group(1)}/", f"/document/{n}/pending/"):
        page = reviewer.get(path).content.decode()
        assert SECOND in page and THIRD in page, path
    # The lists: History's rows, the acceptance's and the return's confirmations — the first line
    # alone.
    for path in (
        f"/document/{n}/history/",
        f"/document/{n}/pending/accept/",
        f"/document/{n}/pending/return/",
    ):
        page = reviewer.get(path).content.decode()
        assert FIRST in page and SECOND not in page, path


def test_a_notification_holds_no_summary(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    from access.rights import Right
    from editing.models import Draft
    from notifications.models import Notification

    client, author, membership = member_of("the.author@example.test")
    _, reviewer, reviewer_membership = member_of("the.reviewer@example.test")
    document = new_document(author)
    link_group(document, [Right.EDIT], [membership], author)
    link_group(document, [Right.ACCEPT], [reviewer_membership], author)
    assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
    with schema_context(migrated_tenant.number):
        draft = Draft.objects.get(hold__document=document)
        draft.content = {**draft.content, "document.md": BODY}
        draft.save()
    assert (
        client.post(f"/document/{document.number}/edit/send/", {"summary": TYPED}).status_code
        == 302
    )

    with schema_context(migrated_tenant.number):
        told = list(Notification.objects.filter(user=reviewer))
    assert told, "the reviewer is told of the version"
    assert all(FIRST not in str(n.__dict__) and SECOND not in str(n.__dict__) for n in told)
