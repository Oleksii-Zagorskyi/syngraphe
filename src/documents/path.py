"""The frame every page of a document draws: the heading's version, its icons and the path of
versions — the document's points and the arcs of edits between them, each reader seeing only what
their rights reach (DL-0518, DL-0522).

Computed once per request by the page's view and drawn by `documents/frame.html`. The path draws;
every route an act posts to decides again under its own gate and locks.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from django.http import HttpRequest
from django.utils.translation import gettext, ngettext, pgettext

from access.rights import Right, rights_on
from documents.models import Document

logger = logging.getLogger(__name__)

# The rights that reach beyond canonical text: without one of them a reader sees no path, only
# the heading, its tags and the icons (DL-0518). Every act implies *edit* or *view accepted*.
REACHING = frozenset(
    {
        Right.VIEW_ACCEPTED,
        Right.VIEW_PENDING,
        Right.EDIT,
        Right.CREATE_AND_EDIT,
        Right.VIEW_PREVIOUS_CANONICAL,
        Right.VIEW_ALL_HISTORY,
    }
)
# `here` names a page's position; two pages stand on an item of another name.
ALIASES = {"review": "run-arc", "finish": "draft"}
# The pages that read no version: the heading names none (DL-0518).
NO_VERSION = frozenset({"history", "info", "end-reservation"})


@dataclass(frozen=True)
class Icon:
    """One of the heading's icons: `name` the key of its drawing in the partial."""

    name: str
    label: str
    href: str


@dataclass(frozen=True)
class Act:
    """An act hung from a point: a link (`href`) or a form (`action`, `method`, `fields`); `reason`
    why it is disabled, `""` when it is not."""

    label: str
    command: str
    href: str = ""
    action: str = ""
    method: str = "post"
    fields: dict[str, str] = field(default_factory=dict)
    reason: str = ""
    primary: bool = False
    window: str = ""
    hidden: bool = False


@dataclass(frozen=True)
class Item:
    """A point — a version — or an arc of edits between two. The draft's dashed segment is an arc
    with no key and no link."""

    kind: str
    key: str
    number: str
    caption: str
    sub: str
    href: str
    here: bool = False
    marks: list[str] = field(default_factory=list)
    acts: list[Act] = field(default_factory=list)


@dataclass(frozen=True)
class Frame:
    """What a document's page draws above its body. `path` is `None` for a reader of canonical
    text alone; `more` the administrator's acts, `None` for anyone else."""

    shown: str
    icons: list[Icon]
    path: list[Item] | None
    more: list[Act] | None = None
    windows: dict[str, dict[str, Any]] = field(default_factory=dict)
    open_window: str = ""


def frame(
    request: HttpRequest,
    document: Document,
    *,
    here: str,
    shown: str | None = None,
    appendix: int | None = None,
    taking: bool = False,
) -> Frame:
    """The frame of `document`'s page at position `here` for the request's reader. `shown` the
    heading's version where the page knows it better than the path; `taking` when the page is
    served to a person whose editor takes the hold as it mounts (DL-0325), so the draft point is
    drawn for them. A record that cannot be read costs the path and the version, never the page."""
    from rendering.views import UNREADABLE

    user = request.user
    rights = rights_on(user, document)
    icons = _icons(document, rights)
    try:
        path, numbers = _path(document, user, rights, here=here, taking=taking)
    except UNREADABLE:
        logger.exception(
            "a document's version could not be read", extra={"document": document.number}
        )
        return Frame(shown=shown or "", icons=icons, path=None)
    return Frame(
        shown=shown if shown is not None else _shown(here, numbers),
        icons=icons,
        path=path,
    )


def _icons(document: Document, rights: frozenset[Right]) -> list[Icon]:
    from review.history import has_tab

    base = f"/document/{document.number}/"
    icons = [Icon("export", gettext("Export"), f"{base}export/")]
    if has_tab(rights):
        icons.append(Icon("history", gettext("History"), f"{base}history/"))
    icons.append(Icon("info", gettext("Info"), f"{base}info/"))
    return icons


def _point(key: str, number: str, caption: str, sub: str = "") -> dict[str, str]:
    # `origin` keeps the point's first name when it becomes the latest: the history arc still
    # joins the canonical version to the latest accepted one.
    return {"key": key, "origin": key, "number": number, "caption": caption, "sub": sub}


def _path(
    document: Document, user: Any, rights: frozenset[Right], *, here: str, taking: bool
) -> tuple[list[Item] | None, dict[str, str]]:
    """The path and the numbers the heading may name: `latest`, each point's by its key, the
    draft's, and each arc's ends."""
    from documents.holds import held_by
    from editing import holds, numbering
    from editions.visible import visible

    seen = visible(user, document)
    if seen is None:
        return None, {}
    numbers: dict[str, str] = {"latest": seen.number}
    if not rights & REACHING:
        return None, numbers
    base = f"/document/{document.number}/"
    pending = seen.stance == "pending"
    run_start, _, run_length = seen.number.partition("-")

    points: list[dict[str, str]] = []
    if seen.canonical is not None:
        points.append(
            _point(
                "canonical", seen.canonical, pgettext("a point of the path", "canonical version")
            )
        )
    if Right.VIEW_ACCEPTED in rights:
        accepted = numbering.accepted(document)
        if seen.canonical is None or accepted != seen.canonical:
            # The created text before any acceptance is nobody's acceptance: its number alone.
            caption = (
                ""
                if accepted == numbering.BEFORE_ANY_ACCEPTANCE
                else pgettext("a point of the path", "latest accepted")
            )
            points.append(_point("accepted", accepted, caption))
    returned = False
    # A page standing on a point that became the latest finds it under its new name.
    renamed: dict[str, str] = {}
    if pending:
        from review.state import returned as run_returned

        returned = run_returned(document)
        sub = gettext("returned") if returned else gettext("awaiting review")
        points.append(
            _point("latest", seen.number, pgettext("a point of the path", "latest version"), sub)
        )
    else:
        # The latest the reader sees is one of the points above; it takes the latest's name, so
        # two points never name one version (DL-0518).
        for point in points:
            if point["number"] == seen.number:
                renamed[point["key"]] = "latest"
                numbers[point["key"]] = seen.number
                point.update(
                    _point("latest", seen.number, pgettext("a point of the path", "latest version"))
                    | {"origin": point["origin"]}
                )

    items: list[Item] = []
    by_origin = {point["origin"]: point for point in points}
    for point in points:
        key = point["key"]
        if point["origin"] == "accepted" and "canonical" in by_origin:
            items.append(
                Item(
                    "arc",
                    "history-arc",
                    "",
                    pgettext("an arc of the path", "edits between versions"),
                    "",
                    f"{base}compare/?from={by_origin['canonical']['number']}&to={point['number']}",
                )
            )
        if key == "latest" and pending:
            sub = (
                gettext("returned")
                if returned
                else ngettext("%(count)s version", "%(count)s versions", int(run_length))
                % {"count": run_length}
            )
            items.append(
                Item(
                    "arc",
                    "run-arc",
                    "",
                    pgettext("an arc of the path", "edits between versions"),
                    sub,
                    f"{base}pending/",
                )
            )
        href = base if key == "latest" else f"{base}version/{point['number']}/"
        items.append(Item("point", key, point["number"], point["caption"], point["sub"], href))
        numbers[key] = point["number"]
    if "canonical" in by_origin and "accepted" in by_origin:
        numbers["history-arc"] = (
            f"{by_origin['canonical']['number']} → {by_origin['accepted']['number']}"
        )
    if pending:
        numbers["run-arc"] = f"{run_start} → {seen.number}"

    # The draft point is its holder's while they may still edit: a hold outliving a withdrawn
    # *edit* would draw a pending number and a link that answers not-found.
    own = Right.EDIT in rights and (held_by(document, user) or taking)
    kept = (
        not own
        and Right.EDIT in rights
        and holds.open_hold(document) is None
        and holds.preserved_draft(document, user) is not None
    )
    if own or kept:
        number = numbering.pending(document)
        numbers["draft"] = number
        items.append(Item("arc", "", "", "", "", ""))
        if own:
            sub = (
                pgettext("the draft's other number", "or %(number)s")
                % {"number": numbering.next_accepted(document)}
                if Right.ACCEPT in rights
                else ""
            )
            items.append(
                Item(
                    "point",
                    "draft",
                    number,
                    pgettext("a point of the path", "your draft"),
                    sub,
                    f"{base}edit/",
                )
            )
        else:
            items.append(
                Item(
                    "point",
                    "kept",
                    number,
                    pgettext("a point of the path", "kept draft"),
                    "",
                    f"{base}edit/",
                )
            )

    target = renamed.get(ALIASES.get(here, here), ALIASES.get(here, here))
    if target:
        items = [_outlined(item) if item.key == target else item for item in items]
    return items, numbers


def _outlined(item: Item) -> Item:
    return Item(item.kind, item.key, item.number, item.caption, item.sub, item.href, True)


def _shown(here: str, numbers: dict[str, str]) -> str:
    """The heading's version for a page at `here`, when the page does not name it."""
    if here in NO_VERSION:
        return ""
    if here in ("draft", "finish", "kept"):
        number = numbers.get("draft", "")
        return gettext("%(number)s — draft") % {"number": number} if number else ""
    if here in ("review", "run-arc"):
        # With nothing pending the review page stands over the latest version.
        return numbers.get("run-arc", numbers.get("latest", ""))
    if here in ("history-arc", "canonical", "accepted"):
        return numbers.get(here, "")
    return numbers.get("latest", "")
