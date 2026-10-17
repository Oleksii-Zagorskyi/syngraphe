"""The folder tree's width, kept per person within its bounds (DL-0195).

People are synthetic examples."""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]


def test_the_tree_width_is_kept_within_its_bounds(migrated_tenant: Any, member_of: Any) -> None:
    client, _, _ = member_of("a.member@example.test")

    kept = client.post("/preferences/folder-tree-width/", {"width": "300"})
    drawn = client.get("/folder/1/").content.decode()
    beyond = client.post("/preferences/folder-tree-width/", {"width": "900"})
    fetched = client.get("/preferences/folder-tree-width/")

    assert kept.status_code == 204
    assert "--tree-width: 300px" in drawn
    assert beyond.status_code == 404
    assert fetched.status_code == 404
    assert "--tree-width: 300px" in client.get("/folder/1/").content.decode()
