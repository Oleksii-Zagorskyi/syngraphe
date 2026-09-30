"""The outline and the document page's panes (DL-0195, DL-0356): every heading of the version shown,
nested, each linking to its heading; the outline's width kept per person; the heading cache read
through the parser and kept for the versions a reader is shown.

People, group names and titles are synthetic examples; every text is invented.
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

DEEP = (
    "# Загальні положення\n\n"
    "Вступне речення порядку.\n\n"
    "## Сфера застосування\n\n"
    "### Підрозділи\n\n"
    "#### Відокремлені підрозділи\n\n"
    "Порядок поширюється на відокремлені підрозділи.\n\n"
    "## Терміни\n\n"
    "# Відповідальність\n"
)


def _pane(body: str) -> str:
    found = re.search(r'<nav class="outline"[^>]*>(.*?)</nav>', body, re.DOTALL)
    assert found is not None, "no outline"
    return found.group(1)


def _accepted(migrated_tenant: Any, edition_cast: Any, commit_version: Any, body: str) -> Any:
    from review import services as review

    people = edition_cast()
    people.accepted_content = commit_version(people.document, people["a"], body, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(people.document, people["r"])
    return people


def test_outline_and_width(migrated_tenant: Any, edition_cast: Any, commit_version: Any) -> None:
    people = _accepted(migrated_tenant, edition_cast, commit_version, DEEP)
    client = people.clients["r"]
    route = f"/document/{people.document.number}/"

    body = client.get(route).content.decode()

    pane = _pane(body)
    labels = re.findall(r'<a href="#h-([0-9.]+)"><span class="num">\1</span> ([^<]+)</a>', pane)
    assert labels == [
        ("1", "Загальні положення"),
        ("1.1", "Сфера застосування"),
        ("1.1.1", "Підрозділи"),
        ("1.1.1.1", "Відокремлені підрозділи"),
        ("1.2", "Терміни"),
        ("2", "Відповідальність"),
    ]
    # Nested: 1.1.1.1 sits three lists deep inside 1.
    nested = pane[pane.index('href="#h-1"') : pane.index('href="#h-1.2"')]
    assert nested.count("<ul>") == 3
    # Each outline link reaches its heading in the text.
    assert '<h4 id="h-1.1.1.1">' in body
    assert "--outline-width: 250px" in body

    kept = client.post("/preferences/outline-width/", {"width": "320"})
    refused = client.post("/preferences/outline-width/", {"width": "9000"})
    malformed = client.post("/preferences/outline-width/", {"width": "12px"})

    assert kept.status_code == 204
    assert refused.status_code == 404 and malformed.status_code == 404
    from identity.models import UserPreference

    stored = UserPreference.objects.get(user=people["r"], key="outline_width")
    assert stored.value == "320"
    assert "--outline-width: 320px" in client.get(route).content.decode()


def test_the_panel_holds_the_attachments(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any
) -> None:
    """The right panel opens on its parts tab; the attachments stand there, not above the text
    (DL-0356)."""
    people = _accepted(migrated_tenant, edition_cast, commit_version, DEEP)

    body = people.clients["r"].get(f"/document/{people.document.number}/").content.decode()

    panel = re.search(r'<aside class="panel"[^>]*>(.*?)</aside>', body, re.DOTALL)
    assert panel is not None, "no panel"
    assert '<section class="attachments">' in panel.group(1)
    assert body.index('<section class="attachments">') > body.index(
        '<article class="document-text">'
    )


def test_heading_rows_kept_for_the_versions_shown(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any
) -> None:
    """After an acceptance and three later versions, the rows stand for the head, its parent and
    the accepted version; an earlier intermediate version's rows are gone."""
    from documents.models import HeadingIndex

    people = _accepted(migrated_tenant, edition_cast, commit_version, DEEP)
    document = people.document
    middle = commit_version(document, people["a"], DEEP + "\n## Додаток\n", "edit")
    commit_version(document, people["a"], DEEP + "\n## Другий додаток\n", "edit")
    head = commit_version(document, people["a"], DEEP + "\n## Третій додаток\n", "edit")

    with schema_context(migrated_tenant.number):
        versions = set(
            HeadingIndex.objects.filter(document=document).values_list("version", flat=True)
        )
    assert head.pk in versions
    assert middle.pk not in versions
    assert people.accepted_content.pk in versions


def test_the_panel_holds_parts_alone_and_keeps_its_width(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any
) -> None:
    """Nothing is drawn for what is not built (DL-0228); the panel's width is kept as the
    outline's is (DL-0195)."""
    people = _accepted(migrated_tenant, edition_cast, commit_version, DEEP)
    client = people.clients["r"]
    route = f"/document/{people.document.number}/"

    body = client.get(route).content.decode()
    kept = client.post("/preferences/panel-width/", {"width": "340"})

    panel = re.search(r'<aside class="panel"[^>]*>(.*?)</aside>', body, re.DOTALL)
    assert panel is not None
    assert panel.group(1).count("<span") == 1 and "aria-disabled" not in panel.group(1)
    assert "--panel-width: 280px" in body
    assert kept.status_code == 204
    assert "--panel-width: 340px" in client.get(route).content.decode()
