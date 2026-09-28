"""The rights vocabulary and what each right includes (ADR-0007, ADR-0016, DL-0234).

Stored rows hold what was granted; every check and every page uses `implied()`.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum

from django.utils.translation import gettext_lazy as _


class Right(StrEnum):
    VIEW_CANONICAL = "view_canonical"
    VIEW_ACCEPTED = "view_accepted"
    VIEW_PENDING = "view_pending"
    EDIT = "edit"
    CREATE_AND_EDIT = "create_and_edit"
    VIEW_PREVIOUS_CANONICAL = "view_previous_canonical"
    VIEW_ALL_HISTORY = "view_all_history"
    ACCEPT = "accept"
    FREEZE = "freeze"
    MAKE_CANONICAL = "make_canonical"
    RESERVE_FOR_EDITING = "reserve_for_editing"
    CREATE_APPENDIX = "create_appendix"
    DELETE_APPENDIX = "delete_appendix"
    UPLOAD_ATTACHMENT = "upload_attachment"
    REPLACE_ATTACHMENT = "replace_attachment"
    DELETE_ATTACHMENT = "delete_attachment"


# The viewing ladder: each step includes those below it.
LADDER = (
    Right.VIEW_CANONICAL,
    Right.VIEW_ACCEPTED,
    Right.VIEW_PENDING,
    Right.EDIT,
    Right.CREATE_AND_EDIT,
)
# History: never beyond what the ladder reaches; neither includes the other.
HISTORY = (Right.VIEW_PREVIOUS_CANONICAL, Right.VIEW_ALL_HISTORY)
# Acts: three include `edit`; *make canonical* includes `view accepted` alone.
ACTS = (Right.ACCEPT, Right.FREEZE, Right.MAKE_CANONICAL, Right.RESERVE_FOR_EDITING)
EDITING_ACTS = frozenset({Right.ACCEPT, Right.FREEZE, Right.RESERVE_FOR_EDITING})
# Parts: usable only where the group can edit.
PARTS = (
    Right.CREATE_APPENDIX,
    Right.DELETE_APPENDIX,
    Right.UPLOAD_ATTACHMENT,
    Right.REPLACE_ATTACHMENT,
    Right.DELETE_ATTACHMENT,
)
# The columns of the groups page, in this order.
GRID = LADDER + HISTORY + ACTS + PARTS

LABELS = {
    Right.VIEW_CANONICAL: _("view canonical"),
    Right.VIEW_ACCEPTED: _("view accepted"),
    Right.VIEW_PENDING: _("view pending"),
    Right.EDIT: _("edit"),
    Right.CREATE_AND_EDIT: _("create and edit"),
    Right.VIEW_PREVIOUS_CANONICAL: _("view previous canonical versions"),
    Right.VIEW_ALL_HISTORY: _("view all history"),
    Right.ACCEPT: _("accept"),
    Right.FREEZE: _("freeze"),
    Right.MAKE_CANONICAL: _("make canonical"),
    Right.RESERVE_FOR_EDITING: _("reserve for editing"),
    Right.CREATE_APPENDIX: _("create appendix"),
    Right.DELETE_APPENDIX: _("delete appendix"),
    Right.UPLOAD_ATTACHMENT: _("upload attachment"),
    Right.REPLACE_ATTACHMENT: _("replace attachment"),
    Right.DELETE_ATTACHMENT: _("delete attachment"),
}


def implied(rights: Iterable[Right]) -> frozenset[Right]:
    """The rights a group effectively holds, given the rights it was granted."""
    result = set(rights)
    if result & EDITING_ACTS:
        result.add(Right.EDIT)
    if Right.MAKE_CANONICAL in result:
        result.add(Right.VIEW_ACCEPTED)
    steps = [LADDER.index(r) for r in result if r in LADDER]
    if steps:
        result.update(LADDER[: max(steps) + 1])
    if Right.EDIT not in result:
        result.difference_update(PARTS)
    return frozenset(result)
