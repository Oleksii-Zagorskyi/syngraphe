"""The `ENTITY` and `IMAGE` rows mirror the tree: rebuilt from the head's `entities.yaml` and from
`images/` when a version is derived, and by the reconciler's replay once the rows are gone.
Invented English; people are synthetic examples; image bytes are placeholders."""

from __future__ import annotations

import hashlib
from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

BODY = "The first synthetic sentence.\n"


def name(data: bytes) -> str:
    return f"images/{hashlib.sha256(data).hexdigest()}.png"


def test_entities_and_images_mirror_the_tree(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    commit_version: Any,
    queued_authorship: list[Any],
) -> None:
    from documents import entities
    from documents.models import Entity, Image, Version

    _, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    one, two, three = b"image one", b"image two", b"image three"
    declared = entities.dump(
        [
            entities.Declared("role", "approver", "the approver"),
            entities.Declared("term", "record", "the record"),
        ]
    )
    first = commit_version(
        document,
        author,
        BODY + f"\n![One]({name(one)})\n\n![Two]({name(two)})\n",
        files={name(one): one, name(two): two, "entities.yaml": declared.encode()},
    )
    second = commit_version(
        document,
        author,
        BODY + f"\n![One]({name(one)})\n\n![Three]({name(three)})\n",
        files={
            name(two): None,
            name(three): three,
            "entities.yaml": entities.dump(
                [entities.Declared("role", "approver", "the approving officer")]
            ).encode(),
        },
    )

    def rows() -> tuple[list[tuple[str, str, str]], list[tuple[str, Any, Any, int]]]:
        with schema_context(migrated_tenant.number):
            return (
                [(e.kind, e.key, e.label) for e in Entity.objects.filter(document=document)],
                sorted(
                    (i.path, i.uploaded_by_id, i.uploaded_at, i.bytes)
                    for i in Image.objects.filter(document=document)
                ),
            )

    expected_entities = [("role", "approver", "the approving officer")]
    expected_images = sorted(
        [
            (name(one), author.pk, first.committed_at, len(one)),
            (name(two), author.pk, first.committed_at, len(two)),
            (name(three), author.pk, second.committed_at, len(three)),
        ]
    )
    found_entities, found_images = rows()
    assert sorted(found_entities) == expected_entities
    assert found_images == expected_images

    from documents import reconcile

    with schema_context(migrated_tenant.number):
        Entity.objects.filter(document=document).delete()
        Image.objects.filter(document=document).delete()
        Version.objects.filter(pk__in=[first.pk, second.pk]).delete()
    reconcile.run(tenant=migrated_tenant.number, repair=True)

    found_entities, found_images = rows()
    assert sorted(found_entities) == expected_entities
    assert found_images == expected_images


def test_an_unreadable_entities_file_leaves_the_rows(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    commit_version: Any,
    queued_authorship: list[Any],
) -> None:
    """A head whose `entities.yaml` is not text is still derived; its entity rows are left as the
    version before it set them."""
    from documents import entities
    from documents.models import Entity, Version

    _, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    declared = entities.dump([entities.Declared("role", "approver", "the approver")])
    commit_version(document, author, BODY, files={"entities.yaml": declared.encode()})
    broken = commit_version(
        document, author, BODY + "A second sentence.\n", files={"entities.yaml": b"\xff"}
    )

    with schema_context(migrated_tenant.number):
        assert Version.objects.filter(pk=broken.pk).exists()
        assert [(e.kind, e.key) for e in Entity.objects.filter(document=document)] == [
            ("role", "approver")
        ]
