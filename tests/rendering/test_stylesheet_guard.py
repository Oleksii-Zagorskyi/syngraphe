"""The platform's sheet after the organisation's (T-23, DL-0360, DL-0477): whatever an
organisation's rules reach — an ancestor's selector, inheritance — the approval line keeps its
look and its words whole.

People, texts and stylesheets are synthetic examples."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from access.rights import Right
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

HOSTILE = (
    ".title-page p { color: #fefefe; font-size: 6pt; margin-left: 50mm }\n"
    "div p { letter-spacing: 0.5em }\n"
    ".callout span { background-color: #ffffff }\n"
    # What is painted behind the line, not only its own colour.
    ".title-page { background-color: #000 }\n"
    "body { background-color: #000 }\n"
    # The insertion mark's own background, as the colour of the words it marks.
    "p { color: #dff0d8 }\n"
)


def test_the_approval_line_and_the_marks_hold(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
    monkeypatch: Any,
) -> None:
    from rendering.export import pdf
    from rendering.models import Stylesheet
    from rendering.stylesheet import check

    assert check(HOSTILE) == []
    with schema_context(migrated_tenant.number):
        Stylesheet.objects.update(text=HOSTILE)
    people = edition_cast()
    kit.switched(migrated_tenant.number, people, title_page=True)
    kit.canonical(migrated_tenant.number, people, commit_version, kit.FIRST)
    commit_version(people.document, people["a"], kit.SECOND, "edit")
    client, _ = kit.reader(member_of, link_group, people, [Right.VIEW_PENDING], "pending")
    given: list[tuple[str, list[str]]] = []
    real = pdf.write

    def recorded(html: str, path: Path, **kwargs: Any) -> None:
        given.append((html, list(kwargs["stylesheets"])))
        real(html, path, **kwargs)

    monkeypatch.setattr(pdf, "write", recorded)
    asked = client.post(
        f"/document/{people.document.number}/export/",
        {
            "document": "on",
            "format": "pdf",
            "view": "pending_edits",
            "changes-pending_edits": "marked",
        },
    )
    assert asked.status_code == 302
    kit.run_job(migrated_tenant.number, exports[0][1])

    ((html, sheets),) = given
    boxes = kit.computed(html, sheets)
    approval = [b for b in boxes if b["tag"] == "p" and "approval" in " ".join(b["classes"])]
    approval = approval or [
        b for b in boxes if b["tag"] == "p" and b["text"].startswith(("Not approved", "Не затв"))
    ]
    assert approval, "the approval line was not drawn"
    for box in approval:
        assert box["color"] == "#000000"
        assert box["font_size"] == pytest.approx(11)
        assert box["margin_left"] == 0
        assert box["letter_spacing"] == "normal"
    # Drawn on its own white box: the paragraph's block, the boxes inside it paint nothing.
    painted = [b["background"] for b in approval if b["background"].alpha]
    assert painted and all(c.coordinates == (1.0, 1.0, 1.0) for c in painted)
    # A mark's words stay in the platform's ink, whatever colour the text around them takes.
    marked = [b for b in boxes if b["tag"] == "ins"]
    assert marked and all(b["color"] == "#222222" for b in marked)
    # The organisation's rule reached the other details, so the guard is what held the line.
    number = next(b for b in boxes if b["tag"] == "p" and b["text"].startswith("#"))
    assert number["color"] == "#fefefe"
