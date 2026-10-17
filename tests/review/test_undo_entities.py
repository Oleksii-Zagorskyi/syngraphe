"""An undo leaves the document's roles, actions and terms as they stand (DL-0380): when the undone
versions declared or relabelled one, the reviewer is told so above the editor, as a title or a
part they changed is. People are synthetic examples; texts and labels are invented."""

from __future__ import annotations

from typing import Any

import pytest
from django.test import Client

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

BASE = "# General provisions\n\nAn application is made in writing.\n"


def test_an_undo_keeps_entities_and_says_so(
    migrated_tenant: Any,
    cast: Any,
    commit_version: Any,
    queued_authorship: list[Any],
    settings: Any,
) -> None:
    from editing.models import Draft
    from review import services, undo

    settings.LANGUAGE_CODE = "en"
    people = cast(editors=("a",), reviewers=("r",))
    document = people.document
    commit_version(document, people["a"], BASE, "edit")
    with schema_context(migrated_tenant.number):
        services.accept(document, people["r"])
    declared = '- kind: "role"\n  key: "role-1"\n  label: "the treasurer"\n'
    version = commit_version(
        document,
        people["a"],
        BASE + "\n[The treasurer]{.role #role-1} signs it.\n",
        "edit",
        files={"entities.yaml": declared.encode()},
    )

    with schema_context(migrated_tenant.number):
        hold = undo.apply(document, people["r"], version=version)
        listed = Draft.objects.get(hold=hold).content["undo"]["listed"]
    assert {"before": "", "after": "", "entities": "kept"} in listed

    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(people["r"])
    session = client.session
    session["tenant_number"] = migrated_tenant.number
    session.save()
    page = client.get(f"/document/{document.number}/edit/").content.decode()
    assert (
        "Roles, actions and terms the undone edits declared or relabelled stay as they stand."
        in page
    )
