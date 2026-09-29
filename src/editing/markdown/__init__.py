"""The whitelist's server side: one specification, the parser configured from it, the validator
and the serialiser (ADR-0010). Imports no Django app, so any app may import it."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

SPEC_PATH = Path(__file__).resolve().parent.parent / "whitelist" / "spec.json"


@dataclass(frozen=True)
class Spec:
    """The whitelist specification, as both parsers read it."""

    version: int
    max_bytes: int
    heading_max_depth: int
    list_max_depth: int
    spans: dict[str, bool]
    callout_types: tuple[str, ...]
    quotes: bool
    headings_top_level_only: bool
    tables_top_level_only: bool
    image_alone: bool
    image_src: re.Pattern[str]
    link_schemes: re.Pattern[str]
    refusals: dict[str, dict[str, str]]


def spec_from(raw: dict[str, Any]) -> Spec:
    """A specification from its JSON form."""
    return Spec(
        version=raw["version"],
        max_bytes=raw["maxBytes"],
        heading_max_depth=raw["headingMaxDepth"],
        list_max_depth=raw["listMaxDepth"],
        spans={name: bool(value["id"]) for name, value in raw["spans"].items()},
        callout_types=tuple(raw["calloutTypes"]),
        quotes=raw["quotes"],
        headings_top_level_only=raw["headingsTopLevelOnly"],
        tables_top_level_only=raw["tablesTopLevelOnly"],
        image_alone=raw["imageAlone"],
        image_src=re.compile(raw["imageSrc"]),
        link_schemes=re.compile(raw["linkSchemes"], re.IGNORECASE),
        refusals=raw["refusals"],
    )


def raw_spec(path: Path = SPEC_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        data: dict[str, Any] = json.load(file)
    return data


@cache
def load_spec() -> Spec:
    """The specification shipped with the application."""
    return spec_from(raw_spec())
