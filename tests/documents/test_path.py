"""The document's path (`documents.path.frame`, DL-0518, DL-0522): the points a reader sees of a
document, the arcs between them, the draft and kept points of their own, the heading's version and
the icons — by reader and by state, every expectation written out by hand from the path's rules,
never computed by the module under test.

People, groups and titles are synthetic examples; every text is invented English.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from django.test import RequestFactory
from django.utils import translation

from access.rights import Right
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

FIRST = "# General provisions\n\nA request for approval is made in writing.\n"
SECOND = FIRST + "\nA copy of the decision goes to the applicant that day.\n"
THIRD = SECOND + "\nThe register of requests is kept by the officer in charge.\n"
FOURTH = THIRD + "\nA request is considered within ten days.\n"
DRAFT_SENTENCE = "The draft's owner added a wholly new sentence on time limits."
RETURN_REASON = "Synthetic reason: the second section needs a date"
FREEZE_REASON = "Synthetic reason: waiting for the board to decide"

# --- the readers: what each one's group is granted (`implied` applied by the grant) -------------

READERS = (
    "canonical_only",
    "view_accepted",
    "view_pending",
    "edit",
    "accept",
    "approver",
    "administrator",
    "previous_canonical",
)
GRANTS: dict[str, list[Right]] = {
    "canonical_only": [Right.VIEW_CANONICAL],
    "view_accepted": [Right.VIEW_ACCEPTED],
    "view_pending": [Right.VIEW_PENDING],
    "edit": [Right.EDIT],
    "accept": [Right.ACCEPT],
    "approver": [Right.ACCEPT, Right.FREEZE, Right.MAKE_CANONICAL],
    # A tenant administrator: no group; `access.rights.ADMINISTRATOR` alone.
    "administrator": [],
    # *view previous canonical versions* does not imply *view canonical*: granted beside it.
    "previous_canonical": [Right.VIEW_CANONICAL, Right.VIEW_PREVIOUS_CANONICAL],
}
# The readers whose rights include *edit*: the only ones a draft or kept point can reach.
EDITING = ("edit", "accept", "approver")
# How the pages name the people who can hold (synthetic examples); the rest stay unnamed.
NAMES = {
    "edit": "Synthetic Editor",
    "accept": "Synthetic Reviewer",
    "approver": "Synthetic Approver",
    "administrator": "Synthetic Administrator",
    "other": "Synthetic Other Editor",
}
# `review.history.has_tab`: a history right or *accept*.
TWO_ICONS = [
    ("export", "Export", "/document/{n}/export/"),
    ("info", "Info", "/document/{n}/info/"),
]
THREE_ICONS = [
    ("export", "Export", "/document/{n}/export/"),
    ("history", "History", "/document/{n}/history/"),
    ("info", "Info", "/document/{n}/info/"),
]
ICONS: dict[str, list[tuple[str, str, str]]] = {
    "canonical_only": TWO_ICONS,
    "view_accepted": TWO_ICONS,
    "view_pending": TWO_ICONS,
    "edit": TWO_ICONS,
    "accept": THREE_ICONS,
    "approver": THREE_ICONS,
    "administrator": THREE_ICONS,
    "previous_canonical": THREE_ICONS,
}

STATES = (
    "new",
    "canonical",
    "accepted",
    "pending",
    "returned",
    "frozen",
    "held_by_other",
    "reserved_by_other",
    "held_by_reader",
    "kept",
    "archived",
)


# --- the expectations, written out by hand ---------------------------------------------------

Item = tuple[str, str, str, str, str, str, bool]


def point(
    key: str, number: str, caption: str, href: str, sub: str = "", here: bool = False
) -> Item:
    return ("point", key, number, caption, sub, href, here)


def arc(key: str, caption: str, sub: str, href: str, here: bool = False) -> Item:
    return ("arc", key, "", caption, sub, href, here)


CANONICAL_10 = point("canonical", "1.0", "canonical version", "/document/{n}/version/1.0/")
HISTORY_ARC_10_11 = arc(
    "history-arc", "edits between versions", "", "/document/{n}/compare/?from=1.0&to=1.1"
)
ACCEPTED_11 = point("accepted", "1.1", "latest accepted", "/document/{n}/version/1.1/")
DASH = arc("", "", "", "")

# No version beyond `0.0`: the created text, nobody's acceptance, is the latest the reader sees.
LATEST_00 = [point("latest", "0.0", "latest version", "/document/{n}/", here=True)]
# The canonical edition is the last word: one point.
LATEST_10 = [point("latest", "1.0", "latest version", "/document/{n}/", here=True)]
# Accepted since the edition: `canonical`, the history arc, `latest` (the accepted point renamed).
CANONICAL_THEN_11 = [
    CANONICAL_10,
    HISTORY_ARC_10_11,
    point("latest", "1.1", "latest version", "/document/{n}/", here=True),
]
# A run of two awaiting review over `1.1`.
PENDING_TWO = [
    CANONICAL_10,
    HISTORY_ARC_10_11,
    ACCEPTED_11,
    arc("run-arc", "edits between versions", "2 versions", "/document/{n}/pending/"),
    point("latest", "1.1-2", "latest version", "/document/{n}/", sub="awaiting review", here=True),
]
# A run of two over the edition `1.0`, returned: no accepted point, the run's arc from `canonical`.
RETURNED_TWO = [
    CANONICAL_10,
    arc("run-arc", "edits between versions", "returned", "/document/{n}/pending/"),
    point("latest", "1.0-2", "latest version", "/document/{n}/", sub="returned", here=True),
]
# One version awaiting review over `1.1`, under a freeze: the freeze changes nothing here.
FROZEN_ONE = [
    CANONICAL_10,
    HISTORY_ARC_10_11,
    ACCEPTED_11,
    arc("run-arc", "edits between versions", "1 version", "/document/{n}/pending/"),
    point("latest", "1.1-1", "latest version", "/document/{n}/", sub="awaiting review", here=True),
]
# The holder's draft after `1.1`: the dashed segment, then the draft point; `or 1.2` to an acceptor.
DRAFT_11_1 = [DASH, point("draft", "1.1-1", "your draft", "/document/{n}/edit/")]
DRAFT_11_1_ACCEPTOR = [DASH, point("draft", "1.1-1", "your draft", "/document/{n}/edit/", "or 1.2")]
KEPT_11_1 = [DASH, point("kept", "1.1-1", "kept draft", "/document/{n}/edit/")]

# A cell the state makes meaningless, or that the table leaves to another cell.
SKIP = object()
# A cell whose `shown` the rules do not settle (`seen is None`): the path alone is asserted.
UNSETTLED = object()

Cell = tuple[Any, Any]  # (path, shown)

# The table: for `here="latest"`, each reader's path and heading on each state.
TABLE: dict[str, dict[str, Cell]] = {
    "new": {
        # No edition: a reader of canonical text does not see the document; neither does one
        # whose only step on the ladder is *view canonical*. What `shown` is then, the rules
        # do not say.
        "canonical_only": (None, UNSETTLED),
        "view_accepted": (LATEST_00, "0.0"),
        "view_pending": (LATEST_00, "0.0"),
        "edit": (LATEST_00, "0.0"),
        "accept": (LATEST_00, "0.0"),
        "approver": (LATEST_00, "0.0"),
        "administrator": (LATEST_00, "0.0"),
        "previous_canonical": (None, UNSETTLED),
    },
    "canonical": {
        "canonical_only": (None, "1.0"),
        "view_accepted": (LATEST_10, "1.0"),
        "view_pending": (LATEST_10, "1.0"),
        "edit": (LATEST_10, "1.0"),
        "accept": (LATEST_10, "1.0"),
        "approver": (LATEST_10, "1.0"),
        "administrator": (LATEST_10, "1.0"),
        "previous_canonical": (LATEST_10, "1.0"),
    },
    "accepted": {
        "canonical_only": (None, "1.0"),
        "view_accepted": (CANONICAL_THEN_11, "1.1"),
        "view_pending": (CANONICAL_THEN_11, "1.1"),
        "edit": (CANONICAL_THEN_11, "1.1"),
        "accept": (CANONICAL_THEN_11, "1.1"),
        "approver": (CANONICAL_THEN_11, "1.1"),
        "administrator": (CANONICAL_THEN_11, "1.1"),
        "previous_canonical": (LATEST_10, "1.0"),
    },
    "pending": {
        "canonical_only": (None, "1.0"),
        "view_accepted": (CANONICAL_THEN_11, "1.1"),
        "view_pending": (PENDING_TWO, "1.1-2"),
        "edit": (PENDING_TWO, "1.1-2"),
        "accept": (PENDING_TWO, "1.1-2"),
        "approver": (PENDING_TWO, "1.1-2"),
        "administrator": (PENDING_TWO, "1.1-2"),
        "previous_canonical": (LATEST_10, "1.0"),
    },
    "returned": {
        "canonical_only": (None, "1.0"),
        "view_accepted": (LATEST_10, "1.0"),
        "view_pending": (RETURNED_TWO, "1.0-2"),
        "edit": (RETURNED_TWO, "1.0-2"),
        "accept": (RETURNED_TWO, "1.0-2"),
        "approver": (RETURNED_TWO, "1.0-2"),
        "administrator": (RETURNED_TWO, "1.0-2"),
        "previous_canonical": (LATEST_10, "1.0"),
    },
    "frozen": {
        "canonical_only": (None, "1.0"),
        "view_accepted": (CANONICAL_THEN_11, "1.1"),
        "view_pending": (FROZEN_ONE, "1.1-1"),
        "edit": (FROZEN_ONE, "1.1-1"),
        "accept": (FROZEN_ONE, "1.1-1"),
        "approver": (FROZEN_ONE, "1.1-1"),
        "administrator": (FROZEN_ONE, "1.1-1"),
        "previous_canonical": (LATEST_10, "1.0"),
    },
    # Another person's hold, ordinary or reserved, draws nothing on anyone's path.
    "held_by_other": {
        "canonical_only": (None, "1.0"),
        "view_accepted": (CANONICAL_THEN_11, "1.1"),
        "view_pending": (CANONICAL_THEN_11, "1.1"),
        "edit": (CANONICAL_THEN_11, "1.1"),
        "accept": (CANONICAL_THEN_11, "1.1"),
        "approver": (CANONICAL_THEN_11, "1.1"),
        "administrator": (CANONICAL_THEN_11, "1.1"),
        "previous_canonical": (LATEST_10, "1.0"),
    },
    "reserved_by_other": {
        "canonical_only": (None, "1.0"),
        "view_accepted": (CANONICAL_THEN_11, "1.1"),
        "view_pending": (CANONICAL_THEN_11, "1.1"),
        "edit": (CANONICAL_THEN_11, "1.1"),
        "accept": (CANONICAL_THEN_11, "1.1"),
        "approver": (CANONICAL_THEN_11, "1.1"),
        "administrator": (CANONICAL_THEN_11, "1.1"),
        "previous_canonical": (LATEST_10, "1.0"),
    },
    # Only a reader who may edit can hold; each editing reader holds in turn. What the others see
    # while someone holds is the `held_by_other` row.
    "held_by_reader": {
        "canonical_only": (SKIP, SKIP),
        "view_accepted": (SKIP, SKIP),
        "view_pending": (SKIP, SKIP),
        "edit": (CANONICAL_THEN_11 + DRAFT_11_1, "1.1"),
        "accept": (CANONICAL_THEN_11 + DRAFT_11_1_ACCEPTOR, "1.1"),
        "approver": (CANONICAL_THEN_11 + DRAFT_11_1_ACCEPTOR, "1.1"),
        "administrator": (SKIP, SKIP),
        "previous_canonical": (SKIP, SKIP),
    },
    # Each editing reader's own hold force-released with an edit in its draft: the kept point to
    # them alone; the administrator, who cannot edit, sees none.
    "kept": {
        "canonical_only": (None, "1.0"),
        "view_accepted": (CANONICAL_THEN_11, "1.1"),
        "view_pending": (CANONICAL_THEN_11, "1.1"),
        "edit": (CANONICAL_THEN_11 + KEPT_11_1, "1.1"),
        "accept": (CANONICAL_THEN_11 + KEPT_11_1, "1.1"),
        "approver": (CANONICAL_THEN_11 + KEPT_11_1, "1.1"),
        "administrator": (CANONICAL_THEN_11, "1.1"),
        "previous_canonical": (LATEST_10, "1.0"),
    },
    # Archived: the administrator alone reaches it; every other reader gets nothing from
    # `readable_document` before the path is drawn, so the table asserts the administrator's frame.
    "archived": {
        "canonical_only": (SKIP, SKIP),
        "view_accepted": (SKIP, SKIP),
        "view_pending": (SKIP, SKIP),
        "edit": (SKIP, SKIP),
        "accept": (SKIP, SKIP),
        "approver": (SKIP, SKIP),
        "administrator": (CANONICAL_THEN_11, "1.1"),
        "previous_canonical": (SKIP, SKIP),
    },
}


# --- building the states through the services --------------------------------------------------


@dataclass
class Scene:
    tenant: Any
    document: Any
    users: dict[str, Any] = field(default_factory=dict)
    memberships: dict[str, Any] = field(default_factory=dict)
    other: Any = None
    # The commit of the content version `1.1` accepted, once the state has one.
    accepted_sha: str = ""

    @property
    def number(self) -> int:
        return int(self.document.number)


def _link(
    tenant: Any, document: Any, name: str, rights: list[Right], memberships: list[Any], by: Any
) -> Any:
    """Link to `document` a new group holding `rights`, with `memberships` as its members. The
    group's name is a synthetic example."""
    from access.models import AccessGroup, DocumentGroup

    with schema_context(tenant.number):
        group = AccessGroup.objects.create(
            name=f"Synthetic group of the {name} reader",
            created_by=by,
            actor_kind="user",
        )
        for right in rights:
            group.grant(right, by=by)
        for membership in memberships:
            group.add_member(membership, by=by)
        DocumentGroup.link(document, group, by=by)
    return group


def _cast(migrated_tenant: Any, member_of: Any, new_document: Any) -> Scene:
    """A document created by an author in no group, the eight readers each linked through a group
    of their own (the administrator through none), and another editor who may reserve."""
    _, author, _ = member_of("author.synthetic@example.test")
    document = new_document(author, "Synthetic approval procedure")
    scene = Scene(migrated_tenant, document)
    for name in (*READERS, "other"):
        _, user, membership = member_of(
            f"{name}.synthetic@example.test", is_tenant_admin=(name == "administrator")
        )
        if name in NAMES:
            user.display_name = NAMES[name]
            user.save(update_fields=["display_name"])
        scene.users[name] = user
        scene.memberships[name] = membership
        rights = GRANTS.get(name, [Right.EDIT, Right.RESERVE_FOR_EDITING])
        if rights:
            _link(migrated_tenant, document, name, rights, [membership], author)
    scene.other = scene.users["other"]
    return scene


def _accept(scene: Scene) -> Any:
    from review import services as review

    with schema_context(scene.tenant.number):
        return review.accept(scene.document, scene.users["accept"])


def _edition(scene: Scene) -> Any:
    """Freeze and make canonical as the approver, who accepted nothing; the edition."""
    from editions import services as editions

    with schema_context(scene.tenant.number):
        editions.freeze(scene.document, scene.users["approver"], FREEZE_REASON)
        return editions.make_canonical(scene.document, scene.users["approver"])


def _canonical(scene: Scene, commit_version: Any) -> None:
    """Edition `1.0` over the first version, accepted as `0.1`."""
    commit_version(scene.document, scene.users["edit"], FIRST, "edit")
    assert _accept(scene).number == "0.1"
    assert _edition(scene).number == "1.0"


def _accepted(scene: Scene, commit_version: Any) -> None:
    """`1.1` accepted over the second version, since edition `1.0`."""
    _canonical(scene, commit_version)
    second = commit_version(scene.document, scene.users["edit"], SECOND, "edit")
    scene.accepted_sha = second.commit_sha
    assert _accept(scene).number == "1.1"


def _take(scene: Scene, user: Any, *, take_back: bool = False) -> Any:
    from editing import holds

    with schema_context(scene.tenant.number):
        return holds.take(scene.document, user, take_back=take_back)


def _discard(scene: Scene, hold: Any, user: Any) -> None:
    from editing import services

    with schema_context(scene.tenant.number):
        services.discard(hold, user)


def _edit_draft(scene: Scene, hold: Any) -> None:
    """A sentence added to the hold's draft, as the editor's capture leaves it."""
    from editing.models import Draft

    with schema_context(scene.tenant.number):
        draft = Draft.objects.get(hold=hold)
        body = draft.content["document.md"]
        draft.content = {**draft.content, "document.md": body + "\n" + DRAFT_SENTENCE + "\n"}
        draft.save()


def _kept_for(scene: Scene, user: Any) -> None:
    """`user` takes the document, writes into the draft, and an administrator forces the hold
    free: the draft is kept for them."""
    from editing import reservations

    hold = _take(scene, user)
    _edit_draft(scene, hold)
    with schema_context(scene.tenant.number):
        assert reservations.force_release(hold, scene.users["administrator"]) is True


def _build(state: str, scene: Scene, commit_version: Any) -> None:
    from editing import reservations
    from review import services as review

    if state == "new":
        return
    if state == "canonical":
        _canonical(scene, commit_version)
        return
    if state == "returned":
        _canonical(scene, commit_version)
        commit_version(scene.document, scene.users["edit"], THIRD, "edit")
        commit_version(scene.document, scene.users["edit"], FOURTH, "edit")
        with schema_context(scene.tenant.number):
            review.return_run(scene.document, scene.users["accept"], RETURN_REASON)
        return
    _accepted(scene, commit_version)
    if state == "pending":
        commit_version(scene.document, scene.users["edit"], THIRD, "edit")
        commit_version(scene.document, scene.users["edit"], FOURTH, "edit")
    elif state == "frozen":
        from editions import services as editions

        commit_version(scene.document, scene.users["edit"], THIRD, "edit")
        with schema_context(scene.tenant.number):
            editions.freeze(scene.document, scene.users["approver"], FREEZE_REASON)
    elif state == "held_by_other":
        _take(scene, scene.other)
    elif state == "reserved_by_other":
        hold = _take(scene, scene.other)
        with schema_context(scene.tenant.number):
            reservations.reserve(hold, scene.other)
    elif state == "kept":
        for name in EDITING:
            _kept_for(scene, scene.users[name])
    elif state == "archived":
        from documents import archive

        with schema_context(scene.tenant.number):
            assert archive.archive(scene.document, scene.users["administrator"]) is True
    else:
        assert state in ("accepted", "held_by_reader"), state


# --- reading the frame ---------------------------------------------------------------------------


def _request(scene: Scene, name: str, query: dict[str, str] | None = None) -> Any:
    """A request as the middleware leaves it: `user`, `tenant`, `membership` with its user."""
    request = RequestFactory().get(
        f"/document/{scene.number}/", query or {}, headers={"host": "127.0.0.1"}
    )
    request.user = scene.users[name]
    request.tenant = scene.tenant
    membership = scene.memberships[name]
    membership.user = scene.users[name]
    request.membership = membership
    return request


def _frame(
    frame: Any, scene: Scene, name: str, query: dict[str, str] | None = None, **given: Any
) -> Any:
    with schema_context(scene.tenant.number), translation.override("en"):
        return frame(_request(scene, name, query), scene.document, **given)


def _items(result: Any) -> list[Item] | None:
    if result.path is None:
        return None
    return [(i.kind, i.key, i.number, i.caption, i.sub, i.href, i.here) for i in result.path]


def _icons(result: Any) -> list[tuple[str, str, str]]:
    return [(i.name, i.label, i.href) for i in result.icons]


def _filled(items: list[Item] | None, n: int) -> list[Item] | None:
    if items is None:
        return None
    return [(*item[:5], item[5].format(n=n), item[6]) for item in items]


def _assert_cell(result: Any, scene: Scene, name: str, cell: Cell) -> None:
    expected_path, expected_shown = cell
    n = scene.number
    assert _items(result) == _filled(expected_path, n), name
    assert _icons(result) == [(a, b, c.format(n=n)) for a, b, c in ICONS[name]], name
    if expected_shown is not UNSETTLED:
        assert result.shown == expected_shown, name
    assert result.open_window == "", name


# --- the table -----------------------------------------------------------------------------------


@pytest.mark.parametrize("state", STATES)
def test_the_path_by_reader_and_state(
    state: str, migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    """One document per state; every reader's frame on it, at `here="latest"`."""
    scene = _cast(migrated_tenant, member_of, new_document)
    _build(state, scene, commit_version)
    from documents.path import frame

    for name in READERS:
        cell = TABLE[state][name]
        if cell[0] is SKIP:
            continue
        if state == "held_by_reader":
            hold = _take(scene, scene.users[name])
            try:
                _assert_cell(_frame(frame, scene, name, here="latest"), scene, name, cell)
            finally:
                _discard(scene, hold, scene.users[name])
            continue
        _assert_cell(_frame(frame, scene, name, here="latest"), scene, name, cell)


# --- `here` ----------------------------------------------------------------------------------


def test_here_review_outlines_the_runs_arc(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    scene = _cast(migrated_tenant, member_of, new_document)
    _build("pending", scene, commit_version)
    from documents.path import frame

    for here in ("review", "run-arc"):
        result = _frame(frame, scene, "view_pending", here=here)
        assert [(i.key, i.here) for i in result.path] == [
            ("canonical", False),
            ("history-arc", False),
            ("accepted", False),
            ("run-arc", True),
            ("latest", False),
        ], here
        assert result.shown == "1.1 → 1.1-2", here


def test_here_finish_outlines_the_draft_point(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    scene = _cast(migrated_tenant, member_of, new_document)
    _build("accepted", scene, commit_version)
    _take(scene, scene.users["accept"])
    from documents.path import frame

    for here in ("finish", "draft"):
        result = _frame(frame, scene, "accept", here=here)
        assert [(i.key, i.here) for i in result.path] == [
            ("canonical", False),
            ("history-arc", False),
            ("latest", False),
            ("", False),
            ("draft", True),
        ], here
        assert result.shown == "1.1-1 — draft", here


def test_here_the_path_lacks_outlines_nothing(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    """A reader of accepted text, nothing pending, no draft: `draft`, `finish`, `review` and
    `run-arc` name items this path lacks; `history`, `info`, `export`, `end-reservation` and `""`
    name no item at all."""
    scene = _cast(migrated_tenant, member_of, new_document)
    _build("accepted", scene, commit_version)
    from documents.path import frame

    for here in (
        "draft",
        "finish",
        "review",
        "run-arc",
        "history",
        "info",
        "export",
        "end-reservation",
        "",
    ):
        result = _frame(frame, scene, "view_accepted", here=here)
        assert [i.key for i in result.path] == ["canonical", "history-arc", "latest"], here
        assert [i.here for i in result.path] == [False, False, False], here
    # The reader who has no path still gets the heading on `latest`.
    result = _frame(frame, scene, "canonical_only", here="latest")
    assert result.path is None and result.shown == "1.0"


def test_here_on_a_point_renamed_latest_outlines_the_latest_point(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    """Accepted since the edition: `accepted` was renamed `latest`, so `here="accepted"` outlines
    it and `shown` is its number; `canonical` is its own point still. Canonical as the last word:
    `canonical` was renamed, so `here="canonical"` outlines the one `latest` point."""
    scene = _cast(migrated_tenant, member_of, new_document)
    _build("accepted", scene, commit_version)
    from documents.path import frame

    result = _frame(frame, scene, "approver", here="accepted")
    assert [(i.key, i.here) for i in result.path] == [
        ("canonical", False),
        ("history-arc", False),
        ("latest", True),
    ]
    assert result.shown == "1.1"
    result = _frame(frame, scene, "approver", here="canonical")
    assert [(i.key, i.here) for i in result.path] == [
        ("canonical", True),
        ("history-arc", False),
        ("latest", False),
    ]
    assert result.shown == "1.0"


def test_here_on_the_canonical_point_renamed_latest(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    """Canonical as the last word: `canonical` was renamed, so `here="canonical"` outlines the
    one `latest` point."""
    from documents.path import frame

    scene = _cast(migrated_tenant, member_of, new_document)
    _build("canonical", scene, commit_version)
    for here in ("canonical", "latest"):
        result = _frame(frame, scene, "approver", here=here)
        assert [(i.key, i.here) for i in result.path] == [("latest", True)], here
        assert result.shown == "1.0", here
    # `accepted` on that path: no accepted point was drawn or renamed; nothing is outlined.
    result = _frame(frame, scene, "approver", here="accepted")
    assert [(i.key, i.here) for i in result.path] == [("latest", False)]


# --- `shown` ---------------------------------------------------------------------------------


def test_shown_given_is_returned_as_given(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    scene = _cast(migrated_tenant, member_of, new_document)
    _build("accepted", scene, commit_version)
    from documents.path import frame

    for here in ("latest", "history", "canonical", ""):
        result = _frame(frame, scene, "view_pending", here=here, shown="Synthetic heading")
        assert result.shown == "Synthetic heading", here
    # Given, it is returned to a reader with no path too.
    result = _frame(frame, scene, "canonical_only", here="latest", shown="Synthetic heading")
    assert result.path is None and result.shown == "Synthetic heading"


def test_shown_by_here(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    """Each row of the heading's `shown` rules, on a run of two over `1.1` since edition `1.0`
    that the reader holds: the draft's number is `1.1-3`."""
    scene = _cast(migrated_tenant, member_of, new_document)
    _build("pending", scene, commit_version)
    _take(scene, scene.users["accept"])
    from documents.path import frame

    rows = {
        "history": "",
        "info": "",
        "end-reservation": "",
        "draft": "1.1-3 — draft",
        "finish": "1.1-3 — draft",
        "kept": "1.1-3 — draft",
        "review": "1.1 → 1.1-2",
        "run-arc": "1.1 → 1.1-2",
        "history-arc": "1.0 → 1.1",
        "canonical": "1.0",
        "accepted": "1.1",
        "latest": "1.1-2",
        "export": "1.1-2",
        "": "1.1-2",
    }
    for here, expected in rows.items():
        assert _frame(frame, scene, "accept", here=here).shown == expected, here


def test_shown_on_kept(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    """`kept` reads the kept draft's number, `pending(document)`: `1.1-1` with nothing pending."""
    scene = _cast(migrated_tenant, member_of, new_document)
    _build("accepted", scene, commit_version)
    _kept_for(scene, scene.users["edit"])
    from documents.path import frame

    result = _frame(frame, scene, "edit", here="kept")
    assert result.shown == "1.1-1 — draft"
    assert [(i.key, i.here) for i in result.path] == [
        ("canonical", False),
        ("history-arc", False),
        ("latest", False),
        ("", False),
        ("kept", True),
    ]


# --- `taking` --------------------------------------------------------------------------------


def test_taking_draws_the_draft_point_to_a_person_who_does_not_hold(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    from editing import holds

    scene = _cast(migrated_tenant, member_of, new_document)
    _build("accepted", scene, commit_version)
    n = scene.number
    from documents.path import frame

    # Without `taking`, nobody holding: no draft point (the table's row, repeated as the control).
    assert _items(_frame(frame, scene, "edit", here="latest")) == _filled(CANONICAL_THEN_11, n)
    # With it: the dashed segment and the draft point, `or 1.2` only to a holder of *accept*.
    for name, segment in (("edit", DRAFT_11_1), ("accept", DRAFT_11_1_ACCEPTOR)):
        result = _frame(frame, scene, name, here="finish", taking=True)
        expected = [
            *CANONICAL_THEN_11[:2],
            point("latest", "1.1", "latest version", "/document/{n}/"),
            segment[0],
            (*segment[1][:6], True),
        ]
        assert _items(result) == _filled(expected, n), name
        assert result.shown == "1.1-1 — draft", name
        assert _acts_of(result)["draft"] == DRAFT_ACTS_TAKING, name
    # Drawing it opened no hold.
    with schema_context(migrated_tenant.number):
        assert holds.open_hold(scene.document) is None


# --- the kept point ------------------------------------------------------------------------


def test_the_kept_point_is_never_beside_a_draft_point(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    """A kept draft of the editor's: not drawn while another person holds the document, and
    replaced by the draft point once the editor takes it back."""
    scene = _cast(migrated_tenant, member_of, new_document)
    _build("accepted", scene, commit_version)
    _kept_for(scene, scene.users["edit"])
    n = scene.number
    from documents.path import frame

    assert _items(_frame(frame, scene, "edit", here="latest")) == _filled(
        CANONICAL_THEN_11 + KEPT_11_1, n
    )
    # Another person holds: the editor's kept point is not drawn, and no draft point either.
    hold = _take(scene, scene.users["accept"])
    assert _items(_frame(frame, scene, "edit", here="latest")) == _filled(CANONICAL_THEN_11, n)
    assert _items(_frame(frame, scene, "accept", here="latest")) == _filled(
        CANONICAL_THEN_11 + DRAFT_11_1_ACCEPTOR, n
    )
    _discard(scene, hold, scene.users["accept"])
    # Taken back: the draft point, and no kept point beside it.
    _take(scene, scene.users["edit"], take_back=True)
    assert _items(_frame(frame, scene, "edit", here="latest")) == _filled(
        CANONICAL_THEN_11 + DRAFT_11_1, n
    )


# --- the icons -------------------------------------------------------------------------------


def test_the_icons_by_reader(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    """Export, then History only with `has_tab` (a history right or *accept*), then Info — to
    every reader, the one with no path included."""
    scene = _cast(migrated_tenant, member_of, new_document)
    _build("canonical", scene, commit_version)
    n = scene.number
    from documents.path import frame

    expected = {
        "canonical_only": TWO_ICONS,
        "view_accepted": TWO_ICONS,
        "view_pending": TWO_ICONS,
        "edit": TWO_ICONS,
        "accept": THREE_ICONS,
        "approver": THREE_ICONS,
        "administrator": THREE_ICONS,
        "previous_canonical": THREE_ICONS,
    }
    for name, icons in expected.items():
        result = _frame(frame, scene, name, here="info")
        assert _icons(result) == [(a, b, c.format(n=n)) for a, b, c in icons], name
        assert result.shown == "", name
    assert _frame(frame, scene, "canonical_only", here="info").path is None


# --- the acts, the marks, *More* and the approve window ------------------------------------------

Act = tuple[str, str, str]  # (command, label, reason)

EDIT = ("edit", "Edit", "")
REVIEW = ("review", "Review the run", "")
FINISH = ("finish", "Finish editing", "")
# The draft point's acts to its holder with nothing edited yet: the disabled finish and the
# finish link, one hidden; release and discard, one hidden; the taker (not holding) gets the
# first two alone.
FINISH_UNEDITED = ("finish", "Finish editing", "After the first edit.")
RELEASE = ("release", "Release the document", "")
DISCARD = ("discard", "Discard my edits…", "")
# The page served for the take to come carries the holder's acts: the editor takes the hold as it
# mounts and stays on the page.
DRAFT_ACTS_TAKING = [FINISH_UNEDITED, FINISH, RELEASE, DISCARD]
DRAFT_ACTS_HOLDING = [FINISH_UNEDITED, FINISH, RELEASE, DISCARD]
# The kept point's acts: take back while the base is the head, then the kept draft's discard.
TAKE_BACK = ("take-back", "Take the document back", "")
DISCARD_DRAFT = ("discard-draft", "Discard this draft…", "")
KEPT_ACTS = [TAKE_BACK, DISCARD_DRAFT]
FREEZE = ("freeze", "Freeze", "")
UNFREEZE = ("unfreeze", "Unfreeze", "")
APPROVE_20 = ("approve", "Make canonical as 2.0…", "")
NOTHING_ACCEPTED = "Nothing new has been accepted to make canonical."
WAITING = "Changes are waiting for review; they must be accepted first."
HELD_FOR_CANONICAL = "The document is held; make it canonical once it is released."
APPROVE_10_NOTHING = ("approve", "Make canonical as 1.0…", NOTHING_ACCEPTED)
APPROVE_20_NOTHING = ("approve", "Make canonical as 2.0…", NOTHING_ACCEPTED)
APPROVE_20_WAITING = ("approve", "Make canonical as 2.0…", WAITING)
APPROVE_20_HELD = ("approve", "Make canonical as 2.0…", HELD_FOR_CANONICAL)
OTHER = NAMES["other"]
EDIT_HELD_BY_OTHER = ("edit", "Edit", f"{OTHER} is editing.")
EDIT_RESERVED_BY_OTHER = ("edit", "Edit", f"{OTHER} has reserved it.")
FREEZE_HELD_BY_OTHER = ("freeze", "Freeze", f"Held by {OTHER} — freeze once it is released")
EDIT_FROZEN = (
    "edit",
    "Edit",
    f"Frozen — “{FREEZE_REASON}” — until it is unfrozen or made canonical.",
)
GROUPS = ("groups", "Groups", "")
GROUPS_HREF = "/administration/tenant/document-links/#link-{n}"

Mark = tuple[str, str]
FROZEN = ("frozen", "frozen")
FROZEN_BY_APPROVER = ("frozen", f"frozen by {NAMES['approver']}")
HELD_BY_OTHER = ("held", f"{OTHER} is editing")
HELD_BY_SOMEONE = ("held", "someone is editing")
RESERVED_BY_OTHER = ("held", f"reserved by {OTHER}")
RESERVED = ("held", "reserved for editing")

# Who reads the holder's name: a holder of *edit* or *accept*, or an administrator.
NAMED = ("edit", "accept", "approver", "administrator")
UNNAMED = ("view_accepted", "view_pending", "previous_canonical")

# Each state: the acts by point key per reader (a point not listed carries none), the marks on
# the `latest` point per reader (none when not listed), and `more`'s reason to the
# administrator (`None` for no *More* at all). Readers not listed have no acts.
ACTS: dict[str, dict[str, dict[str, list[Act]]]] = {
    "new": {
        "edit": {"latest": [EDIT]},
        "accept": {"latest": [EDIT]},
        # The one point is the created text, nobody's acceptance, renamed `latest`: the
        # accepted point's acts hang on it, after the latest's.
        "approver": {"latest": [EDIT, APPROVE_10_NOTHING, FREEZE]},
    },
    "canonical": {
        "edit": {"latest": [EDIT]},
        "accept": {"latest": [EDIT]},
        # No accepted point: the canonical point, renamed `latest`, carries the approver's acts.
        "approver": {"latest": [EDIT, APPROVE_20_NOTHING, FREEZE]},
    },
    "accepted": {
        "edit": {"latest": [EDIT]},
        "accept": {"latest": [EDIT]},
        "approver": {"latest": [EDIT, APPROVE_20, FREEZE]},
    },
    "pending": {
        "edit": {"latest": [EDIT]},
        "accept": {"latest": [EDIT, REVIEW]},
        "approver": {"latest": [EDIT, REVIEW], "accepted": [APPROVE_20_WAITING, FREEZE]},
    },
    "returned": {
        "edit": {"latest": [EDIT]},
        "accept": {"latest": [EDIT, REVIEW]},
        # Nothing accepted since the edition: the canonical point is the approver's.
        "approver": {"latest": [EDIT, REVIEW], "canonical": [APPROVE_20_NOTHING, FREEZE]},
    },
    "frozen": {
        "edit": {"latest": [EDIT_FROZEN]},
        "accept": {"latest": [EDIT, REVIEW]},
        "approver": {"latest": [EDIT, REVIEW], "accepted": [APPROVE_20_WAITING, UNFREEZE]},
    },
    "held_by_other": {
        "edit": {"latest": [EDIT_HELD_BY_OTHER]},
        "accept": {"latest": [EDIT_HELD_BY_OTHER]},
        "approver": {"latest": [EDIT_HELD_BY_OTHER, APPROVE_20_HELD, FREEZE_HELD_BY_OTHER]},
    },
    "reserved_by_other": {
        "edit": {"latest": [EDIT_RESERVED_BY_OTHER]},
        "accept": {"latest": [EDIT_RESERVED_BY_OTHER]},
        "approver": {"latest": [EDIT_RESERVED_BY_OTHER, APPROVE_20_HELD, FREEZE_HELD_BY_OTHER]},
    },
    # No *Edit* to the holder; the draft point's acts; the approver's own hold still stops the
    # approve act and the freeze, and names them.
    "held_by_reader": {
        "edit": {"draft": DRAFT_ACTS_HOLDING},
        "accept": {"draft": DRAFT_ACTS_HOLDING},
        "approver": {
            "latest": [
                APPROVE_20_HELD,
                ("freeze", "Freeze", f"Held by {NAMES['approver']} — freeze once it is released"),
            ],
            "draft": DRAFT_ACTS_HOLDING,
        },
    },
    # A kept draft (with an edit, which is what keeps it), nobody holding: the acts of the
    # accepted state, and the kept point's own — the head unmoved, no freeze.
    "kept": {
        "edit": {"latest": [EDIT], "kept": KEPT_ACTS},
        "accept": {"latest": [EDIT], "kept": KEPT_ACTS},
        "approver": {"latest": [EDIT, APPROVE_20, FREEZE], "kept": KEPT_ACTS},
    },
    # Archived: no acts on any point.
    "archived": {},
}
MARKS: dict[str, dict[str, list[Mark]]] = {
    "frozen": {
        **{name: [FROZEN] for name in ("view_accepted", "view_pending", "edit")},
        **{name: [FROZEN_BY_APPROVER] for name in ("accept", "approver", "administrator")},
        "previous_canonical": [FROZEN_BY_APPROVER],
    },
    "held_by_other": {
        **{name: [HELD_BY_OTHER] for name in NAMED},
        **{name: [HELD_BY_SOMEONE] for name in UNNAMED},
    },
    "reserved_by_other": {
        **{name: [RESERVED_BY_OTHER] for name in NAMED},
        **{name: [RESERVED] for name in UNNAMED},
    },
}
MORE: dict[str, str] = {
    "held_by_other": f"{OTHER} is editing.",
    "reserved_by_other": f"{OTHER} has reserved it.",
}
# The cells whose approve act is enabled: the window is filled.
APPROVE_OPEN = {("accepted", "approver"), ("kept", "approver")}


def _acts_of(result: Any) -> dict[str, list[Act]]:
    """The acts of each point that carries any, by key."""
    return {
        item.key: [(a.command, a.label, a.reason) for a in item.acts]
        for item in result.path or []
        if item.acts
    }


def _marks_of(result: Any) -> dict[str, list[Mark]]:
    return {
        item.key: [(m.kind, m.text) for m in item.marks] for item in result.path or [] if item.marks
    }


def _assert_acts(result: Any, scene: Scene, state: str, name: str) -> None:
    n = scene.number
    assert _acts_of(result) == ACTS[state].get(name, {}), (state, name)
    expected_marks = MARKS.get(state, {}).get(name, [])
    expected = {"latest": expected_marks} if expected_marks else {}
    assert _marks_of(result) == expected, (state, name)
    if name == "administrator":
        assert [(a.command, a.label, a.reason) for a in result.more] == [
            ("groups", "Groups", MORE.get(state, ""))
        ], state
        assert result.more[0].href == GROUPS_HREF.format(n=n), state
    else:
        assert result.more is None, (state, name)
    if (state, name) in APPROVE_OPEN:
        assert result.windows == {
            "approve": {
                "accepted": "1.1",
                "number": "2.0",
                "frozen": False,
                "confirmed": scene.accepted_sha,
            }
        }, (state, name)
    else:
        assert result.windows == {}, (state, name)


@pytest.mark.parametrize("state", STATES)
def test_the_acts_by_reader_and_state(
    state: str, migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    """One document per state; the acts of every point, the marks, *More* and the windows of
    every reader's frame on it."""
    scene = _cast(migrated_tenant, member_of, new_document)
    _build(state, scene, commit_version)
    from documents.path import frame

    for name in READERS:
        if TABLE[state][name][0] is SKIP:
            continue
        if state == "held_by_reader":
            hold = _take(scene, scene.users[name])
            try:
                _assert_acts(_frame(frame, scene, name, here="latest"), scene, state, name)
            finally:
                _discard(scene, hold, scene.users[name])
            continue
        _assert_acts(_frame(frame, scene, name, here="latest"), scene, state, name)
    # Edit is primary unless the reader holds *accept* and a run is pending; Review is primary.
    if state in ("pending", "returned", "frozen"):
        by_command = {
            a.command: a.primary for a in _latest(_frame(frame, scene, "accept", here="latest"))
        }
        assert by_command == {"edit": False, "review": True}, state
    if state in ("accepted", "held_by_other"):
        assert [a.primary for a in _latest(_frame(frame, scene, "edit", here="latest"))] == [True]


def _latest(result: Any) -> list[Any]:
    return next(item.acts for item in result.path if item.key == "latest")


def test_the_approve_window_on_a_frozen_and_an_unfrozen_document(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    """`1.1` accepted since edition `1.0`, nothing pending: the approve act is enabled with or
    without a freeze — a freeze is not asked for — and the window says which."""
    from editions import services as editions

    scene = _cast(migrated_tenant, member_of, new_document)
    _build("accepted", scene, commit_version)
    from documents.path import frame

    window = {
        "accepted": "1.1",
        "number": "2.0",
        "frozen": False,
        "confirmed": scene.accepted_sha,
    }
    result = _frame(frame, scene, "approver", here="accepted")
    assert result.windows == {"approve": window}
    assert _acts_of(result) == {"latest": [EDIT, APPROVE_20, FREEZE]}

    with schema_context(migrated_tenant.number):
        editions.freeze(scene.document, scene.users["approver"], FREEZE_REASON)
    result = _frame(frame, scene, "approver", here="accepted")
    assert result.windows == {"approve": {**window, "frozen": True}}
    assert _acts_of(result) == {"latest": [EDIT, APPROVE_20, UNFREEZE]}
    assert _marks_of(result) == {"latest": [FROZEN_BY_APPROVER]}
    # The one who may edit but not accept: Edit disabled by the freeze, the mark unnamed.
    result = _frame(frame, scene, "edit", here="latest")
    assert _acts_of(result) == {"latest": [EDIT_FROZEN]}
    assert _marks_of(result) == {"latest": [FROZEN]}


def test_a_merged_point_carries_the_union_of_acts(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    """Nothing pending, accepted since the edition: the one `latest` point carries *Edit* (the
    latest's), then *Approve* and the toggle (the accepted point's), each with its link or form."""
    scene = _cast(migrated_tenant, member_of, new_document)
    _build("accepted", scene, commit_version)
    n = scene.number
    from documents.path import frame

    result = _frame(frame, scene, "approver", here="latest")
    assert [item.key for item in result.path if item.acts] == ["latest"]
    edit, approve, freeze = _latest(result)
    assert (edit.command, edit.href, edit.primary, edit.window) == (
        "edit",
        f"/document/{n}/edit/",
        True,
        "",
    )
    assert (approve.command, approve.action, approve.method, approve.primary, approve.window) == (
        "approve",
        f"/document/{n}/make-canonical/",
        "get",
        True,
        "approve",
    )
    assert not approve.fields
    assert (freeze.command, freeze.action, freeze.method, freeze.primary) == (
        "freeze",
        f"/document/{n}/freeze/",
        "post",
        False,
    )
    assert not freeze.fields
    assert all(not a.hidden for a in (edit, approve, freeze))


def test_edit_is_not_drawn_to_the_holder_nor_on_an_archived_document(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    from documents import archive

    scene = _cast(migrated_tenant, member_of, new_document)
    _build("accepted", scene, commit_version)
    from documents.path import frame

    # The holder: the draft point's acts alone, and no mark for their own hold.
    n = scene.number
    hold = _take(scene, scene.users["edit"])
    result = _frame(frame, scene, "edit", here="finish")
    assert _acts_of(result) == {"draft": DRAFT_ACTS_HOLDING}
    assert _marks_of(result) == {}
    unedited, finish, release, discard = _latest_draft(result)
    # Nothing edited yet: the disabled finish shows, the link is hidden; release shows, discard
    # is hidden.
    assert [(a.when, a.hidden) for a in (unedited, finish, release, discard)] == [
        ("unedited", False),
        ("edited", True),
        ("unedited", False),
        ("edited", True),
    ]
    assert (finish.href, finish.primary) == (f"/document/{n}/edit/finish/", True)
    assert (release.action, release.method, release.fields, release.window) == (
        f"/document/{n}/edit/discard/",
        "post",
        {"release": "1"},
        "",
    )
    assert (discard.action, discard.method, discard.fields, discard.window) == (
        "",
        "get",
        {"confirm": "discard"},
        "discard",
    )
    assert result.windows == {"discard": {"reserved": False}}
    # With an edit: the hidden ones swap; the windows stand.
    _edit_draft(scene, hold)
    result = _frame(frame, scene, "edit", here="finish")
    assert _acts_of(result) == {"draft": DRAFT_ACTS_HOLDING}
    assert [a.hidden for a in _latest_draft(result)] == [True, False, True, False]
    assert result.windows == {"discard": {"reserved": False}}
    # Outlined elsewhere, the draft's windows are not drawn.
    assert _frame(frame, scene, "edit", here="latest").windows == {}
    # Taking: the holder's acts for the hold the editor is about to take, and their window.
    _discard(scene, hold, scene.users["edit"])
    result = _frame(frame, scene, "edit", here="finish", taking=True)
    # Not holding, the reader is still offered Edit on the latest point.
    assert _acts_of(result) == {"latest": [EDIT], "draft": DRAFT_ACTS_TAKING}
    assert result.windows == {"discard": {"reserved": False}}

    # Archived: no acts on any point to the administrator, who alone reads it; *More* stands.
    with schema_context(migrated_tenant.number):
        assert archive.archive(scene.document, scene.users["administrator"]) is True
    result = _frame(frame, scene, "administrator", here="latest")
    assert [item.key for item in result.path] == ["canonical", "history-arc", "latest"]
    assert _acts_of(result) == {}
    assert [(a.command, a.reason) for a in result.more] == [("groups", "")]


def test_the_reservations_acts_on_the_draft_point(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    """A holder of *reserve for editing*: *Reserve for editing* while the hold is ordinary,
    *Cancel the reservation* once reserved; under a freeze, *Reserve* is disabled with the
    freeze's reason."""
    from editing import reservations
    from editions import services as editions

    scene = _cast(migrated_tenant, member_of, new_document)
    _build("accepted", scene, commit_version)
    n = scene.number
    from documents.path import frame

    hold = _take(scene, scene.other)
    result = _frame(frame, scene, "other", here="finish")
    assert _acts_of(result) == {
        "draft": [*DRAFT_ACTS_HOLDING, ("reserve", "Reserve for editing", "")]
    }
    reserve = _latest_draft(result)[4]
    assert (reserve.action, reserve.method) == (f"/document/{n}/edit/reserve/", "post")
    assert result.windows == {"discard": {"reserved": False}}

    with schema_context(migrated_tenant.number):
        reservations.reserve(hold, scene.other)
    result = _frame(frame, scene, "other", here="finish")
    assert _acts_of(result) == {
        "draft": [*DRAFT_ACTS_HOLDING, ("cancel-reservation", "Cancel the reservation", "")]
    }
    release, cancel = _latest_draft(result)[2], _latest_draft(result)[4]
    # Reserved: the release is confirmed first, since the reservation ends with it.
    assert (release.action, release.method, release.fields, release.window) == (
        "",
        "get",
        {"confirm": "release"},
        "release",
    )
    assert (cancel.action, cancel.method) == (f"/document/{n}/edit/cancel-reservation/", "post")
    assert result.windows == {"discard": {"reserved": True}, "release": {"reserved": True}}
    _discard(scene, hold, scene.other)

    # Under a freeze only a holder of *accept* may take: the reviewer, given the right to reserve.
    _link(
        migrated_tenant,
        scene.document,
        "reserving reviewer",
        [Right.RESERVE_FOR_EDITING],
        [scene.memberships["accept"]],
        scene.users["accept"],
    )
    with schema_context(migrated_tenant.number):
        editions.freeze(scene.document, scene.users["approver"], FREEZE_REASON)
    _take(scene, scene.users["accept"])
    result = _frame(frame, scene, "accept", here="finish")
    assert _acts_of(result) == {
        "draft": [
            *DRAFT_ACTS_HOLDING,
            (
                "reserve",
                "Reserve for editing",
                f"Frozen: “{FREEZE_REASON}” — reserve once it is unfrozen",
            ),
        ]
    }


def test_the_kept_points_acts_and_the_open_window(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    """The kept point: *Take the document back* while the draft's base is still the head and no
    freeze is open (or the reader holds *accept*), then *Discard this draft…*; its window when
    outlined; `open_window` from the request's `confirm` when it names a drawn window."""
    from editions import services as editions

    scene = _cast(migrated_tenant, member_of, new_document)
    _build("accepted", scene, commit_version)
    n = scene.number
    _kept_for(scene, scene.users["edit"])
    _kept_for(scene, scene.users["accept"])
    from documents.path import frame

    result = _frame(frame, scene, "edit", here="kept")
    assert _acts_of(result) == {"latest": [EDIT], "kept": KEPT_ACTS}
    take_back, discard_draft = next(i.acts for i in result.path if i.key == "kept")
    assert (take_back.action, take_back.method, take_back.primary) == (
        f"/document/{n}/edit/take-back/",
        "post",
        True,
    )
    assert (
        discard_draft.action,
        discard_draft.method,
        discard_draft.fields,
        discard_draft.window,
    ) == (
        "",
        "get",
        {"confirm": "discard-draft"},
        "discard-draft",
    )
    assert result.windows == {"discard-draft": {"kept": True}}
    assert result.open_window == ""
    assert _frame(frame, scene, "edit", here="latest").windows == {}

    # `confirm` opens a drawn window, and nothing else.
    opened = _frame(frame, scene, "edit", here="kept", query={"confirm": "discard-draft"})
    assert opened.open_window == "discard-draft"
    assert _frame(frame, scene, "edit", here="kept", query={"confirm": "discard"}).open_window == ""
    assert (
        _frame(frame, scene, "edit", here="latest", query={"confirm": "discard-draft"}).open_window
        == ""
    )

    # A freeze: no take-back for the editor, who lacks *accept*; still one for the reviewer.
    with schema_context(migrated_tenant.number):
        editions.freeze(scene.document, scene.users["approver"], FREEZE_REASON)
    assert _acts_of(_frame(frame, scene, "edit", here="kept"))["kept"] == [DISCARD_DRAFT]
    assert _acts_of(_frame(frame, scene, "accept", here="kept"))["kept"] == KEPT_ACTS
    with schema_context(migrated_tenant.number):
        editions.end_freeze(
            scene.document, "Synthetic reason: unfrozen", user=scene.users["approver"]
        )

    # The head moved on: no take-back for anyone.
    commit_version(scene.document, scene.users["approver"], THIRD, "edit")
    assert _acts_of(_frame(frame, scene, "edit", here="kept"))["kept"] == [DISCARD_DRAFT]
    assert _acts_of(_frame(frame, scene, "accept", here="kept"))["kept"] == [DISCARD_DRAFT]

    # The holder's draft window opens the same way.
    hold = _take(scene, scene.other)
    held = _frame(frame, scene, "other", here="finish", query={"confirm": "discard"})
    assert held.open_window == "discard"
    _discard(scene, hold, scene.other)


def _latest_draft(result: Any) -> list[Any]:
    return next(item.acts for item in result.path if item.key == "draft")


def test_the_marks_by_reader(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    """A freeze and, under it, a reviewer's hold: the frozen mark first, named to those with the
    history tab or administering; the held mark named to holders of *edit* or *accept* and to
    administrators; nothing on the holder's own; the hold's reason before the freeze's on
    *Edit*."""
    from editions import services as editions

    scene = _cast(migrated_tenant, member_of, new_document)
    _build("accepted", scene, commit_version)
    from documents.path import frame

    with schema_context(migrated_tenant.number):
        editions.freeze(scene.document, scene.users["approver"], FREEZE_REASON)
    _take(scene, scene.users["accept"])
    held = ("held", f"{NAMES['accept']} is editing")
    expected = {
        "view_accepted": [FROZEN, HELD_BY_SOMEONE],
        "view_pending": [FROZEN, HELD_BY_SOMEONE],
        "edit": [FROZEN, held],
        # The holder: the freeze's mark, never their own hold's.
        "accept": [FROZEN_BY_APPROVER],
        "approver": [FROZEN_BY_APPROVER, held],
        "administrator": [FROZEN_BY_APPROVER, held],
        "previous_canonical": [FROZEN_BY_APPROVER, HELD_BY_SOMEONE],
    }
    for name, marks in expected.items():
        result = _frame(frame, scene, name, here="latest")
        assert _marks_of(result) == ({"latest": marks} if marks else {}), name
    assert _frame(frame, scene, "canonical_only", here="latest").path is None
    # The hold's reason comes before the freeze's.
    result = _frame(frame, scene, "edit", here="latest")
    assert _acts_of(result) == {"latest": [("edit", "Edit", f"{NAMES['accept']} is editing.")]}
    result = _frame(frame, scene, "administrator", here="latest")
    assert [(a.command, a.reason) for a in result.more] == [
        ("groups", f"{NAMES['accept']} is editing.")
    ]
