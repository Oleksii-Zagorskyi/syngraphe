"""Images in the reading view, the historical page and the edit tab's drawn text, and the committed
image route (DL-0439): an image is shown where its reader's ceiling reaches a version holding it,
and nowhere else. Images are invented by Pillow; people and titles are synthetic examples."""

from __future__ import annotations

import re
from typing import Any

import pytest

from access.rights import Right
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]


def test_images_show_in_the_view(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    kit: Any,
    pictures: Any,
) -> None:
    people = edition_cast()
    plan = pictures.make(1)
    pictures.canonical_with(
        migrated_tenant.number,
        people,
        commit_version,
        kit.FIRST + plan.paragraph,
        {plan.path: plan.data},
    )
    client, _ = kit.reader(
        member_of, link_group, people, [Right.VIEW_CANONICAL, Right.VIEW_ALL_HISTORY], "reader"
    )
    number = people.document.number
    image = f'<img src="/document/{number}/image/{plan.name}/" alt="A synthetic plan 1">'

    for address in (f"/document/{number}/", f"/document/{number}/version/0.1/"):
        page = client.get(address).content.decode()
        assert image in page, address
        # An image paragraph carries no clause number.
        assert not re.search(r'<p><span class="num">[^<]*</span> <img', page), address


def test_the_image_route_follows_the_ceiling(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    kit: Any,
    pictures: Any,
) -> None:
    people = edition_cast()
    pictures.canonical_with(migrated_tenant.number, people, commit_version, kit.FIRST, {})
    later = pictures.make(2)
    commit_version(
        people.document,
        people["a"],
        kit.FIRST + later.paragraph,
        "edit",
        files={later.path: later.data},
    )
    canonical_reader, _ = kit.reader(member_of, link_group, people, [Right.VIEW_CANONICAL], "canon")
    pending_reader, _ = kit.reader(member_of, link_group, people, [Right.VIEW_PENDING], "pending")
    stranger, _, _ = member_of("stranger.synthetic@example.test")
    number = people.document.number
    address = f"/document/{number}/image/{later.name}/"

    assert canonical_reader.get(address).status_code == 404
    shown = pending_reader.get(address)
    assert shown.status_code == 200 and shown.content == later.data
    assert shown["Content-Type"] == "image/png"
    assert shown["X-Content-Type-Options"] == "nosniff"
    assert "private" in shown["Cache-Control"].split(", ")
    assert stranger.get(address).status_code == 404
    assert pending_reader.get(f"/document/{number}/image/{later.name.upper()}/").status_code == 404
    for name in ("plan.png", later.name.replace(".png", ".svg")):
        assert pending_reader.get(f"/document/{number}/image/{name}/").status_code == 404
    assert pending_reader.post(address).status_code == 404


def test_the_image_route_answers_nothing_when_the_reader_may_not_read(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    kit: Any,
    pictures: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A right lost, the document archived, or a record that does not read: *nothing to show
    here*, as every page answers them."""
    from access.models import DocumentGroup
    from documents.models import Document, DocumentState, Version

    people = edition_cast()
    plan = pictures.make(5)
    pictures.canonical_with(
        migrated_tenant.number,
        people,
        commit_version,
        kit.FIRST + plan.paragraph,
        {plan.path: plan.data},
    )
    client, _, membership = member_of("reader.synthetic@example.test")
    group = link_group(people.document, [Right.VIEW_CANONICAL], [membership], people["a"])
    address = f"/document/{people.document.number}/image/{plan.name}/"
    assert client.get(address).status_code == 200

    from review import services

    def unreadable(*_: Any, **__: Any) -> Any:
        raise Version.DoesNotExist("a record that does not read")

    with monkeypatch.context() as patched:
        patched.setattr(services, "base", unreadable)
        assert client.get(address).status_code == 404
    with schema_context(migrated_tenant.number):
        DocumentGroup.objects.filter(document=people.document, group=group).delete()
    assert client.get(address).status_code == 404
    with schema_context(migrated_tenant.number):
        DocumentGroup.link(people.document, group, by=people["a"])
    assert client.get(address).status_code == 200
    with schema_context(migrated_tenant.number):
        Document.objects.filter(pk=people.document.pk).update(state=DocumentState.ARCHIVED)
    assert client.get(address).status_code == 404


def test_the_drawn_text_shows_images_from_its_own_route(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any, pictures: Any
) -> None:
    """The edit tab draws the head's text through the committed route before any hold, and the
    holder's draft through the draft's route."""
    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    plan = pictures.make(3)
    commit_version(
        document, author, "A synthetic sentence.\n" + plan.paragraph, files={plan.path: plan.data}
    )
    number = document.number

    before = client.get(f"/document/{number}/edit/").content.decode()
    assert f'<img src="/document/{number}/image/{plan.name}/"' in before

    assert client.post(f"/document/{number}/edit/take/").status_code == 200
    with schema_context(migrated_tenant.number):
        held = client.get(f"/document/{number}/edit/").content.decode()
    assert f'<img src="/document/{number}/edit/image/{plan.name}/"' in held


def test_a_reader_of_canonical_text_alone_reaches_no_notice_image(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    pictures: Any,
    kit: Any,
) -> None:
    """A notice's images are its passages', which only a reader of accepted text is shown: once
    the recipient holds *view canonical* alone, the notice opens without them and its route
    serves none."""
    from access.models import DocumentGroup
    from editions import services as editions
    from notifications.models import Notification
    from review import services as review

    people = edition_cast()
    old, new = pictures.make(9), pictures.make(10)
    commit_version(
        people.document, people["a"], kit.FIRST + old.paragraph, "edit", files={old.path: old.data}
    )
    commit_version(
        people.document,
        people["r"],
        kit.FIRST + new.paragraph,
        "reviewer_edit",
        files={old.path: None, new.path: new.data},
    )
    with schema_context(migrated_tenant.number):
        review.accept(people.document, people["r"])
        editions.freeze(people.document, people["p"], "Synthetic reason")
        editions.make_canonical(people.document, people["p"])
        notification = Notification.objects.get(user=people["a"], event="correction_notice")
    author = people.clients["a"]
    address = f"/notifications/{notification.pk}/image/{old.name}/"
    assert author.get(address).status_code == 200

    with schema_context(migrated_tenant.number):
        DocumentGroup.objects.filter(
            document=people.document, group=people.groups["editors"]
        ).delete()
    link_group(people.document, [Right.VIEW_CANONICAL], [people.memberships["a"]], people["p"])

    assert author.get(address).status_code == 404
    page = author.get(f"/notifications/{notification.pk}/").content.decode()
    assert "<img" not in page
