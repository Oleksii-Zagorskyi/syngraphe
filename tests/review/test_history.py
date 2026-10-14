"""The History tab and the ceiling of what a reader may open of the past (DL-0209, DL-0286,
ADR-0007): `review.history.entries` lists a document's versions and its freezes to holders of
*view all history*, *view previous canonical versions* or *accept*, each reader's list cut at the
highest stance their rights reach; `version_for` resolves any number a version carries within that
ceiling and nothing beyond it; a kept draft is compared with the history its holder may read
(DL-0417).

People, organisations, groups and texts are synthetic examples: every address ends in
`@example.test`, and every text is invented.
"""

from __future__ import annotations

import html
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlsplit

import pytest

from access.rights import Right
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

REASON = "Synthetic reason: waiting for the board's decision"
FIRST = "# General provisions\n\nA request for approval is made in writing.\n"
ONLY_IN_SECOND = "The applicant attaches a synthetic record of service."
SECOND = FIRST + f"\n{ONLY_IN_SECOND}\n"
THIRD = FIRST + "\nA request is considered within ten days.\n"
FOURTH = THIRD + "\nA copy of the decision goes to the applicant that day.\n"
FIFTH = FOURTH + "\nThe register of requests is kept by the officer in charge.\n"
SIXTH = FIFTH + "\nRequests are considered in the order they arrive.\n"
SAME_ORIGIN = {"Sec-Fetch-Site": "same-origin"}


# --- the cast of an edition, copied from `tests/editions/conftest.py` ----------------------------


@dataclass
class Cast:
    document: Any
    people: dict[str, Any]
    memberships: dict[str, Any]
    groups: dict[str, Any] = field(default_factory=dict)
    clients: dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, name: str) -> Any:
        return self.people[name]


@pytest.fixture
def edition_cast(member_of: Any, new_document: Any, link_group: Any) -> Callable[..., Cast]:
    """A document linked to one group per role — `edit`, `accept`, and `freeze` with
    `make_canonical` — each member signed in as `<name>.synthetic@example.test`."""

    def make(
        editors: tuple[str, ...] = ("a",),
        reviewers: tuple[str, ...] = ("r",),
        approvers: tuple[str, ...] = ("p",),
    ) -> Cast:
        people: dict[str, Any] = {}
        memberships: dict[str, Any] = {}
        clients: dict[str, Any] = {}
        for name in dict.fromkeys((*editors, *reviewers, *approvers)):
            clients[name], people[name], memberships[name] = member_of(
                f"{name}.synthetic@example.test"
            )
        creator = people[(editors or reviewers or approvers)[0]]
        document = new_document(creator)
        made = Cast(document, people, memberships, clients=clients)
        roles = (
            ("editors", editors, [Right.EDIT]),
            ("reviewers", reviewers, [Right.ACCEPT]),
            ("approvers", approvers, [Right.FREEZE, Right.MAKE_CANONICAL]),
        )
        for role, names, rights in roles:
            if names:
                made.groups[role] = link_group(
                    document, rights, [memberships[n] for n in names], creator
                )
        return made

    return make


# --- the standard history ----------------------------------------------------------------------


def standard_history(tenant: Any, edition_cast: Any, commit_version: Any) -> SimpleNamespace:
    """Created (`0.0`); three edits by `a` (`0.0-1` to `0.0-3`); accepted by `r` as `0.1`; a
    freeze and its unfreeze; one edit (`0.1-1`) accepted as `0.2`; a freeze and *make canonical*
    (`1.0`, approving `0.1-1`); two edits by `a` and `b` (`1.0-1`, `1.0-2`). `.versions` by
    pending number; `.acceptances`, `.edition`, `.freezes`.

    A second passes around the first freeze and its unfreeze, so the commits beside them never
    share their second: the order is then the clock's, whatever precision each record keeps."""
    from documents.models import Version
    from editions import services as editions
    from review import services as review

    people = edition_cast(editors=("a", "b"))
    for name, display in (
        ("a", "Synthetic Author A"),
        ("b", "Synthetic Author B"),
        ("r", "Synthetic Reviewer R"),
        ("p", "Synthetic Approver P"),
    ):
        people[name].display_name = display
        people[name].save(update_fields=["display_name"])
    document = people.document
    versions: dict[str, Any] = {}
    with schema_context(tenant.number):
        versions["0.0"] = Version.objects.get(document=document, kind="created")
    versions["0.0-1"] = commit_version(document, people["a"], FIRST, "edit")
    versions["0.0-2"] = commit_version(document, people["a"], SECOND, "edit")
    versions["0.0-3"] = commit_version(document, people["a"], THIRD, "edit")
    with schema_context(tenant.number):
        first = review.accept(document, people["r"])
        time.sleep(1.1)
        freeze = editions.freeze(document, people["p"], REASON)
        editions.end_freeze(document, user=people["p"])
        time.sleep(1.1)
    versions["0.1-1"] = commit_version(document, people["a"], FOURTH, "edit")
    with schema_context(tenant.number):
        second = review.accept(document, people["r"])
        assert second.number == "0.2"
        editions.freeze(document, people["p"], REASON)
        edition = editions.make_canonical(document, people["p"])
        assert edition.number == "1.0"
    versions["1.0-1"] = commit_version(document, people["a"], FIFTH, "edit")
    versions["1.0-2"] = commit_version(document, people["b"], SIXTH, "edit")
    return SimpleNamespace(
        people=people,
        document=document,
        versions=versions,
        acceptances=(first, second),
        edition=edition,
        freeze=freeze,
    )


def reader(
    member_of: Any, link_group: Any, history: Any, name: str, rights: list[Any]
) -> tuple[Any, Any]:
    """`(client, user)` for a member whose one group on the document holds `rights`."""
    client, user, membership = member_of(f"{name}.synthetic@example.test")
    link_group(history.document, rights, [membership], history.people["a"])
    return client, user


READERS = {
    "i": [Right.VIEW_ALL_HISTORY, Right.VIEW_PENDING],
    "ii": [Right.VIEW_PREVIOUS_CANONICAL, Right.VIEW_CANONICAL],
    "iii": [Right.ACCEPT],
    "iv": [Right.VIEW_ALL_HISTORY, Right.VIEW_ACCEPTED],
}


def text_of(body: str) -> str:
    """The page's text: each tag a space, entities read, whitespace collapsed."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", body)))


def anchors(body: str, href: str) -> list[str]:
    """The opening tag of every link to `href`."""
    return [
        tag
        for tag in re.findall(r"<a\b[^>]*>", body)
        if re.search(rf'\bhref="{re.escape(href)}"', tag)
    ]


def shape(entry: Any) -> tuple[Any, ...]:
    """An entry as the assertions compare it."""
    return (
        entry.event,
        entry.number,
        entry.version.pk if entry.version is not None else None,
        entry.actor.pk if entry.actor is not None else None,
        entry.boundary,
    )


def test_entries_by_right(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    member_of: Any,
    link_group: Any,
) -> None:
    from review import history as review_history

    history = standard_history(migrated_tenant, edition_cast, commit_version)
    v = history.versions
    a, r, p = history.people["a"], history.people["r"], history.people["p"]
    first, second = history.acceptances
    users = {
        key: reader(member_of, link_group, history, f"history-{key}", rights)[1]
        for key, rights in READERS.items()
    }

    with schema_context(migrated_tenant.number):
        listed = {
            key: review_history.entries(user, history.document) for key, user in users.items()
        }

    # (i): every version, oldest first, under its displayed number.
    full = listed["i"]
    assert all(e.at is not None for e in full)
    of_versions = [shape(e)[:4] for e in full if e.version is not None]
    assert of_versions == [
        ("created", "0.0", v["0.0"].pk, a.pk),
        ("edit", "0.0-1", v["0.0-1"].pk, a.pk),
        ("edit", "0.0-2", v["0.0-2"].pk, a.pk),
        ("edit", "0.1", v["0.0-3"].pk, a.pk),
        ("acceptance", "0.1", first.version.pk, r.pk),
        ("edit", "1.0", v["0.1-1"].pk, a.pk),
        ("acceptance", "0.2", second.version.pk, r.pk),
        ("approval", "1.0", history.edition.approval_version.pk, p.pk),
        ("edit", "1.0-1", v["1.0-1"].pk, a.pk),
        ("edit", "1.0-2", v["1.0-2"].pk, history.people["b"].pk),
    ]
    # The freeze and its unfreeze, between the acceptance `0.1` and the edit `0.1-1`.
    events = [(e.event, e.version.pk if e.version is not None else None) for e in full]
    accepted_at = events.index(("acceptance", first.version.pk))
    edited_at = events.index(("edit", v["0.1-1"].pk))
    between = full[accepted_at + 1 : edited_at]
    assert [(e.event, e.number, e.version) for e in between] == [
        ("freeze", "", None),
        ("unfreeze", "", None),
    ]
    assert all(e.actor is not None and e.actor.pk == p.pk for e in between)
    assert [e.event for e in full].count("unfreeze") == 1
    assert {e.event for e in full if e.version is None} <= {"freeze", "unfreeze"}
    # One boundary: the latest accepted content version, `0.1-1`.
    bounded = [e for e in full if e.boundary]
    assert len(bounded) == 1
    assert bounded[0].version is not None and bounded[0].version.pk == v["0.1-1"].pk

    # (ii): the edition's approval alone.
    assert [(e.event, e.number) for e in listed["ii"]] == [("approval", "1.0")]

    # (iii): the run alone.
    assert [(e.event, e.number, e.version.pk) for e in listed["iii"]] == [
        ("edit", "1.0-1", v["1.0-1"].pk),
        ("edit", "1.0-2", v["1.0-2"].pk),
    ]

    # (iv): as (i), without the pending work its ladder does not reach.
    run = {v["1.0-1"].pk, v["1.0-2"].pk}
    assert [shape(e) for e in listed["iv"]] == [
        shape(e) for e in full if e.version is None or e.version.pk not in run
    ]


def test_no_tab_without_a_right(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    member_of: Any,
    link_group: Any,
) -> None:
    history = standard_history(migrated_tenant, edition_cast, commit_version)
    number = history.document.number
    accepted, _ = reader(member_of, link_group, history, "accepted", [Right.VIEW_ACCEPTED])
    previous, _ = reader(
        member_of, link_group, history, "previous", [Right.VIEW_PREVIOUS_CANONICAL]
    )

    for client in (accepted, previous):
        assert client.get(f"/document/{number}/history/").status_code == 404
        page = client.get(f"/document/{number}/").content.decode()
        assert f"/document/{number}/history/" not in page


def test_the_tab(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    member_of: Any,
    link_group: Any,
    settings: Any,
) -> None:
    settings.LANGUAGE_CODE = "en"
    history = standard_history(migrated_tenant, edition_cast, commit_version)
    number = history.document.number
    client, _ = reader(member_of, link_group, history, "history-i", READERS["i"])

    response = client.get(f"/document/{number}/history/")

    assert response.status_code == 200
    body = response.content.decode()
    shown = text_of(body)
    for word in ("created", "edit", "acceptance", "canonisation", "freeze", "unfreeze"):
        assert re.search(rf"\b{word}\b", shown), word
    for name in ("a", "b", "r", "p"):
        person = history.people[name]
        assert person.display_name in shown or person.email in shown, name
    # Each version linked to its historical page, in a new tab.
    for shown_number in ("0.0", "0.0-1", "0.0-2", "0.1", "0.2", "1.0", "1.0-1", "1.0-2"):
        links = anchors(body, f"/document/{number}/version/{shown_number}/")
        assert links, shown_number
        assert all('target="_blank"' in tag for tag in links), shown_number
    # Newest first.
    newest = body.index(f'href="/document/{number}/version/1.0-2/"')
    oldest = body.index(f'href="/document/{number}/version/0.0-1/"')
    assert newest < oldest
    assert re.search(r'class="[^"]*\bboundary\b[^"]*"', body)

    page = client.get(f"/document/{number}/").content.decode()
    assert anchors(page, f"/document/{number}/history/")


def test_version_for_applies_the_ceiling(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    member_of: Any,
    link_group: Any,
) -> None:
    from review.history import version_for

    history = standard_history(migrated_tenant, edition_cast, commit_version)
    document, v = history.document, history.versions
    full = reader(member_of, link_group, history, "history-i", READERS["i"])[1]
    previous = reader(member_of, link_group, history, "history-ii", READERS["ii"])[1]
    accepted = reader(member_of, link_group, history, "accepted", [Right.VIEW_ACCEPTED])[1]
    pending = reader(member_of, link_group, history, "pending", [Right.VIEW_PENDING])[1]

    def pk(found: Any) -> Any:
        return None if found is None else found.pk

    with schema_context(migrated_tenant.number):
        # (i): the versions themselves; `0.0-3` and the `0.1` that accepted it are one.
        assert pk(version_for(full, document, "0.0-2")) == v["0.0-2"].pk
        assert pk(version_for(full, document, "0.0-3")) == v["0.0-3"].pk
        assert pk(version_for(full, document, "0.1")) == v["0.0-3"].pk
        # (ii): the editions alone.
        assert pk(version_for(previous, document, "1.0")) == v["0.1-1"].pk
        assert version_for(previous, document, "0.1") is None
        assert version_for(previous, document, "1.0-1") is None
        # *view accepted* alone: the latest accepted version, which is also the edition.
        assert pk(version_for(accepted, document, "1.0")) == v["0.1-1"].pk
        assert version_for(accepted, document, "0.1") is None
        assert version_for(accepted, document, "0.0-2") is None
        # *view pending* alone: the run, and nothing earlier than the latest accepted.
        assert pk(version_for(pending, document, "1.0-1")) == v["1.0-1"].pk
        assert pk(version_for(pending, document, "1.0-2")) == v["1.0-2"].pk
        assert version_for(pending, document, "0.0-2") is None
        # Anyone: a number no version carries, or not a number at all.
        for number in ("9.9", "0.0-99", "abc", "1.0.1"):
            assert version_for(full, document, number) is None, number


def against_options(body: str) -> list[tuple[str, str]]:
    """The `(value, label)` of every option of the page's `<select name="against">`."""
    found = re.search(r'<select\b[^>]*\bname="against"[^>]*>(.*?)</select>', body, re.S)
    assert found is not None, "no comparison to choose"
    return [
        (html.unescape(value), text_of(label).strip())
        for value, label in re.findall(
            r'<option\b[^>]*\bvalue="([^"]*)"[^>]*>(.*?)</option>', found.group(1), re.S
        )
    ]


def offers(options: list[tuple[str, str]], number: str) -> bool:
    """Whether an option names version `number` — `0.1` never matching inside `0.1-2`."""
    pattern = rf"(?<![\d.-]){re.escape(number)}(?![\d-])"
    return any(re.search(pattern, f"{value} {label}") for value, label in options)


def redirected_to(response: Any, path: str) -> bool:
    return response.status_code == 302 and urlsplit(response["Location"]).path == path


def test_the_kept_draft_compares_with_the_history(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    settings: Any,
) -> None:
    """A holder whose reservation an administrator ended, holding *view all history*, compares
    the kept draft with the earlier content versions too (DL-0417)."""
    from editing.models import Draft, Hold
    from review import services

    settings.LANGUAGE_CODE = "en"
    _, author, _ = member_of("author.synthetic@example.test")
    holder_client, holder, holder_membership = member_of("holder.synthetic@example.test")
    _, other, other_membership = member_of("other.synthetic@example.test")
    _, reviewer, reviewer_membership = member_of("reviewer.synthetic@example.test")
    admin_client, _, _ = member_of("admin.synthetic@example.test", is_tenant_admin=True)
    document = new_document(author)
    number = document.number
    link_group(
        document,
        [Right.EDIT, Right.RESERVE_FOR_EDITING, Right.VIEW_ALL_HISTORY],
        [holder_membership],
        author,
    )
    link_group(document, [Right.EDIT], [other_membership], author)
    link_group(document, [Right.ACCEPT], [reviewer_membership], author)
    commit_version(document, other, FIRST, "edit")
    commit_version(document, other, THIRD, "edit")
    with schema_context(migrated_tenant.number):
        services.accept(document, reviewer)

    # The holder takes the document, writes, reserves; the administrator ends the reservation.
    assert holder_client.post(f"/document/{number}/edit/take/").status_code == 200
    with schema_context(migrated_tenant.number):
        draft = Draft.objects.get(hold__document=document, hold__released_at__isnull=True)
        draft.content = {**draft.content, "document.md": THIRD + f"\n{ONLY_IN_SECOND}\n"}
        draft.save()
        hold = Hold.objects.get(pk=draft.hold_id)
    reserved = holder_client.post(f"/document/{number}/edit/reserve/")
    assert redirected_to(reserved, f"/document/{number}/edit/"), reserved.status_code
    ended = admin_client.post(
        f"/document/{number}/edit/end-reservation/", {"reason": REASON, "hold": str(hold.pk)}
    )
    assert redirected_to(ended, f"/document/{number}/"), ended.status_code
    with schema_context(migrated_tenant.number):
        assert Hold.objects.get(pk=hold.pk).release_kind == "forced"
    commit_version(document, other, FOURTH, "edit")

    page = holder_client.get(f"/document/{number}/edit/", headers=SAME_ORIGIN)

    assert page.status_code == 200
    options = against_options(page.content.decode())
    for wanted in ("0.1", "0.1-1", "0.0-1"):
        assert offers(options, wanted), (wanted, options)
