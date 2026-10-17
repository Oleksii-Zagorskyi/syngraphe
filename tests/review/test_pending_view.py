"""The *Pending edits* tab: the whole document, every change since the last acceptance marked in
place and, with *show author* on, attributed (DL-0040, DL-0170, ASR-21).

Groups, people and texts are synthetic examples.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

FIRST = "# Загальні положення\n\nЗаяву подають письмово.\nСтрок розгляду становить десять днів.\n"
SECOND = FIRST.replace("десять днів", "п'ять робочих днів")
THIRD = SECOND + "\nКопію рішення надсилають заявникові.\n"


def named(user: Any, name: str) -> Any:
    user.display_name = name
    user.save(update_fields=["display_name"])
    return user


def reviewer_and_authors(member_of: Any, new_document: Any, link_group: Any) -> tuple[Any, ...]:
    from access.rights import Right

    reviewer_client, reviewer, reviewer_membership = member_of("the.reviewer@example.test")
    _, author_a, membership_a = member_of("author.a@example.test")
    _, author_b, membership_b = member_of("author.b@example.test")
    named(reviewer, "Погоджувач Р")
    named(author_a, "Автор А")
    named(author_b, "Автор Б")
    document = new_document(reviewer)
    link_group(document, [Right.ACCEPT], [reviewer_membership], reviewer)
    link_group(document, [Right.EDIT], [membership_a, membership_b], reviewer)
    return reviewer_client, reviewer, author_a, author_b, document


def show_author(client: Any, on: bool = True) -> None:
    response = client.post("/preferences/show-author/", {"show_author": "on" if on else "off"})
    assert response.status_code in (302, 303)


def test_run_marked_and_attributed(
    member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    """Two versions by two authors since the `created` commit: both marked, each attributed,
    numbered from `0.0`."""
    client, _, author_a, author_b, document = reviewer_and_authors(
        member_of, new_document, link_group
    )
    commit_version(document, author_a, FIRST, "edit")
    commit_version(document, author_b, THIRD.replace("п'ять робочих", "десять"), "edit")
    page = client.get(f"/document/{document.number}/pending/").content.decode()
    assert "<ins>Заяву подають письмово.</ins>" in page
    assert "<ins>Копію рішення надсилають заявникові.</ins>" in page
    assert 'data-number="0.0-1"' in page and 'data-number="0.0-2"' in page
    assert 'data-author="' not in page
    show_author(client)
    page = client.get(f"/document/{document.number}/pending/").content.decode()
    assert '<span class="by" data-author="Автор А" title="Автор А"><ins>Заяву' in page
    assert '<span class="by" data-author="Автор Б" title="Автор Б"><ins>Копію' in page


def test_run_after_an_acceptance_marked_word_by_word(
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    accepted_directly: Any,
) -> None:
    client, reviewer, author_a, author_b, document = reviewer_and_authors(
        member_of, new_document, link_group
    )
    commit_version(document, reviewer, FIRST, "reviewer_edit")
    accepted_directly(document, reviewer)
    commit_version(document, author_a, SECOND, "edit")
    commit_version(document, author_b, THIRD, "edit")
    page = client.get(f"/document/{document.number}/pending/").content.decode()
    # Both changes marked in place; unattributed while *show author* is off.
    assert "<ins>п&#x27;ять робочих</ins>" in page and "<del>десять</del>" in page
    assert "<ins>Копію рішення надсилають заявникові.</ins>" in page
    assert 'data-author="' not in page
    assert 'data-number="0.1-1"' in page and 'data-number="0.1-2"' in page
    show_author(client)
    page = client.get(f"/document/{document.number}/pending/").content.decode()
    assert 'data-author="Автор А"' in page and 'data-author="Автор Б"' in page
    assert '<span class="by" data-author="Автор Б" title="Автор Б"><ins>Копію' in page
    show_author(client, on=False)
    page = client.get(f"/document/{document.number}/pending/").content.decode()
    assert 'data-author="' not in page


def test_style_change_collapsed(
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    accepted_directly: Any,
) -> None:
    client, reviewer, author_a, _, document = reviewer_and_authors(
        member_of, new_document, link_group
    )
    commit_version(document, author_a, FIRST, "edit")
    accepted_directly(document, reviewer)
    commit_version(document, author_a, FIRST.replace("письмово", "**письмово**"), "edit")
    page = client.get(f"/document/{document.number}/pending/").content.decode()
    changes = page.split('class="changes document-text"', 1)[1]
    assert '<span class="format-changed" tabindex="0" data-label="' in changes
    # The sentence as it now reads, its earlier form kept aside, no word marked.
    assert (
        'Заяву подають <strong>письмово</strong>.<span class="format-old">'
        "Заяву подають письмово.</span></span>" in changes
    )
    assert "<ins>" not in changes and "<del>" not in changes


def test_base_without_rows_renders_and_queues_nothing(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    queued_authorship: list[Any],
    accepted_directly: Any,
) -> None:
    client, reviewer, author_a, author_b, document = reviewer_and_authors(
        member_of, new_document, link_group
    )
    show_author(client)
    # Never accepted: the `created` commit's lines are the creator's.
    commit_version(document, author_a, FIRST, "edit")
    page = client.get(f"/document/{document.number}/pending/").content.decode()
    assert '<span class="by" data-author="Погоджувач Р" title="Погоджувач Р">' in page
    # Accepted, the accepted version without rows: its lines render without an author.
    accepted_directly(document, reviewer)
    commit_version(document, author_b, SECOND, "edit")
    queued_authorship.clear()
    page = client.get(f"/document/{document.number}/pending/").content.decode()
    assert "Погоджувач Р" not in page.split('class="changes document-text"', 1)[1]
    assert 'data-author="Автор Б"' in page
    assert 'data-author="Автор А"' not in page
    assert queued_authorship == []


def test_pending_needs_view_pending(
    member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    from access.rights import Right

    _, author, author_membership = member_of("the.author@example.test")
    reader_client, _, reader_membership = member_of("the.reader@example.test")
    document = new_document(author)
    link_group(document, [Right.ACCEPT], [author_membership], author)
    link_group(document, [Right.VIEW_ACCEPTED], [reader_membership], author)
    commit_version(document, author, FIRST, "edit")
    assert reader_client.get(f"/document/{document.number}/pending/").status_code == 404
    page = reader_client.get(f"/document/{document.number}/").content.decode()
    assert f"/document/{document.number}/pending/" not in page


def test_the_tabs_are_the_documents_on_pending_and_its_confirmation(
    member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    """The pending tab and the accept confirmation draw the tab bar every other tab draws: *Edit*
    to a holder of *edit* (DL-0208)."""
    client, _, author_a, _, document = reviewer_and_authors(member_of, new_document, link_group)
    commit_version(document, author_a, FIRST, "edit")
    edit = f'href="/document/{document.number}/edit/"'
    for address in ("pending/", "pending/accept/"):
        page = client.get(f"/document/{document.number}/{address}").content.decode()
        tabs = page.split('<nav class="tabs">', 1)[1].split("</nav>", 1)[0]
        assert edit in tabs, address


def test_empty_run(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    accepted_directly: Any,
) -> None:
    client, reviewer, author_a, _, document = reviewer_and_authors(
        member_of, new_document, link_group
    )
    page = client.get(f"/document/{document.number}/pending/").content.decode()
    assert 'class="nothing-pending"' in page
    assert "<ins>" not in page and "<del>" not in page
    commit_version(document, author_a, FIRST, "edit")
    accepted_directly(document, reviewer)
    page = client.get(f"/document/{document.number}/pending/").content.decode()
    assert 'class="nothing-pending"' in page
    assert "<ins>" not in page and "Строк розгляду становить десять днів." in page
    with schema_context(migrated_tenant.number):
        from review.services import run

        assert run(document) == []


def test_base_lines_take_the_accepted_versions_rows(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    accepted_directly: Any,
) -> None:
    """The heading to the creator, an unchanged base line to who wrote it, a base line moved in
    the run to who wrote it rather than the mover, the changed line to the run's author."""
    from documents import gitstore
    from editing import authorship

    client, reviewer, author_a, author_b, document = reviewer_and_authors(
        member_of, new_document, link_group
    )
    written = commit_version(document, author_a, FIRST, "edit")
    accepted_directly(document, reviewer)
    with schema_context(migrated_tenant.number):
        authorship.compute(
            document,
            written.commit_sha,
            repository_path=gitstore.repository_path(migrated_tenant.number, document.number),
        )
    moved = (
        "# Загальні положення\n\n"
        "Строк розгляду становить десять днів.\n"
        "Заяву подають письмово в канцелярії.\n"
        "\nЗаяву подають письмово.\n"
    )
    commit_version(document, author_b, moved, "edit")
    show_author(client)
    changes = client.get(f"/document/{document.number}/pending/").content.decode()
    changes = changes.split('class="changes document-text"', 1)[1]
    assert 'data-author="Погоджувач Р" title="Погоджувач Р">Загальні положення' in changes
    assert 'title="Автор А">Строк розгляду становить десять днів.</span>' in changes
    # Moved within the run: shown where it went, still its writer's.
    assert 'title="Автор А"><ins>Заяву подають письмово.</ins></span>' in changes
    assert 'title="Автор Б"><ins>Заяву подають письмово в канцелярії.</ins>' in changes


def test_a_missing_or_archived_document_answers_as_forbidden(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    from documents.models import Document

    client, _, author_a, _, document = reviewer_and_authors(member_of, new_document, link_group)
    commit_version(document, author_a, FIRST, "edit")
    assert client.get(f"/document/{document.number + 99}/pending/").status_code == 404
    with schema_context(migrated_tenant.number):
        Document.objects.filter(pk=document.pk).update(state="archived")
    assert client.get(f"/document/{document.number}/pending/").status_code == 404


def test_names_are_escaped_and_addresses_kept_from_readers(
    member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    from access.rights import Right

    client, reviewer, author_a, author_b, document = reviewer_and_authors(
        member_of, new_document, link_group
    )
    named(author_a, 'Автор "<script>" А')
    author_b.display_name = ""
    author_b.save(update_fields=["display_name"])
    commit_version(document, author_a, FIRST, "edit")
    commit_version(document, author_b, SECOND, "edit")
    show_author(client)
    page = client.get(f"/document/{document.number}/pending/").content.decode()
    assert "<script>" not in page and "&lt;script&gt;" in page
    assert author_b.email not in page and 'data-author="анонімний редактор"' in page
    # An administrator reads the same label: a person without a name is anonymous to everyone.
    admin_client, _, _ = member_of("the.admin@example.test", is_tenant_admin=True)
    show_author(admin_client)
    admin_page = admin_client.get(f"/document/{document.number}/pending/").content.decode()
    assert author_b.email not in admin_page and 'data-author="анонімний редактор"' in admin_page
    assert Right.VIEW_PENDING  # the administrator reads pending edits without a group


def test_a_changed_image_before_and_after(
    migrated_tenant: Any, cast: Any, commit_version: Any
) -> None:
    """A pending run that replaced an image draws the pair, captioned with the accepted number and
    the run's, both images from the committed route (DL-0439, DL-11-002)."""
    import hashlib

    from django.test import Client

    from review import services

    old, new = b"the accepted image", b"the run's image"
    paths = [f"images/{hashlib.sha256(d).hexdigest()}.png" for d in (old, new)]
    body = "# General provisions\n\nA request for approval is made in writing.\n"
    people = cast(editors=("a",), reviewers=("r",))
    commit_version(
        people.document,
        people["a"],
        body + f"\n![A plan]({paths[0]})\n",
        "edit",
        files={paths[0]: old},
    )
    with schema_context(migrated_tenant.number):
        services.accept(people.document, people["r"])
    commit_version(
        people.document,
        people["a"],
        body + f"\n![A plan]({paths[1]})\n",
        "edit",
        files={paths[0]: None, paths[1]: new},
    )
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(people["r"])
    session = client.session
    session["tenant_number"] = migrated_tenant.number
    session.save()

    page = client.get(f"/document/{people.document.number}/pending/").content.decode()

    pair = page[page.index('<div class="imgpair">') :]
    for data_path in paths:
        assert f'src="/document/{people.document.number}/image/{data_path[7:]}/"' in pair
    assert "0.1 —" in pair and "0.1-1 —" in pair
    assert "image changed" in page or "зображення змінено" in page


def test_entity_changes_are_listed(
    migrated_tenant: Any, cast: Any, commit_version: Any, settings: Any
) -> None:
    """The run's roles, actions and terms added, relabelled or removed, the base's
    `entities.yaml` against the head's (DL-0073, ASR-04)."""
    from django.test import Client

    from review import services

    settings.LANGUAGE_CODE = "en"
    body = "# General provisions\n\nA request for approval is made in writing.\n"
    clerk = '- kind: "role"\n  key: "role-1"\n  label: "the clerk"\n'
    auditor = '- kind: "role"\n  key: "role-3"\n  label: "the auditor"\n'
    people = cast(editors=("a",), reviewers=("r",))
    commit_version(
        people.document,
        people["a"],
        body,
        "edit",
        files={"entities.yaml": (clerk + auditor).encode()},
    )
    with schema_context(migrated_tenant.number):
        services.accept(people.document, people["r"])
    later = (
        clerk.replace("the clerk", "the senior clerk")
        + '- kind: "role"\n  key: "role-2"\n  label: "the treasurer"\n'
    )
    commit_version(
        people.document, people["a"], body, "edit", files={"entities.yaml": later.encode()}
    )
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(people["r"])
    session = client.session
    session["tenant_number"] = migrated_tenant.number
    session.save()

    page = client.get(f"/document/{people.document.number}/pending/").content.decode()

    listed = page[page.index('class="entity-changes"') :]

    def row(key: str) -> str:
        found = re.search(rf'data-key="{key}">.*?</tr>', listed, re.S)
        assert found, key
        return found.group(0)

    assert "the senior clerk" in row("role-1") and "relabelled from the clerk" in row("role-1")
    assert "the treasurer" in row("role-2") and "added" in row("role-2")
    assert "the auditor" in row("role-3") and "removed" in row("role-3")
