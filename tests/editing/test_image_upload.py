"""An image uploaded into the holder's draft (DL-0232, DL-0439, DL-11-001): staged once per
content, audited each time, refused to anyone but the holder's open editor and once the hold has
ended; and the draft's images served to the person whose draft it is, from its rows or the commit
it was taken from. Images are invented by Pillow; people are synthetic examples."""

from __future__ import annotations

import hashlib
import json
import threading
from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

BODY = "The first synthetic sentence.\n"


def upload(client: Any, document: Any, data: bytes, name: str = "plan.png", **more: str) -> Any:
    from django.core.files.uploadedfile import SimpleUploadedFile

    return client.post(
        f"/document/{document.number}/edit/image/",
        {"file": SimpleUploadedFile(name, data), **more},
    )


def held(member_of: Any, new_document: Any, link_group: Any) -> tuple[Any, Any, Any, Any]:
    """A document its author holds, with an editor open; another member holding *edit*."""
    from access.rights import Right

    client, author, membership = member_of("the.author@example.test")
    other_client, _, other_membership = member_of("the.other@example.test")
    document = new_document(author)
    link_group(document, [Right.EDIT], [membership, other_membership], author)
    assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
    loaded = client.post(
        f"/document/{document.number}/edit/load/",
        data=json.dumps({"range": "whole"}),
        content_type="application/json",
    ).json()
    return client, other_client, document, loaded["editor"]


def test_upload_stages_one_file(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, invented_image: Any
) -> None:
    from audit.models import AuditEvent
    from editing.models import DraftFile

    client, _, document, editor = held(member_of, new_document, link_group)
    data = invented_image("png")

    first = upload(client, document, data, "Site plan.png", editor=editor)
    second = upload(client, document, data, "Site plan.png", editor=editor)

    assert first.status_code == second.status_code == 200
    answer = first.json()
    assert answer["alt"] == "Site plan"
    assert answer["src"].startswith("images/") and answer["src"].endswith(".png")
    with schema_context(migrated_tenant.number):
        [row] = DraftFile.objects.filter(draft__hold__document=document)
        assert (row.kind, row.operation, row.path) == ("image", "add", answer["src"])
        assert hashlib.sha256(bytes(row.content)).hexdigest() == answer["src"][7:71] == row.sha256
    events = AuditEvent.objects.filter(action="image.uploaded")
    assert events.count() == 2
    assert events.first().after == {
        "number": document.number,
        "path": answer["src"],
        "bytes": len(bytes(row.content)),
    }


def test_upload_refusals(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    invented_image: Any,
    monkeypatch: pytest.MonkeyPatch,
    settings: Any,
) -> None:
    """A member who does not hold the document reaches nothing; a refused file names its rule; the
    holder's upload after a force release is told the hold has ended, as a capture is; one that
    waits on a commit answers busy. Nothing is staged by any of them."""
    from documents.locks import document_lock
    from editing.models import DraftFile, Hold
    from editing.views import capture

    settings.LANGUAGE_CODE = "en"
    client, other_client, document, editor = held(member_of, new_document, link_group)
    data = invented_image("png")

    assert upload(other_client, document, data, editor=editor).status_code == 404
    # The holder's upload names an open editor of the hold, as a capture does.
    assert upload(client, document, data).status_code == 404
    svg = b"<svg xmlns='http://www.w3.org/2000/svg'/>"
    refused = upload(client, document, svg, "a.svg", editor=editor)
    assert refused.status_code == 400
    assert refused.json() == {"refused": "Only PNG, JPEG and GIF images are accepted."}

    monkeypatch.setattr(capture, "CAPTURE_LOCK_SECONDS", 0.2)
    taken, done = threading.Event(), threading.Event()

    def commit() -> None:
        with document_lock(migrated_tenant.number, document.number):
            taken.set()
            done.wait(10)

    committing = threading.Thread(target=commit)
    committing.start()
    taken.wait(10)
    try:
        busy = upload(client, document, data, editor=editor)
    finally:
        done.set()
        committing.join()
    assert busy.status_code == 503 and busy.json() == {"busy": True}

    admin_client, _, _ = member_of("the.admin@example.test", is_tenant_admin=True)
    with schema_context(migrated_tenant.number):
        hold = Hold.objects.get(document=document, released_at__isnull=True)
    forced = admin_client.post(
        f"/document/{document.number}/edit/force-release/", {"hold": str(hold.pk)}
    )
    assert forced.status_code == 302
    closed = upload(client, document, data, editor=editor)
    assert closed.status_code == 409
    assert closed.json() == {"closed": True, "released": "forced"}
    assert upload(client, document, data).status_code == 404
    with schema_context(migrated_tenant.number):
        assert not DraftFile.objects.filter(draft__hold__document=document).exists()


def test_the_draft_image_is_the_holders(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, invented_image: Any
) -> None:
    client, other_client, document, editor = held(member_of, new_document, link_group)
    src = upload(client, document, invented_image("png"), editor=editor).json()["src"]
    address = f"/document/{document.number}/edit/{src.replace('images/', 'image/')}/"

    assert other_client.get(address).status_code == 404
    shown = client.get(address)
    assert shown.status_code == 200
    assert shown["Content-Type"] == "image/png"
    assert shown["X-Content-Type-Options"] == "nosniff"
    assert "private" in shown["Cache-Control"].split(", ")
    assert client.get(address.replace(".png/", ".gif/")).status_code == 404
    assert client.get(f"/document/{document.number}/edit/image/plan.png/").status_code == 404


def test_a_kept_draft_shows_its_base_images(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    invented_image: Any,
    queued_authorship: list[Any],
) -> None:
    """A's draft, kept after a force release, references X in its body and Y in its appendix,
    both committed; B removes both and commits. A — *edit*, no history right — still sees X and Y
    from the commit the draft was taken from; nothing else, and nothing once the right is gone or
    the document is archived."""
    from access.models import DocumentGroup
    from access.rights import Right
    from documents.models import Document, DocumentState
    from editing import services
    from editing.models import Draft, Hold

    a_client, a, a_membership = member_of("the.author@example.test")
    b_client, b, b_membership = member_of("the.other@example.test")
    admin_client, _, _ = member_of("the.admin@example.test", is_tenant_admin=True)
    owner_client, owner, _ = member_of("the.owner@example.test")
    document = new_document(owner)
    a_group = link_group(document, [Right.EDIT], [a_membership], owner)
    link_group(document, [Right.EDIT], [b_membership], owner)
    x, y, other = (invented_image("png", shade=n) for n in (1, 2, 3))

    def name(data: bytes) -> str:
        return f"{hashlib.sha256(data).hexdigest()}.png"

    commit_version(
        document,
        owner,
        BODY + f"\n![Old]({'images/' + name(other)})\n",
        files={"images/" + name(other): other},
    )
    commit_version(
        document,
        owner,
        BODY + f"\n![X](images/{name(x)})\n",
        files={
            "images/" + name(other): None,
            "images/" + name(x): x,
            "images/" + name(y): y,
            "appendices/1.md": f"# Synthetic appendix\n\n![Y](images/{name(y)})\n",
        },
        appendices=[{"number": 1, "title": "Synthetic appendix"}],
    )
    assert a_client.post(f"/document/{document.number}/edit/take/").status_code == 200
    with schema_context(migrated_tenant.number):
        hold = Hold.objects.get(document=document, released_at__isnull=True)
    admin_client.post(f"/document/{document.number}/edit/force-release/", {"hold": str(hold.pk)})

    assert b_client.post(f"/document/{document.number}/edit/take/").status_code == 200
    with schema_context(migrated_tenant.number):
        b_hold = Hold.objects.get(document=document, released_at__isnull=True)
        b_draft = Draft.objects.get(hold=b_hold)
        b_draft.content = {
            **b_draft.content,
            "document.md": BODY,
            "appendices/1.md": "# Synthetic appendix\n\nNothing.\n",
        }
        b_draft.save()
        services.commit_draft(b_hold, b, "Both images removed")

    def address(data: bytes) -> str:
        return f"/document/{document.number}/edit/image/{name(data)}/"

    assert a_client.get(address(x)).content == x
    assert a_client.get(address(y)).content == y
    assert a_client.get(address(other)).status_code == 404

    with schema_context(migrated_tenant.number):
        DocumentGroup.objects.filter(document=document, group=a_group).delete()
    assert a_client.get(address(x)).status_code == 404
    with schema_context(migrated_tenant.number):
        DocumentGroup.link(document, a_group, by=owner)
    assert a_client.get(address(x)).status_code == 200
    with schema_context(migrated_tenant.number):
        Document.objects.filter(pk=document.pk).update(state=DocumentState.ARCHIVED)
    assert a_client.get(address(x)).status_code == 404


def test_a_closed_editor_uploads_nothing(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, invented_image: Any
) -> None:
    """An editor closed on the server — a stale tab — is told so, as its capture would be, and
    stages nothing in the draft the person holds now."""
    from editing.models import DraftFile

    client, _, document, editor = held(member_of, new_document, link_group)
    client.post(
        f"/document/{document.number}/edit/close/",
        data=json.dumps({"editor": editor}),
        content_type="application/json",
    )

    answer = upload(client, document, invented_image("png"), editor=editor)

    assert answer.status_code == 409 and answer.json() == {"closed": True}
    with schema_context(migrated_tenant.number):
        assert not DraftFile.objects.filter(draft__hold__document=document).exists()


def test_a_base_image_shows_while_its_paragraph_is_cut(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    commit_version: Any,
    invented_image: Any,
) -> None:
    """The images of the commit a draft was taken from stay visible to its holder while the
    draft no longer shows them — a paragraph cut, to be pasted back — and nothing older does."""
    from editing.models import Draft

    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    x, older = invented_image("png", shade=4), invented_image("png", shade=5)
    x_name = f"{hashlib.sha256(x).hexdigest()}.png"
    older_name = f"{hashlib.sha256(older).hexdigest()}.png"
    commit_version(document, author, BODY, files={f"images/{older_name}": older})
    commit_version(
        document,
        author,
        BODY + f"\n![X](images/{x_name})\n",
        files={f"images/{older_name}": None, f"images/{x_name}": x},
    )
    assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
    with schema_context(migrated_tenant.number):
        draft = Draft.objects.get(hold__document=document, hold__released_at__isnull=True)
        draft.content = {**draft.content, "document.md": BODY}
        draft.save()

    assert client.get(f"/document/{document.number}/edit/image/{x_name}/").content == x
    assert client.get(f"/document/{document.number}/edit/image/{older_name}/").status_code == 404
