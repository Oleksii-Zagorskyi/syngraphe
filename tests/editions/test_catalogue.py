"""Every page and screen the editions added renders in Ukrainian from the one catalogue: the band,
the *Freeze* and *Make canonical* controls with their reasons, the edit tab while frozen, the
confirmation, the header's version line, the list's version columns and the help page.

People and groups are synthetic examples; the text is invented.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from django.db import transaction

from access.rights import Right
from review import services as review
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

CATALOGUE = Path(__file__).resolve().parents[2] / "src/shell/locale/uk/LC_MESSAGES/django.po"
FIRST = "Заяву на погодження подають письмово.\n"
SECOND = FIRST + "\nКопію рішення надсилають заявникові того ж дня.\n"


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


def text_of(body: str) -> str:
    return re.sub(r"<[^>]*>", " ", body)


def test_catalogue_covers_epic_6_pages(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    settings: Any,
) -> None:
    from editions import services as editions

    settings.LANGUAGE_CODE = "uk"
    people = edition_cast()
    document = people.document
    number = document.number
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
    administrator, _, admin_membership = member_of(
        "admin.synthetic@example.test", is_tenant_admin=True
    )
    link_group(document, [Right.FREEZE, Right.MAKE_CANONICAL], [admin_membership], people["a"])
    reader, _, reader_membership = member_of("reader.synthetic@example.test")
    link_group(document, [Right.VIEW_CANONICAL], [reader_membership], people["a"])
    pages: list[tuple[str, Any, str]] = []

    # Held: *Freeze* disabled with the holder's name, and without it.
    with schema_context(migrated_tenant.number):
        from editing import holds

        hold = holds.take(document, people["r"])
    pages += [
        ("held, administrator", administrator, f"/document/{number}/"),
        ("held, approver", people.clients["p"], f"/document/{number}/"),
    ]
    for name, client, path in pages:
        response = client.get(path)
        assert response.status_code == 200, name
        body = response.content.decode()
        assert 'data-command="freeze"' in body, name
        _assert_translated(name, body)
    from django.db import transaction

    with schema_context(migrated_tenant.number), transaction.atomic():
        holds.release(hold, holds.ReleaseKind.FINISHED)

    # Frozen: the band, *Make canonical* refused over pending work, the editor's refusal.
    commit_version(document, people["a"], SECOND, "edit")
    with schema_context(migrated_tenant.number):
        editions.freeze(document, people["p"], "Синтетична причина")
    for name, client, path in (
        ("frozen, historian", administrator, f"/document/{number}/"),
        ("frozen, approver", people.clients["p"], f"/document/{number}/"),
        ("frozen, editor's tab", people.clients["a"], f"/document/{number}/edit/"),
    ):
        response = client.get(path)
        assert response.status_code == 200, name
        body = response.content.decode()
        assert "Заморожено" in body, name
        _assert_translated(name, body)

    # Accepted and confirmed; then made canonical.
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
    confirmation = people.clients["p"].get(f"/document/{number}/make-canonical/")
    assert confirmation.status_code == 200
    _assert_translated("confirmation", confirmation.content.decode())
    confirmed = re.search(r'name="confirmed" value="([0-9a-f]{40})"', confirmation.content.decode())
    assert confirmed is not None
    made = people.clients["p"].post(
        f"/document/{number}/make-canonical/", {"confirmed": confirmed.group(1)}, follow=True
    )
    _assert_translated("made canonical", made.content.decode())
    for name, client, path in (
        ("list, reader of pending", people.clients["r"], "/folder/1/"),
        ("list, reader of canonical", reader, "/folder/1/"),
        ("page, reader of canonical", reader, f"/document/{number}/"),
        ("page, reviewer", people.clients["r"], f"/document/{number}/"),
        ("help", reader, "/help/editions/"),
    ):
        response = client.get(path)
        assert response.status_code == 200, name
        if name == "help":
            assert "Заморожування та редакції" in response.content.decode()
        _assert_translated(name, response.content.decode())


def _assert_translated(name: str, body: str) -> None:
    ids = message_ids(CATALOGUE.read_text(encoding="utf-8"))
    shown = text_of(body)
    leaked = [i for i in ids if re.search(rf"(?<![\w-]){re.escape(i)}(?![\w-])", shown)]
    assert leaked == [], f"{name} shows message ids verbatim: {leaked}"


def test_catalogue_covers_the_refusal_screens(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any, settings: Any
) -> None:
    """The screens a refusal draws: the freeze's notices, the frozen tab without a reason, the
    confirmation outrun by an acceptance, a finish refused while frozen."""
    from editing import holds
    from editing.models import Draft

    settings.LANGUAGE_CODE = "uk"
    people = edition_cast()
    document = people.document
    number = document.number
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
        # A reviewer holds the document before the freeze, and loses *accept* during it.
        hold = holds.take(document, people["r"])
        draft = Draft.objects.get(hold=hold)
        draft.content = {**draft.content, "document.md": SECOND}
        draft.save()
    approver = people.clients["p"]

    refused = approver.post(f"/document/{number}/freeze/", {"reason": ""}, follow=True)
    assert refused.status_code == 200
    _assert_translated("freeze refused while held", refused.content.decode())
    with schema_context(migrated_tenant.number), transaction.atomic():
        holds.release(hold, holds.ReleaseKind.FINISHED)
    frozen = approver.post(f"/document/{number}/freeze/", {"reason": ""}, follow=True)
    _assert_translated("frozen notice", frozen.content.decode())
    tab = people.clients["a"].get(f"/document/{number}/edit/")
    assert tab.status_code == 200 and "Заморожено" in tab.content.decode()
    _assert_translated("frozen tab without a reason", tab.content.decode())

    confirmation = approver.get(f"/document/{number}/make-canonical/")
    first = re.search(r'name="confirmed" value="([0-9a-f]{40})"', confirmation.content.decode())
    assert first is not None
    commit_version(document, people["r"], SECOND, "reviewer_edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
    stale = approver.post(f"/document/{number}/make-canonical/", {"confirmed": first.group(1)})
    assert stale.status_code == 409
    _assert_translated("stale confirmation", stale.content.decode())

    with schema_context(migrated_tenant.number):
        hold = holds.take(document, people["r"])
        draft = Draft.objects.get(hold=hold)
        draft.content = {**draft.content, "document.md": SECOND + "\nЩе одне речення.\n"}
        draft.save()
        group = people.groups["reviewers"]
        group.revoke(Right.ACCEPT, by=people["a"])
        group.grant(Right.EDIT, by=people["a"])
    finish = people.clients["r"].post(
        f"/document/{number}/edit/send/", {"summary": "Синтетична правка", "choice": "send"}
    )
    assert finish.status_code == 409, finish.status_code
    body = finish.content.decode()
    assert "Заморожено" in body
    _assert_translated("finish refused while frozen", body)
