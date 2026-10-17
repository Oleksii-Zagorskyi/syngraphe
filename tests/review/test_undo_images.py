"""An undo brings back the images its reversal shows (DL-0439): every image the draft's texts
reference that the head no longer holds is staged from the versions it undoes or the text they
started from, and the reviewer's finish commits it; an image only an earlier version holds is not.
People are synthetic examples; texts are invented; images are placeholders, since the commit reads
no image's content."""

from __future__ import annotations

import hashlib
from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

BASE = "# General provisions\n\nAn application is made in writing.\n"


def path(data: bytes) -> str:
    return f"images/{hashlib.sha256(data).hexdigest()}.png"


def with_image(data: bytes) -> str:
    return BASE + f"\n![A synthetic plan]({path(data)})\n"


def test_an_undo_stages_the_images_it_restores(
    migrated_tenant: Any, cast: Any, commit_version: Any, queued_authorship: list[Any]
) -> None:
    from documents import gitstore
    from editing import holds
    from editing.models import Draft, DraftFile, Hold
    from review import services, undo

    people = cast(editors=("a", "b"), reviewers=("r",))
    document = people.document
    a_image, b_image, old_image = b"author A's image", b"author B's image", b"an appendix image"
    heading = "# Synthetic appendix\n\n"
    appendix = f"{heading}An appendix sentence.\n\n![An older plan]({path(old_image)})\n"
    commit_version(
        document,
        people["a"],
        BASE,
        "edit",
        files={path(old_image): old_image, "appendices/1.md": appendix.encode()},
        appendices=[{"number": 1, "title": "Synthetic appendix"}],
    )
    with schema_context(migrated_tenant.number):
        services.accept(document, people["r"])
    commit_version(
        document, people["a"], with_image(a_image), "edit", files={path(a_image): a_image}
    )
    # B replaces A's image and removes the appendix's: undoing B brings both texts back.
    commit_version(
        document,
        people["b"],
        with_image(b_image),
        "edit",
        files={
            path(a_image): None,
            path(b_image): b_image,
            path(old_image): None,
            "appendices/1.md": f"{heading}An appendix sentence.\n".encode(),
        },
    )

    with schema_context(migrated_tenant.number):
        hold = holds.take(document, people["r"])
        draft = Draft.objects.get(hold=hold)
        # The appendix text as an undo of B would restore it; undoing an appendix is a later
        # part's, which hands its text to the draft as this does.
        draft.content = {**draft.content, "appendices/1.md": appendix}
        draft.save()
        hold = undo.apply(document, people["r"], author=people["b"])
        staged = set(
            DraftFile.objects.filter(draft__hold=hold, kind="image").values_list("path", flat=True)
        )
        assert staged == {path(a_image), path(old_image)}

        services.accept_as(Hold.objects.get(pk=hold.pk), people["r"], "Synthetic undo")
        repo = gitstore.open_repository(migrated_tenant.number, document.number)
        head = gitstore.head(repo)
        committed = {f"images/{name}" for name in gitstore.listing(repo, "images", head)}
    assert committed == {path(a_image), path(old_image)}


def test_an_undo_stages_no_image_beyond_what_it_undoes(
    migrated_tenant: Any, cast: Any, commit_version: Any, queued_authorship: list[Any]
) -> None:
    """A reference the reviewer typed to an image only an earlier, accepted version holds is not
    staged by an undo: the undo reads only the versions it undoes and the text they started from,
    so it never shows a reviewer what their rights do not."""
    from editing import holds
    from editing.models import Draft, DraftFile
    from review import services, undo

    people = cast(editors=("a", "b"), reviewers=("r",))
    document = people.document
    earlier = b"an image of an earlier version"
    commit_version(
        document, people["a"], with_image(earlier), "edit", files={path(earlier): earlier}
    )
    commit_version(
        document, people["a"], BASE, "edit", summary="Removed", files={path(earlier): None}
    )
    with schema_context(migrated_tenant.number):
        services.accept(document, people["r"])
    commit_version(document, people["b"], BASE + "\nA paragraph of author B.\n", "edit")

    with schema_context(migrated_tenant.number):
        hold = holds.take(document, people["r"])
        draft = Draft.objects.get(hold=hold)
        body = draft.content["document.md"] + f"\n![Typed]({path(earlier)})\n"
        draft.content = {**draft.content, "document.md": body}
        draft.save()
        hold = undo.apply(document, people["r"], author=people["b"])
        assert not DraftFile.objects.filter(draft__hold=hold, kind="image").exists()
