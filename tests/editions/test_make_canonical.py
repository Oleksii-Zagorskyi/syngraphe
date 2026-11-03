"""Making canonical (ST-0039, DL-0183, DL-0234, DL-0260, DL-0267, DL-0515): refused until every
content version since the latest acceptance is accepted, frozen or not; then the approval is a
passport commit of kind `approval`, tagged with the edition's number by the approver, recorded as
an `EDITION`, an open freeze ended and the act audited; the numbering continues from the edition.

People and groups are synthetic examples; the text is invented.
"""

from __future__ import annotations

import html
import inspect
import re
from typing import Any

import pygit2
import pytest

from access.rights import Right
from audit.models import AuditEvent
from documents import bundle, gitstore
from documents.identity import DOMAIN
from review import services as review
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

FIRST = "# General provisions\n\nA request for approval is made in writing.\n"
SECOND = FIRST + "\nA request is considered within ten days.\n"
THIRD = SECOND.replace("ten days", "five working days")
FOURTH = THIRD + "\nA copy of the decision goes to the applicant that day.\n"
REASON = "Synthetic reason: waiting for the board to decide"


def _tag(migrated_tenant: Any, document: Any, name: str) -> pygit2.Tag | None:
    """The annotated tag `name` of the document's repository, or `None`."""
    repo = gitstore.open_repository(migrated_tenant.number, document.number)
    ref = repo.references.get(f"refs/tags/{name}")
    if ref is None:
        return None
    found = repo[ref.target]
    assert isinstance(found, pygit2.Tag), f"{name} is a lightweight tag"
    return found


def _passport(repository: Any, document: Any) -> list[bundle.PassportEntry]:
    return bundle.passport_entries(repository.read(document, "passport.md"))


def test_refused_over_unaccepted_versions_without_the_number(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    repository: Any,
) -> None:
    """An approver holding *make canonical* alone — which includes *view accepted*, never *view
    pending* (DL-0234) — is refused while `0.2-1` waits, and never shown that number."""
    from editions import services as editions
    from editions.models import Edition

    people = edition_cast()
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
    commit_version(document, people["a"], SECOND, "edit")
    with schema_context(migrated_tenant.number):
        assert review.accept(document, people["r"]).number == "0.2"
    commit_version(document, people["a"], THIRD, "edit")
    with schema_context(migrated_tenant.number):
        editions.freeze(document, people["p"], REASON)
    approver_client, approver, membership = member_of("q.synthetic@example.test")
    link_group(document, [Right.MAKE_CANONICAL], [membership], people["a"])
    head = repository.head(document)

    with schema_context(migrated_tenant.number):
        from editing import numbering

        # The version the refusal must not name.
        assert numbering.latest(document) == "0.2-1"
        reason = editions.canonical_refusal(document, approver)
        assert reason == "unaccepted_changes"
        with pytest.raises(editions.CanonicalRefused) as refused:
            editions.make_canonical(document, approver)
        assert refused.value.reason == "unaccepted_changes"
        assert not Edition.objects.exists()
    assert repository.head(document) == head

    # The document page, control and all, names no pending number to this approver.
    response = approver_client.get(f"/document/{document.number}/")
    assert response.status_code == 200
    assert "0.2-1" not in response.content.decode()


def test_refused_when_nothing_accepted(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any, repository: Any
) -> None:
    """No acceptance at all; then, after an edition, none since it."""
    from editions import services as editions
    from editions.models import Edition

    people = edition_cast()
    document, approver = people.document, people["p"]
    with schema_context(migrated_tenant.number):
        editions.freeze(document, approver, REASON)
        assert editions.canonical_refusal(document, approver) == "nothing_accepted"
        with pytest.raises(editions.CanonicalRefused) as refused:
            editions.make_canonical(document, approver)
        assert refused.value.reason == "nothing_accepted"
        assert not Edition.objects.exists()

    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
        editions.make_canonical(document, approver)
        editions.freeze(document, approver, REASON)
        with pytest.raises(editions.CanonicalRefused) as refused:
            editions.make_canonical(document, approver)
        assert refused.value.reason == "nothing_accepted"
        assert list(Edition.objects.values_list("number", flat=True)) == ["1.0"]
    assert repository.kinds(document).count("approval") == 1


def test_refused_without_the_right(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any, repository: Any
) -> None:
    """A reviewer holding *accept* — and so *edit* and *view pending* — but not *make canonical*."""
    from editions import services as editions
    from editions.models import Edition

    people = edition_cast()
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
        editions.freeze(document, people["p"], REASON)
        for outsider in (people["r"], people["a"]):
            assert editions.canonical_refusal(document, outsider) == "not_permitted"
            with pytest.raises(editions.CanonicalRefused) as refused:
                editions.make_canonical(document, outsider)
            assert refused.value.reason == "not_permitted"
        assert not Edition.objects.exists()
    assert _tag(migrated_tenant, document, "1.0") is None


def test_numbering_after_an_edition(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any, repository: Any
) -> None:
    """`pending()` is the number the next content version will carry; `latest()` the number of
    the newest one (`editing.numbering`). After edition `1.0`: the first version is `1.0-1`
    (DL-0267), the next acceptance `1.1` (DL-0183), and the first version after it `1.1-1`."""
    from editing import numbering
    from editions import services as editions

    people = edition_cast()
    document, approver = people.document, people["p"]
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
        editions.freeze(document, approver, REASON)
        editions.make_canonical(document, approver)

        assert numbering.edition(document) == "1.0"
        assert numbering.accepted(document) == "1.0"
        assert numbering.pending(document) == "1.0-1"
        assert numbering.next_accepted(document) == "1.1"

    commit_version(document, people["a"], SECOND, "edit")
    with schema_context(migrated_tenant.number):
        assert numbering.latest(document) == "1.0-1"
        assert numbering.pending(document) == "1.0-2"

        acceptance = review.accept(document, people["r"])
        assert acceptance.number == "1.1"
        assert numbering.accepted(document) == "1.1"
        assert numbering.edition(document) == "1.0"
        assert numbering.pending(document) == "1.1-1"

    commit_version(document, people["a"], THIRD, "edit")
    with schema_context(migrated_tenant.number):
        assert numbering.latest(document) == "1.1-1"

    # The passport records the sequence the numbers are counted from.
    sections = [(e.kind, e.number) for e in _passport(repository, document)]
    assert sections == [("acceptance", "0.1"), ("approval", "1.0"), ("acceptance", "1.1")]


def test_second_edition_is_two(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any, repository: Any
) -> None:
    """`N+1.0`, N the editions made (DL-0183): the next edition after `1.0` is `2.0`, tagged so."""
    from editions import services as editions
    from editions.models import Edition

    people = edition_cast()
    document, approver = people.document, people["p"]
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
        editions.freeze(document, approver, REASON)
        editions.make_canonical(document, approver)
    second = commit_version(document, people["a"], FOURTH, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
        editions.freeze(document, approver, REASON)
        edition = editions.make_canonical(document, approver)
        assert edition.number == "2.0"
        assert edition.version_id == second.pk
        assert sorted(Edition.objects.values_list("number", flat=True)) == ["1.0", "2.0"]
    last = _passport(repository, document)[-1]
    assert (last.kind, last.number, last.edition) == ("approval", "2.0", "2.0")
    tag = _tag(migrated_tenant, document, "2.0")
    assert tag is not None and str(tag.peel(pygit2.Commit).id) == repository.head(document)
    assert _tag(migrated_tenant, document, "1.0") is not None


def test_the_pending_tab_numbers_from_the_edition(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any
) -> None:
    """After edition `1.0` — whose version was accepted as `0.1` — the first version waiting for
    review reads `1.0-1` on the pending tab, as it does everywhere else (DL-0267), never `0.1-1`."""
    from editions import services as editions

    people = edition_cast()
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
        editions.freeze(document, people["p"], REASON)
        editions.make_canonical(document, people["p"])
    commit_version(document, people["a"], SECOND, "edit")

    body = people.clients["r"].get(f"/document/{document.number}/pending/").content.decode()

    assert "1.0-1" in body
    assert "0.1-1" not in body
    # The act names the version accepted and the number it becomes, both from the edition.
    assert re.search(r'data-command="accept">[^<]*1\.0-1 — [^<]*1\.1</a>', body)


def test_a_notice_after_an_edition_numbers_its_versions_from_it(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any
) -> None:
    """A run accepted after an edition counts from the edition, as the pending tab does
    (DL-0267): the correction notice names `1.0-1` and `1.0-2`, never the acceptance before it."""
    from django.test import Client

    from editions import services as editions
    from notifications.models import Notification

    people = edition_cast()
    document, approver = people.document, people["p"]
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
        editions.freeze(document, approver, REASON)
        editions.make_canonical(document, approver)
    commit_version(document, people["a"], SECOND, "edit")
    commit_version(document, people["r"], THIRD, "reviewer_edit")
    with schema_context(migrated_tenant.number):
        assert review.accept(document, people["r"]).number == "1.1"
        notification = Notification.objects.get(user=people["a"], event="correction_notice")
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(people["a"])
    session = client.session
    session["tenant_number"] = migrated_tenant.number
    session.save()
    body = client.get(f"/notifications/{notification.pk}/").content.decode()
    assert "1.0-1" in body and "1.0-2" in body
    assert "0.1-" not in body


TAIL = "An edition is never undone: the next one supersedes it."


def _control(page: str) -> str:
    """The attributes of the *Make canonical* control, as drawn on the document page."""
    return page.split('data-command="approve"')[1].split(">")[0]


# replaces tests/editions/test_make_canonical.py::test_edition_is_a_tagged_passport_commit
def test_edition_is_a_tagged_passport_commit(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    repository: Any,
) -> None:
    """On a frozen document the open freeze ends at the approval, as before; afterwards the
    control's reason is `nothing_accepted`, no longer a freeze."""
    from editing import numbering
    from editions import services as editions
    from editions.models import Edition, Freeze, open_freeze
    from review.state import state

    people = edition_cast()
    document, approver = people.document, people["p"]
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
    approved = commit_version(document, people["a"], SECOND, "edit")
    with schema_context(migrated_tenant.number):
        assert review.accept(document, people["r"]).number == "0.2"
        freeze = editions.freeze(document, approver, REASON)
    before = repository.head(document)
    passport_before = repository.read(document, "passport.md")

    with schema_context(migrated_tenant.number):
        edition = editions.make_canonical(document, approver)

    head = repository.head(document)
    # One commit of kind `approval` on top of the `0.2` acceptance, the text unchanged.
    assert repository.kinds(document) == [
        "created",
        "edit",
        "acceptance",
        "edit",
        "acceptance",
        "approval",
    ]
    assert repository.parent(document, head) == before
    assert repository.read(document, "document.md", head) == repository.read(
        document, "document.md", approved.commit_sha
    )
    # The passport gains `## approval 1.0`, every earlier byte kept.
    passport = repository.read(document, "passport.md", head)
    assert passport.startswith(passport_before)
    last = _passport(repository, document)[-1]
    assert last.kind == "approval"
    assert last.number == "1.0"
    assert last.edition == "1.0"
    assert last.version == approved.commit_sha
    assert last.by == str(approver.pk)
    assert approver.email not in passport

    # An annotated tag `1.0` on the approval commit, by the approver's identity (DL-0260).
    tag = _tag(migrated_tenant, document, "1.0")
    assert tag is not None
    assert str(tag.peel(pygit2.Commit).id) == head
    assert tag.tagger.name == str(approver.pk)
    assert tag.tagger.email == f"{approver.pk}@{DOMAIN}"

    with schema_context(migrated_tenant.number):
        row = Edition.objects.get()
        assert row.pk == edition.pk
        assert row.number == "1.0"
        assert row.version_id == approved.pk
        assert row.approval_version.commit_sha == head
        assert row.approval_version.kind == "approval"
        assert row.freeze_id == freeze.pk
        assert row.approved_by_id == approver.pk
        assert row.approved_at is not None

        ended = Freeze.objects.get(pk=freeze.pk)
        assert ended.ended_by_kind == "made_canonical"
        assert ended.ended_at is not None
        assert open_freeze(document) is None

        assert state(document) == "canonical"
        assert numbering.edition(document) == "1.0"
        assert numbering.accepted(document) == "1.0"
        # Nothing accepted since the edition: the control's reason is that, never a freeze
        # (DL-0515).
        assert editions.canonical_refusal(document, approver) == "nothing_accepted"

    event = AuditEvent.objects.get(action="document.made_canonical")
    assert event.actor_id == approver.pk
    assert event.object_id == document.pk
    # A freeze was open: the approval's details carry no `freeze` key, as before.
    assert "freeze" not in (event.after or {})


# replaces tests/editions/test_make_canonical.py::test_needs_a_freeze
def test_needs_no_freeze(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any, repository: Any
) -> None:
    """With an acceptance since the last edition, nothing unaccepted, nobody holding
    it and no freeze open, the refusal is `None` and the control enabled; the act makes the edition
    with a freeze row of its own — begun and ended at the approval, by the approver, made canonical,
    no reason — audited as the approval alone, never as `document.freeze_derived`."""
    from editions import services as editions
    from editions.models import Edition, Freeze, open_freeze

    people = edition_cast()
    document, approver = people.document, people["p"]
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
        assert open_freeze(document) is None
        assert editions.canonical_refusal(document, approver) is None
    before = repository.head(document)
    page = people.clients["p"].get(f"/document/{document.number}/").content.decode()
    assert "disabled" not in _control(page)

    with schema_context(migrated_tenant.number):
        edition = editions.make_canonical(document, approver)

    head = repository.head(document)
    assert repository.parent(document, head) == before
    assert repository.kinds(document)[-1] == "approval"
    last = _passport(repository, document)[-1]
    assert (last.kind, last.number, last.edition) == ("approval", "1.0", "1.0")
    tag = _tag(migrated_tenant, document, "1.0")
    assert tag is not None and str(tag.peel(pygit2.Commit).id) == head
    with schema_context(migrated_tenant.number):
        row = Edition.objects.get()
        assert row.pk == edition.pk and row.number == "1.0"
        assert row.approved_by_id == approver.pk
        freeze = Freeze.objects.get(pk=row.freeze_id)
        assert Freeze.objects.filter(document=document).count() == 1
        assert freeze.frozen_at == freeze.ended_at == row.approved_at
        assert freeze.frozen_at.microsecond == 0
        assert freeze.frozen_by_id == freeze.ended_by_id == approver.pk
        assert freeze.ended_by_kind == "made_canonical"
        assert freeze.reason == ""
        assert open_freeze(document) is None
        assert editions.canonical_refusal(document, approver) == "nothing_accepted"

    made = AuditEvent.objects.get(action="document.made_canonical")
    assert made.actor_id == approver.pk
    assert made.object_id == document.pk
    assert (made.after or {}).get("freeze") == "none open"
    assert not AuditEvent.objects.filter(action="document.freeze_derived").exists()


def test_the_refusals_in_order(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any
) -> None:
    """With no freeze open, each refusal of the act's order — `not_permitted`, `held`,
    `nothing_accepted`, `unaccepted_changes`, `distinct_approver` — and never `not_frozen`; the
    view's table has no such key and the service no `once_frozen` keyword."""
    from editing import holds
    from editions import services as editions
    from editions.models import open_freeze
    from editions.views import CANONICAL_REFUSALS

    migrated_tenant.require_distinct_approver = True
    migrated_tenant.save()
    people = edition_cast(editors=("a",), reviewers=("r", "p"), approvers=("p", "t"))
    document = people.document
    seen: list[tuple[str, str | None]] = []

    with schema_context(migrated_tenant.number):
        seen.append(("editor", editions.canonical_refusal(document, people["a"])))
        seen.append(("nothing accepted", editions.canonical_refusal(document, people["t"])))
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        assert review.accept(document, people["p"]).number == "0.1"
        seen.append(("accepted by another", editions.canonical_refusal(document, people["t"])))
        seen.append(("accepted by oneself", editions.canonical_refusal(document, people["p"])))
    commit_version(document, people["a"], SECOND, "edit")
    with schema_context(migrated_tenant.number):
        seen.append(("a version waits", editions.canonical_refusal(document, people["t"])))
        # Before the approver's own acceptance counts against them.
        seen.append(("a version waits, oneself", editions.canonical_refusal(document, people["p"])))
        holds.take(document, people["a"])
        seen.append(("held", editions.canonical_refusal(document, people["t"])))
        with pytest.raises(editions.CanonicalRefused) as refused:
            editions.make_canonical(document, people["t"])
        assert open_freeze(document) is None

    assert seen == [
        ("editor", "not_permitted"),
        ("nothing accepted", "nothing_accepted"),
        ("accepted by another", None),
        ("accepted by oneself", "distinct_approver"),
        ("a version waits", "unaccepted_changes"),
        ("a version waits, oneself", "unaccepted_changes"),
        ("held", "held"),
    ]
    assert refused.value.reason == "held"
    assert "not_frozen" not in CANONICAL_REFUSALS
    assert "once_frozen" not in inspect.signature(editions.canonical_refusal).parameters


def test_the_confirmation_names_the_freeze_only_when_open(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any, settings: Any
) -> None:
    """*Version 0.1 becomes edition 1.0.* with no freeze open; *…, and the freeze ends.*
    with one; the tail *An edition is never undone…* in both, in one paragraph."""
    from editions import services as editions

    settings.LANGUAGE_CODE = "en"
    people = edition_cast()
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
    client = people.clients["p"]
    url = f"/document/{document.number}/make-canonical/"

    unfrozen = client.get(url)
    with schema_context(migrated_tenant.number):
        editions.freeze(document, people["p"], REASON)
    frozen = client.get(url)

    assert unfrozen.status_code == 200
    body = re.sub(r"\s+", " ", html.unescape(unfrozen.content.decode()))
    assert f"Version 0.1 becomes edition 1.0. {TAIL}" in body
    assert "and the freeze ends" not in body
    assert frozen.status_code == 200
    body = re.sub(r"\s+", " ", html.unescape(frozen.content.decode()))
    assert f"Version 0.1 becomes edition 1.0, and the freeze ends. {TAIL}" in body
    assert "Version 0.1 becomes edition 1.0." not in body


def test_the_window_approves(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any, settings: Any
) -> None:
    """The path's *Make canonical as 1.0…* opens a window naming the version, the edition and
    that it is never undone; its form makes the edition as the page's does, and a stale
    confirmation is refused as built (DL-0513)."""
    from editions.models import Edition

    settings.LANGUAGE_CODE = "en"
    people = edition_cast()
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
    client = people.clients["p"]

    page = html.unescape(client.get(f"/document/{document.number}/").content.decode())
    act = page.split('data-command="approve"', 1)[0].rsplit("<button", 1)[1]
    window = page.split('<dialog id="approve"', 1)[1].split("</dialog>", 1)[0]
    confirmed = re.search(r'name="confirmed" value="([0-9a-f]{40})"', window)

    assert (
        "Make canonical as 1.0…" in page
        and "data-window" in page.split('data-command="approve"', 1)[1].split(">", 1)[0]
    )
    assert "disabled" not in act
    assert f"Version 0.1 becomes edition 1.0. {TAIL}" in re.sub(r"\s+", " ", window)
    assert confirmed is not None
    stale = client.post(f"/document/{document.number}/make-canonical/", {"confirmed": "0" * 40})
    assert stale.status_code == 409
    made = client.post(
        f"/document/{document.number}/make-canonical/", {"confirmed": confirmed.group(1)}
    )
    assert made.status_code == 302
    with schema_context(migrated_tenant.number):
        assert Edition.objects.filter(version__document=document, number="1.0").exists()


def test_the_page_stands_without_script(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any, settings: Any
) -> None:
    """Without script the act is a form that opens the confirmation page, which stands."""
    settings.LANGUAGE_CODE = "en"
    people = edition_cast()
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
    client = people.clients["p"]
    url = f"/document/{document.number}/make-canonical/"

    page = client.get(f"/document/{document.number}/").content.decode()

    assert f'<form class="inline" method="get" action="{url}">' in page
    assert client.get(url).status_code == 200


def test_the_window_only_where_its_act_is_drawn(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any, settings: Any
) -> None:
    """The window reads the repository to name its numbers: drawn on the page that outlines the
    act's version, never on History or Info, which outline nothing."""
    settings.LANGUAGE_CODE = "en"
    people = edition_cast()
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
    client = people.clients["p"]

    assert '<dialog id="approve"' in client.get(f"/document/{document.number}/").content.decode()
    for page in ("history/", "info/"):
        body = client.get(f"/document/{document.number}/{page}").content.decode()
        assert '<dialog id="approve"' not in body, page
