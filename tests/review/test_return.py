"""Returning a run (DL-0224, DL-0233, DL-0369, DL-0378, DL-0420): a holder of *accept* declines the
pending run with a reason, as a passport commit of kind `return` and its rows; the run stays
pending and whole, its authors are told — the reason in the entry, never in the email — and the
document shows *returned* to readers of pending work until a new version is sent. Refused with its
reason, under the rule a reason keeps.

People, organisations, groups and texts are synthetic examples: every address ends in
`@example.test`, and every text is invented.
"""

from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import urlsplit

import pytest
from django.test import Client
from django.utils import translation

from access.rights import Right
from audit.models import AuditEvent
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

REASON = "Synthetic reason: the time limits contradict the section on the register"
BIDI = "‮"
FIRST = (
    "# General provisions\n\n"
    "A request for approval is made in writing.\n"
    "A request is considered within ten days.\n"
)
SECOND = FIRST + "\nA copy of the decision goes to the applicant that day.\n"
THIRD = SECOND + "\nThe register of requests is kept by the officer in charge.\n"
REFUSED = (
    "x" * 501,
    "",
    "   ",
    f"Synthetic reason {BIDI}with a direction control",
    "Synthetic first line\nSynthetic second line",
)


def signed_in(tenant: Any, user: Any) -> Client:
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(user)
    session = client.session
    session["tenant_number"] = tenant.number
    session.save()
    return client


def sending_address(number: int) -> Any:
    """A sending address in an organisation's schema, so its emails are queued."""
    from mail.models import MailSender

    with schema_context(number):
        return MailSender.objects.create(
            host="127.0.0.1",
            port=2525,
            address="mail@example.test",
            display_name="Synthetic",
            username="",
            password_encrypted=b"",
            security="none",
        )


def redirected_to(response: Any, path: str) -> bool:
    return response.status_code == 302 and urlsplit(response["Location"]).path == path


def text_nodes(body: str) -> set[str]:
    """Every run of text between two tags, stripped, entities read."""
    return {html.unescape(node).strip() for node in re.findall(r">([^<]+)<", body) if node.strip()}


def has_reason_field(body: str) -> bool:
    return any(
        re.search(r'\bname="reason"', tag)
        for tag in re.findall(r"<(?:input|textarea)\b[^>]*>", body)
    )


def notices(body: str) -> list[str]:
    """The text of each message the page shows."""
    return [
        html.unescape(re.sub(r"<[^>]+>", "", found)).strip()
        for found in re.findall(r'<p class="notice" role="status">(.*?)</p>', body, re.S)
    ]


def tags_of(tenant: Any, user: Any, document: Any) -> list[Any]:
    from review.state import tags

    with schema_context(tenant.number), translation.override("en"):
        return tags(user, [document])[document.pk]


def returns() -> int:
    from review.models import Return

    return Return.objects.count()


def test_return_is_a_passport_commit(
    migrated_tenant: Any,
    cast: Any,
    commit_version: Any,
    repository: Any,
    settings: Any,
) -> None:
    from documents import bundle
    from documents.models import Version
    from mail.models import EmailOutbox
    from notifications.models import Notification
    from review.models import Return

    settings.LANGUAGE_CODE = "en"
    sending_address(migrated_tenant.number)
    people = cast(editors=("a", "b"), reviewers=("r",))
    document, reviewer = people.document, people["r"]
    number = document.number
    commit_version(document, people["a"], FIRST, "edit")
    last = commit_version(document, people["b"], SECOND, "edit")
    passport_before = repository.read(document, "passport.md")
    client = signed_in(migrated_tenant, reviewer)
    address = f"/document/{number}/pending/return/"

    confirmation = client.get(address)
    assert confirmation.status_code == 200
    body = confirmation.content.decode()
    assert has_reason_field(body)
    assert any(
        'type="hidden"' in tag and f'value="{last.commit_sha}"' in tag
        for tag in re.findall(r'<input\b[^>]*\bname="confirmed"[^>]*>', body)
    ), "no hidden `confirmed` naming the run's last version"

    response = client.post(address, {"reason": REASON, "confirmed": last.commit_sha})

    assert redirected_to(response, f"/document/{number}/pending/"), response.status_code
    head = repository.head(document)
    assert repository.kinds(document) == ["created", "edit", "edit", "return"]
    assert repository.parent(document, head) == last.commit_sha
    assert repository.read(document, "document.md", head) == repository.read(
        document, "document.md", last.commit_sha
    )
    # The passport ends with a `## return` section: `at`, `by`, `version`, `reason`.
    passport = repository.read(document, "passport.md", head)
    assert passport.startswith(passport_before)
    appended = passport[len(passport_before) :]
    headings = re.findall(r"^## .*$", passport, re.MULTILINE)
    assert headings and re.fullmatch(r"## return\b.*", headings[-1]), headings
    section = appended.split(headings[-1], 1)[1]
    assert re.search(r"^at: \S+", section, re.MULTILINE)
    assert re.search(rf"^by: {reviewer.pk}$", section, re.MULTILINE)
    assert re.search(rf"^version: {last.commit_sha}$", section, re.MULTILINE)
    assert re.search(rf"^reason: {re.escape(REASON)}$", section, re.MULTILINE)
    entry = bundle.passport_entries(passport)[-1]
    assert (entry.kind, entry.by, entry.version, entry.reason) == (
        "return",
        str(reviewer.pk),
        last.commit_sha,
        REASON,
    )
    assert reviewer.email not in passport

    with schema_context(migrated_tenant.number):
        created = Version.objects.get(document=document, kind="created")
        row = Version.objects.get(document=document, kind="return")
        assert row.commit_sha == head
        returned = Return.objects.get()
        assert returned.version_id == row.pk
        assert returned.returned_from_id == created.pk
        assert returned.reviewer_id == reviewer.pk
        assert returned.reason == REASON
        assert returned.at is not None
        told = list(Notification.objects.filter(event="returned"))
        assert sorted(n.user_id for n in told) == sorted([people["a"].pk, people["b"].pk])
        for notification in told:
            assert notification.category == "document"
            assert notification.document_id == document.pk
            assert notification.facts["reason"] == REASON
            [email] = EmailOutbox.objects.filter(notification_id=notification.pk)
            assert REASON not in email.subject and REASON not in email.body
    event = AuditEvent.objects.get(action="document.returned")
    assert event.actor_id == reviewer.pk
    assert event.object_id == document.pk
    assert any(
        tag.state == "returned" and tag.label == "returned"
        for tag in tags_of(migrated_tenant, reviewer, document)
    )


def test_the_run_stays_whole(
    migrated_tenant: Any, cast: Any, commit_version: Any, settings: Any
) -> None:
    from review import services

    settings.LANGUAGE_CODE = "en"
    people = cast(editors=("a", "b"), reviewers=("r",))
    document, reviewer = people.document, people["r"]
    commit_version(document, people["a"], FIRST, "edit")
    last = commit_version(document, people["b"], SECOND, "edit")
    with schema_context(migrated_tenant.number):
        services.return_run(document, reviewer, REASON, confirmed=last.commit_sha)

    commit_version(document, people["a"], THIRD, "edit")

    shown = tags_of(migrated_tenant, reviewer, document)
    assert not [tag for tag in shown if tag.state == "returned"]
    assert any(
        tag.state == "awaiting_review" and tag.label == "awaiting review" for tag in shown
    ), shown
    page = signed_in(migrated_tenant, reviewer).get(f"/document/{document.number}/pending/accept/")
    assert page.status_code == 200
    body = page.content.decode()
    for pending in ("0.0-1", "0.0-2", "0.0-3"):
        assert f'data-number="{pending}"' in body, pending


@pytest.mark.parametrize(
    "case",
    ["reserved", "no_reviewer", "nothing_to_return", "not_a_reviewer", "run_changed", "returned"],
)
def test_refusals(
    case: str,
    migrated_tenant: Any,
    cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    repository: Any,
    settings: Any,
) -> None:
    from access.models import AccessGroup
    from editing import holds, reservations
    from review import services

    settings.LANGUAGE_CODE = "en"
    people = cast(editors=("a",), reviewers=() if case == "no_reviewer" else ("r",))
    document = people.document
    number = document.number
    first = (
        commit_version(document, people["a"], FIRST, "edit")
        if case != "nothing_to_return"
        else None
    )
    confirmed: str | None = None
    actor = people["r"] if "r" in people.people else None
    if case == "reserved":
        link_group(document, [Right.RESERVE_FOR_EDITING], [people.memberships["a"]], people["a"])
        with schema_context(migrated_tenant.number):
            reservations.reserve(holds.take(document, people["a"]), people["a"])
        expected = "reserved"
    elif case == "no_reviewer":
        _, actor, membership = member_of("q.synthetic@example.test")
        with schema_context(migrated_tenant.number):
            group = AccessGroup.objects.create(
                name="Synthetic reviewers without a document", created_by=actor, actor_kind="user"
            )
            group.grant(Right.ACCEPT, by=actor)
            group.add_member(membership, by=actor)
        expected = "no_reviewer"
    elif case == "nothing_to_return":
        expected = "nothing_to_return"
    elif case == "not_a_reviewer":
        actor = people["a"]
        expected = "not_a_reviewer"
    elif case == "run_changed":
        assert first is not None
        second = commit_version(document, people["a"], SECOND, "edit")
        confirmed = first.commit_sha
        expected = "run_changed"
    else:
        with schema_context(migrated_tenant.number):
            services.return_run(document, people["r"], REASON)
        expected = "already_returned"
    head = repository.head(document)
    with schema_context(migrated_tenant.number):
        before = returns()

    with schema_context(migrated_tenant.number):
        with pytest.raises(services.ReturnRefused) as refused:
            services.return_run(document, actor, REASON, confirmed=confirmed)

    assert refused.value.reason == expected
    assert repository.head(document) == head
    with schema_context(migrated_tenant.number):
        assert returns() == before

    address = f"/document/{number}/pending/return/"
    if case in ("reserved", "nothing_to_return"):
        client = signed_in(migrated_tenant, actor)
        response = client.post(
            address, {"reason": REASON, "confirmed": first.commit_sha if first else ""}
        )
        assert redirected_to(response, f"/document/{number}/pending/"), response.status_code
        following = client.get(response["Location"]).content.decode()
        assert [text for text in notices(following) if text], "no reason shown"
    elif case == "not_a_reviewer":
        client = signed_in(migrated_tenant, actor)
        assert client.get(address).status_code == 404
        assert client.post(address, {"reason": REASON}).status_code == 404
    elif case == "run_changed":
        client = signed_in(migrated_tenant, actor)
        response = client.post(address, {"reason": REASON, "confirmed": confirmed})
        assert response.status_code == 409
        body = response.content.decode()
        assert has_reason_field(body)
        assert f'value="{second.commit_sha}"' in body
    assert repository.head(document) == head
    with schema_context(migrated_tenant.number):
        assert returns() == before


def test_reason_rule(
    migrated_tenant: Any, cast: Any, commit_version: Any, repository: Any, settings: Any
) -> None:
    from editing.reservations import ReasonRefused
    from notifications.models import Notification
    from review import services

    settings.LANGUAGE_CODE = "en"
    people = cast(editors=("a",), reviewers=("r",))
    document = people.document
    last = commit_version(document, people["a"], FIRST, "edit")
    client = signed_in(migrated_tenant, people["r"])
    address = f"/document/{document.number}/pending/return/"
    plain = client.get(address)
    assert plain.status_code == 200
    before = text_nodes(plain.content.decode())
    head = repository.head(document)
    events = AuditEvent.objects.count()
    with schema_context(migrated_tenant.number):
        notifications = Notification.objects.count()

    for reason in REFUSED:
        refused = client.post(address, {"reason": reason, "confirmed": last.commit_sha})

        assert refused.status_code == 400, repr(reason[:20])
        body = refused.content.decode()
        assert has_reason_field(body), repr(reason[:20])
        assert f'value="{last.commit_sha}"' in body, repr(reason[:20])
        # A sentence the plain confirmation did not have, other than the reason typed coming back.
        typed = [part.replace(BIDI, "").strip() for part in reason.split("\n")]
        added = [
            node
            for node in text_nodes(body) - before
            if not any(part and part in node.replace(BIDI, "") for part in typed)
            and re.search(r"[A-Za-z]{2}", node)
        ]
        assert added, repr(reason[:20])
        with schema_context(migrated_tenant.number):
            with pytest.raises(ReasonRefused):
                services.return_run(document, people["r"], reason, confirmed=last.commit_sha)
        assert repository.head(document) == head, repr(reason[:20])
        with schema_context(migrated_tenant.number):
            assert returns() == 0
            assert Notification.objects.count() == notifications
        assert AuditEvent.objects.count() == events


def test_returned_runs_leave_in_review(
    migrated_tenant: Any, cast: Any, commit_version: Any, settings: Any
) -> None:
    from review import services

    settings.LANGUAGE_CODE = "en"
    people = cast(editors=("a",), reviewers=("r",))
    document = people.document
    listed_as = f'data-number="{document.number}"'
    commit_version(document, people["a"], FIRST, "edit")
    client = signed_in(migrated_tenant, people["r"])
    assert listed_as in client.get("/in-review/").content.decode()
    with schema_context(migrated_tenant.number):
        services.return_run(document, people["r"], REASON)

    in_review = client.get("/in-review/")
    menu = client.get("/folder/1/").content.decode()

    assert in_review.status_code == 200
    body = in_review.content.decode()
    assert listed_as not in body
    assert "No documents here." in body
    assert 'href="/in-review/"' not in menu

    commit_version(document, people["a"], SECOND, "edit")

    assert listed_as in client.get("/in-review/").content.decode()
    assert re.search(r'<a\b[^>]*\bhref="/in-review/"', client.get("/folder/1/").content.decode())


def test_returned_is_shown_to_readers_of_pending_work(
    migrated_tenant: Any, cast: Any, member_of: Any, link_group: Any, commit_version: Any
) -> None:
    from review import services

    people = cast(editors=("a",), reviewers=("r",))
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    _, accepted, membership = member_of("accepted.synthetic@example.test")
    link_group(document, [Right.VIEW_ACCEPTED], [membership], people["a"])
    with schema_context(migrated_tenant.number):
        services.return_run(document, people["r"], REASON)

    assert any(tag.state == "returned" for tag in tags_of(migrated_tenant, people["r"], document))
    assert not [
        tag for tag in tags_of(migrated_tenant, accepted, document) if tag.state == "returned"
    ]
