"""Every memoised function in `src/` is emptied before each test, so a test runs the function's
body whichever test ran before it on its worker — what the coverage-based selection of a story's
tests relies on to see the body (`docs/test-strategy.md § Tests done, for a story`)."""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.fast

SRC = Path(__file__).resolve().parents[2] / "src"
MEMOISERS = {"cache", "lru_cache"}


def _memoisers(tree: ast.Module) -> set[str]:
    """The names a module calls `functools.cache` and `lru_cache` by: their own, an alias they are
    imported under, and a name bound to one (`memo = functools.lru_cache(maxsize=8)`)."""
    names = set(MEMOISERS)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "functools":
            names.update(a.asname for a in node.names if a.name in MEMOISERS and a.asname)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and _is_memoiser(node.value, names):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return names


def _is_memoiser(node: ast.expr, names: set[str]) -> bool:
    """`cache`, `functools.cache`, `lru_cache(...)` or an alias of one."""
    target = node.func if isinstance(node, ast.Call) else node
    if isinstance(target, ast.Attribute):
        return target.attr in MEMOISERS
    return isinstance(target, ast.Name) and target.id in names


def memoised_in_src() -> set[str]:
    """`module.function` for every function in `src/` kept by `cache` or `lru_cache`, decorated or
    rebound (`load = lru_cache(load)`)."""
    found = set()
    for path in SRC.rglob("*.py"):
        if "migrations" in path.parts:
            continue
        module = ".".join(path.relative_to(SRC).with_suffix("").parts).removesuffix(".__init__")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = _memoisers(tree)
        defined = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                defined.add(node.name)
                if any(_is_memoiser(d, names) for d in node.decorator_list):
                    found.add(f"{module}.{node.name}")
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Call)
                and _is_memoiser(node.value.func, names)
                and any(isinstance(a, ast.Name) and a.id in defined for a in node.value.args)
            ):
                found.update(f"{module}.{t.id}" for t in node.targets if isinstance(t, ast.Name))
    return found


def test_the_scan_sees_every_spelling(tmp_path: Path, monkeypatch: Any) -> None:
    """The guard's own check: each way of memoising a function is found."""
    (tmp_path / "planted.py").write_text(
        "import functools\n"
        "from functools import cache as memo, lru_cache\n"
        "keep = functools.lru_cache(maxsize=8)\n"
        "@functools.cache\ndef one(): ...\n"
        "@lru_cache(maxsize=2)\ndef two(): ...\n"
        "@memo\ndef three(): ...\n"
        "@keep\ndef four(): ...\n"
        "def five(): ...\n"
        "five = lru_cache(five)\n"
        "def plain(): ...\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys.modules[__name__], "SRC", tmp_path)

    assert memoised_in_src() == {f"planted.{n}" for n in ("one", "two", "three", "four", "five")}


def test_every_memoised_function_is_emptied(memoised_functions: tuple[Any, ...]) -> None:
    emptied = {f"{f.__module__}.{f.__qualname__}" for f in memoised_functions}
    assert emptied == memoised_in_src()
    assert all(f.cache_info().currsize == 0 for f in memoised_functions)
