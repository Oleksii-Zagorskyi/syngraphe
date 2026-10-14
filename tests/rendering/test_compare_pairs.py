"""A comparison at its edges (ST-0033, DL-0195, DL-0208, DL-0361): one version asked against
itself — by one number or two — opens that version's page; a renamed attachment reads as changed,
its earlier title kept; the banner's versions open in a window of their own; stepping crosses an
acceptance, where the numbers change.

People, groups and texts are synthetic examples; every text is invented.
"""

from __future__ import annotations

from typing import Any

import pytest

from access.rights import Right
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

FIRST = "# General provisions\n\nAn application is made in writing.\n"
SECOND = FIRST + "\nThe decision is sent the same day.\n"
THIRD = SECOND + "\nA copy is kept in the register.\n"


def _reader(member_of: Any, link_group: Any, people: Any) -> Any:
    client, _user, membership = member_of("h.synthetic@example.test")
    link_group(
        people.document, [Right.VIEW_ALL_HISTORY, Right.VIEW_PENDING], [membership], people["a"]
    )
    return client


def test_one_version_against_itself_opens_its_page(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    member_of: Any,
    link_group: Any,
) -> None:
    from review import services

    people = edition_cast()
    commit_version(people.document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        services.accept(people.document, people["r"])
    client = _reader(member_of, link_group, people)
    n = people.document.number
    for query in ("?from=0.0-1&to=0.1", "?from=0.1&to=0.1"):
        answer = client.get(f"/document/{n}/compare/{query}")
        assert answer.status_code == 302, query
        assert answer["Location"] == f"/document/{n}/version/0.1/"


def test_a_renamed_attachment_reads_as_changed(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    member_of: Any,
    link_group: Any,
    kit: Any,
    settings: Any,
) -> None:
    import dataclasses

    from documents import bundle, gitstore, services
    from documents.identity import identity_for
    from documents.locks import document_lock

    settings.LANGUAGE_CODE = "en"
    people = edition_cast()
    tenant = migrated_tenant.number
    kit.attach(tenant, people, FIRST, b"same bytes\n")
    with schema_context(tenant):
        repo = gitstore.open_repository(tenant, people.document.number)
        with document_lock(tenant, people.document.number):
            head = gitstore.head(repo)
            assert head is not None
            frontmatter, body = bundle.parse(gitstore.read(repo, "document.md", head).decode())
            renamed = [{**frontmatter.attachments[0], "title": "Renamed synthetic table"}]
            text = bundle.render(dataclasses.replace(frontmatter, attachments=renamed), body)
            sha = gitstore.commit(
                repo,
                {"document.md": text.encode()},
                identity_for(people["a"]),
                "Synthetic rename",
                gitstore.Kind.EDIT,
            )
            services.derive_version(people.document, gitstore.commit_at(repo, sha), people["a"])
    client = _reader(member_of, link_group, people)
    page = client.get(f"/document/{people.document.number}/compare/?from=0.0-1&to=0.0-2")
    body_text = page.content.decode()
    assert 'data-change="changed"' in body_text
    assert "Renamed synthetic table" in body_text
    assert "Таблиця строків" in body_text  # the earlier title, as the fixture names it


def test_the_banners_versions_open_in_a_window_of_their_own(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    member_of: Any,
    link_group: Any,
) -> None:
    people = edition_cast()
    commit_version(people.document, people["a"], FIRST, "edit")
    commit_version(people.document, people["a"], SECOND, "edit")
    client = _reader(member_of, link_group, people)
    n = people.document.number
    page = client.get(f"/document/{n}/compare/?from=0.0-1&to=0.0-2").content.decode()
    banner = page[page.index('class="band historical"') : page.index("</p>", page.index("band"))]
    assert banner.count('target="_blank"') == 2


def test_stepping_crosses_an_acceptance(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    member_of: Any,
    link_group: Any,
) -> None:
    from review import services

    people = edition_cast()
    commit_version(people.document, people["a"], FIRST, "edit")
    commit_version(people.document, people["a"], SECOND, "edit")
    with schema_context(migrated_tenant.number):
        services.accept(people.document, people["r"])
    commit_version(people.document, people["a"], THIRD, "edit")
    client = _reader(member_of, link_group, people)
    n = people.document.number
    page = client.get(f"/document/{n}/compare/?from=0.0-1&to=0.1").content.decode()
    assert f'class="step next" href="/document/{n}/compare/?from=0.1&amp;to=0.1-1"' in page
