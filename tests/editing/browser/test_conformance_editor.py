"""The editor's half of the conformance suite: every case through the editor's own validator, and
every accepted text loaded into a real editor in Chromium and serialised back (ADR-0010)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from editing.markdown import SPEC_PATH


@pytest.mark.conformance
def test_browser_side_matches_every_case(
    browser_server: str, page: Any, cases: Any, expected_refusals: Any
) -> None:
    page.goto(browser_server + "/editing/conformance/")
    results = page.evaluate(
        "cases => SyngrapheEditor.conformance(cases, document.getElementById('editor'))", cases
    )
    failures = []
    for case, result in zip(cases, results, strict=True):
        refusals = [[r["code"], r["line"]] for r in result["refusals"]]
        if refusals != expected_refusals(case) or result["stored"] != case.get("stored"):
            failures.append((case["id"], refusals, result["stored"]))
        elif result["stored"] is not None and not result["fixed"]:
            failures.append((case["id"], "the stored form is not a fixed point"))
    assert not failures, "\n".join(map(repr, failures))


@pytest.mark.conformance
def test_the_bundle_carries_the_shipped_specification(browser_server: str, page: Any) -> None:
    page.goto(browser_server + "/editing/conformance/")
    shipped = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    assert page.evaluate("SyngrapheEditor.rawSpec") == shipped
