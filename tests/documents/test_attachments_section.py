"""The *Attachments* section of the View tab (DL-0349): the attachments of the
version shown, from `PART_INDEX` — the title a link to the download route, the file name, the
size — or *No attachments* when it lists none. Nothing else.

The suite renders in `uk`: *Attachments* is *Вкладені файли*, *No attachments* is *Вкладених
файлів немає*. People, groups and titles are synthetic examples; every text is invented.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from django.template.defaultfilters import filesizeformat
from django.utils import translation

from access.rights import Right

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

FORM = ("Форма заявки", "form.csv", "номер,дата\n1,2026-01-15\n".encode())


def section(body: str) -> str:
    found = re.search(r'<section class="attachments">(.*?)</section>', body, re.DOTALL)
    assert found is not None, "no attachments section"
    return found.group(1)


def size(data: bytes) -> str:
    with translation.override("uk"):
        return str(filesizeformat(len(data)))


def test_section_lists_attachments(accepted_with_parts: Any, reader_in: Any) -> None:
    made = accepted_with_parts(_two())
    document = made.document
    client, _ = reader_in(Right.VIEW_ACCEPTED, document)

    response = client.get(f"/document/{document.number}/")

    assert response.status_code == 200
    listed = section(response.content.decode())
    assert re.search(r"<h2[^>]*>\s*Вкладені файли\s*</h2>", listed)
    items = re.findall(r"<li\b[^>]*>(.*?)</li>", listed, re.DOTALL)
    assert len(items) == 2
    for n, (item, (title, file_name, data)) in enumerate(
        zip(items, made.attachments, strict=True), 1
    ):
        link = rf'<a [^>]*href="/document/{document.number}/attachment/{n}/"[^>]*>\s*{title}\s*</a>'
        assert re.search(link, item), item
        assert file_name in item
        assert size(data) in item
    # The section offers the downloads and nothing else: no form, no button.
    assert "<form" not in listed and "<button" not in listed
    assert "Вкладених файлів немає" not in listed


def test_no_attachments(accepted_with_parts: Any, reader_in: Any) -> None:
    document = accepted_with_parts([]).document
    client, _ = reader_in(Right.VIEW_ACCEPTED, document)

    body = client.get(f"/document/{document.number}/").content.decode()

    listed = section(body)
    assert "Вкладених файлів немає" in listed
    assert "<li" not in listed
    assert "/attachment/" not in listed


def test_section_follows_the_version_shown(
    accepted_with_parts: Any, reader_in: Any, operator: Any, commit_parts: Any
) -> None:
    made = accepted_with_parts()
    document = made.document
    commit_parts(document, operator.user, made.body, [*made.attachments, FORM])
    accepted_client, _ = reader_in(Right.VIEW_ACCEPTED, document)
    pending_client, _ = reader_in(Right.VIEW_PENDING, document)

    as_accepted = section(accepted_client.get(f"/document/{document.number}/").content.decode())
    as_pending = section(pending_client.get(f"/document/{document.number}/").content.decode())

    assert "form.csv" not in as_accepted
    assert f"/document/{document.number}/attachment/2/" not in as_accepted
    assert "form.csv" in as_pending
    assert f"/document/{document.number}/attachment/2/" in as_pending


def _two() -> list[tuple[str, str, bytes]]:
    return [
        ("Схема погодження", "scheme.txt", "Синтетична схема погодження.\n".encode()),
        FORM,
    ]
