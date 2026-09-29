"""The server's half of the conformance suite: every case in `tests/fixtures/whitelist/cases.json`
through the Python validator and serialiser (ADR-0010). The editor's half is
`browser/test_conformance_editor.py`."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Any

import pytest

from editing.markdown import raw_spec, spec_from
from editing.markdown.serializer import serialize
from editing.markdown.validator import validate

SRC = Path(__file__).resolve().parents[2] / "src" / "editing"
MARKDOWN = SRC / "markdown"
# The patterns written once in each language, compared as text: Python's `\\Z` is JavaScript's `$`.
TWINS = {
    "markdown/rules.py": "js/rules.js",
    "markdown/serializer.py": "js/serializer.js",
}


def python_side(case: dict[str, Any], spec: Any = None) -> tuple[list[list[Any]], str | None]:
    refusals = [[r.code, r.line] for r in validate(case["input"], spec)]
    return refusals, None if refusals else serialize(case["input"])


def diverging(cases: list[dict[str, Any]], expected: Any, spec: Any = None) -> set[str]:
    """The ids of the cases whose verdict, code, line or stored form differ from the case."""
    ids = set()
    for case in cases:
        refusals, stored = python_side(case, spec)
        if refusals != expected(case) or stored != case.get("stored"):
            ids.add(case["id"])
    return ids


@pytest.mark.conformance
def test_python_side_matches_every_case(cases: Any, expected_refusals: Any) -> None:
    failures = []
    for case in cases:
        refusals, stored = python_side(case)
        if refusals != expected_refusals(case) or stored != case.get("stored"):
            failures.append((case["id"], refusals, stored))
    assert not failures, "\n".join(map(repr, failures))


@pytest.mark.conformance
def test_python_serialiser_writes_the_stored_form(cases: Any) -> None:
    """Every accepted and re-spelled case comes out in its stored form, and the stored form is a
    fixed point: written again, it does not change."""
    written = [c for c in cases if c["kind"] in ("accept", "respell")]
    assert written
    for case in written:
        assert serialize(case["input"]) == case["stored"], case["id"]
        assert serialize(case["stored"]) == case["stored"], case["id"]


@pytest.mark.conformance
def test_drift_is_caught(cases: Any, expected_refusals: Any) -> None:
    """A specification changed in one value on one side diverges on exactly the cases that value
    governs: allowing fifth-level headings frees the cases refused for a fifth-level heading."""
    raw = raw_spec()
    raw["headingMaxDepth"] = 5
    governed = {
        case["id"]
        for case in cases
        if case["kind"] == "refuse"
        and any(r["code"] == "heading-depth" for r in case["refusals"])
        and any(line.startswith("##### ") for line in case["input"].split("\n"))
    }
    assert governed
    assert diverging(cases, expected_refusals, spec_from(raw)) == governed
    assert diverging(cases, expected_refusals) == set()


@pytest.mark.fast
def test_the_markdown_package_imports_no_app() -> None:
    """`editing.markdown` imports only the standard library, markdown-it-py and itself, so any
    app may import it without a cycle."""
    allowed = set(sys.stdlib_module_names) | {"markdown_it", "editing"}
    for path in MARKDOWN.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                names = [node.module]
            for name in names:
                assert name.split(".")[0] in allowed, f"{path.name} imports {name}"
                if name.startswith("editing."):
                    assert name.startswith("editing.markdown"), f"{path.name} imports {name}"


def _python_patterns(path: Path) -> dict[str, str]:
    found = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and getattr(node.value.func, "attr", "") == "compile"
            and node.value.args
            and isinstance(node.value.args[0], ast.Constant)
        ):
            name = node.targets[0].id  # type: ignore[attr-defined]
            found[name] = str(node.value.args[0].value).replace("\\Z", "$")
    return found


def _javascript_patterns(path: Path) -> dict[str, str]:
    pattern = re.compile(r"^(?:export )?const ([A-Z_]+) = /(.+)/[a-z]*;$", re.MULTILINE)
    return {m.group(1): m.group(2) for m in pattern.finditer(path.read_text(encoding="utf-8"))}


@pytest.mark.fast
def test_the_twins_share_their_patterns() -> None:
    """Every regular expression written as a literal on both sides is the same expression."""
    compared = 0
    for python, javascript in TWINS.items():
        left, right = _python_patterns(SRC / python), _javascript_patterns(SRC / javascript)
        for name in left.keys() & right.keys():
            assert left[name] == right[name], f"{name} differs between {python} and {javascript}"
            compared += 1
    assert compared >= 10
