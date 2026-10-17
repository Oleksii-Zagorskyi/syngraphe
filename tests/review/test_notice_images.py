"""A correction notice's images (DL-0439): the notice page shows its recipient the images of its
own passages through the notice's route — the author's before and the accepted after, an image
that never reached an edition included — whatever their history right; nothing else, nobody
else, nothing once they may not read the document or it is archived. People are synthetic
examples; text is invented; images are placeholders, since no image is decoded."""

from __future__ import annotations

import hashlib
from typing import Any

import pytest
from django.test import Client

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

BODY = "# General provisions\n\nA request for approval is made in writing.\n"


def path(data: bytes) -> str:
    return f"images/{hashlib.sha256(data).hexdigest()}.png"


def signed_in(tenant: Any, user: Any) -> Client:
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(user)
    session = client.session
    session["tenant_number"] = tenant.number
    session.save()
    return client


def test_a_notice_shows_its_own_images(
    migrated_tenant: Any, cast: Any, commit_version: Any, member_of: Any
) -> None:
    from access.models import DocumentGroup
    from access.rights import Right
    from documents.models import Document, DocumentState
    from notifications.models import Notification
    from review import services

    x, y, other = b"author A's image", b"the reviewer's image", b"an image of no passage"
    people = cast(editors=("a",), reviewers=("r",))
    commit_version(people.document, people["a"], BODY, "edit", files={path(other): other})
    commit_version(
        people.document,
        people["a"],
        BODY + f"\n![The author's plan]({path(x)})\n",
        "edit",
        files={path(x): x, path(other): None},
    )
    commit_version(
        people.document,
        people["r"],
        BODY + f"\n![The reviewer's plan]({path(y)})\n",
        "reviewer_edit",
        files={path(x): None, path(y): y},
    )
    with schema_context(migrated_tenant.number):
        services.accept(people.document, people["r"])
        notification = Notification.objects.get(user=people["a"], event="correction_notice")
        # The author keeps *view accepted* alone: no history right, no pending text.
        group = people.groups["editors"]
        group.revoke(Right.EDIT, by=people["r"])
        group.grant(Right.VIEW_ACCEPTED, by=people["r"])
    author = signed_in(migrated_tenant, people["a"])

    def address(data: bytes) -> str:
        return f"/notifications/{notification.pk}/image/{path(data)[7:]}/"

    # The ordinary route keeps the author's ceiling: the image that never reached an edition is
    # not theirs to read there.
    committed = f"/document/{people.document.number}/image/{path(x)[7:]}/"
    assert author.get(committed).status_code == 404

    # The route reads, and only reads: opening the notice is what marks it read.
    assert author.get(address(x)).content == x
    assert author.post(address(x)).status_code == 404
    with schema_context(migrated_tenant.number):
        notification.refresh_from_db()
        assert notification.read_at is None

    page = author.get(f"/notifications/{notification.pk}/").content.decode()
    assert f'src="{address(x)}"' in page and f'src="{address(y)}"' in page
    assert '<div class="imgpair">' in page
    assert author.get(address(x)).content == x
    assert author.get(address(y)).content == y
    assert author.get(address(other)).status_code == 404
    assert signed_in(migrated_tenant, people["r"]).get(address(x)).status_code == 404

    with schema_context(migrated_tenant.number):
        DocumentGroup.objects.filter(document=people.document, group=group).delete()
    assert author.get(address(x)).status_code == 404
    with schema_context(migrated_tenant.number):
        DocumentGroup.link(people.document, group, by=people["r"])
    assert author.get(address(x)).status_code == 200
    with schema_context(migrated_tenant.number):
        Document.objects.filter(pk=people.document.pk).update(state=DocumentState.ARCHIVED)
    assert author.get(address(x)).status_code == 404
