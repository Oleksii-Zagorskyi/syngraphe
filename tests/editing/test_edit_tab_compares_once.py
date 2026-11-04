"""Opening the edit tab compares the holder's draft with the head once (ASR-21): the tab's own
*edited* and the path's draft acts read the same answer, so a long draft is normalised once per
opening, not once for each.

The text is invented; the people are synthetic examples at `@example.test`."""

from __future__ import annotations

from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

EDIT = "\nA synthetic sentence the holder added.\n"


@pytest.mark.parametrize("edited", [False, True])
def test_one_opening_compares_the_draft_once(
    migrated_tenant: Any, member_of: Any, new_document: Any, monkeypatch: Any, edited: bool
) -> None:
    from editing import services
    from editing.models import Draft

    client, holder, _ = member_of("the.holder@example.test")
    document = new_document(holder)
    assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
    if edited:
        with schema_context(migrated_tenant.number):
            draft = Draft.objects.get(hold__document=document)
            draft.content = {**draft.content, "document.md": draft.content["document.md"] + EDIT}
            draft.save()
    compared: list[Any] = []
    real = services.holds_later_work

    def counted(*args: Any, **kwargs: Any) -> bool:
        compared.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(services, "holds_later_work", counted)

    page = client.get(f"/document/{document.number}/edit/").content.decode()

    assert len(compared) == 1, compared
    # The path's draft acts drew the same answer: the live *Finish editing* shown only once edited.
    assert ('<span class="act" data-when="edited">' in page) is edited
    assert ('<span class="act" data-when="edited" hidden>' in page) is not edited
