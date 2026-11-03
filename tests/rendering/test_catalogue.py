"""Every page and screen of reading and export renders in Ukrainian from the one catalogue: the view
with its outline, panel and header, the *Info* state line, the export dialog with its offers and
refusal, the job's page in each of its states, the help pages for reading and exporting, two
documents compared and the list's start; the export's
appendices, an appendix of a past version, and the compare page's appendix pickers with a pair's
page.

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


def test_catalogue_covers_the_reading_and_export_pages(
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
    """Two documents compared and the list's start, in Ukrainian."""
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
        ("the list", "/folder/1/"),
    ):
        response = client.get(path)
        assert response.status_code == 200, name
        body = response.content.decode()
        _assert_translated(name, body)
        assert "Порівняти" in body or "Порівняння" in body, name


def test_catalogue_covers_the_appendices_in_an_export(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
    settings: Any,
) -> None:
    """The dialog's appendices, a refused choice and the separate files' names, in Ukrainian."""
    import zipfile

    settings.LANGUAGE_CODE = "uk"
    tenant = migrated_tenant.number
    people = edition_cast()
    number = people.document.number
    kit.canonical(tenant, people, commit_version, kit.FIRST)
    commit_version(
        people.document,
        people["a"],
        kit.FIRST,
        "edit",
        files={"appendices/1.md": "# Додаток\n\nРечення додатка.\n".encode()},
        appendices=[{"number": 1, "title": "Форми (приклад)"}],
    )
    pending = people.clients["r"]
    dialog = pending.get(f"/document/{number}/export/").content.decode()
    _assert_translated("export dialog with appendices", dialog)
    assert "у документі" in dialog and "окремими файлами" in dialog
    refused = pending.post(
        f"/document/{number}/export/",
        {"document": "on", "appendices": "on", "format": "pdf", "view": "canonical"},
    )
    assert refused.status_code == 400
    _assert_translated("appendices refused", refused.content.decode())
    asked = pending.post(
        f"/document/{number}/export/",
        {"appendices": "on", "format": "markdown", "view": "pending_edits"},
    )
    assert asked.status_code == 302
    job = kit.run_job(tenant, exports[-1][1])
    assert job.state == "done", job.failure_reason
    with zipfile.ZipFile(Path(settings.EXPORT_ROOT) / job.artifact_ref) as bundle:
        assert bundle.namelist() == ["додаток-1_—_Форми_(приклад).md"]


def test_catalogue_covers_an_appendix_at_a_version(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    kit: Any,
    settings: Any,
) -> None:
    """An appendix of a past version, in Ukrainian: the historical banner over it."""
    from review import services as review

    settings.LANGUAGE_CODE = "uk"
    tenant = migrated_tenant.number
    people = edition_cast()
    commit_version(
        people.document,
        people["a"],
        kit.FIRST,
        "edit",
        files={"appendices/1.md": "# Додаток\n\nРечення додатка.\n".encode()},
        appendices=[{"number": 1, "title": "Форми (приклад)"}],
    )
    with schema_context(tenant):
        number = review.accept(people.document, people["r"]).number
    reader, _ = kit.reader(member_of, link_group, people, [Right.VIEW_ACCEPTED], "past")
    page = reader.get(f"/document/{people.document.number}/version/{number}/appendix/1/")
    assert page.status_code == 200
    _assert_translated("an appendix at a version", page.content.decode())
    assert f"Історична версія {number}" in page.content.decode()


def test_catalogue_covers_comparing_appendices(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    kit: Any,
    settings: Any,
) -> None:
    """The compare page's appendix pickers and a pair's page, in Ukrainian."""
    from review import services as review

    settings.LANGUAGE_CODE = "uk"
    tenant = migrated_tenant.number
    people = edition_cast()
    numbers = []
    for word in ("Перше", "Друге"):
        commit_version(
            people.document,
            people["a"],
            kit.FIRST,
            "edit",
            files={"appendices/1.md": f"# Додаток\n\n{word} речення додатка.\n".encode()},
            appendices=[{"number": 1, "title": "Форми (приклад)"}],
        )
        with schema_context(tenant):
            numbers.append(review.accept(people.document, people["r"]).number)
    reader, _ = kit.reader(
        member_of, link_group, people, [Right.VIEW_ACCEPTED, Right.VIEW_ALL_HISTORY], "pairs"
    )
    m = people.document.number
    older, newer = numbers
    for name, path in (
        ("the compare page's pickers", f"/document/{m}/compare/?from={older}&to={newer}"),
        ("a pair of appendices", f"/document/{m}/compare/appendix/?from={older}:1&to={newer}:1"),
    ):
        page = reader.get(path)
        assert page.status_code == 200, name
        _assert_translated(name, page.content.decode())
    assert "Назад до порівняння" in page.content.decode()


@pytest.mark.fast
def test_catalogue_covers_the_title_page() -> None:
    """Every detail a title page can show, in `uk`, from the catalogue."""
    from django.utils import translation

    from rendering.title_page import DETAILS, Layout, TitleFacts, html

    facts = TitleFacts(
        title="Синтетична політика",
        number="#7",
        type_label="Документ",
        edition="1.0",
        approver="Синтетичний затверджувач",
        approval_date="1 жовтня 2026",
        text="Реєстр: EX-1",
        approval="Затверджено",
    )
    with translation.override("uk"):
        page = html(facts, Layout((*DETAILS, "approval"), "left"))

    _assert_translated("the title page", page)


@pytest.mark.integration
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_catalogue_covers_the_styles_page(
    migrated_tenant: Any, member_of: Any, settings: Any, queued_samples: Any
) -> None:
    """The styles page in `uk`, a refusal of every kind among it."""
    settings.LANGUAGE_CODE = "uk"
    admin, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    refused = (
        "@import 'x';\nh1 { color: red !important }\n#id { color: red }\n"
        "p { display: none }\nh2 { background: url(x) }\nh3 { font-family: Synthetic }\n"
        "p { color: }\n"
    )

    answers = [
        admin.get("/administration/tenant/styles/"),
        admin.post("/administration/tenant/styles/", {"text": refused}),
        admin.post("/administration/tenant/styles/", {"text": "p {} " * 20_001}),
    ]
    # And with what Word cannot carry listed.
    from rendering.models import Stylesheet

    with schema_context(migrated_tenant.number):
        Stylesheet.objects.update(text="li { letter-spacing: 1px }\n")
    answers.append(admin.get("/administration/tenant/styles/"))
    # And with a sample's progress drawn, and the refusal of a second one.
    asked = admin.post("/administration/tenant/styles/sample/", {"text": "", "format": "pdf"})
    answers.append(admin.get(asked["Location"]))
    answers.append(
        admin.post("/administration/tenant/styles/sample/", {"text": "", "format": "docx"})
    )

    assert [answer.status_code for answer in answers] == [200, 400, 400, 200, 200, 409]
    assert "li — letter-spacing" in answers[-1].content.decode()
    for n, answer in enumerate(answers):
        _assert_translated(f"the styles page ({n})", answer.content.decode())


def test_catalogue_covers_the_historical_authors(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    member_of: Any,
    link_group: Any,
    settings: Any,
    monkeypatch: Any,
) -> None:
    """The historical page with *Show edit authors* on: the toggle, and the line asking for a
    reload while the edit authors are worked out."""
    import importlib.util
    import sys
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "catalogue_historical_page", Path(__file__).resolve().parent / "test_historical_page.py"
    )
    assert spec is not None and spec.loader is not None
    page = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = page
    spec.loader.exec_module(page)
    monkeypatch.setattr("editing.tasks.compute_authorship_at.delay", lambda *args: None)

    settings.LANGUAGE_CODE = "uk"
    history = page.standard_history(migrated_tenant, edition_cast, commit_version)
    viewer = page.reader(member_of, link_group, history.people, "viewer", page.READER_I)
    url = f"/document/{history.document.number}/version/0.0-2/"
    off = viewer.client.get(url).content.decode()
    viewer.client.post("/preferences/show-author/", {"show_author": "on"})
    waiting = viewer.client.get(url).content.decode()

    assert "Показувати авторів правок" in off
    assert "Авторів правок ще визначають" in waiting
    _assert_translated("the historical page", off)
    _assert_translated("the historical page, edit authors waiting", waiting)
