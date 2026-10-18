"""`entities.yaml`'s rules: what a declaration may hold, its round trip, the declarations a commit
adds for spans the file lacks (DL-0440), and the changes between two files. Invented English."""

from __future__ import annotations

from typing import Any

import pytest

from documents import entities
from documents.entities import Declared, EntityChange

pytestmark = pytest.mark.fast


def test_entities_yaml_rules() -> None:
    malformed = [
        "kind: role\n",
        '- kind: "role"\n  key: "approver"\n',
        '- kind: "role"\n  key: "approver"\n  label: "the approver"\n  extra: "x"\n',
        '- kind: "place"\n  key: "office"\n  label: "the office"\n',
        '- kind: "role"\n  key: "has space"\n  label: "the approver"\n',
        '- kind: "role"\n  key: "approver"\n  label: ""\n',
        '- kind: "role"\n  key: "approver"\n  label: "two\\nlines"\n',
        '- kind: "role"\n  key: "approver"\n  label: "' + "x" * 201 + '"\n',
        '- kind: "role"\n  key: "approver"\n  kind: "action"\n  label: "the approver"\n',
    ]
    for text in malformed:
        with pytest.raises(ValueError, match="entry 1"):
            entities.parse(text)
    repeated = (
        '- kind: "role"\n  key: "approver"\n  label: "the approver"\n'
        '- kind: "role"\n  key: "approver"\n  label: "the second approver"\n'
    )
    with pytest.raises(ValueError, match="entry 2"):
        entities.parse(repeated)

    declared = [
        Declared("role", "approver", "the approver"),
        Declared("action", "approves", "approves"),
        Declared("term", "fixed-asset", 'an asset "fixed" for a year'),
    ]
    assert entities.parse(entities.dump(declared)) == declared
    assert entities.dump([]) == "[]\n"
    assert entities.parse("[]\n") == []
    assert entities.parse("") == []

    body = (
        "The request goes to [the approver]{.role #approver}.\n"
        "[The approver]{.role #approver} then [signs  *it*]{.action #signs}.\n"
        "[The clerk]{.role} files it.\n"
    )
    appendix = "[The auditor]{.role #auditor} reads [the record]{.term #record}.\n"
    once = entities.declared_with(entities.dump(declared[:1]), body, appendix)
    assert entities.parse(once) == [
        declared[0],
        Declared("action", "signs", "signs it"),
        Declared("role", "auditor", "The auditor"),
        Declared("term", "record", "the record"),
    ]
    assert entities.declared_with(once, body, appendix) == once
    unchanged = entities.dump(declared[:1])
    assert entities.declared_with(unchanged, "[the approver]{.role #approver}\n") is unchanged

    old = entities.dump(declared)
    new = entities.dump(
        [
            Declared("role", "approver", "the approving officer"),
            Declared("action", "approves", "approves"),
            Declared("role", "clerk", "the clerk"),
        ]
    )
    assert entities.changes(old, new) == [
        EntityChange("role", "approver", "relabelled", "the approver", "the approving officer"),
        EntityChange("role", "clerk", "added", "", "the clerk"),
        EntityChange("term", "fixed-asset", "removed", 'an asset "fixed" for a year', ""),
    ]
    assert entities.changes(old, old) == []


def test_whatever_does_not_read_is_a_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every text `parse` cannot read raises `ValueError`, so a caller that keeps a draft over a
    stop never meets another exception."""
    unreadable = [
        "- ? [a]\n  : b\n",
        "[" * 5000,
        '- kind: "role"\n  key: "approver\\n"\n  label: "the approver"\n',
    ]
    for text in unreadable:
        with pytest.raises(ValueError):
            entities.parse(text)
    with pytest.raises(ValueError):
        entities.parse(None)  # type: ignore[arg-type]
    monkeypatch.setattr(entities, "MAX_BYTES", 100)
    long = entities.dump([Declared("role", f"role-{n}", f"role {n}") for n in range(5)])
    with pytest.raises(ValueError, match="longer"):
        entities.parse(long)


@pytest.mark.budget
def test_spans_cost_what_the_parse_costs(grows_linearly: Any) -> None:
    """Reading the spans of a body up to the size limit grows with its length: each span's words
    are read in place, never from a copy of the rest of the paragraph."""
    counted: list[int] = []
    grows_linearly(
        lambda n: "[x]{.role #x} " * n + "\n",
        lambda body: counted.append(len(list(entities.spans(body)))),
        7_000,
    )
    assert counted[-1] == 28_000


def test_kinds_follow_the_specification() -> None:
    """An entity is a span of the specification's that names something the document defines: not
    the underline, which is formatting, nor the mention, which names another document."""
    from editing.markdown import load_spec

    assert entities.KINDS == tuple(
        kind for kind in load_spec().spans if kind not in ("underline", "document")
    )
