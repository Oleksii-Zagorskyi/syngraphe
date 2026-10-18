"""The title page in a draft (DL-0463, DL-0476): the switch and the document's own text, two keys
of the frontmatter the holder changes as draft changes, staged through the frontmatter's
registry, listed among the run's changes for the reviewer, and committed with the run."""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext as _

from documents import bundle
from editing.parts import FrontmatterKind, register_frontmatter_kind


def _switched(older: Any, newer: Any) -> str:
    return _("Title page switched on") if newer else _("Title page switched off")


def _written(older: Any, newer: Any) -> str:
    if not newer:
        return _("Title page text removed")
    # The whole new text, its line breaks drawn as slashes so the list stays one line each.
    return _("Title page text: %(text)s") % {"text": " / ".join(str(newer).split("\n"))}


def _valid_text(value: Any) -> bool:
    return isinstance(value, str) and bundle.valid_title_page_text(value)


TITLE_PAGE = FrontmatterKind(
    "title_page", valid=lambda value: isinstance(value, bool), describe=_switched, absent=False
)
TITLE_PAGE_TEXT = FrontmatterKind(
    "title_page_text", valid=_valid_text, describe=_written, absent=""
)


def register() -> None:
    """Admit both keys to drafts; run once a process, from the app's `ready`."""
    register_frontmatter_kind(TITLE_PAGE)
    register_frontmatter_kind(TITLE_PAGE_TEXT)


def state(document: Any, hold: Any) -> dict[str, Any]:
    """The switch and the text as the holder's draft has them, or the head's before a hold."""
    from documents import gitstore
    from editing import holds
    from editing.models import Draft

    draft = Draft.objects.filter(hold=hold).first() if hold is not None else None
    if draft is not None:
        frontmatter = draft.content.get(holds.FRONTMATTER, {})
        return {
            "title_page": bool(frontmatter.get("title_page", False)),
            "text": str(frontmatter.get("title_page_text", "")),
        }
    repo = gitstore.open_repository(holds.tenant_number(), document.number)
    head = gitstore.head(repo)
    if head is None:
        return {"title_page": False, "text": ""}
    current = bundle.parse(gitstore.read(repo, holds.BODY, head).decode("utf-8"))[0]
    return {"title_page": current.title_page, "text": current.title_page_text}
