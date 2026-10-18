"""Every page and screen review and acceptance added renders in Ukrainian from the one catalogue.

People, groups and the document's text are synthetic examples."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from django.test import Client

from tenancy.schemas import schema_context

CATALOGUE = (
    Path(__file__).resolve().parents[2] / "src" / "shell" / "locale" / "uk" / "LC_MESSAGES"
) / "django.po"


WRITTEN = (
    "# Загальні положення\n\n"
    "Заяву на погодження подають письмово.\n"
    "Строк розгляду заяви становить десять днів.\n"
)
CORRECTED = WRITTEN.replace("десять днів", "п'ять робочих днів")
RESTYLED = CORRECTED.replace("письмово", "**письмово**")


def message_ids(catalogue: str) -> list[str]:
    """Every live message id longer than two characters, continuation lines joined — but for one
    the Ukrainian itself uses: a name such as *HTML* or *Markdown* reads the same in both."""
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


def text_of(body: str) -> str:
    """What a reader sees: the page without its tags and their attributes."""
    return re.sub(r"<[^>]*>", " ", body)


def signed_in(tenant: Any, user: Any) -> Client:
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(user)
    session = client.session
    session["tenant_number"] = tenant.number
    session.save()
    return client


@pytest.mark.integration
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_catalogue_covers_review_pages(
    migrated_tenant: Any,
    cast: Any,
    commit_version: Any,
    settings: Any,
    queued_authorship: list[Any],
) -> None:
    from editing.models import Draft
    from notifications.models import Notification

    settings.LANGUAGE_CODE = "uk"
    people = cast(editors=("a",), reviewers=("r",))
    document, author, reviewer = people.document, people["a"], people["r"]
    reviewer_client = signed_in(migrated_tenant, reviewer)
    author_client = signed_in(migrated_tenant, author)
    ids = message_ids(CATALOGUE.read_text(encoding="utf-8"))

    def shown(client: Client, path: str, status: int = 200) -> str:
        response = client.get(path, follow=True)
        assert response.status_code == status, path
        return text_of(response.content.decode())

    number = document.number
    bodies = {"the empty pending tab": shown(reviewer_client, f"/document/{number}/pending/")}
    commit_version(document, author, WRITTEN, "edit")
    commit_version(document, author, RESTYLED, "edit")
    reviewer_client.post("/preferences/show-author/", {"show_author": "on"})
    bodies["the pending tab"] = shown(reviewer_client, f"/document/{number}/pending/")
    bodies["the list"] = shown(reviewer_client, "/folder/1/")
    bodies["the confirmation"] = shown(reviewer_client, f"/document/{number}/pending/accept/")
    bodies["the help page"] = shown(reviewer_client, "/help/review/")
    bodies["the correcting tab"] = shown(reviewer_client, f"/document/{number}/edit/")
    assert reviewer_client.post(f"/document/{number}/edit/take/").status_code == 200
    bodies["correct while held"] = shown(author_client, f"/document/{number}/pending/")
    with schema_context(migrated_tenant.number):
        draft = Draft.objects.get(hold__document=document, hold__released_at__isnull=True)
        draft.content = {**draft.content, "document.md": WRITTEN}
        draft.save()
    bodies["the reviewer's finishing screen"] = shown(
        reviewer_client, f"/document/{number}/edit/finish/"
    )
    accepted = reviewer_client.post(
        f"/document/{number}/edit/send/", {"summary": "Строк", "choice": "accept"}, follow=True
    )
    bodies["the notice after accepting"] = text_of(accepted.content.decode())
    with schema_context(migrated_tenant.number):
        notification = Notification.objects.get(user=author, event="correction_notice")
    bodies["the correction notice"] = shown(author_client, f"/notifications/{notification.pk}/")

    for name, body in bodies.items():
        leaked = [i for i in ids if re.search(rf"(?<![\w-]){re.escape(i)}(?![\w-])", body)]
        assert leaked == [], f"{name} shows message ids verbatim: {leaked}"
    assert "Погоджено як 0.1" in bodies["the notice after accepting"]
    assert "Сповіщення про виправлення" in bodies["the correction notice"]


@pytest.mark.integration
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_catalogue_covers_history_compare_and_return(
    migrated_tenant: Any,
    cast: Any,
    commit_version: Any,
    link_group: Any,
    settings: Any,
) -> None:
    from access.rights import Right
    from editions import services as editions
    from review import services

    settings.LANGUAGE_CODE = "uk"
    people = cast(editors=("a",), reviewers=("r",))
    document, author, reviewer = people.document, people["a"], people["r"]
    link_group(document, [Right.VIEW_ALL_HISTORY, Right.FREEZE], [people.memberships["r"]], author)
    reviewer_client = signed_in(migrated_tenant, reviewer)
    ids = message_ids(CATALOGUE.read_text(encoding="utf-8"))

    def shown(path: str) -> str:
        response = reviewer_client.get(path, follow=True)
        assert response.status_code == 200, path
        return text_of(response.content.decode())

    number = document.number
    commit_version(document, author, WRITTEN, "edit")
    with schema_context(migrated_tenant.number):
        services.accept(document, reviewer)
        editions.freeze(document, reviewer, "Синтетична причина")
        editions.end_freeze(document, user=reviewer)
    commit_version(document, author, CORRECTED, "edit")
    bodies = {
        "the history tab": shown(f"/document/{number}/history/"),
        "the historical page": shown(f"/document/{number}/version/0.1/"),
        "the export at a version": shown(f"/document/{number}/version/0.1/export/"),
        "the compare page": shown(f"/document/{number}/compare/?from=0.1&to=0.1-1"),
    }
    bodies["the pending tab"] = shown(f"/document/{number}/pending/")
    bodies["the return's confirmation"] = shown(f"/document/{number}/pending/return/")
    refused = reviewer_client.post(f"/document/{number}/pending/return/", {"reason": ""})
    bodies["a refused reason"] = text_of(refused.content.decode())
    with schema_context(migrated_tenant.number):
        services.return_run(document, reviewer, "Synthetic reason: recheck the time limits")
    bodies["the list"] = shown("/folder/1/")
    bodies["the info tab"] = shown(f"/document/{number}/info/")
    bodies["the author's notifications"] = text_of(
        signed_in(migrated_tenant, author).get("/notifications/").content.decode()
    )
    with schema_context(migrated_tenant.number):
        from review import undo

        undo.apply(document, reviewer, author=author)
    bodies["the edit tab after an undo"] = shown(f"/document/{number}/edit/")
    for name, body in bodies.items():
        leaked = [i for i in ids if re.search(rf"(?<![\w-]){re.escape(i)}(?![\w-])", body)]
        assert leaked == [], f"{name} shows message ids verbatim: {leaked}"
    assert "Історична версія 0.1" in bodies["the historical page"]
    assert "повернено" in bodies["the list"]


@pytest.mark.integration
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_catalogue_covers_the_runs_parts(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    accepted_directly: Any,
    settings: Any,
) -> None:
    """*Pending edits* with the run's appendices, part operations and *Parts:* lines, in
    Ukrainian."""
    import hashlib

    from access.rights import Right

    settings.LANGUAGE_CODE = "uk"
    ids = message_ids(CATALOGUE.read_text(encoding="utf-8"))
    client, author, own = member_of("the.author@example.test")
    document = new_document(author)
    link_group(document, [Right.ACCEPT, Right.VIEW_PENDING], [own], author)

    def form(data: bytes, title: str) -> dict[str, Any]:
        digest = hashlib.sha256(data).hexdigest()
        return {"number": 2, "title": title, "file_name": "f.txt", "sha256": digest, "bytes": 1}

    commit_version(
        document,
        author,
        "# Мета\n\nПерше речення.\n",
        files={"appendices/1.md": "# Додаток\n\nРечення.\n".encode(), "attachments/2": b"a"},
        appendices=[{"number": 1, "title": "Перша назва (приклад)"}],
        attachments=[form(b"a", "Форма (приклад)")],
    )
    accepted_directly(document, author)
    commit_version(
        document,
        author,
        "# Мета\n\nПерше речення.\n",
        files={"appendices/1.md": "# Додаток\n\nІнше речення.\n".encode(), "attachments/2": b"b"},
        appendices=[{"number": 1, "title": "Друга назва (приклад)"}],
        attachments=[form(b"b", "Форма (приклад)")],
    )
    body = text_of(client.get(f"/document/{document.number}/pending/").content.decode())
    leaked = [i for i in ids if re.search(rf"(?<![\w-]){re.escape(i)}(?![\w-])", body)]
    assert leaked == [], f"pending edits shows message ids verbatim: {leaked}"
    assert "перейменовано з «Перша назва (приклад)»" in body
    assert "Частини:" in body
    assert "повернути як було" in body
    stale = client.post(
        f"/document/{document.number}/pending/revert/",
        {"part": "appendix:1", "change": "renamed", "head": "0" * 40},
        follow=True,
    )
    refused = text_of(stale.content.decode())
    leaked = [i for i in ids if re.search(rf"(?<![\w-]){re.escape(i)}(?![\w-])", refused)]
    assert leaked == [], f"a refused revert shows message ids verbatim: {leaked}"
    assert "Правки змінилися" in refused


@pytest.mark.integration
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_catalogue_covers_the_notices_parts(
    migrated_tenant: Any,
    cast: Any,
    commit_version: Any,
    accepted_directly: Any,
    queued_authorship: list[Any],
    settings: Any,
) -> None:
    """The correction notice's part entries, its counts and its list line, in Ukrainian."""
    import hashlib

    from notifications.models import Notification
    from review import services

    settings.LANGUAGE_CODE = "uk"
    ids = message_ids(CATALOGUE.read_text(encoding="utf-8"))
    people = cast(editors=("a",), reviewers=("r",))
    document, author, reviewer = people.document, people["a"], people["r"]
    body = "# Мета\n\nРечення.\n"
    commit_version(document, author, body)
    with schema_context(migrated_tenant.number):
        services.accept(document, reviewer)
    form = {
        "number": 3,
        "title": "Форма (приклад)",
        "file_name": "f.txt",
        "sha256": hashlib.sha256(b"3").hexdigest(),
        "bytes": 1,
    }
    commit_version(document, author, body, files={"attachments/3": b"3"}, attachments=[form])
    commit_version(
        document, reviewer, body, "reviewer_edit", files={"attachments/3": None}, attachments=[]
    )
    with schema_context(migrated_tenant.number):
        services.accept(document, reviewer)
        notification = Notification.objects.get(user=author, event="correction_notice")
    client = signed_in(migrated_tenant, author)
    for path in ("/notifications/?tab=document", f"/notifications/{notification.pk}/"):
        page = text_of(client.get(path).content.decode())
        leaked = [i for i in ids if re.search(rf"(?<![\w-]){re.escape(i)}(?![\w-])", page)]
        assert leaked == [], f"{path} shows message ids verbatim: {leaked}"
        assert "1 частину документа" in page
    assert "Ви додали цей вкладений файл" in page


@pytest.mark.integration
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_catalogue_covers_the_undo_over_appendices(
    migrated_tenant: Any, cast: Any, commit_version: Any, settings: Any
) -> None:
    """The edit tab's *After the undo* naming an appendix's place, in Ukrainian."""
    from review import services, undo

    settings.LANGUAGE_CODE = "uk"
    ids = message_ids(CATALOGUE.read_text(encoding="utf-8"))
    people = cast(editors=("a", "b"), reviewers=("r",))
    document = people.document
    body = "# Мета\n\nРечення.\n"
    one = [{"number": 1, "title": "Додаток (приклад)"}]
    text = "# Додаток\n\nРечення додатка.\n"
    commit_version(
        document, people["a"], body, files={"appendices/1.md": text.encode()}, appendices=one
    )
    with schema_context(migrated_tenant.number):
        services.accept(document, people["r"])
    commit_version(
        document, people["a"], body, files={"appendices/1.md": (text + "Речення А.\n").encode()}
    )
    commit_version(
        document, people["b"], body, files={"appendices/1.md": (text + "Речення Б.\n").encode()}
    )
    with schema_context(migrated_tenant.number):
        undo.apply(document, people["r"], author=people["a"])
    page = text_of(
        signed_in(migrated_tenant, people["r"])
        .get(f"/document/{document.number}/edit/")
        .content.decode()
    )
    leaked = [i for i in ids if re.search(rf"(?<![\w-]){re.escape(i)}(?![\w-])", page)]
    assert leaked == [], f"the edit tab shows message ids verbatim: {leaked}"
    assert "У додатку «Додаток (приклад)»:" in page


@pytest.mark.integration
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_catalogue_covers_the_title_page_changes(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    settings: Any,
) -> None:
    """*Pending edits* listing the title page switched and its text written, then removed, in
    Ukrainian."""
    from access.rights import Right
    from review import services as review

    settings.LANGUAGE_CODE = "uk"
    ids = message_ids(CATALOGUE.read_text(encoding="utf-8"))
    editor, holder, own = member_of("the.holder@example.test")
    client, reviewer, theirs = member_of("the.reviewer@example.test")
    document = new_document(holder)
    link_group(document, [Right.EDIT], [own], holder)
    link_group(document, [Right.ACCEPT, Right.VIEW_PENDING], [theirs], holder)
    commit_version(document, holder, WRITTEN)
    n = document.number

    def run(fields: dict[str, str]) -> str:
        assert editor.post(f"/document/{n}/edit/take/").status_code == 200
        editor.post(f"/document/{n}/edit/title-page/", fields)
        editor.post(f"/document/{n}/edit/send/", {"summary": "Титульна сторінка (приклад)"})
        body = text_of(client.get(f"/document/{n}/pending/").content.decode())
        leaked = [i for i in ids if re.search(rf"(?<![\w-]){re.escape(i)}(?![\w-])", body)]
        assert leaked == [], f"pending edits shows message ids verbatim: {leaked}"
        return body

    written = run({"title_page": "on", "title_page_text": "Реєстровий запис (приклад)"})
    assert "Титульну сторінку увімкнено" in written
    assert "Текст титульної сторінки: Реєстровий запис (приклад)" in written
    with schema_context(migrated_tenant.number):
        review.accept(document, reviewer)
    removed = run({"title_page_text": ""})
    assert "Титульну сторінку вимкнено" in removed
    assert "Текст титульної сторінки вилучено" in removed
