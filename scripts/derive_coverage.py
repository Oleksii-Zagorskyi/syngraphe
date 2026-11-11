"""Derive the story table of `docs/interface/coverage.md` from `docs/interface/pages.md`.

Usage, from the repository root:

    uv run python scripts/derive_coverage.py            # rewrite the table and its count line
    uv run python scripts/derive_coverage.py --check    # exit 1 with the diff if they are stale

The rules, which `coverage.md`'s header states for its readers:

- **Regions** are the rows of every table in `pages.md` whose first column is *Region*, *Tab*
  or *Section*; fenced blocks are skipped. A row's stories are its *Stories* cell;
  `ST-0019 to ST-0022` is a range.
- **Where** names a region as the section heading it sits under — a page's `## ` heading, or
  the page and its `### ` subsection, as `Document page › The draft's page` — then an em
  dash and the region cell cut at its first ` — ` or `; `, emphasis and code marks removed,
  longer than 58 characters cut to 58 and an ellipsis; a region named as its section is the
  section alone.
  A story's regions are listed in the order `pages.md` gives them.
- **Drawn**: a region is not yet drawn when its row says *not yet drawn* anywhere, in any
  case. A story is *drawn* when every region carrying it is drawn, *partly drawn* when some
  are, *not yet drawn* when none are.
- **Stories** are those of `docs/user-stories.md`, in its order, with their title up to the
  *so that* clause or the sentence's end, and without an italic parenthesis such as
  *(skeleton)*; a withdrawn story and one marked *Not in stage 1* are left out.

Only the count line and the table are written; the rest of `coverage.md` is left as it is.
Running it twice changes nothing.
"""

from __future__ import annotations

import difflib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = ROOT / "docs" / "interface" / "pages.md"
STORIES = ROOT / "docs" / "user-stories.md"
COVERAGE = ROOT / "docs" / "interface" / "coverage.md"

REGION_HEADERS = {"Region", "Tab", "Section"}
UNDRAWN = "not yet drawn"
MARK = re.compile(r"\s*\*\([^)]*\)\*")
WHERE_LIMIT = 58
STORY_LINE = re.compile(r"^\*\*(ST-\d{4})\*\* — (.*)$")
STORY_ID = re.compile(r"ST-(\d{4})(?:\s+to\s+ST-(\d{4}))?")
TABLE_HEAD = "| # | Story | Where | Drawn |"
COUNT_LINE = re.compile(r"^\*\*\d+ stories:\*\*.*$", re.MULTILINE)


@dataclass(frozen=True)
class Region:
    where: str
    stories: tuple[str, ...]
    drawn: bool


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _plain(text: str) -> str:
    return text.replace("*", "").replace("`", "").strip()


def _story_ids(cell: str) -> list[str]:
    ids: list[str] = []
    for match in STORY_ID.finditer(cell):
        first = int(match.group(1))
        last = int(match.group(2) or first)
        ids.extend(f"ST-{n:04d}" for n in range(first, last + 1))
    return ids


def _where(section: str, region_cell: str) -> str:
    region = _plain(re.split(r" — |; ", region_cell, maxsplit=1)[0])
    if len(region) > WHERE_LIMIT:
        region = region[:WHERE_LIMIT] + "…"
    return f"{section} — {region}" if region and region != section else section


def read_regions(text: str) -> list[Region]:
    """Every region row of `pages.md`, in the file's order."""
    regions: list[Region] = []
    page = section = ""
    header: list[str] | None = None
    fenced = False
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
            header = None
        elif fenced:
            continue
        elif line.startswith("## "):
            page = section = line[3:].strip()
            header = None
        elif line.startswith("### "):
            section = f"{page} › {line[4:].strip()}"
            header = None
        elif not line.startswith("|"):
            header = None
        elif header is None:
            cells = _cells(line)
            header = cells if cells[0] in REGION_HEADERS else []
        elif header and not set(line) <= set("|- "):
            if "Stories" not in header:
                raise SystemExit(f"pages.md: a {header[0]} table under {section} has no Stories")
            cells = _cells(line)
            stories = cells[header.index("Stories")]
            regions.append(
                Region(
                    where=_where(section, cells[0]),
                    stories=tuple(_story_ids(stories)),
                    drawn=UNDRAWN not in line.lower(),
                )
            )
    return regions


def read_stories(text: str) -> list[tuple[str, str]]:
    """The release's stories in the file's order: identifier and title without *so that*."""
    stories: list[tuple[str, str]] = []
    for line in text.splitlines():
        match = STORY_LINE.match(line)
        if not match or "*withdrawn" in line or "*Not in stage 1" in line:
            continue
        title = MARK.sub("", match.group(2))
        title = re.split(r",? — so that |, so that |\. ", title, maxsplit=1)[0]
        title = title.strip().rstrip(".")
        stories.append((match.group(1), title))
    return stories


def derive(pages: str, user_stories: str) -> tuple[str, list[str]]:
    """The count line and the table rows."""
    regions = read_regions(pages)
    rows = [TABLE_HEAD, "|---|---|---|---|"]
    counts = {"drawn": 0, "partly drawn": 0, "not yet drawn": 0}
    missing: list[str] = []
    for story, title in read_stories(user_stories):
        carrying = [r for r in regions if story in r.stories]
        if not carrying:
            missing.append(story)
            continue
        wheres = list(dict.fromkeys(r.where for r in carrying))
        drawn = sum(r.drawn for r in carrying)
        state = (
            "drawn" if drawn == len(carrying) else "not yet drawn" if drawn == 0 else "partly drawn"
        )
        counts[state] += 1
        rows.append(f"| {story} | {title} | {'; '.join(wheres)} | {state} |")
    total = sum(counts.values()) + len(missing)
    count = (
        f"**{total} stories:** {counts['drawn']} drawn · {counts['partly drawn']} partly drawn · "
        f"{counts['not yet drawn']} not yet drawn. "
        + (
            "Every story has at least one region."
            if not missing
            else f"Without a region: {', '.join(missing)}."
        )
    )
    return count, rows


def render(coverage: str, count: str, rows: list[str]) -> str:
    """`coverage.md` with its count line and its story table replaced."""
    if not COUNT_LINE.search(coverage):
        raise SystemExit("coverage.md: no count line to replace")
    coverage = COUNT_LINE.sub(lambda _: count, coverage, count=1)
    lines = coverage.split("\n")
    if TABLE_HEAD not in lines:
        raise SystemExit("coverage.md: no story table to replace")
    start = lines.index(TABLE_HEAD)
    end = start
    while end < len(lines) and lines[end].startswith("|"):
        end += 1
    return "\n".join(lines[:start] + rows + lines[end:])


def main(argv: list[str]) -> int:
    if set(argv) - {"--check"}:
        raise SystemExit("usage: derive_coverage.py [--check]")
    check = "--check" in argv
    current = COVERAGE.read_text(encoding="utf-8")
    count, rows = derive(PAGES.read_text(encoding="utf-8"), STORIES.read_text(encoding="utf-8"))
    derived = render(current, count, rows)
    if derived == current:
        print("coverage.md is current")
        return 0
    if check:
        sys.stdout.writelines(
            difflib.unified_diff(
                current.splitlines(keepends=True),
                derived.splitlines(keepends=True),
                "coverage.md",
                "derived",
            )
        )
        return 1
    COVERAGE.write_text(derived, encoding="utf-8")
    print("coverage.md rewritten")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
