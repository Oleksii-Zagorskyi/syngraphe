"""The context a page renders a document's text for: who reads it, and so which images are shown
from which address. The surfaces that render text for a person build their context here.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from documents import gitstore, images
from rendering.renderer import RenderContext


def context(
    user: Any,
    document: Any,
    *bodies: str,
    images: Callable[[str], str] | None,
    sides: tuple[str, str] = ("", ""),
) -> RenderContext:
    """The reader's context for `bodies` of `document`: images shown from `images`, a change's
    sides named by `sides`."""
    return RenderContext(image_url=images, sides=sides)


def committed_images(document: Any) -> Callable[[str], str]:
    """Each image's address on the committed route, which follows its reader's ceiling."""
    number = document.number
    return lambda src: f"/document/{number}/image/{src.removeprefix(images.FOLDER + '/')}/"


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
