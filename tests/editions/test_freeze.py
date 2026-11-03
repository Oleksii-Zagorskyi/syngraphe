"""Freezing (ST-0038, DL-0189, DL-0236, DL-0351, DL-0353, ADR-0016): a holder of *freeze* stops
editing while something outside the document is resolved; the band tells every reader why, the
name only those who may see history; editors are kept out of the edit tab, holders of *accept* are
not, and their acceptances continue the numbering.

People and groups are synthetic examples; the text is invented.
"""

from __future__ import annotations

import html
from typing import Any

import pytest
from django.db import transaction

from access.rights import Right
from audit.models import AuditEvent
from editing import holds
from review import services
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

FIRST = "A request for approval is made in writing.\n"
SECOND = FIRST + "\nA request is considered within ten days.\n"
THIRD = SECOND.replace("ten days", "five working days")
REASON = "Synthetic reason: waiting for the board to decide"


def _accepted(migrated_tenant: Any, people: Any, commit_version: Any) -> None:
    commit_version(people.document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        services.accept(people.document, people["r"])


def test_freeze_records_and_audits(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any
) -> None:
    from editions import services as editions
    from editions.models import Freeze
    from review.state import State, state

    people = edition_cast()
    _accepted(migrated_tenant, people, commit_version)

    with schema_context(migrated_tenant.number):
        freeze = editions.freeze(people.document, people["p"], REASON)

        assert list(Freeze.objects.filter(document=people.document, ended_at__isnull=True)) == [
            freeze
        ]
        assert freeze.reason == REASON
        assert freeze.frozen_by == people["p"]
        assert freeze.ended_by_kind == ""
        assert AuditEvent.objects.filter(
            action="document.frozen", object_id=people.document.pk
        ).exists()
        assert state(people.document) == State.FROZEN


def test_freeze_reason_is_one_line_of_at_most_500(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any
) -> None:
    from editions import services as editions

    people = edition_cast()
    _accepted(migrated_tenant, people, commit_version)

    with schema_context(migrated_tenant.number):
        for bad in ("two\nlines", "x" * 501):
            with pytest.raises(editions.FreezeRefused) as refused:
                editions.freeze(people.document, people["p"], bad)
            assert refused.value.reason == "reason_invalid"
        # No reason at all is a freeze too (DL-0353).
        assert editions.freeze(people.document, people["p"]).reason == ""


def test_freeze_refused_while_held(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any, member_of: Any, link_group: Any
) -> None:
    from editions import services as editions

    people = edition_cast()
    _accepted(migrated_tenant, people, commit_version)
    administrator, admin_user, admin_membership = member_of(
        "admin.synthetic@example.test", is_tenant_admin=True
    )
    link_group(
        people.document, [Right.FREEZE], [admin_membership], people["a"]
    )  # an administrator who may freeze
    people["a"].display_name = "Synthetic Editor E"
    people["a"].save(update_fields=["display_name"])

    with schema_context(migrated_tenant.number):
        holds.take(people.document, people["a"])
        with pytest.raises(editions.FreezeRefused) as refused:
            editions.freeze(people.document, people["p"], REASON)
        assert refused.value.reason == "held"

    number = people.document.number
    # A holder of *freeze* holds *edit*, so the holder is named to both (DL-0516).
    for client in (administrator, people.clients["p"]):
        page = client.get(f"/document/{number}/").content.decode()
        assert 'data-command="freeze"' in page
        control = page.split('data-command="freeze"')[1].split(">")[0]
        assert "disabled" in control
        assert "Synthetic Editor E" in control


def test_band_by_rights(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    member_of: Any,
    link_group: Any,
    settings: Any,
) -> None:
    from editions import services as editions

    settings.LANGUAGE_CODE = "en"
    people = edition_cast()
    _accepted(migrated_tenant, people, commit_version)
    people["p"].display_name = "Synthetic Approver P"
    people["p"].save(update_fields=["display_name"])
    reader, _, reader_membership = member_of("reader.synthetic@example.test")
    historian, _, historian_membership = member_of("history.synthetic@example.test")
    link_group(people.document, [Right.VIEW_ACCEPTED], [reader_membership], people["a"])
    link_group(
        people.document,
        [Right.VIEW_ACCEPTED, Right.VIEW_ALL_HISTORY],
        [historian_membership],
        people["a"],
    )
    with schema_context(migrated_tenant.number):
        editions.freeze(people.document, people["p"], REASON)

    number = people.document.number
    shown = reader.get(f"/document/{number}/").content.decode()
    assert 'class="band frozen"' in shown
    assert REASON in shown
    assert "Synthetic Approver P" not in shown
    named = historian.get(f"/document/{number}/").content.decode()
    assert REASON in named
    assert "Synthetic Approver P" in named
    # Every reader sees the *frozen* tag, beside the title (DL-0351).
    assert 'data-state="frozen"' in shown


def test_edit_tab_while_frozen(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any, settings: Any
) -> None:
    from editions import services as editions

    settings.LANGUAGE_CODE = "en"
    people = edition_cast()
    _accepted(migrated_tenant, people, commit_version)
    with schema_context(migrated_tenant.number):
        editions.freeze(people.document, people["p"], REASON)
    number = people.document.number
    editor, reviewer = people.clients["a"], people.clients["r"]

    tab = editor.get(f"/document/{number}/edit/")
    assert tab.status_code == 200
    body = tab.content.decode()
    assert REASON in body and "until it is unfrozen or made canonical" in body
    assert 'id="editor"' not in body
    taken = editor.post(f"/document/{number}/edit/take/")
    assert taken.status_code == 409 and taken.json() == {"frozen": True}
    with schema_context(migrated_tenant.number), pytest.raises(holds.Frozen):
        holds.take(people.document, people["a"])

    assert reviewer.post(f"/document/{number}/edit/take/").json() == {"held": False}
    with schema_context(migrated_tenant.number):
        assert holds.open_hold(people.document).user_id == people["r"].pk


def test_acceptance_continues_numbering_while_frozen(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any
) -> None:
    from editions import services as editions
    from editions.models import open_freeze

    people = edition_cast()
    _accepted(migrated_tenant, people, commit_version)
    with schema_context(migrated_tenant.number):
        editions.freeze(people.document, people["p"], REASON)
        hold = holds.take(people.document, people["r"])
        with transaction.atomic():
            holds.release(hold, holds.ReleaseKind.FINISHED)
    commit_version(people.document, people["r"], SECOND, "reviewer_edit")

    with schema_context(migrated_tenant.number):
        acceptance = services.accept(people.document, people["r"])
        assert acceptance.number == "0.2"
        assert open_freeze(people.document) is not None


def test_one_freeze_at_a_time(migrated_tenant: Any, edition_cast: Any, commit_version: Any) -> None:
    from editions import services as editions

    people = edition_cast()
    _accepted(migrated_tenant, people, commit_version)
    with schema_context(migrated_tenant.number):
        editions.freeze(people.document, people["p"], REASON)
        with pytest.raises(editions.FreezeRefused) as refused:
            editions.freeze(people.document, people["p"], "again")
        assert refused.value.reason == "already_frozen"


def test_freeze_needs_the_right(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any
) -> None:
    from editions import services as editions

    people = edition_cast()
    _accepted(migrated_tenant, people, commit_version)
    with schema_context(migrated_tenant.number):
        with pytest.raises(editions.FreezeRefused) as refused:
            editions.freeze(people.document, people["a"], REASON)
        assert refused.value.reason == "not_permitted"
    # Over HTTP the act answers as an address that does not exist.
    act = f"/document/{people.document.number}/freeze/"
    assert people.clients["a"].post(act).status_code == 404


def test_the_toggle_on_the_path(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any, settings: Any
) -> None:
    """*Freeze* asks no reason (DL-0518): its form posts nothing but the token, and the freeze
    opens; once someone holds the document, *Unfreeze* waits with its reason."""
    from editions.models import open_freeze

    settings.LANGUAGE_CODE = "en"
    people = edition_cast()
    _accepted(migrated_tenant, people, commit_version)
    number = people.document.number
    client = people.clients["p"]

    page = client.get(f"/document/{number}/").content.decode()
    form = page.split(f'action="/document/{number}/freeze/"', 1)[1].split("</form>", 1)[0]
    assert 'name="reason"' not in form and 'data-command="freeze"' in form
    assert client.post(f"/document/{number}/freeze/").status_code == 302
    with schema_context(migrated_tenant.number):
        assert open_freeze(people.document) is not None
        holds.take(people.document, people["r"])

    page = html.unescape(client.get(f"/document/{number}/").content.decode())
    control = page.split('data-command="unfreeze"', 1)[1].split(">", 1)[0]
    assert "disabled" in control
    assert "The document is held; unfreeze it once it is released." in control
