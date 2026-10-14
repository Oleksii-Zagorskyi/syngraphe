"""*Unfreeze* (ST-0040, DL-0189, ADR-0016): a holder of *freeze* ends the freeze, `unfrozen`, with
themself as the actor; ordinary editing resumes at the same accepted number. People and groups are
synthetic examples; the text is invented."""

from __future__ import annotations

from typing import Any

import pytest

from audit.models import AuditEvent
from review import services as review
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

BODY = "Заяву на погодження подають письмово.\n"
LATER = BODY + "Копію рішення надсилають заявникові.\n"


def frozen(tenant: Any, edition_cast: Any, commit_version: Any) -> Any:
    from editions import services as editions

    people = edition_cast()
    commit_version(people.document, people["a"], BODY, "edit")
    with schema_context(tenant.number):
        review.accept(people.document, people["r"])
        editions.freeze(people.document, people["p"], "Синтетична причина")
    return people


def test_unfreeze_resumes_editing_at_the_same_number(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any, settings: Any
) -> None:
    from editing import numbering
    from editions.models import Freeze, open_freeze
    from notifications.models import Notification

    settings.LANGUAGE_CODE = "en"
    people = frozen(migrated_tenant, edition_cast, commit_version)
    number = people.document.number
    page = people.clients["p"].get(f"/document/{number}/").content.decode()
    assert f'action="/document/{number}/unfreeze/"' in page

    response = people.clients["p"].post(f"/document/{number}/unfreeze/")

    assert response.status_code == 302 and response["Location"] == f"/document/{number}/"
    with schema_context(migrated_tenant.number):
        freeze = Freeze.objects.get()
        assert freeze.ended_by_kind == "unfrozen" and freeze.ended_by_id == people["p"].pk
        assert open_freeze(people.document) is None
        assert Notification.objects.filter(event="unfrozen").exists()
        assert not Notification.objects.filter(event="unfrozen", user=people["p"]).exists()
    event = AuditEvent.objects.get(action="document.unfrozen")
    assert event.actor_id == people["p"].pk
    page = people.clients["a"].get(f"/document/{number}/").content.decode()
    assert 'class="band frozen"' not in page
    # Editing resumes for everyone with *edit*: an editor without *accept* takes the document.
    assert people.clients["a"].post(f"/document/{number}/edit/take/").status_code == 200
    assert people.clients["a"].post(f"/document/{number}/edit/discard/").status_code == 302
    commit_version(people.document, people["a"], LATER, "edit")
    with schema_context(migrated_tenant.number):
        assert numbering.latest(people.document) == "0.1-1"


def test_needs_freeze(migrated_tenant: Any, edition_cast: Any, commit_version: Any) -> None:
    from editions.models import open_freeze

    people = frozen(migrated_tenant, edition_cast, commit_version)
    number = people.document.number
    page = people.clients["a"].get(f"/document/{number}/").content.decode()
    assert f"/document/{number}/unfreeze/" not in page
    assert people.clients["a"].post(f"/document/{number}/unfreeze/").status_code == 404
    assert people.clients["p"].get(f"/document/{number}/unfreeze/").status_code == 404
    with schema_context(migrated_tenant.number):
        assert open_freeze(people.document) is not None
    assert not AuditEvent.objects.filter(action="document.unfrozen").exists()


def test_unfreeze_on_a_document_not_frozen(
    migrated_tenant: Any, edition_cast: Any, settings: Any
) -> None:
    """Nothing to end: back to the page with the reason, nothing written — even while someone
    holds the document."""
    settings.LANGUAGE_CODE = "en"
    people = edition_cast()
    number = people.document.number
    assert people.clients["a"].post(f"/document/{number}/edit/take/").status_code == 200
    response = people.clients["p"].post(f"/document/{number}/unfreeze/", follow=True)
    assert "The document is not frozen." in response.content.decode()
    assert not AuditEvent.objects.filter(action="document.unfrozen").exists()


def test_unfreeze_waits_while_the_document_is_held(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any, settings: Any
) -> None:
    """A holder of *accept* may hold a frozen document (ADR-0016): *Unfreeze* is drawn disabled
    with its reason, as *Freeze* is, and a forged POST changes nothing (DL-0223, DL-0233)."""
    from editing import holds
    from editions.models import open_freeze

    settings.LANGUAGE_CODE = "en"
    people = frozen(migrated_tenant, edition_cast, commit_version)
    number = people.document.number
    with schema_context(migrated_tenant.number):
        holds.take(people.document, people["r"])
    page = people.clients["p"].get(f"/document/{number}/").content.decode()
    control = page.split('data-command="unfreeze"', 1)[1].split(">", 1)[0]
    assert "disabled" in control
    assert "unfreeze it once it is released" in page
    response = people.clients["p"].post(f"/document/{number}/unfreeze/", follow=True)
    assert "unfreeze it once it is released" in response.content.decode()
    with schema_context(migrated_tenant.number):
        assert open_freeze(people.document) is not None


def test_the_control_in_ukrainian(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any, settings: Any
) -> None:
    """*Unfreeze* reads *Розморозити*, the glossary's word, from the one catalogue."""
    settings.LANGUAGE_CODE = "uk"
    people = frozen(migrated_tenant, edition_cast, commit_version)
    page = people.clients["p"].get(f"/document/{people.document.number}/").content.decode()
    assert ">Розморозити</button>" in page


def test_the_right_is_read_under_the_locks(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any
) -> None:
    """A person without *freeze* reaching the act itself is refused there, nothing written."""
    from editions import services as editions
    from editions.models import open_freeze

    people = frozen(migrated_tenant, edition_cast, commit_version)
    with schema_context(migrated_tenant.number):
        with pytest.raises(editions.FreezeRefused) as refused:
            editions.end_freeze(people.document, user=people["a"])
        assert refused.value.reason == "not_permitted"
        assert open_freeze(people.document) is not None
    assert not AuditEvent.objects.filter(action="document.unfrozen").exists()


def test_a_stopped_approval_is_said_as_an_edition(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any, settings: Any
) -> None:
    """An approval stopped after its commit is settled by the unfreeze's click: the freeze ends as
    the edition made, and the person is told so, not that the document was not frozen."""
    from editions import services as editions

    settings.LANGUAGE_CODE = "en"
    people = frozen(migrated_tenant, edition_cast, commit_version)
    with schema_context(migrated_tenant.number), pytest.raises(review.InjectedFault):
        editions.make_canonical(people.document, people["p"], fault_at=1)
    page = (
        people.clients["p"]
        .post(f"/document/{people.document.number}/unfreeze/", follow=True)
        .content.decode()
    )
    assert "made canonical meanwhile" in page
    assert not AuditEvent.objects.filter(action="document.unfrozen").exists()


def test_make_canonical_waits_while_the_document_is_held(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any, settings: Any
) -> None:
    """*Make canonical* ends a freeze too, and waits for its holder as unfreeze does (DL-0419); the
    operator's command does not wait (DL-0419)."""
    from editing import holds
    from editions import services as editions
    from editions.models import open_freeze

    settings.LANGUAGE_CODE = "en"
    people = frozen(migrated_tenant, edition_cast, commit_version)
    number = people.document.number
    with schema_context(migrated_tenant.number):
        holds.take(people.document, people["r"])
        assert editions.canonical_refusal(people.document, people["p"]) == "held"
        with pytest.raises(editions.CanonicalRefused):
            editions.make_canonical(people.document, people["p"])
        assert open_freeze(people.document) is not None
    page = people.clients["p"].get(f"/document/{number}/").content.decode()
    assert "make it canonical once it is released" in page
    with schema_context(migrated_tenant.number):
        editions.end_freeze(people.document, "Синтетичне рішення оператора")
        assert open_freeze(people.document) is None
