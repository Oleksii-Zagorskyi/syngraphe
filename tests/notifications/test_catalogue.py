"""The notifications page renders in Ukrainian from the one catalogue: its tabs and filters, an
entry for every event — a correction notice through the acceptance that writes it, each backup
condition begun and cleared — its sentences and the count in the shell.

People, groups and titles are synthetic examples."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

_spec = importlib.util.spec_from_file_location(
    "review_catalogue", Path(__file__).resolve().parents[1] / "review" / "test_catalogue.py"
)
assert _spec is not None and _spec.loader is not None
_review = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_review)

CATALOGUE = _review.CATALOGUE
message_ids = _review.message_ids
text_of = _review.text_of


BODY = "# Умови\n\nПерше синтетичне речення.\nДруге синтетичне речення.\n"
CORRECTED = BODY.replace("Друге синтетичне речення.", "Друге синтетичне речення, виправлене.")
CONDITIONS = ("repository_failing", "backup_behind", "archive_waiting", "unknown")


@pytest.mark.integration
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_catalogue_covers_notifications_pages(
    migrated_tenant: Any,
    member_of: Any,
    make_document: Any,
    written: Any,
    written_platform: Any,
    cast: Any,
    commit_version: Any,
    settings: Any,
) -> None:
    from access.models import AccessGroup
    from notifications.models import PLATFORM_EVENTS, Event
    from review import services
    from tenancy.schemas import schema_context

    settings.LANGUAGE_CODE = "uk"
    client, admin, _ = member_of(
        "p.admin@example.test", is_platform_admin=True, is_tenant_admin=True
    )
    document = make_document(title="Синтетичне положення")
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(
            name="Синтетична група", created_by=admin, actor_kind="user"
        )
    n = 0
    for event in Event:
        if event in PLATFORM_EVENTS:
            continue
        if event != Event.CORRECTION_NOTICE:
            facts = {"group": str(group.pk), "version": "0.0-1", "accepted": "0.1"}
            written(admin, event, document=document, at=n, facts={**facts, "edition": "1.0"})
            n += 1
    written(admin, "access_granted", at=n, facts={})
    written(admin, "document_created", document=document, at=n + 1, facts={"recreated": True})
    for condition in CONDITIONS:
        for change in ("began", "cleared"):
            n += 2
            written_platform(
                admin, "backup_condition", at=n, facts={"condition": condition, "change": change}
            )
    written_platform(admin, "email_failed", at=n + 1, facts={})
    # A correction notice, through the acceptance that writes it, to its author.
    people = cast(editors=("a",), reviewers=("r",))
    commit_version(people.document, people["a"], BODY, "edit")
    commit_version(people.document, people["r"], CORRECTED, "reviewer_edit")
    with schema_context(migrated_tenant.number):
        services.accept(people.document, people["r"])
    author = _review.signed_in(migrated_tenant, people["a"])

    ids = message_ids(CATALOGUE.read_text(encoding="utf-8"))
    bodies = {
        tab: text_of(client.get(f"/notifications/?tab={tab}").content.decode())
        for tab in ("document", "administrative")
    }
    bodies["the author's document tab"] = text_of(
        author.get("/notifications/?tab=document").content.decode()
    )
    assert "Сповіщення про виправлення" in bodies["the author's document tab"]
    for name, body in bodies.items():
        leaked = [message for message in ids if message in body]
        assert leaked == [], (name, leaked)
