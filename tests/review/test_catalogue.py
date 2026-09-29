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
        notification = Notification.objects.get(user=author)
    bodies["the correction notice"] = shown(author_client, f"/notifications/{notification.pk}/")

    for name, body in bodies.items():
        leaked = [i for i in ids if re.search(rf"(?<![\w-]){re.escape(i)}(?![\w-])", body)]
        assert leaked == [], f"{name} shows message ids verbatim: {leaked}"
    assert "Погоджено як 0.1" in bodies["the notice after accepting"]
    assert "Сповіщення про виправлення" in bodies["the correction notice"]
