"""Every page and screen of reading and export renders in Ukrainian from the one catalogue: the view
with its outline, panel and header, the *Info* state line, the export dialog with its offers and
refusal, the job's page in each of its states, the help pages for reading and exporting, and two
documents compared, the picker, and the starts on the document page and the list.

People, groups and titles are synthetic examples; every text is invented.
"""

from __future__ import annotations

import os
import re
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from django.utils import timezone

from access.rights import Right
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

CATALOGUE = Path(__file__).resolve().parents[2] / "src/shell/locale/uk/LC_MESSAGES/django.po"


def message_ids(catalogue: str) -> list[str]:
    """Every live message id longer than two characters, continuation lines joined — but for one
    the Ukrainian itself uses."""
    pairs: list[tuple[str, str]] = []
    for block in catalogue.split("\n\n"):
        parts: dict[str, list[str]] = {"msgid": [], "msgstr": []}
        current = None
        for line in block.splitlines():
            keyword = line.split(" ", 1)[0]
            if keyword in parts:
                current = keyword
                parts[keyword].append(line[len(keyword) + 1 :].strip('"'))
            elif keyword == "msgctxt" or line.startswith("#"):
                current = None
            elif current and line.startswith('"'):
                parts[current].append(line.strip('"'))
        message, translation = "".join(parts["msgid"]), "".join(parts["msgstr"])
        if len(message) > 2:
            pairs.append((message, translation))
    ukrainian = "\n".join(translation for _, translation in pairs)
    return [message for message, _ in pairs if message not in ukrainian]


def _assert_translated(name: str, body: str) -> None:
    ids = message_ids(CATALOGUE.read_text(encoding="utf-8"))
    # Help pages are checked like any other: an English message id in a Ukrainian page is a leak.
    shown = re.sub(r"<[^>]*>", " ", body)
    leaked = [i for i in ids if re.search(rf"(?<![\w-]){re.escape(i)}(?![\w-])", shown)]
    assert leaked == [], f"{name} shows message ids verbatim: {leaked}"


def test_catalogue_covers_epic_7_pages(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
    settings: Any,
) -> None:
    from documents import reconcile
    from rendering.export.job import sweep
    from rendering.models import ExportJob

    settings.LANGUAGE_CODE = "uk"
    tenant = migrated_tenant.number
    people = edition_cast()
    document = people.document
    number = document.number
    kit.canonical(tenant, people, commit_version, kit.FIRST)
    kit.attach(tenant, people, kit.SECOND, "Синтетичний рядок.\n".encode(), title_page=True)
    reader, _ = kit.reader(member_of, link_group, people, [Right.VIEW_CANONICAL], "reader")
    pending = people.clients["r"]

    for name, client, path in (
        ("canonical view", reader, f"/document/{number}/"),
        ("canonical info", reader, f"/document/{number}/info/"),
        ("canonical export dialog", reader, f"/document/{number}/export/"),
        ("pending view", pending, f"/document/{number}/"),
        ("pending edits", pending, f"/document/{number}/pending/"),
        ("pending info", pending, f"/document/{number}/info/"),
        ("export dialog with offers", pending, f"/document/{number}/export/"),
        ("reading help", reader, "/help/reading/"),
        ("export help", reader, "/help/exporting/"),
    ):
        response = client.get(path)
        assert response.status_code == 200, name
        _assert_translated(name, response.content.decode())

    # A job queued, then refused a second one, then done, then swept.
    asked = pending.post(
        f"/document/{number}/export/",
        {"document": "on", "attachments": "on", "format": "pdf", "view": "pending_edits",
         "changes-pending_edits": "marked"},
    )  # fmt: skip
    assert asked.status_code == 302
    route = asked["Location"]
    _assert_translated("job queued", pending.get(route).content.decode())
    again = pending.post(
        f"/document/{number}/export/", {"document": "on", "format": "pdf", "view": "pending_edits"}
    )
    _assert_translated("second export refused", again.content.decode())
    job = kit.run_job(tenant, exports[0][1])
    assert job.state == "done"
    _assert_translated("job done", pending.get(route).content.decode())
    folder = Path(settings.EXPORT_ROOT) / str(job.pk)
    old = (timezone.now() - timedelta(hours=25)).timestamp()
    os.utime(folder, (old, old))
    assert sweep() == 1
    _assert_translated("job swept", pending.get(route).content.decode())

    # A job nobody ran, failed by the reconciler an hour on.
    asked = reader.post(
        f"/document/{number}/export/", {"document": "on", "format": "docx", "view": "canonical"}
    )
    assert asked.status_code == 302
    with schema_context(tenant):
        queued = ExportJob.objects.get(state="queued")
        ExportJob.objects.filter(pk=queued.pk).update(
            created_at=timezone.now() - timedelta(hours=2)
        )
    reconcile.run(tenant=tenant, repair=True)
    with schema_context(tenant):
        assert ExportJob.objects.get(pk=queued.pk).state == "failed"
    _assert_translated("job failed", reader.get(asked["Location"]).content.decode())


# Epic 10
def test_catalogue_covers_comparing_two_documents(
    migrated_tenant: Any,
    edition_cast: Any,
    new_document: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    kit: Any,
    settings: Any,
) -> None:
    """Two documents compared, the picker, and the starts on the document page and the list, in
    Ukrainian."""
    settings.LANGUAGE_CODE = "uk"
    tenant = migrated_tenant.number
    people = edition_cast()
    first = people.document
    kit.canonical(tenant, people, commit_version, kit.FIRST)
    second = new_document(people["a"], "Синтетичні правила для підрядників")
    commit_version(second, people["a"], kit.SECOND, "edit")
    client, _user, membership = member_of("reader.synthetic@example.test")
    for document in (first, second):
        link_group(
            document, [Right.VIEW_ALL_HISTORY, Right.VIEW_PENDING], [membership], people["a"]
        )

    for name, path in (
        ("two documents", f"/document/{first.number}/compare/?with={second.number}"),
        ("the picker", f"/document/{first.number}/compare/?with="),
        ("the document page", f"/document/{first.number}/"),
        ("the list", "/folder/1/"),
    ):
        response = client.get(path)
        assert response.status_code == 200, name
        body = response.content.decode()
        _assert_translated(name, body)
        assert "Порівняти" in body or "Порівняння" in body, name
