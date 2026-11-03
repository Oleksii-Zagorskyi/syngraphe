"""The frame every page of a document draws: the heading's version, its icons and the path of
versions — the document's points and the arcs of edits between them, each reader seeing only what
their rights reach (DL-0518, DL-0522).

Computed once per request by the page's view and drawn by `documents/frame.html`. The path draws;
every route an act posts to decides again under its own gate and locks.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from typing import Any

from django.http import HttpRequest
from django.utils.translation import gettext, ngettext, pgettext

from access.rights import Right, rights_on
from documents.models import Document, DocumentState

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
# `frame()`'s `seen` when the view did not read it.
UNREAD: Any = object()


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
    # The explanation behind the act's *?*, where it has one.
    hint: str = ""


@dataclass(frozen=True)
class Mark:
    """A hold or a freeze, in words under the latest version: `kind` is `held` or `frozen`."""

    kind: str
    text: str


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
    marks: list[Mark] = field(default_factory=list)
    acts: list[Act] = field(default_factory=list)
    # A point's first name — `canonical`, `accepted` — when it became the latest.
    origin: str = ""


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
    # What follows the document's title in the heading: an appendix's own title.
    subtitle: str = ""


def frame(
    request: HttpRequest,
    document: Document,
    *,
    here: str,
    shown: str | None = None,
    appendix: int | None = None,
    taking: bool = False,
    rights: frozenset[Right] | None = None,
    seen: Any = UNREAD,
    at: str | None = None,
    pair: tuple[str, str] | None = None,
    subtitle: str = "",
) -> Frame:
    """The frame of `document`'s page at position `here` for the request's reader. `shown` the
    heading's version where the page knows it better than the path; `taking` when the page is
    served to a person whose editor takes the hold as it mounts (DL-0325), so the draft point is
    drawn for them; `rights` and `seen` (`editions.visible.visible`) where the view read them
    already. A page of one version passes `at`, its number, and stands on the point that names
    it, if any; a comparison passes `pair`, and stands on the arc that is that pair, if any.
    `appendix`, an appendix's number, draws the document's path for that appendix's pages
    (DL-0522): its points open the appendix at their version, and *Edit* its editor.
    A record that cannot be read costs the path and the version, never the page."""
    from access.views import administers
    from editions.visible import visible
    from rendering.views import UNREADABLE

    user = request.user
    rights = rights if rights is not None else rights_on(user, document)
    icons = _icons(document, rights)
    if at is not None:
        # A version's page exports that version.
        export = f"/document/{document.number}/version/{at}/export/"
        icons = [replace(i, href=export) if i.name == "export" else i for i in icons]
    administrator = administers(request)
    try:
        seen = visible(user, document) if seen is UNREAD else seen
        path, numbers = _path(
            document, user, rights, seen, here=here, taking=taking, at=at, pair=pair
        )
        situation = _Situation.of(document, user, rights, administrator)
        windows: dict[str, dict[str, Any]] = {}
        if path is not None and appendix is not None:
            path = _in_appendix(document, path, appendix)
        if path is not None and document.state == DocumentState.ACTIVE:
            path = _with_acts(
                document, user, rights, seen, path, situation, windows, appendix=appendix
            )
        # An appendix's page offers no document act (DL-0207).
        more = _more(document, situation) if administrator and appendix is None else None
    except UNREADABLE:
        logger.exception(
            "a document's version could not be read", extra={"document": document.number}
        )
        return Frame(shown=shown or "", icons=icons, path=None, subtitle=subtitle)
    return Frame(
        shown=shown if shown is not None else _shown(here, numbers),
        icons=icons,
        path=path,
        more=more,
        windows=windows,
        subtitle=subtitle,
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
    document: Document,
    user: Any,
    rights: frozenset[Right],
    seen: Any,
    *,
    here: str,
    taking: bool,
    at: str | None = None,
    pair: tuple[str, str] | None = None,
) -> tuple[list[Item] | None, dict[str, str]]:
    """The path and the numbers the heading may name: `latest`, each point's by its key, the
    draft's, and each arc's ends."""
    from documents.holds import held_by
    from editing import holds, numbering

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
        items.append(
            Item(
                "point",
                key,
                point["number"],
                point["caption"],
                point["sub"],
                href,
                origin=point["origin"],
            )
        )
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
    if at is not None:
        # A version's own page stands on the point that names it, or on none.
        target = next((i.key for i in items if i.kind == "point" and i.number == at), "")
    if pair is not None:
        # A comparison stands on the arc that is its pair, or on none.
        shown_pair = f"{pair[0]} → {pair[1]}"
        target = next(
            (key for key in ("history-arc", "run-arc") if numbers.get(key) == shown_pair), ""
        )
        numbers["pair"] = shown_pair
    if target:
        items = [_outlined(item) if item.key == target else item for item in items]
    return items, numbers


def _outlined(item: Item) -> Item:
    return replace(item, here=True)


def _in_appendix(document: Document, path: list[Item], part: int) -> list[Item]:
    """The path's points opening appendix `part` at their version (DL-0522): the latest at the
    appendix's address, a past version at its historical appendix page, the draft at the
    appendix's editor; a version that does not list the appendix drawn without a link. The arcs
    keep the document's comparison."""
    from documents.models import PartIndex, PartKind
    from editing import numbering

    base = f"/document/{document.number}/"
    history = numbering.history(document)
    shas = {
        item.number: history.aliases.get(item.number)
        for item in path
        if item.kind == "point" and item.key not in ("draft", "kept")
    }
    listing = set(
        PartIndex.objects.filter(
            version__document=document,
            version__commit_sha__in=[sha for sha in shas.values() if sha],
            kind=PartKind.APPENDIX,
            part_number=part,
        ).values_list("version__commit_sha", flat=True)
    )
    out = []
    for item in path:
        if item.kind != "point":
            out.append(item)
        elif item.key == "latest":
            # A draft's own appendix has no page until a version lists it.
            listed = shas.get(item.number) in listing
            out.append(replace(item, href=f"{base}appendix/{part}/" if listed else ""))
        elif item.key == "draft":
            out.append(replace(item, href=f"{base}appendix/{part}/edit/"))
        elif item.key == "kept":
            out.append(item)
        else:
            listed = shas.get(item.number) in listing
            href = f"{base}version/{item.number}/appendix/{part}/" if listed else ""
            out.append(replace(item, href=href))
    return out


@dataclass(frozen=True)
class _Situation:
    """What the acts and marks are decided from, read once: the open hold, the open freeze, and
    whether this reader learns who holds the document (DL-0516)."""

    hold: Any
    freeze: Any
    named: bool
    administrator: bool

    @classmethod
    def of(
        cls, document: Document, user: Any, rights: frozenset[Right], administrator: bool
    ) -> _Situation:
        from editing.holds import open_hold
        from editions.models import open_freeze
        from review.state import NAMED_ON_A_HOLD

        return cls(
            hold=open_hold(document),
            freeze=open_freeze(document),
            named=administrator or bool(rights & NAMED_ON_A_HOLD),
            administrator=administrator,
        )

    def held_by_another(self, user: Any) -> bool:
        return self.hold is not None and self.hold.user_id != getattr(user, "pk", None)

    def held_reason(self, *, named: bool) -> str:
        """Why an act waits while someone holds the document: the holder named or the fact."""
        from identity.naming import person
        from review.state import reserved_since

        hold = self.hold
        if hold.reserved_at is None:
            if named:
                return pgettext("the reason beside a disabled act", "%(name)s is editing.") % {
                    "name": person(hold.user)
                }
            return gettext("This document is held: someone is editing it.")
        if named:
            return pgettext("the reason beside a disabled act", "%(name)s has reserved it.") % {
                "name": person(hold.user)
            }
        return gettext("Reserved for editing since %(date)s.") % {
            "date": reserved_since(hold.reserved_at)
        }

    def frozen_reason(self, *, for_editing: bool) -> str:
        """Why editing or reserving waits while the document is frozen, with its reason."""
        reason = self.freeze.reason
        if for_editing:
            if reason:
                return gettext(
                    "Frozen — “%(reason)s” — until it is unfrozen or made canonical."
                ) % {"reason": reason}
            return gettext("Frozen — until it is unfrozen or made canonical.")
        if reason:
            return gettext("Frozen: “%(reason)s” — reserve once it is unfrozen") % {
                "reason": reason
            }
        return gettext("Frozen — reserve once it is unfrozen")


def _with_acts(
    document: Document,
    user: Any,
    rights: frozenset[Right],
    seen: Any,
    path: list[Item],
    situation: _Situation,
    windows: dict[str, dict[str, Any]],
    *,
    appendix: int | None = None,
) -> list[Item]:
    """Each point with its acts, and the marks under the latest (DL-0518, DL-0233): the latest
    carries *Edit* and *Review the run*; the latest accepted — the canonical point while nothing
    was accepted since it — *Make canonical as N.0…* and the freeze toggle; a point that is both
    carries both; the draft, its holder's acts."""
    pending = seen.stance == "pending"
    accepted_origin = "accepted" if any(item.origin == "accepted" for item in path) else "canonical"
    out = []
    for item in path:
        acts: list[Act] = []
        marks: list[Mark] = []
        if item.kind == "point" and item.key == "latest":
            acts += _latest_acts(document, user, rights, pending, situation, appendix=appendix)
            marks = _marks(rights, situation, user)
        # An appendix's page carries *Edit* and the draft's acts alone (DL-0207, DL-0522).
        if item.kind == "point" and item.origin == accepted_origin and appendix is None:
            # The window's two repository reads are paid only where its act is drawn.
            acts += _accepted_acts(
                document, user, rights, seen, situation, windows if item.here else None
            )
        if item.kind == "point" and item.key == "draft":
            acts += _draft_acts(document, user, rights, situation)
        out.append(replace(item, acts=acts, marks=marks) if acts or marks else item)
    return out


def _latest_acts(
    document: Document,
    user: Any,
    rights: frozenset[Right],
    pending: bool,
    situation: _Situation,
    *,
    appendix: int | None = None,
) -> list[Act]:
    base = f"/document/{document.number}/"
    editor = f"{base}appendix/{appendix}/edit/" if appendix is not None else f"{base}edit/"
    acts = []
    own = situation.hold is not None and not situation.held_by_another(user)
    if Right.EDIT in rights and not own:
        reason = ""
        if situation.held_by_another(user):
            reason = situation.held_reason(named=situation.named)
        elif situation.freeze is not None and Right.ACCEPT not in rights:
            reason = situation.frozen_reason(for_editing=True)
        acts.append(
            Act(
                pgettext("the act on the latest version", "Edit"),
                "edit",
                href=editor,
                reason=reason,
                primary=not (Right.ACCEPT in rights and pending),
            )
        )
    # The review page opens while someone else holds the document and disables its own acts
    # (DL-0522), so this act is never disabled.
    if Right.ACCEPT in rights and pending and appendix is None:
        acts.append(Act(gettext("Review the run"), "review", href=f"{base}pending/", primary=True))
    return acts


def _accepted_acts(
    document: Document,
    user: Any,
    rights: frozenset[Right],
    seen: Any,
    situation: _Situation,
    windows: dict[str, dict[str, Any]] | None,
) -> list[Act]:
    from editions.services import canonical_refusal, edition_number_agrees
    from editions.views import canonical_reason
    from identity.naming import person
    from rendering.views import UNREADABLE

    base = f"/document/{document.number}/"
    acts = []
    if Right.MAKE_CANONICAL in rights:
        major = int(seen.canonical.split(".")[0]) if seen.canonical else 0
        incomplete = gettext(
            "The document's record is incomplete; it cannot be changed until it is repaired."
        )
        try:
            refused = canonical_refusal(document, user)
            reason = canonical_reason(refused) if refused else ""
            # A stopped approval, or a tag in the way: the window would name an edition that
            # cannot be made, as the confirmation page refuses to.
            if refused is None and not edition_number_agrees(document):
                refused, reason = "incomplete", incomplete
        except UNREADABLE:
            logger.exception(
                "a document's record could not be read", extra={"document": document.number}
            )
            refused, reason = "unreadable", incomplete
        acts.append(
            Act(
                gettext("Make canonical as %(number)s…") % {"number": f"{major + 1}.0"},
                "approve",
                action=f"{base}make-canonical/",
                method="get",
                reason=reason,
                primary=True,
                window="approve",
            )
        )
        if refused is None and windows is not None:
            windows["approve"] = _approval(document, situation)
    if Right.FREEZE in rights:
        held = situation.hold is not None
        if situation.freeze is None:
            reason = ""
            if held:
                reason = (
                    gettext("Held by %(name)s — freeze once it is released")
                    % {"name": person(situation.hold.user)}
                    if situation.named
                    else gettext("Held — freeze once it is released")
                )
            acts.append(Act(gettext("Freeze"), "freeze", action=f"{base}freeze/", reason=reason))
        else:
            reason = (
                gettext("The document is held; unfreeze it once it is released.") if held else ""
            )
            acts.append(
                Act(gettext("Unfreeze"), "unfreeze", action=f"{base}unfreeze/", reason=reason)
            )
    return acts


def _approval(document: Document, situation: _Situation) -> dict[str, Any]:
    """What the approval's window names, as its confirmation page does
    (`editions.views._confirmation`): the version, the edition it becomes, whether a freeze
    ends, and the commit the act checks."""
    from documents import gitstore
    from editing.holds import tenant_number
    from editions.services import canonical_target, next_edition
    from review.services import passport_at

    target = canonical_target(document)
    assert target is not None
    repo = gitstore.open_repository(tenant_number(), document.number)
    head = gitstore.head(repo)
    return {
        "accepted": target[1],
        "number": next_edition(passport_at(repo, head) if head else []),
        "frozen": situation.freeze is not None,
        "confirmed": target[0].commit_sha,
    }


def _draft_acts(
    document: Document, user: Any, rights: frozenset[Right], situation: _Situation
) -> list[Act]:
    base = f"/document/{document.number}/"
    acts = [
        Act(gettext("Finish editing"), "finish", href=f"{base}edit/finish/", primary=True),
    ]
    if Right.RESERVE_FOR_EDITING in rights:
        if situation.hold is not None and situation.hold.reserved_at is not None:
            acts.append(
                Act(
                    gettext("Cancel the reservation"),
                    "cancel-reservation",
                    action=f"{base}edit/cancel-reservation/",
                )
            )
        else:
            reason = (
                situation.frozen_reason(for_editing=False) if situation.freeze is not None else ""
            )
            acts.append(
                Act(
                    gettext("Reserve for editing"),
                    "reserve",
                    action=f"{base}edit/reserve/",
                    reason=reason,
                    hint=gettext(
                        "Until the reservation ends, review, freezing and changes to the "
                        "document's groups wait."
                    ),
                )
            )
    return acts


def _marks(rights: frozenset[Right], situation: _Situation, user: Any) -> list[Mark]:
    """The freeze and someone else's hold, under the latest version: who froze it to holders of a
    history right and administrators (DL-0236); who holds it to those DL-0516 names."""
    from identity.naming import person
    from review.history import has_tab

    marks = []
    if situation.freeze is not None:
        if has_tab(rights) or situation.administrator:
            text = gettext("frozen by %(name)s") % {"name": person(situation.freeze.frozen_by)}
        else:
            text = gettext("frozen")
        marks.append(Mark("frozen", text))
    if situation.held_by_another(user):
        hold, ctx = situation.hold, "the mark under the latest version"
        if hold.reserved_at is None:
            text = (
                pgettext(ctx, "%(name)s is editing") % {"name": person(hold.user)}
                if situation.named
                else pgettext(ctx, "someone is editing")
            )
        else:
            text = (
                pgettext(ctx, "reserved by %(name)s") % {"name": person(hold.user)}
                if situation.named
                else pgettext(ctx, "reserved for editing")
            )
        marks.append(Mark("held", text))
    return marks


def _more(document: Document, situation: _Situation) -> list[Act]:
    """*More* (⋯), the administrator's acts (DL-0522): *Groups* here, locked with the holder's name
    while the document is held or reserved; archiving and the hold's acts are their own tags'."""
    reason = situation.held_reason(named=True) if situation.hold is not None else ""
    return [
        Act(
            gettext("Groups"),
            "groups",
            href=f"/administration/tenant/document-links/#link-{document.number}",
            reason=reason,
        )
    ]


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
    if "pair" in numbers:
        return numbers["pair"]
    if here in ("history-arc", "canonical", "accepted"):
        return numbers.get(here, "")
    return numbers.get("latest", "")
