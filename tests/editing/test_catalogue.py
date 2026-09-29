"""Every page and screen the editor added renders in Ukrainian from the one catalogue.

People, groups and the document's text are synthetic examples."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from tenancy.schemas import schema_context

CATALOGUE = (
    Path(__file__).resolve().parents[2] / "src" / "shell" / "locale" / "uk" / "LC_MESSAGES"
) / "django.po"

BODY = "# Синтетичний розділ\n\nПерше речення умов.\nДруге речення умов.\n"


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


@pytest.mark.integration
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_catalogue_covers_epic_4_pages(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    queued_authorship: list[Any],
    settings: Any,
) -> None:
    from access.rights import Right
    from editing.messages import HELP_PAGES
    from editing.models import Draft

    settings.LANGUAGE_CODE = "uk"
    holder, author, own = member_of("the.holder@example.test")
    other, _, membership = member_of("another.editor@example.test")
    document = new_document(author)
    link_group(document, [Right.EDIT], [own, membership], author)
    assert holder.post(f"/document/{document.number}/edit/take/").status_code == 200
    with schema_context(migrated_tenant.number):
        draft = Draft.objects.get(hold__document=document, hold__released_at__isnull=True)
        draft.content = {**draft.content, "document.md": BODY}
        draft.save()
    ids = message_ids(CATALOGUE.read_text(encoding="utf-8"))

    def shown(client: Any, path: str, status: int = 200) -> str:
        response = client.get(path, follow=True)
        assert response.status_code == status, path
        return text_of(response.content.decode())

    bodies = {
        "the edit tab": shown(holder, f"/document/{document.number}/edit/"),
        "the held tab": shown(other, f"/document/{document.number}/edit/"),
        "my edits": shown(holder, f"/document/{document.number}/my-edits/"),
        "the finishing screen": shown(holder, f"/document/{document.number}/edit/finish/"),
        "the help index": shown(holder, "/help/"),
    }
    for slug in HELP_PAGES:
        bodies[f"help: {slug}"] = shown(holder, f"/help/{slug}/")
    refused = holder.post(f"/document/{document.number}/edit/send/", {"summary": ""})
    bodies["a refused summary"] = text_of(refused.content.decode())
    loaded = holder.post(f"/document/{document.number}/edit/load/")
    assert loaded.status_code == 200
    bodies["waiting for editors"] = shown(holder, f"/document/{document.number}/edit/finish/", 409)
    holder.post(f"/document/{document.number}/edit/close/", {"editor": loaded.json()["editor"]},
                content_type="application/json")  # fmt: skip
    sent = holder.post(
        f"/document/{document.number}/edit/send/", {"summary": "Уточнено умови"}, follow=True
    )
    bodies["the notice after sending"] = text_of(sent.content.decode())

    for name, body in bodies.items():
        leaked = [i for i in ids if re.search(rf"(?<![\w-]){re.escape(i)}(?![\w-])", body)]
        assert leaked == [], f"{name} shows message ids verbatim: {leaked}"
    assert "Відправлено на розгляд" in bodies["the notice after sending"]
