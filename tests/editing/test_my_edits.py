"""*My edits* as a switch inside the editor (DL-0518): its address answers the changes alone for
the switch, and the whole page under the frame otherwise (DL-0514).

People and titles are synthetic examples; the text is invented English."""

from __future__ import annotations

from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]


def test_the_fragment_and_the_page(
    migrated_tenant: Any, member_of: Any, new_document: Any, settings: Any
) -> None:
    from editing.models import Draft

    settings.LANGUAGE_CODE = "en"
    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    client.post(f"/document/{document.number}/edit/take/")
    with schema_context(migrated_tenant.number):
        draft = Draft.objects.get(hold__document=document)
        body = draft.content["document.md"] + "\nA synthetic sentence added.\n"
        draft.content = {**draft.content, "document.md": body}
        draft.save()
    url = f"/document/{document.number}/my-edits/"

    fragment = client.get(f"{url}?fragment=1")
    page = client.get(url)
    other = client.get(f"{url}?fragment=yes")

    assert fragment.status_code == page.status_code == other.status_code == 200
    part = fragment.content.decode()
    assert '<div class="changes document-text">' in part and "<ins>" in part
    assert "<html" not in part and '<nav class="path"' not in part
    for whole in (page.content.decode(), other.content.decode()):
        assert "<html" in whole and '<nav class="path"' in whole and "<ins>" in whole
    stranger, _, _ = member_of("a.stranger@example.test")
    assert stranger.get(f"{url}?fragment=1").status_code == 404
