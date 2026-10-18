"""An appendix of a past version (DL-0195, DL-0444): the historical page lists the
version's appendices, each opening its page at that version — read only, under the historical
banner, gated by the reader's ceiling — and the generated views at that version link an
appendix's places to it there. People and titles are synthetic examples; text is invented
English."""

from __future__ import annotations

import re
from typing import Any

import pytest

from access.rights import Right
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

BODY = "# Purpose\n\n[The approver]{.role #approver} signs the request.\n"
FIRST = "# Approval matrix\n\n[The approver]{.role #approver} keeps the first matrix.\n"
SECOND = "# Approval matrix\n\nThe matrix is kept by the office.\n"
OLD, NEW = "Approval matrix (example)", "Signing matrix (example)"


def _two_versions(tenant: Any, people: Any, commit_version: Any) -> tuple[str, str]:
    """Version one lists appendix 1 as `OLD`; version two renames it and changes its text. Both
    accepted; their numbers."""
    from documents import entities
    from review import services

    declared = entities.dump([entities.Declared("role", "approver", "the approver")])
    commit_version(
        people.document,
        people["a"],
        BODY,
        files={"appendices/1.md": FIRST.encode(), "entities.yaml": declared.encode()},
        appendices=[{"number": 1, "title": OLD}],
    )
    with schema_context(tenant):
        first = services.accept(people.document, people["r"]).number
    commit_version(
        people.document,
        people["a"],
        BODY,
        files={"appendices/1.md": SECOND.encode()},
        appendices=[{"number": 1, "title": NEW}],
    )
    with schema_context(tenant):
        second = services.accept(people.document, people["r"]).number
    return first, second


def test_the_historical_page_lists_appendices(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    kit: Any,
    settings: Any,
) -> None:
    settings.LANGUAGE_CODE = "en"
    people = edition_cast()
    first, _ = _two_versions(migrated_tenant.number, people, commit_version)
    client, _ = kit.reader(
        member_of, link_group, people, [Right.VIEW_ACCEPTED, Right.VIEW_ALL_HISTORY], "history"
    )
    m = people.document.number
    html = client.get(f"/document/{m}/version/{first}/").content.decode()
    panel = html[html.index('class="appendices"') :]
    assert f'<a href="/document/{m}/version/{first}/appendix/1/">{OLD}</a>' in panel


def test_an_appendix_at_a_version(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    kit: Any,
    settings: Any,
) -> None:
    from django.urls import resolve

    settings.LANGUAGE_CODE = "en"
    people = edition_cast()
    first, _ = _two_versions(migrated_tenant.number, people, commit_version)
    client, _ = kit.reader(
        member_of, link_group, people, [Right.VIEW_ACCEPTED, Right.VIEW_ALL_HISTORY], "history"
    )
    m = people.document.number
    address = f"/document/{m}/version/{first}/appendix/1/"
    assert resolve(address).url_name == "document_version_appendix"
    response = client.get(address)
    assert response.status_code == 200
    html = response.content.decode()
    assert f"Historical version {first} — read only" in html
    assert OLD in html and NEW not in html
    assert "keeps the first matrix" in html and "kept by the office" not in html
    assert 'class="tabs' not in html and "/edit/" not in html
    assert f'<a href="/document/{m}/">open the current document</a>' in html
    assert f'<span class="version-number">{first}</span>' in html
    title = html[html.index("<title>") : html.index("</title>")]
    assert OLD in title and first in title


def test_unreachable_or_unlisted_is_missing(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    kit: Any,
) -> None:
    people = edition_cast()
    first, second = _two_versions(migrated_tenant.number, people, commit_version)
    m = people.document.number
    history, _ = kit.reader(
        member_of, link_group, people, [Right.VIEW_ACCEPTED, Right.VIEW_ALL_HISTORY], "history"
    )
    accepted, _ = kit.reader(member_of, link_group, people, [Right.VIEW_ACCEPTED], "accepted")
    missing = history.get(f"/document/{m}/version/{first}/appendix/9/")
    beyond = accepted.get(f"/document/{m}/version/{first}/appendix/1/")
    # The uniform body is each reader's own page: compared with the same reader's.
    nowhere = accepted.get("/document/9999/version/0.1/appendix/1/")
    assert accepted.get(f"/document/{m}/version/{second}/appendix/1/").status_code == 200
    for response in (missing, beyond):
        assert response.status_code == 404
    # The form tokens aside, which differ per response.
    assert re.sub(rb'value="[^"]*"', b"", beyond.content) == re.sub(
        rb'value="[^"]*"', b"", nowhere.content
    )


def test_generated_views_at_a_version_cover_appendices(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    kit: Any,
    settings: Any,
) -> None:
    settings.LANGUAGE_CODE = "en"
    people = edition_cast()
    first, _ = _two_versions(migrated_tenant.number, people, commit_version)
    client, _ = kit.reader(
        member_of, link_group, people, [Right.VIEW_ACCEPTED, Right.VIEW_ALL_HISTORY], "history"
    )
    m = people.document.number
    at = f"/document/{m}/version/{first}/appendix/1/"
    version = f"/document/{m}/version/{first}/"
    for path, body in ((version, "#c-1-1"), (at, f"{version}#c-1-1")):
        html = client.get(path).content.decode()
        panel = html[html.index('class="generated-views"') :]
        places = re.findall(r'<li><a href="([^"]+)">([^<]+)</a>', panel.split("See also")[0])
        assert places == [(body, "1-1"), (f"{at}#c-1-1", f"{OLD}, 1-1")], path
    assert 'id="c-1-1"' in client.get(at).content.decode()
