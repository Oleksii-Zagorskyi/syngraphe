"""The correction notice over appendices and parts (ADR-0014): at acceptance, an appendix line
another author of the run wrote that a covered version replaced or removed is an entry of that
appendix's file; a part state another author of the run set that a covered version changed is a
part entry; a reorder is none. Its page reads them, and its list line counts them. People and
titles are synthetic examples; text is invented English and file bytes are placeholders."""

from __future__ import annotations

import hashlib
import re
from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

BODY = "# Purpose\n\nThe body's sentence.\n"
ONE = [{"number": 1, "title": "Appendix one (example)"}]


def entry(number: int, data: bytes, title: str) -> dict[str, Any]:
    return {
        "number": number,
        "title": title,
        "file_name": f"form-{number}.txt",
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }


def accepted(tenant: Any, document: Any, reviewer: Any) -> Any:
    from review import services
    from review.models import Acceptance

    with schema_context(tenant.number):
        acceptance = services.accept(document, reviewer)
        return Acceptance.objects.get(pk=acceptance.pk)


def lines_of(tenant: Any, acceptance: Any) -> list[Any]:
    from review.models import CorrectionLine

    with schema_context(tenant.number):
        return list(CorrectionLine.objects.filter(notice__acceptance=acceptance))


def with_appendix(
    commit_version: Any, document: Any, user: Any, text: str, kind: str = "edit"
) -> Any:
    return commit_version(
        document, user, BODY, kind, files={"appendices/1.md": text.encode()}, appendices=ONE
    )


def flat(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def test_an_appendix_line_is_disclosed(
    migrated_tenant: Any, cast: Any, commit_version: Any, queued_authorship: list[Any]
) -> None:
    people = cast(editors=("a",), reviewers=("r",))
    document, author, reviewer = people.document, people["a"], people["r"]
    with_appendix(commit_version, document, author, "# One\n\nThe base sentence.\n")
    accepted(migrated_tenant, document, reviewer)
    with_appendix(
        commit_version, document, author, "# One\n\nThe base sentence.\n\nA's sentence.\n"
    )
    with_appendix(
        commit_version,
        document,
        reviewer,
        "# One\n\nThe base sentence.\n\nR's wording.\n",
        "reviewer_edit",
    )
    acceptance = accepted(migrated_tenant, document, reviewer)
    [line] = lines_of(migrated_tenant, acceptance)
    assert (line.entry, line.file, line.part) == ("line", "appendices/1.md", "")
    with schema_context(migrated_tenant.number):
        assert line.notice.author_id == author.pk


def test_part_entries_follow_the_rule(
    migrated_tenant: Any, cast: Any, commit_version: Any, queued_authorship: list[Any]
) -> None:
    people = cast(editors=("a",), reviewers=("r",))
    document, author, reviewer = people.document, people["a"], people["r"]
    two = b"the base's form"
    base_attachments = [
        entry(2, two, "Form two (example)"),
        entry(5, b"five", "Form five (example)"),
    ]
    commit_version(
        document,
        author,
        BODY,
        files={"appendices/1.md": b"# One\n", "attachments/2": two, "attachments/5": b"five"},
        appendices=ONE,
        attachments=base_attachments,
    )
    accepted(migrated_tenant, document, reviewer)
    # A adds 3, renames appendix 1, replaces 2 and reorders; R undoes each.
    commit_version(
        document,
        author,
        BODY,
        files={"attachments/2": b"A's form", "attachments/3": b"three"},
        appendices=[{"number": 1, "title": "Renamed by A (example)"}],
        attachments=[
            entry(5, b"five", "Form five (example)"),
            entry(2, b"A's form", "Form two (example)"),
            entry(3, b"three", "Form three (example)"),
        ],
    )
    commit_version(
        document,
        reviewer,
        BODY,
        "reviewer_edit",
        files={"attachments/2": b"R's form", "attachments/3": None},
        appendices=ONE,
        attachments=[
            entry(2, b"R's form", "Form two (example)"),
            entry(5, b"five", "Form five (example)"),
        ],
    )
    acceptance = accepted(migrated_tenant, document, reviewer)
    found = {(line.entry, line.part) for line in lines_of(migrated_tenant, acceptance)}
    assert found == {
        ("part_operation", "attachments/3"),
        ("part_operation", "appendices/1.md"),
        ("part_operation", "attachments/2"),
    }


def test_nobody_is_told_of_their_own_or_the_bases_part(
    migrated_tenant: Any, cast: Any, commit_version: Any, queued_authorship: list[Any]
) -> None:
    people = cast(editors=("a",), reviewers=("r",))
    document, author, reviewer = people.document, people["a"], people["r"]
    commit_version(
        document,
        author,
        BODY,
        files={"attachments/2": b"base"},
        attachments=[entry(2, b"base", "Form two (example)")],
    )
    accepted(migrated_tenant, document, reviewer)
    commit_version(
        document,
        reviewer,
        BODY,
        "reviewer_edit",
        files={"attachments/4": b"R's"},
        attachments=[
            entry(2, b"base", "Renamed by R (example)"),
            entry(4, b"R's", "R's form (example)"),
        ],
    )
    commit_version(
        document,
        reviewer,
        BODY,
        "reviewer_edit",
        files={"attachments/4": None},
        attachments=[entry(2, b"base", "Renamed again by R (example)")],
    )
    acceptance = accepted(migrated_tenant, document, reviewer)
    assert lines_of(migrated_tenant, acceptance) == []


def notice_page(tenant: Any, client: Any, author: Any) -> str:
    from notifications.models import Notification

    with schema_context(tenant.number):
        notification = Notification.objects.get(user=author, event="correction_notice")
    return client.get(f"/notifications/{notification.pk}/").content.decode()


def test_a_deleted_appendixs_lines_read(
    migrated_tenant: Any,
    cast: Any,
    commit_version: Any,
    member_of: Any,
    queued_authorship: list[Any],
    settings: Any,
) -> None:
    from django.test import Client

    settings.LANGUAGE_CODE = "en"
    people = cast(editors=("a",), reviewers=("r",))
    document, author, reviewer = people.document, people["a"], people["r"]
    with_appendix(commit_version, document, author, "# One\n\nThe base sentence.\n")
    accepted(migrated_tenant, document, reviewer)
    with_appendix(
        commit_version, document, author, "# One\n\nThe base sentence.\n\nA's sentence.\n"
    )
    commit_version(
        document, reviewer, BODY, "reviewer_edit", files={"appendices/1.md": None}, appendices=[]
    )
    accepted(migrated_tenant, document, reviewer)
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(author)
    session = client.session
    session["tenant_number"] = migrated_tenant.number
    session.save()
    html = notice_page(migrated_tenant, client, author)
    assert "A&#x27;s sentence." in html or "A's sentence." in html
    changes = re.search(r'<div class="changes document-text">(.*?)</div>', html, re.S)
    assert changes and "<del>" in changes.group(1) and "<ins>" not in changes.group(1)
    link = re.search(r'<a class="btn" href="([^"]+)">Open the document</a>', html)
    assert link and re.fullmatch(rf"/document/{document.number}/version/[0-9.]+/", link.group(1))


def test_appendix_lines_alone_open_the_accepted_version(
    migrated_tenant: Any, cast: Any, commit_version: Any, queued_authorship: list[Any]
) -> None:
    from django.test import Client

    people = cast(editors=("a",), reviewers=("r",))
    document, author, reviewer = people.document, people["a"], people["r"]
    two = [{"number": 2, "title": "Appendix two (example)"}]
    commit_version(
        document, author, BODY, files={"appendices/2.md": b"# Two\n\nBase.\n"}, appendices=two
    )
    accepted(migrated_tenant, document, reviewer)
    commit_version(document, author, BODY, files={"appendices/2.md": b"# Two\n\nBase.\n\nA's.\n"})
    commit_version(
        document,
        reviewer,
        BODY,
        "reviewer_edit",
        files={"appendices/2.md": b"# Two\n\nBase.\n\nR's.\n"},
    )
    acceptance = accepted(migrated_tenant, document, reviewer)
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(author)
    session = client.session
    session["tenant_number"] = migrated_tenant.number
    session.save()
    from django.urls import resolve

    html = notice_page(migrated_tenant, client, author)
    page = f"/document/{document.number}/version/{acceptance.number}/"
    assert f'<a class="btn" href="{page}">' in html
    assert resolve(page).url_name == "document_version"
    assert "/appendix/" not in html


def test_an_appendix_image_reaches_the_notices_author(
    migrated_tenant: Any,
    cast: Any,
    commit_version: Any,
    member_of: Any,
    invented_image: Any,
    queued_authorship: list[Any],
) -> None:
    """A, holding no history right, wrote image X into appendix 1; R's version replaced it with Y,
    so the head drops X: the notice's before side shows X, served to A alone."""
    from django.test import Client

    from notifications.models import Notification

    people = cast(editors=("a",), reviewers=("r",))
    document, author, reviewer = people.document, people["a"], people["r"]
    x, y = invented_image("png"), invented_image("png", shade=1)
    name_x = f"images/{hashlib.sha256(x).hexdigest()}.png"
    name_y = f"images/{hashlib.sha256(y).hexdigest()}.png"
    with_appendix(commit_version, document, author, "# One\n\nBase.\n")
    accepted(migrated_tenant, document, reviewer)
    commit_version(
        document,
        author,
        BODY,
        files={"appendices/1.md": f"# One\n\nBase.\n\n![X]({name_x})\n".encode(), name_x: x},
    )
    commit_version(
        document,
        reviewer,
        BODY,
        "reviewer_edit",
        files={
            "appendices/1.md": f"# One\n\nBase.\n\n![Y]({name_y})\n".encode(),
            name_y: y,
            name_x: None,
        },
    )
    accepted(migrated_tenant, document, reviewer)
    with schema_context(migrated_tenant.number):
        notification = Notification.objects.get(user=author, event="correction_notice")
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(author)
    session = client.session
    session["tenant_number"] = migrated_tenant.number
    session.save()
    route = f"/notifications/{notification.pk}/image/{name_x.removeprefix('images/')}/"
    assert f'src="{route}"' in client.get(f"/notifications/{notification.pk}/").content.decode()
    assert client.get(route).content == x
    other, _, _ = member_of("a.stranger@example.test")
    assert other.get(route).status_code == 404


def test_the_list_line_counts_lines_and_parts(
    migrated_tenant: Any,
    cast: Any,
    commit_version: Any,
    queued_authorship: list[Any],
    settings: Any,
) -> None:
    """DL-0480: the Notifications list says how many lines and parts the notice holds."""
    from django.test import Client

    settings.LANGUAGE_CODE = "en"
    people = cast(editors=("a",), reviewers=("r",))
    document, author, reviewer = people.document, people["a"], people["r"]
    with_appendix(commit_version, document, author, "# One\n\nThe base sentence.\n")
    accepted(migrated_tenant, document, reviewer)
    commit_version(
        document,
        author,
        BODY,
        files={
            "appendices/1.md": b"# One\n\nThe base sentence.\n\nA's sentence.\n",
            "attachments/3": b"3",
        },
        appendices=[{"number": 1, "title": "Renamed by A (example)"}],
        attachments=[entry(3, b"3", "Form three (example)")],
    )
    commit_version(
        document,
        reviewer,
        BODY,
        "reviewer_edit",
        files={"appendices/1.md": b"# One\n\nThe base sentence.\n\nR's.\n", "attachments/3": None},
        appendices=ONE,
        attachments=[],
    )
    accepted(migrated_tenant, document, reviewer)
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(author)
    session = client.session
    session["tenant_number"] = migrated_tenant.number
    session.save()
    listed = flat(client.get("/notifications/?tab=document").content.decode())
    assert "— 1 line and 2 parts changed." in listed


def signed(tenant: Any, user: Any) -> Any:
    from django.test import Client

    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(user)
    session = client.session
    session["tenant_number"] = tenant.number
    session.save()
    return client


def run_with_parts(tenant: Any, cast: Any, commit_version: Any) -> tuple[Any, Any, Any]:
    """A run whose author added attachment 3 and wrote an appendix line, and whose reviewer
    removed the attachment and replaced the line; accepted. `(people, document, acceptance)`."""
    people = cast(editors=("a",), reviewers=("r",))
    document, author, reviewer = people.document, people["a"], people["r"]
    from identity.models import User

    User.objects.filter(pk=reviewer.pk).update(display_name="Reviewer R")
    with_appendix(commit_version, document, author, "# One\n\nThe base sentence.\n")
    accepted(tenant, document, reviewer)
    commit_version(
        document,
        author,
        BODY,
        files={
            "appendices/1.md": b"# One\n\nThe base sentence.\n\nA's sentence.\n",
            "attachments/3": b"3",
        },
        attachments=[entry(3, b"3", "Payment form (example)")],
    )
    commit_version(
        document,
        reviewer,
        BODY,
        "reviewer_edit",
        files={"appendices/1.md": b"# One\n\nThe base sentence.\n\nR's.\n", "attachments/3": None},
        attachments=[],
    )
    return people, document, accepted(tenant, document, reviewer)


def test_the_page_draws_part_entries(
    migrated_tenant: Any,
    cast: Any,
    commit_version: Any,
    queued_authorship: list[Any],
    settings: Any,
) -> None:
    settings.LANGUAGE_CODE = "en"
    people, document, acceptance = run_with_parts(migrated_tenant, cast, commit_version)
    html = notice_page(migrated_tenant, signed(migrated_tenant, people["a"]), people["a"])
    text = flat(html)
    assert "A's sentence." in text or "A&#x27;s sentence." in html
    assert "You added this attachment in" in text and "Reviewer R removed it in" in text
    assert "📎 Payment form (example)" in text
    # Removed at the accepted version: nothing to open.
    assert "/attachment/3/" not in html
    assert "a reviewer changed what you wrote: 1 line and 1 part." in text


def test_a_restored_part_is_named_as_it_was_and_opens(
    migrated_tenant: Any,
    cast: Any,
    commit_version: Any,
    queued_authorship: list[Any],
    settings: Any,
) -> None:
    """A removes the base's attachment 2; R restores it under a new title. A is told, the part
    named by its title before A's version, and *open* leads to it at the accepted version."""
    from django.urls import resolve

    from identity.models import User

    settings.LANGUAGE_CODE = "en"
    people = cast(editors=("a",), reviewers=("r",))
    document, author, reviewer = people.document, people["a"], people["r"]
    User.objects.filter(pk=reviewer.pk).update(display_name="Reviewer R")
    commit_version(
        document,
        author,
        BODY,
        files={"attachments/2": b"two"},
        attachments=[entry(2, b"two", "Form two (example)")],
    )
    accepted(migrated_tenant, document, reviewer)
    commit_version(document, author, BODY, files={"attachments/2": None}, attachments=[])
    commit_version(
        document,
        reviewer,
        BODY,
        "reviewer_edit",
        files={"attachments/2": b"two"},
        attachments=[entry(2, b"two", "Restored by R (example)")],
    )
    acceptance = accepted(migrated_tenant, document, reviewer)
    html = notice_page(migrated_tenant, signed(migrated_tenant, author), author)
    text = flat(html)
    assert "You removed this attachment in" in text and "Reviewer R restored it in" in text
    assert "📎 Form two (example)" in text and "Restored by R" not in text
    link = f"/document/{document.number}/version/{acceptance.number}/attachment/2/"
    assert f'href="{link}"' in html
    assert resolve(link).url_name == "document_version_attachment"


def test_a_part_entry_follows_the_state_its_change_undid(
    migrated_tenant: Any, cast: Any, commit_version: Any, queued_authorship: list[Any]
) -> None:
    """The file and the title are state of their own: R replacing the file of the base's
    attachment 2, which A only renamed, tells nobody; R replacing the file of attachment 4,
    which A replaced and B then renamed, tells A, not B."""
    people = cast(editors=("a", "b"), reviewers=("r",))
    document, a, b, reviewer = people.document, people["a"], people["b"], people["r"]
    commit_version(
        document,
        a,
        BODY,
        files={"attachments/2": b"two", "attachments/4": b"four"},
        attachments=[entry(2, b"two", "Form two (example)"), entry(4, b"four", "Form four")],
    )
    accepted(migrated_tenant, document, reviewer)
    commit_version(
        document,
        a,
        BODY,
        files={"attachments/4": b"A's four"},
        attachments=[entry(2, b"two", "Renamed by A"), entry(4, b"A's four", "Form four")],
    )
    commit_version(
        document,
        b,
        BODY,
        attachments=[entry(2, b"two", "Renamed by A"), entry(4, b"A's four", "Renamed by B")],
    )
    commit_version(
        document,
        reviewer,
        BODY,
        "reviewer_edit",
        files={"attachments/2": b"R's two", "attachments/4": b"R's four"},
        attachments=[entry(2, b"R's two", "Renamed by A"), entry(4, b"R's four", "Renamed by B")],
    )
    acceptance = accepted(migrated_tenant, document, reviewer)
    with schema_context(migrated_tenant.number):
        found = [
            (line.notice.author_id, line.part) for line in lines_of(migrated_tenant, acceptance)
        ]
    assert found == [(a.pk, "attachments/4")]


def test_the_authors_half_names_what_was_undone(
    migrated_tenant: Any,
    cast: Any,
    commit_version: Any,
    queued_authorship: list[Any],
    settings: Any,
) -> None:
    """A replaces and renames attachment 2 in one version; R renames it back: A's half is the
    rename, the half R's change undid."""
    settings.LANGUAGE_CODE = "en"
    people = cast(editors=("a",), reviewers=("r",))
    document, author, reviewer = people.document, people["a"], people["r"]
    commit_version(
        document,
        author,
        BODY,
        files={"attachments/2": b"two"},
        attachments=[entry(2, b"two", "Form two (example)")],
    )
    accepted(migrated_tenant, document, reviewer)
    commit_version(
        document,
        author,
        BODY,
        files={"attachments/2": b"A's two"},
        attachments=[entry(2, b"A's two", "Renamed by A (example)")],
    )
    commit_version(
        document,
        reviewer,
        BODY,
        "reviewer_edit",
        attachments=[entry(2, b"A's two", "Form two (example)")],
    )
    accepted(migrated_tenant, document, reviewer)
    text = flat(notice_page(migrated_tenant, signed(migrated_tenant, author), author))
    assert "You renamed this attachment in" in text and "renamed it in" in text
    assert "📎 Renamed by A (example)" in text


def test_an_unreadable_history_costs_the_links_never_the_notice(
    migrated_tenant: Any,
    cast: Any,
    commit_version: Any,
    queued_authorship: list[Any],
    settings: Any,
    monkeypatch: Any,
) -> None:
    from review import history

    settings.LANGUAGE_CODE = "en"
    people, document, _acceptance = run_with_parts(migrated_tenant, cast, commit_version)

    def unreadable(*_args: Any) -> None:
        raise ValueError("a record that does not read")

    monkeypatch.setattr(history, "version_for", unreadable)
    response = signed(migrated_tenant, people["a"]).get(
        notice_page_url(migrated_tenant, people["a"])
    )
    html = response.content.decode()
    assert response.status_code == 200
    assert "You added this attachment in" in flat(html)
    assert f'<a class="btn" href="/document/{document.number}/">' in html


def notice_page_url(tenant: Any, author: Any) -> str:
    from notifications.models import Notification

    with schema_context(tenant.number):
        notification = Notification.objects.get(user=author, event="correction_notice")
    return f"/notifications/{notification.pk}/"


def test_an_appendix_has_no_frontmatter(
    migrated_tenant: Any, cast: Any, commit_version: Any, queued_authorship: list[Any]
) -> None:
    """An appendix's whole text is its body: lines between two rules at its top are disclosed."""
    people = cast(editors=("a",), reviewers=("r",))
    document, author, reviewer = people.document, people["a"], people["r"]
    with_appendix(commit_version, document, author, "---\nThe base sentence.\n---\n")
    accepted(migrated_tenant, document, reviewer)
    with_appendix(commit_version, document, author, "---\nA's sentence.\n---\n")
    with_appendix(commit_version, document, reviewer, "---\nR's wording.\n---\n", "reviewer_edit")
    acceptance = accepted(migrated_tenant, document, reviewer)
    [line] = lines_of(migrated_tenant, acceptance)
    assert (line.file, line.range_after) == ("appendices/1.md", "2")
