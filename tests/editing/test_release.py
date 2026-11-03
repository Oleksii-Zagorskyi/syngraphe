"""A hold released by inactivity, by force or by a block keeps its draft only when the draft has
edits (DL-0514): an empty one is deleted with the release, so nothing is kept for the holder — no
band, no kept point on the path, nothing to take back. People, titles and texts are synthetic
examples."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from access.rights import Right
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

KINDS = ("inactivity", "forced", "blocked")
EDIT = "\nA synthetic sentence the holder added before the hold ended.\n"


def holding(member_of: Any, new_document: Any, link_group: Any) -> dict[str, Any]:
    """An editor holding a document they may edit, and an administrator; the holder's client,
    user and membership, the administrator's user, and the document."""
    client, holder, membership = member_of("the.holder@example.test")
    _, admin, _ = member_of("the.admin@example.test", is_tenant_admin=True)
    document = new_document(holder)
    link_group(document, [Right.EDIT], [membership], holder)
    assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
    return {
        "client": client,
        "holder": holder,
        "membership": membership,
        "admin": admin,
        "document": document,
    }


def open_hold(tenant: Any, document: Any) -> Any:
    from editing.models import Hold

    with schema_context(tenant.number):
        return Hold.objects.get(document=document, released_at__isnull=True)


def add_an_edit(tenant: Any, hold: Any) -> None:
    """The holder's text, as the editor's capture leaves it in the draft."""
    from editing.models import Draft

    with schema_context(tenant.number):
        draft = Draft.objects.get(hold=hold)
        draft.content = {**draft.content, "document.md": draft.content["document.md"] + EDIT}
        draft.save()


def release(kind: str, tenant: Any, scene: dict[str, Any]) -> None:
    """End the hold the way `kind` names, through the service or the task that does it."""
    from django.utils import timezone

    from editing import reservations, tasks
    from editing.models import Hold
    from identity import blocking

    document = scene["document"]
    if kind == "inactivity":
        with schema_context(tenant.number):
            Hold.objects.filter(document=document, released_at__isnull=True).update(
                last_activity_at=timezone.now() - timedelta(minutes=41)
            )
        assert tasks.release_inactive_holds() == 1
    elif kind == "forced":
        hold = open_hold(tenant, document)
        with schema_context(tenant.number):
            assert reservations.force_release(hold, scene["admin"]) is True
    else:
        blocking.block_membership(scene["membership"], by=scene["admin"])
        # Lifted at once: the person's pages are read after, and a lift restores no draft.
        blocking.lift_membership_block(scene["membership"], by=scene["admin"])


def released_hold(tenant: Any, document: Any) -> Any:
    from editing.models import Hold

    with schema_context(tenant.number):
        return Hold.objects.get(document=document)


def hold_released_event() -> Any:
    from audit.models import AuditEvent

    return AuditEvent.objects.get(action="document.hold_released")


@pytest.mark.parametrize("kind", KINDS)
def test_an_empty_hold_keeps_nothing(
    kind: str,
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    settings: Any,
) -> None:
    """Nothing edited when the hold ends: the draft row and its files go with it, the audit says
    nothing was kept, and the holder finds no band, no kept point and nothing to take back."""
    from documents import holds as document_holds
    from editing import holds
    from editing.models import Draft, DraftFile

    settings.LANGUAGE_CODE = "en"
    scene = holding(member_of, new_document, link_group)
    document, holder, client = scene["document"], scene["holder"], scene["client"]
    hold = open_hold(migrated_tenant, document)

    release(kind, migrated_tenant, scene)

    with schema_context(migrated_tenant.number):
        hold.refresh_from_db()
        assert hold.released_at is not None and hold.release_kind == kind
        assert not Draft.objects.filter(hold=hold).exists()
        assert not DraftFile.objects.exists()
        assert not document_holds.is_held(document)
        assert holds.preserved_draft(document, holder) is None
    event = hold_released_event()
    assert event.after["release_kind"] == kind
    assert event.after["kept"] is False
    assert event.after["draft_base"], "the draft's state is read before it is deleted"
    page = client.get(f"/document/{document.number}/")
    assert page.status_code == 200
    body = page.content.decode()
    assert 'class="band end"' not in body
    assert "Your editing of this document was ended" not in body
    assert 'data-go="kept"' not in body
    # Nothing to take back: the tab opens as usual, and a take-back finds nothing.
    tab = client.get(f"/document/{document.number}/edit/").content.decode()
    assert 'id="editor"' in tab and 'class="band end"' not in tab
    assert f"/document/{document.number}/edit/take-back/" not in tab


@pytest.mark.parametrize("kind", KINDS)
def test_a_hold_with_an_edit_keeps_its_draft(
    kind: str,
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    settings: Any,
) -> None:
    """The same releases with an edit in the draft: the draft is kept as built, the band and the
    kept point drawn for the holder."""
    from editing import holds
    from editing.models import Draft

    settings.LANGUAGE_CODE = "en"
    scene = holding(member_of, new_document, link_group)
    document, holder, client = scene["document"], scene["holder"], scene["client"]
    hold = open_hold(migrated_tenant, document)
    add_an_edit(migrated_tenant, hold)

    release(kind, migrated_tenant, scene)

    with schema_context(migrated_tenant.number):
        hold.refresh_from_db()
        assert hold.released_at is not None and hold.release_kind == kind
        kept = Draft.objects.get(hold=hold)
        assert kept.content["document.md"].endswith(EDIT)
        assert holds.preserved_draft(document, holder) == kept
    event = hold_released_event()
    assert event.after["release_kind"] == kind
    assert event.after.get("kept") in (None, True)
    body = client.get(f"/document/{document.number}/").content.decode()
    assert 'class="band end"' in body
    assert "Your editing of this document was ended" in body
    assert 'data-go="kept"' in body


def test_a_released_kind_never_deletes_an_edit(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    """Whatever the kind, the draft decides: a release of kind *released* over a draft that holds
    an edit keeps it."""
    from django.db import transaction

    from documents.locks import document_lock
    from editing import holds
    from editing.models import Draft, Hold, ReleaseKind

    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
    with schema_context(migrated_tenant.number):
        draft = Draft.objects.get(hold__document=document)
        draft.content = {**draft.content, "document.md": "# Kept\n\nAn invented edit.\n"}
        draft.save()
        with document_lock(migrated_tenant.number, document.number), transaction.atomic():
            holds.release(Hold.objects.get(document=document), ReleaseKind.RELEASED)
        assert Draft.objects.filter(pk=draft.pk).exists()


def test_has_edits_never_raises(migrated_tenant: Any, member_of: Any, new_document: Any) -> None:
    """A hold whose draft is gone counts as edited, and nothing raises: a release never fails on
    what a draft holds."""
    from editing import services
    from editing.models import Draft, Hold

    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
    with schema_context(migrated_tenant.number):
        Draft.objects.filter(hold__document=document).delete()
        assert services.has_edits(Hold.objects.get(document=document)) is True
