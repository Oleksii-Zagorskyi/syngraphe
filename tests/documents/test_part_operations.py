"""The operations on a document's parts between two states (ADR-0005): one per change of each part,
by number, then one reorder per list. Titles and file names are synthetic examples."""

from __future__ import annotations

from typing import Any


def attachment(
    number: int, title: str, sha: str = "a" * 64, name: str = "form.txt"
) -> dict[str, Any]:
    return {"number": number, "title": title, "file_name": name, "sha256": sha, "bytes": 3}


def test_operations_between_two_states() -> None:
    from documents.parts import PartOperation, part_operations

    older = (
        [{"number": 1, "title": "Kept (example)"}, {"number": 2, "title": "Old name (example)"}],
        [
            attachment(1, "Untouched (example)"),
            attachment(2, "Replaced (example)"),
            attachment(3, "Removed (example)"),
            attachment(4, "Both (example)"),
        ],
    )
    newer = (
        [
            {"number": 2, "title": "New name (example)"},
            {"number": 1, "title": "Kept (example)"},
            {"number": 5, "title": "Added (example)"},
        ],
        [
            attachment(1, "Untouched (example)"),
            attachment(2, "Replaced (example)", sha="b" * 64),
            attachment(4, "Both, renamed (example)", name="form-2.txt"),
            attachment(6, "Uploaded (example)"),
        ],
    )

    found = [(o.kind, o.number, o.change) for o in part_operations(older, newer)]

    assert found == [
        ("appendix", 2, "renamed"),
        ("appendix", 5, "added"),
        ("appendix", None, "reordered"),
        ("attachment", 2, "replaced"),
        ("attachment", 3, "removed"),
        ("attachment", 4, "replaced"),
        ("attachment", 4, "renamed"),
        ("attachment", 6, "added"),
    ]
    removed = part_operations(older, newer)[4]
    assert removed == PartOperation("attachment", 3, "removed", older[1][2], None)


def test_nothing_changed_is_no_operation() -> None:
    from documents.parts import part_operations

    lists = ([{"number": 1, "title": "One (example)"}], [attachment(1, "One (example)")])
    assert part_operations(lists, lists) == []
