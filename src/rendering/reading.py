"""The context a page renders a document's text for: who reads it, and so which documents its
mentions link to and which images are shown from which address. The surfaces that render text
for a person build their context here.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

from documents import gitstore, images
from rendering.renderer import RenderContext

if TYPE_CHECKING:
    from rendering.mentions import Mention


def context(
    user: Any,
    document: Any,
    *bodies: str,
    images: Callable[[str], str] | None,
    sides: tuple[str, str] = ("", ""),
    found: Sequence[Mention] | None = None,
) -> RenderContext:
    """The reader's context for `bodies` of `document`: the documents its mentions name that
    `user` may follow, images shown from `images`, a change's sides named by `sides`. `found`,
    where the page has read them, are the bodies' mentions."""
    from rendering import mentions

    if found is None:
        found = mentions.targets(*bodies)
    numbers = {mention.number for mention in found}
    return RenderContext(reachable=mentions.reachable(user, numbers), image_url=images, sides=sides)


def committed_images(document: Any) -> Callable[[str], str]:
    """Each image's address on the committed route, which follows its reader's ceiling."""
    number = document.number
    return lambda src: f"/document/{number}/image/{src.removeprefix(images.FOLDER + '/')}/"


def notice_images(notification: Any) -> Callable[[str], str]:
    """Each image's address on the correction notice's own route, which serves its recipient the
    images of the notice's passages alone."""
    base = f"/notifications/{notification.pk}/image/"
    return lambda src: f"{base}{src.removeprefix(images.FOLDER + '/')}/"


def draft_images(document: Any, draft: Any, repo: Any = None) -> Callable[[str], str]:
    """Each image the draft's route serves to the draft's owner — staged in it, or held by the
    commit it was taken from — on that route; any other, an older version's in a comparison, on
    the committed route."""
    from editing.holds import tenant_number
    from editing.models import DraftFileKind

    if repo is None:
        repo = gitstore.open_repository(tenant_number(), document.number)
    number = document.number
    served = set(
        draft.files.filter(kind=DraftFileKind.IMAGE, content__isnull=False).values_list(
            "path", flat=True
        )
    )
    served.update(
        f"{images.FOLDER}/{name}"
        for name in gitstore.listing(repo, images.FOLDER, draft.base_commit)
    )
    committed = committed_images(document)

    def address(src: str) -> str:
        if src in served:
            return f"/document/{number}/edit/image/{src.removeprefix(images.FOLDER + '/')}/"
        return committed(src)

    return address
