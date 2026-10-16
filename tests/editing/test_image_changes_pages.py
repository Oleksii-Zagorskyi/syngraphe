"""The image pair on the pages that show a change to the person whose draft or document it is
(DL-0439, DL-11-002): compare between two versions; the holder's finishing screen and *my
edits*, the draft's side through the draft's route and named *your draft*; a kept draft's
changes; the stopped editor. The pending view and the notice page have their own modules' tests.
People are synthetic examples; text is invented; images are placeholders, since no image is
decoded."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from access.rights import Right
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

BODY = "A first synthetic sentence.\n"


def path(data: bytes) -> str:
    return f"images/{hashlib.sha256(data).hexdigest()}.png"


def test_compare_finish_and_my_edits_show_the_pair(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    commit_version: Any,
    link_group: Any,
    queued_authorship: list[Any],
    settings: Any,
) -> None:
    from django.utils import timezone

    from editing.models import Draft, DraftFile

    settings.LANGUAGE_CODE = "en"
    client, author, membership = member_of("the.author@example.test")
    document = new_document(author)
    link_group(document, [Right.VIEW_ALL_HISTORY, Right.EDIT], [membership], author)
    first, second, staged = b"the first image", b"the second image", b"the draft's image"
    commit_version(
        document, author, BODY + f"\n![A plan]({path(first)})\n", files={path(first): first}
    )
    commit_version(
        document,
        author,
        BODY + f"\n![A plan]({path(second)})\n",
        files={path(first): None, path(second): second},
    )
    number = document.number

    compare = client.get(f"/document/{number}/compare/?from=0.0-1&to=0.0-2").content.decode()
    assert '<div class="imgpair">' in compare
    assert f'src="/document/{number}/image/{path(first)[7:]}/"' in compare

    assert client.post(f"/document/{number}/edit/take/").status_code == 200
    with schema_context(migrated_tenant.number):
        draft = Draft.objects.get(hold__document=document, hold__released_at__isnull=True)
        draft.content = {**draft.content, "document.md": BODY + f"\n![A plan]({path(staged)})\n"}
        draft.save()
        DraftFile.objects.create(
            draft=draft,
            kind="image",
            path=path(staged),
            operation="add",
            content=staged,
            file_name="plan.png",
            sha256=hashlib.sha256(staged).hexdigest(),
            at=timezone.now(),
        )
    for page in ("edit/finish/", "my-edits/"):
        shown = client.get(f"/document/{number}/{page}").content.decode()
        assert '<div class="imgpair">' in shown, page
        assert f'src="/document/{number}/edit/image/{path(staged)[7:]}/"' in shown, page
        assert f'src="/document/{number}/edit/image/{path(second)[7:]}/"' in shown, page
        assert "before · 0.0-2 — A plan" in shown and "after · your draft — A plan" in shown, page


def test_a_stopped_editor_draws_the_pair(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    """The stopped editor's changes — its typed text against the draft — draw images from the
    draft's route."""
    from django.utils import timezone

    from editing.models import Draft, DraftFile

    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    old, new = b"the committed image", b"the typed image"
    commit_version(document, author, BODY + f"\n![A plan]({path(old)})\n", files={path(old): old})
    number = document.number
    client.post(f"/document/{number}/edit/take/")
    loaded = client.post(
        f"/document/{number}/edit/load/",
        data=json.dumps({"range": "whole"}),
        content_type="application/json",
    ).json()
    with schema_context(migrated_tenant.number):
        draft = Draft.objects.get(hold__document=document, hold__released_at__isnull=True)
        DraftFile.objects.create(
            draft=draft,
            kind="image",
            path=path(new),
            operation="add",
            content=new,
            file_name="plan.png",
            sha256=hashlib.sha256(new).hexdigest(),
            at=timezone.now(),
        )
    answer = client.post(
        f"/document/{number}/edit/changes/",
        data=json.dumps({"editor": loaded["editor"], "body": BODY + f"\n![A plan]({path(new)})\n"}),
        content_type="application/json",
    ).json()
    assert '<div class="imgpair">' in answer["html"]
    assert f'src="/document/{number}/edit/image/{path(new)[7:]}/"' in answer["html"]

    # Typed text is not normalized: the same image with its description emphasised in the source
    # is a change of formatting, never the picture struck and inserted again.
    answer = client.post(
        f"/document/{number}/edit/changes/",
        data=json.dumps(
            {"editor": loaded["editor"], "body": BODY + f"\n![*A plan*]({path(old)})\n"}
        ),
        content_type="application/json",
    ).json()
    assert "format-changed" in answer["html"]
    assert "<del>" not in answer["html"] and "<ins>" not in answer["html"]


def test_a_kept_draft_draws_the_pair(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    commit_version: Any,
    link_group: Any,
    queued_authorship: list[Any],
    settings: Any,
) -> None:
    """A draft kept after a force release, the head moved on since: its changes against the head
    draw the pair from the draft's own route — the image its base commit holds and the one it
    stages — the *before* side named by the head's number."""
    from django.utils import timezone

    from editing.models import Draft, DraftFile, Hold

    settings.LANGUAGE_CODE = "en"
    client, author, membership = member_of("the.author@example.test")
    _, other, other_membership = member_of("the.other@example.test")
    admin, _, _ = member_of("the.admin@example.test", is_tenant_admin=True)
    document = new_document(author)
    link_group(document, [Right.EDIT], [membership, other_membership], author)
    committed, staged = b"the committed image", b"the kept draft's image"
    commit_version(
        document,
        author,
        BODY + f"\n![A plan]({path(committed)})\n",
        files={path(committed): committed},
    )
    number = document.number
    assert client.post(f"/document/{number}/edit/take/").status_code == 200
    with schema_context(migrated_tenant.number):
        hold = Hold.objects.get(document=document, released_at__isnull=True)
        draft = Draft.objects.get(hold=hold)
        draft.content = {**draft.content, "document.md": BODY + f"\n![A plan]({path(staged)})\n"}
        draft.save()
        DraftFile.objects.create(
            draft=draft,
            kind="image",
            path=path(staged),
            operation="add",
            content=staged,
            file_name="plan.png",
            sha256=hashlib.sha256(staged).hexdigest(),
            at=timezone.now(),
        )
    admin.post(f"/document/{number}/edit/force-release/", {"hold": str(hold.pk)})
    commit_version(
        document, other, BODY + "Another sentence.\n\n" + f"![A plan]({path(committed)})\n"
    )

    page = client.get(f"/document/{number}/edit/").content.decode()

    assert '<div class="imgpair">' in page
    assert f'src="/document/{number}/edit/image/{path(committed)[7:]}/"' in page
    assert f'src="/document/{number}/edit/image/{path(staged)[7:]}/"' in page
    assert "before · 0.0-2 — A plan" in page
