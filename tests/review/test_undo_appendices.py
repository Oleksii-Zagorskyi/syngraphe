"""The undo walks each appendix (ADR-0015, DL-0447, DL-0425): *undo this edit* and *undo all of
this author's edits* revert an appendix's clean lines in the reviewer's draft as they revert the
body's, list its built-on lines under its title, leave an appendix an undone version created where
it stands, walk one the base lacks from the empty file, and list, never merge, the lines of one the
head or the draft no longer holds. People and titles are synthetic examples; every text is
invented English."""

from __future__ import annotations

import dataclasses
import hashlib
from typing import Any

import pytest
from django.test import Client

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

BODY = "# General provisions\n\nAn application is made in writing.\nIt is signed.\n"
BODY_B = BODY + "Author B added a body sentence.\n"
ONE = [{"number": 1, "title": "Synthetic appendix one"}]
TWO = [*ONE, {"number": 2, "title": "Synthetic appendix two"}]
A1 = "# One\n\nThe first sentence.\nThe second sentence.\n"
A2 = "# Two\n\nAnother first sentence.\nAnother second sentence.\n"


def _draft(document: Any) -> Any:
    from editing.models import Draft

    return Draft.objects.get(hold__document=document, hold__released_at__isnull=True)


def _based(tenant: Any, cast: Any, commit_version: Any, appendices: Any = ONE) -> Any:
    """Authors A and B, reviewer R; the body and the appendices accepted as the run's base."""
    from review import services

    people = cast(editors=("a", "b"), reviewers=("r",))
    files = {"appendices/1.md": A1.encode()}
    if len(appendices) > 1:
        files["appendices/2.md"] = A2.encode()
    commit_version(people.document, people["a"], BODY, files=files, appendices=appendices)
    with schema_context(tenant.number):
        services.accept(people.document, people["r"])
    return people


def test_an_appendix_only_version_is_undone(
    migrated_tenant: Any, cast: Any, commit_version: Any
) -> None:
    from review import undo

    people = _based(migrated_tenant, cast, commit_version)
    document = people.document
    commit_version(document, people["a"], BODY_B)
    changed = commit_version(
        document,
        people["b"],
        BODY_B,
        files={"appendices/1.md": (A1 + "Author B's appendix sentence.\n").encode()},
    )
    with schema_context(migrated_tenant.number):
        undo.apply(document, people["r"], version=changed)
        draft = _draft(document)
        assert draft.content["appendices/1.md"] == A1
        assert draft.content["document.md"] == BODY_B


def test_built_on_appendix_lines_are_listed(
    migrated_tenant: Any, cast: Any, commit_version: Any
) -> None:
    from review import undo

    people = _based(migrated_tenant, cast, commit_version, TWO)
    document = people.document
    commit_version(
        document,
        people["a"],
        BODY_B,
        files={"appendices/2.md": (A2 + "A's sentence.\nA's other sentence.\n").encode()},
    )
    commit_version(
        document,
        people["b"],
        BODY_B,
        files={
            "appendices/2.md": (A2 + "B reworded A's sentence.\nA's other sentence.\n").encode()
        },
    )
    with schema_context(migrated_tenant.number):
        undo.apply(document, people["r"], author=people["a"])
        draft = _draft(document)
        assert draft.content["document.md"] == BODY
        assert draft.content["appendices/2.md"] == A2 + "B reworded A's sentence.\n"
        listed = draft.content["undo"]["listed"]
        assert [(e.get("appendix"), e["after"]) for e in listed] == [
            ("Synthetic appendix two", "B reworded A's sentence.")
        ]
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(people["r"])
    session = client.session
    session["tenant_number"] = migrated_tenant.number
    session.save()
    html = client.get(f"/document/{document.number}/edit/").content.decode()
    tab = html[html.index('class="undo-listed"') :]
    assert tab.index("Synthetic appendix two") < tab.index("B reworded A")


def test_a_created_appendix_is_kept(migrated_tenant: Any, cast: Any, commit_version: Any) -> None:
    from review import undo

    people = _based(migrated_tenant, cast, commit_version)
    document = people.document
    three = [*ONE, {"number": 3, "title": "Synthetic appendix three"}]
    created = commit_version(
        document,
        people["a"],
        BODY_B,
        files={"appendices/3.md": b"# Three\n\nA's created appendix.\n"},
        appendices=three,
    )
    only = commit_version(
        document,
        people["b"],
        BODY_B,
        files={"appendices/4.md": b"# Four\n\nB's created appendix.\n"},
        appendices=[*three, {"number": 4, "title": "Synthetic appendix four"}],
    )
    with schema_context(migrated_tenant.number):
        undo.apply(document, people["r"], version=created)
        draft = _draft(document)
        assert draft.content["document.md"] == BODY
        assert "appendices/3.md" not in draft.content or draft.content["appendices/3.md"] == (
            "# Three\n\nA's created appendix.\n"
        )
        assert {"before": "", "after": "", "frontmatter": "kept"} in draft.content["undo"]["listed"]
        with pytest.raises(undo.UndoRefused) as refused:
            undo.apply(document, people["r"], version=only)
        assert refused.value.reason == "nothing_to_undo"


def _image(data: bytes) -> str:
    return f"images/{hashlib.sha256(data).hexdigest()}.png"


def test_an_appendixs_reversal_stages_its_images(
    migrated_tenant: Any, cast: Any, commit_version: Any
) -> None:
    from editing.models import DraftFile
    from review import undo

    people = cast(editors=("a",), reviewers=("r",))
    document = people.document
    plan = b"a synthetic plan"
    with_plan = A1 + f"\n![A synthetic plan]({_image(plan)})\n"
    commit_version(
        document,
        people["a"],
        BODY,
        files={"appendices/1.md": with_plan.encode(), _image(plan): plan},
        appendices=ONE,
    )
    from review import services

    with schema_context(migrated_tenant.number):
        services.accept(document, people["r"])
    removed = commit_version(
        document,
        people["a"],
        BODY,
        files={"appendices/1.md": A1.encode(), _image(plan): None},
    )
    with schema_context(migrated_tenant.number):
        undo.apply(document, people["r"], version=removed)
        draft = _draft(document)
        assert draft.content["appendices/1.md"] == with_plan
        row = DraftFile.objects.get(draft=draft, kind="image")
        assert (row.path, bytes(row.content)) == (_image(plan), plan)


def test_an_appendix_past_the_size_is_refused(
    migrated_tenant: Any, cast: Any, commit_version: Any, monkeypatch: Any
) -> None:
    """The size is checked per file: the version shortened appendix 1 and changed the body; the
    body undone fits, appendix 1 undone does not."""
    from editing.markdown import load_spec
    from editing.models import Hold
    from review import services, undo

    people = cast(editors=("a",), reviewers=("r",))
    document = people.document
    long = "# One\n\n" + "".join(f"A long invented sentence number {n}.\n" for n in range(9))
    commit_version(
        document, people["a"], BODY, files={"appendices/1.md": long.encode()}, appendices=ONE
    )
    with schema_context(migrated_tenant.number):
        services.accept(document, people["r"])
    shortened = commit_version(
        document, people["a"], BODY_B, files={"appendices/1.md": b"# One\n\nShort.\n"}
    )
    small = dataclasses.replace(load_spec(), max_bytes=len(long.encode()) - 1)
    assert len(BODY.encode()) < small.max_bytes
    monkeypatch.setattr(undo, "load_spec", lambda: small)
    with schema_context(migrated_tenant.number):
        with pytest.raises(undo.UndoRefused) as refused:
            undo.apply(document, people["r"], version=shortened)
        assert refused.value.reason == "too_large"
        assert not Hold.objects.filter(document=document, released_at__isnull=True).exists()


def test_an_appendix_the_base_lacks_is_walked(
    migrated_tenant: Any, cast: Any, commit_version: Any
) -> None:
    from review import undo

    people = _based(migrated_tenant, cast, commit_version)
    document = people.document
    five = [*ONE, {"number": 5, "title": "Synthetic appendix five"}]
    commit_version(
        document,
        people["a"],
        BODY,
        files={"appendices/5.md": b"# Five\n\nA's sentence.\nA's second sentence.\n"},
        appendices=five,
    )
    changed = commit_version(
        document,
        people["b"],
        BODY,
        files={"appendices/5.md": b"# Five\n\nA's sentence.\nB's rewording.\n"},
    )
    with schema_context(migrated_tenant.number):
        undo.apply(document, people["r"], version=changed)
        draft = _draft(document)
        assert draft.content["appendices/5.md"] == "# Five\n\nA's sentence.\nA's second sentence.\n"
        assert [e["number"] for e in draft.content["frontmatter"]["appendices"]] == [1, 5]


def test_an_unlisted_appendix_is_listed_not_merged(
    migrated_tenant: Any, cast: Any, commit_version: Any
) -> None:
    from editing import parts
    from review import undo

    people = _based(migrated_tenant, cast, commit_version, TWO)
    document = people.document
    changed = commit_version(
        document,
        people["b"],
        BODY,
        files={
            "appendices/1.md": (A1 + "B's sentence in one.\n").encode(),
            "appendices/2.md": (A2 + "B's sentence in two.\n").encode(),
        },
    )
    commit_version(
        document,
        people["a"],
        BODY,
        files={"appendices/1.md": None},
        appendices=[{"number": 2, "title": "Synthetic appendix two"}],
    )
    with schema_context(migrated_tenant.number):
        from editing import holds

        # The reviewer's draft drops appendix 2, as an editor holding *delete appendix* would.
        holds.take(document, people["r"])
        parts.apply_to_draft(_draft(document), "delete_appendix", number=2)
        undo.apply(document, people["r"], version=changed)
        draft = _draft(document)
        assert "appendices/1.md" not in draft.content
        assert "appendices/2.md" not in draft.content
        listed = {
            e.get("appendix"): (e["wrote"], e["after"]) for e in draft.content["undo"]["listed"]
        }
        assert listed == {
            "Synthetic appendix one": ("B's sentence in one.", ""),
            "Synthetic appendix two": ("B's sentence in two.", ""),
        }


def _three(tenant: Any, cast: Any, commit_version: Any) -> Any:
    """A's version creates appendix 3 and changes the body; B's then rewords a line of it."""
    people = _based(tenant, cast, commit_version)
    three = [*ONE, {"number": 3, "title": "Synthetic appendix three"}]
    people.created = commit_version(
        people.document,
        people["a"],
        BODY_B,
        files={"appendices/3.md": b"# Three\n\nA's first sentence.\nA's second sentence.\n"},
        appendices=three,
    )
    people.changed = commit_version(
        people.document,
        people["b"],
        BODY_B,
        files={"appendices/3.md": b"# Three\n\nA's first sentence.\nB's rewording.\n"},
    )
    return people


def test_a_second_undo_reverts_a_created_appendixs_later_change(
    migrated_tenant: Any, cast: Any, commit_version: Any
) -> None:
    """Undoing A's creating version leaves appendix 3; undoing B's after it reverts B's line
    there, from the text the draft holds."""
    from review import undo

    people = _three(migrated_tenant, cast, commit_version)
    with schema_context(migrated_tenant.number):
        undo.apply(people.document, people["r"], version=people.created)
        undo.apply(people.document, people["r"], version=people.changed)
        draft = _draft(people.document)
        assert draft.content["appendices/3.md"] == (
            "# Three\n\nA's first sentence.\nA's second sentence.\n"
        )
        assert [e for e in draft.content["undo"]["listed"] if e.get("appendix")] == []


def test_an_authors_undo_leaves_the_appendix_it_created(
    migrated_tenant: Any, cast: Any, commit_version: Any
) -> None:
    """An appendix the undone versions created stays as it stands, whatever else they wrote in
    it; the kept entry says so."""
    from review import undo

    people = _three(migrated_tenant, cast, commit_version)
    people.again = commit_version(
        people.document,
        people["a"],
        BODY_B,
        files={"appendices/3.md": b"# Three\n\nA's first sentence.\nB's rewording.\nA's.\n"},
    )
    with schema_context(migrated_tenant.number):
        undo.apply(people.document, people["r"], author=people["a"])
        draft = _draft(people.document)
        assert "appendices/3.md" not in draft.content or draft.content["appendices/3.md"] == (
            "# Three\n\nA's first sentence.\nB's rewording.\nA's.\n"
        )
        assert {"before": "", "after": "", "frontmatter": "kept"} in draft.content["undo"]["listed"]


def test_a_deleted_appendix_is_kept(migrated_tenant: Any, cast: Any, commit_version: Any) -> None:
    """An appendix the undone version deleted stays deleted, a part operation: the kept entry,
    and no place carrying its text."""
    from review import undo

    people = _based(migrated_tenant, cast, commit_version)
    deleted = commit_version(
        people.document, people["a"], BODY_B, files={"appendices/1.md": None}, appendices=[]
    )
    with schema_context(migrated_tenant.number):
        undo.apply(people.document, people["r"], version=deleted)
        draft = _draft(people.document)
        assert draft.content["document.md"] == BODY
        assert draft.content["undo"]["listed"] == [
            {"before": "", "after": "", "frontmatter": "kept"}
        ]


def test_a_second_undo_lists_only_its_own_lines_of_an_unlisted_appendix(
    migrated_tenant: Any, cast: Any, commit_version: Any
) -> None:
    from review import undo

    people = _based(migrated_tenant, cast, commit_version)
    document = people.document
    first = commit_version(
        document, people["b"], BODY, files={"appendices/1.md": (A1 + "B's one.\n").encode()}
    )
    second = commit_version(
        document,
        people["b"],
        BODY,
        files={"appendices/1.md": (A1 + "B's one.\nB's two.\n").encode()},
    )
    commit_version(document, people["a"], BODY, files={"appendices/1.md": None}, appendices=[])
    with schema_context(migrated_tenant.number):
        undo.apply(document, people["r"], version=first)
        undo.apply(document, people["r"], version=second)
        listed = [e["wrote"] for e in _draft(document).content["undo"]["listed"] if "wrote" in e]
        assert listed == ["B's one.", "B's two."]


def test_a_file_outside_the_appendix_naming_is_not_walked(
    migrated_tenant: Any, cast: Any, commit_version: Any
) -> None:
    """A file under `appendices/` the application would not name, written by a version not undone
    and changed by the undone one, is never walked into the draft."""
    from review import undo

    people = _based(migrated_tenant, cast, commit_version)
    commit_version(
        people.document, people["a"], BODY, files={"appendices/01.md": b"# Stray\n\nText.\n"}
    )
    stray = commit_version(
        people.document,
        people["b"],
        BODY_B,
        files={"appendices/01.md": b"# Stray\n\nText.\nMore.\n"},
    )
    with schema_context(migrated_tenant.number):
        undo.apply(people.document, people["r"], version=stray)
        draft = _draft(people.document)
        assert draft.content["document.md"] == BODY
        assert "appendices/01.md" not in draft.content
        assert [e for e in draft.content["undo"]["listed"] if "appendix" in e] == []
