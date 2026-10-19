"""The deterministic publishability checks of `scripts/check_record.py`, each proven on a tree
planted under `tmp_path` that holds exactly the files the check reads: one planted fault the check
must name with its file and line, and the clean twin it must pass. The ids check scans `tests/`,
so no id, never-used word or route a planted tree carries is written out here — each is assembled
at run time."""

from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

pytestmark = pytest.mark.fast

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "check_record.py"
DERIVE = REPO / "scripts" / "derive_coverage.py"
LOG = "docs/design-record/decision-log.md"
PAGES = "docs/interface/pages.md"
DESIGN = "docs/technical-design.md"
CATALOGUE = "src/shell/locale/uk/LC_MESSAGES/django.po"

# The planted ids, joined so the ids check never meets one in this file.
ACTIVE, SUPERSEDED, PARTLY = "DL-" + "0002", "DL-" + "0001", "DL-" + "0003"
LANE, MISSING_DL = "DL-" + "12-001", "DL-" + "9999"
ADR_OK, ST_OK, B_OK = "ADR-" + "0001", "ST-" + "0001", "B-" + "001"
V_OK, V_TABLE = "V-" + "01", "V-" + "02"
MISSING_ADR, MISSING_ST = "ADR-" + "0404", "ST-" + "9999"
MISSING_V, MISSING_B = "V-" + "99", "B-" + "999"
STORIES = ["ST-" + f"{n:04d}" for n in range(1, 6)]
# The planted never-used words and stems, joined for the same reason.
LEDGER, VAULT, STASH = "led" + "ger", "va" + "ult", "st" + "ash"
SKHOV, KOMIR = "схов" + "ищ", "ком" + "ір"


@pytest.fixture(scope="module")
def check_record() -> ModuleType:
    """The script, loaded by its path: `scripts/` is not a package."""
    spec = importlib.util.spec_from_file_location("check_record", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _plant(root: Path, files: dict[str, list[str]]) -> None:
    """Write each file, given as its lines, under the planted root."""
    for name, lines in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _lines(rows: list[tuple[str, str | None]], *, faults: bool) -> tuple[list[str], dict[int, str]]:
    """The lines of a planted file from `(text, fault)` rows — a fault row names what the check
    must find there and is left out of the clean twin — and the faults by their 1-based line."""
    kept = [row for row in rows if faults or row[1] is None]
    lines = [text for text, _ in kept]
    expected = {n: fault for n, (_, fault) in enumerate(kept, start=1) if fault is not None}
    return lines, expected


def _by_line(findings: list) -> dict[tuple[str, int], list[str]]:
    return {
        key: [f.message for f in findings if (f.path, f.line) == key]
        for key in {(f.path, f.line) for f in findings}
    }


# --- ids ----------------------------------------------------------------------------------------


def _ids_tree(root: Path, *, faults: bool) -> dict[tuple[str, int], str]:
    """Plant the ids check's files; return `(path, line) → the id` of every planted fault."""
    expected: dict[tuple[str, int], str] = {}
    files: dict[str, list[str]] = {
        LOG: [
            "# Decision log",
            "",
            "| ID | Date | Question | Decision | Rationale | Impact | Status |",
            "|----|------|----------|----------|-----------|--------|--------|",
            f"| {ACTIVE} | 2026-01-02 | q | d | r | i | active |",
            f"| {SUPERSEDED} | 2026-01-01 | q | d | r | i | superseded — {ACTIVE} |",
            f"| {PARTLY} | 2026-01-03 | q | d | r | i | partly superseded — {ACTIVE} |",
            f"| {LANE} | 2026-01-04 | q | d | r | i | active |",
        ],
        f"docs/adr/{ADR_OK}-reading-by-lamplight.md": [
            "# Reading by lamplight",
            "",
            f"Refines {SUPERSEDED}, which it may cite as it stands: this is an ADR.",
        ],
        "docs/user-stories.md": [
            "# User stories",
            "",
            f"**{ST_OK}** — As a reader, I open a shelf, so that I find a document.",
        ],
        "docs/verification-plan.md": [
            "# Verification plan",
            "",
            f"### {V_OK} — The shelf holds",
            "",
            "| Claim | Status |",
            "|---|---|",
            f"| {V_TABLE} | proven |",
        ],
        "docs/backlog.md": ["# Backlog", "", f"## {B_OK} — A second lamp", "", "When asked."],
        "docs/design-record/analysis.md": [
            f"The analysis behind {SUPERSEDED}, cited as it stands: this is the design record.",
        ],
        "src/app/migrations/0001_planted.py": [f"# Cites {MISSING_DL}, unread: a migration."],
        "src/notes.rst": [f"Cites {MISSING_DL}, unread: not a scanned extension."],
    }
    planted = {
        "src/planted.py": [
            ("# The decisions this module follows.", None),
            (f"# Follows {ACTIVE}, {LANE}, {ADR_OK}, {ST_OK}, {V_OK}, {V_TABLE}, {B_OK}.", None),
            (f"# Cites {MISSING_DL}, which no row defines.", MISSING_DL),
            (f"# Cites {SUPERSEDED} as if it were current.", SUPERSEDED),
            (f"# Supersedes {SUPERSEDED}: the line says so, and is not a finding.", None),
            (f"# Cites {PARTLY}, partly superseded, which is not a finding.", None),
            (f"# Cites {MISSING_ADR}.", MISSING_ADR),
            (f"# Cites {MISSING_ST}.", MISSING_ST),
            (f"# Cites {MISSING_V}.", MISSING_V),
            (f"# Cites {MISSING_B}.", MISSING_B),
        ],
        "docs/notes.md": [
            ("# Notes", None),
            ("", None),
            (f"Outside the design record and the ADRs, {SUPERSEDED} is current here.", SUPERSEDED),
        ],
        "tests/test_planted.py": [
            (f"# A test that still follows {SUPERSEDED}.", SUPERSEDED),
            (f"# One that follows {LANE}, a lane id that exists.", None),
        ],
    }
    for name, rows in planted.items():
        files[name], by_line = _lines(rows, faults=faults)
        expected.update({(name, n): id_ for n, id_ in by_line.items()})
    _plant(root, files)
    return expected


def test_ids_exist_and_superseded_rows_are_flagged(
    check_record: ModuleType, tmp_path: Path
) -> None:
    """A missing id, and a superseded row cited as current, are each named at their line; a lane
    id that exists, a partly superseded row and a line that says *supersedes* pass."""
    expected = _ids_tree(tmp_path / "fault", faults=True)
    findings = check_record.check_ids(tmp_path / "fault")

    assert all(f.check == "ids" for f in findings)
    found = _by_line(findings)
    assert set(found) == set(expected)
    for key, id_ in expected.items():
        assert any(id_ in message for message in found[key]), (key, found[key])

    _ids_tree(tmp_path / "clean", faults=False)
    assert check_record.check_ids(tmp_path / "clean") == []


# --- coverage -----------------------------------------------------------------------------------


def _coverage_tree(root: Path) -> None:
    """The files `derive_coverage.py` reads, the script itself beside them, and a `coverage.md`
    whose table says the second story is drawn when one of its regions is not."""
    first, second = STORIES[0], STORIES[1]
    _plant(
        root,
        {
            PAGES: [
                "# Pages",
                "",
                "## Reading room",
                "",
                "| Region | Release | Stories | Built by |",
                "|---|---|---|---|",
                f"| the shelf | **0.1** | {first}, {second} | Epic 1 |",
                f"| the desk — not yet drawn | **0.1** | {second} | Epic 1 |",
            ],
            "docs/user-stories.md": [
                "# User stories",
                "",
                f"**{first}** — As a reader, I open a shelf, so that I find a document.",
                "",
                f"**{second}** — As a reader, I sit at the desk, so that I read.",
            ],
            "docs/interface/coverage.md": [
                "# Coverage",
                "",
                "**2 stories:** 2 drawn · 0 partly drawn · 0 not yet drawn. "
                "Every story has at least one region.",
                "",
                "| # | Story | Where | Drawn |",
                "|---|---|---|---|",
                f"| {first} | I open a shelf | Reading room — the shelf | drawn |",
                f"| {second} | I sit at the desk | Reading room — the shelf | drawn |",
            ],
        },
    )
    (root / "scripts").mkdir()
    shutil.copy(DERIVE, root / "scripts" / "derive_coverage.py")


def test_coverage_is_current(check_record: ModuleType, tmp_path: Path) -> None:
    """A stale `coverage.md` is one finding on the file as a whole, carrying the diff; the file
    once rewritten passes."""
    _coverage_tree(tmp_path)
    findings = check_record.check_coverage(tmp_path)

    assert len(findings) == 1
    (finding,) = findings
    assert (finding.path, finding.line) == ("docs/interface/coverage.md", 0)
    assert finding.check == "coverage"
    assert "coverage.md" in finding.message

    derive = tmp_path / "scripts" / "derive_coverage.py"
    subprocess.run([sys.executable, str(derive)], check=True, capture_output=True)
    assert check_record.check_coverage(tmp_path) == []


# --- pages --------------------------------------------------------------------------------------


def _pages_tree(root: Path, *, faults: bool) -> dict[int, str]:
    """Plant `pages.md`; return the line of each faulty inventory row and the story it must name
    (the page's name for the row whose anchor finds no section)."""
    s1, s2, s3, s4, s5 = STORIES
    rows: list[tuple[str, str | None]] = [
        ("# Pages", None),
        ("", None),
        ("## Page inventory", None),
        ("", None),
        ("| Page | URL | Stories | Release |", None),
        ("|---|---|---|---|", None),
        (f"| [Reading room](#reading-room) | `/room/` | {s1}, {s2} | **0.1** |", None),
        (
            f"| [Send-for-review screen](#send-for-review-screen) | a dialog | {s3}"
            f"{'' if faults else ', ' + s4} | **0.1** |",
            s4 if faults else None,
        ),
        (
            f"| [Lamps, lit](#lamps-lit) | — | {s4}{', ' + s5 if faults else ''} | **0.1** |",
            s5 if faults else None,
        ),
        (f"| [Lost page](#lost-page) | — | {s1} | **0.1** |", "Lost page"),
        ("", None),
        ("## Reading room", None),
        ("", None),
        ("| Region | Release | Stories | Built by |", None),
        ("|---|---|---|---|", None),
        (f"| the shelf | **0.1** | {s1} | Epic 1 |", None),
        ("", None),
        ("### The desk", None),
        ("", None),
        ("| Tab | Release | Stories | Built by |", None),
        ("|---|---|---|---|", None),
        (f"| the lamp | **0.1** | {s2} | Epic 1 |", None),
        ("", None),
        ("## Send-for-review screen", None),
        ("", None),
        ("| Region | Release | Stories | Built by |", None),
        ("|---|---|---|---|", None),
        (f"| the form | **0.1** | {s3}, {s4} | Epic 2 |", None),
        ("", None),
        ("## Lamps, lit", None),
        ("", None),
        ("| Region | Release | Stories | Built by |", None),
        ("|---|---|---|---|", None),
        (f"| the bulb | **0.1** | {s4} | Epic 2 |", None),
        ("", None),
        ("## Nothing to show here", None),
        ("", None),
        ("One page, no table.", None),
    ]
    lines, expected = _lines(rows, faults=faults)
    _plant(root, {PAGES: lines})
    return expected


def test_the_page_inventory_matches_its_regions(check_record: ModuleType, tmp_path: Path) -> None:
    """A row missing a story its region tables name, a row naming one they do not, and a row
    whose anchor finds no section are each named at the row's line; the inventory whose rows are
    the union of their sections' tables — across a subsection, an anchor with punctuation —
    passes."""
    expected = _pages_tree(tmp_path / "fault", faults=True)
    findings = check_record.check_pages(tmp_path / "fault")

    assert all((f.path, f.check) == (PAGES, "pages") for f in findings)
    found = _by_line(findings)
    assert {line for _, line in found} == set(expected)
    for line, named in expected.items():
        # The row without a section may be named by its page or by its anchor.
        messages = " ".join(found[(PAGES, line)]).lower()
        assert named.lower() in messages or named.lower().replace(" ", "-") in messages, found

    _pages_tree(tmp_path / "clean", faults=False)
    assert check_record.check_pages(tmp_path / "clean") == []


# --- help ---------------------------------------------------------------------------------------


def _help_tree(root: Path, *, faults: bool) -> None:
    """`HELP_PAGES` and `pages.md § Help`: with faults, the index holds a page the list lacks and
    the list a page the index lacks."""
    listed = "lamps and windows" if faults else "lamps and doors"
    _plant(
        root,
        {
            "src/editing/messages.py": [
                "from django.utils.translation import gettext_lazy as _",
                "",
                'NOT_A_PAGE = _("Not a help page")',
                "",
                "HELP_PAGES = {",
                '    "shelves": _("Shelves and their labels"),',
                '    "lamps": _("Lamps"),',
                '    "doors": _("Doors"),',
                "}",
            ],
            PAGES: [
                "# Pages",
                "",
                "## Help",
                "",
                "Pages rendered from files shipped with the application, opening on *shelves* "
                f"with the list beside it: shelves and their labels, {listed}. Linked from every "
                "refusal.",
                "",
                "| Region | Release | Stories | Built by |",
                "|---|---|---|---|",
                f"| the pages | **0.1** | {STORIES[0]} | Epic 1 |",
                "",
                "## Nothing to show here",
                "",
                "One page: shelves, lamps, doors and windows are not listed here.",
            ],
        },
    )


def test_help_index_both_ways(check_record: ModuleType, tmp_path: Path) -> None:
    """A title in `HELP_PAGES` the list lacks, and a piece of the list no title accounts for, are
    both named; a list that is the titles joined by commas and *and* passes."""
    _help_tree(tmp_path / "fault", faults=True)
    findings = check_record.check_help(tmp_path / "fault")

    assert findings
    assert all(f.check == "help" for f in findings)
    named = " ".join(f.message.lower() for f in findings)
    assert "doors" in named
    assert "windows" in named

    _help_tree(tmp_path / "clean", faults=False)
    assert check_record.check_help(tmp_path / "clean") == []


# --- routes -------------------------------------------------------------------------------------

CONVERTER = re.compile(r"<[^>]+>")
SCOPE = ("document/", "folder/", "search/", "compare/")


def _in_scope_routes() -> list[tuple[str, str]]:
    """`(name, pattern)` of every named route of the real resolver under the four prefixes."""
    from django.urls import URLPattern, URLResolver, get_resolver

    routes: list[tuple[str, str]] = []

    def walk(patterns: list, prefix: str) -> None:
        for pattern in patterns:
            if isinstance(pattern, URLResolver):
                walk(pattern.url_patterns, prefix + str(pattern.pattern))
            elif isinstance(pattern, URLPattern) and pattern.name:
                routes.append((pattern.name, prefix + str(pattern.pattern)))

    walk(get_resolver().url_patterns, "")
    return sorted(r for r in routes if r[1].startswith(SCOPE))


def _matcher(pattern: str) -> re.Pattern[str]:
    """The contract's reading of a route: each converter one or more characters other than `/`."""
    return re.compile("[^/]+".join(re.escape(part) for part in CONVERTER.split(pattern)) + r"\Z")


def _design_tree(root: Path, paths: list[str]) -> None:
    _plant(
        root,
        {
            DESIGN: [
                "# Technical design",
                "",
                "## Addresses",
                "",
                "- **Hosts** — the organisation's domain names the tenant.",
                "- **URLs** (within the tenant the host names): "
                + "; ".join(f"`{p}`" for p in paths)
                + ".",
                "- **Headers** — none is trusted.",
            ]
        },
    )


def test_routes_in_the_technical_design(check_record: ModuleType, tmp_path: Path) -> None:
    """Against the real resolver: a design naming a path for every in-scope route passes, one
    with a query on it included; the same design with one route's path dropped fails naming it."""
    routes = _in_scope_routes()
    assert routes, "the resolver has routes in scope"
    paths = {name: "/" + CONVERTER.sub("1", pattern) for name, pattern in routes}
    sample = {name: path[1:] for name, path in paths.items()}
    # Dropped: the first route no other route's path matches, so its absence is its own finding.
    dropped, dropped_pattern = next(
        (name, pattern)
        for name, pattern in routes
        if not any(_matcher(pattern).match(p) for n, p in sample.items() if n != name)
    )
    exempt = check_record.EXEMPT_PREFIXES
    assert isinstance(exempt, dict)
    assert all(isinstance(reason, str) and reason for reason in exempt.values())

    listed = list(paths.values())
    listed[-1] += "?from=1&to=2"
    _design_tree(tmp_path / "clean", listed)
    assert check_record.check_routes(tmp_path / "clean") == []

    _design_tree(tmp_path / "fault", [path for name, path in paths.items() if name != dropped])
    findings = check_record.check_routes(tmp_path / "fault")
    assert len(findings) == 1
    (finding,) = findings
    assert (finding.path, finding.check) == (DESIGN, "routes")
    assert dropped in finding.message or dropped_pattern in finding.message


# --- words --------------------------------------------------------------------------------------


def _words_tree(root: Path, *, faults: bool) -> dict[tuple[str, int], str]:
    """Plant the glossary, one help page in both languages and the catalogue; return
    `(path, line) → the word or stem` of every planted never-used word. With faults, the English
    page also uses a glossary term — *reading room* — its Ukrainian page lacks."""
    en, uk = "src/editing/help/en/shelves.md", "src/editing/help/uk/shelves.md"
    expected: dict[tuple[str, int], str] = {}
    files: dict[str, list[str]] = {
        "docs/glossary.md": [
            "# Glossary",
            "",
            "**shelf** · полиця · *fixed* — a place where documents rest.",
            "**reading room** · читальна кімната · *fixed* — the place they are read in.",
            "**lamp/light** · світильник · *proposed* — what they are read by.",
            "",
            "## Words we never use",
            "",
            "The substrate is invisible, so none of these appears anywhere a user can see.",
            "",
            f"**{LEDGER} · {VAULT}**",
            "",
            f"Українською: {SKHOV} · {KOMIR}",
            "",
            f"And one that is not a substrate word: **{STASH}**. Nothing is put away by hand.",
            "",
            "## Status",
            "",
            "*fixed* — the owner has settled it.",
        ],
    }
    planted = {
        en: [
            ("# Shelves and their labels", None),
            ("", None),
            (f"## The {LEDGER}", LEDGER),
            ("", None),
            ("A shelf holds documents; the reading room holds them, each under its light.", None),
            ("", None),
            (f"- Open the {VAULT} to see the older shelves.", VAULT),
            (f"- The `{VAULT}` key is a name in a code span, not the interface speaking.", None),
            (f"- Nothing {VAULT}s itself: an inflected form is the word.", VAULT),
            (f"- A {VAULT}ish shelf: a longer word is not.", None),
        ],
        uk: [
            ("# Полиці та їхні підписи", None),
            ("", None),
            (
                "На полиці лежать документи"
                + ("" if faults else " у читальній кімнаті")
                + ", кожна під своїм світильником.",
                None,
            ),
            ("", None),
            (f"- Відкрийте {SKHOV}е, щоб побачити старі полиці.", SKHOV),
            (f"- Клавіша `{SKHOV}е` — це назва в коді.", None),
        ],
        CATALOGUE: [
            ('msgid ""', None),
            ('msgstr ""', None),
            ('"Content-Type: text/plain; charset=UTF-8\\n"', None),
            ("", None),
            ("#: shelves/views.py:1", None),
            ('msgid "Open the shelf"', None),
            ('msgstr "Відкрити полицю"', None),
            ("", None),
            ("#: shelves/views.py:2", None),
            (f'msgid "Open the {VAULT}"', VAULT),
            (f'msgstr "Відкрити {SKHOV}е"', SKHOV),
        ],
    }
    for name, rows in planted.items():
        files[name], by_line = _lines(rows, faults=faults)
        expected.update({(name, n): word for n, word in by_line.items()})
    _plant(root, files)
    return expected


def test_words_against_the_glossary(check_record: ModuleType, tmp_path: Path) -> None:
    """A never-used word in an English page's heading and list, in a `msgid`, and its Ukrainian
    stem in the `uk` page and a `msgstr`, are each named at their line — not one in a code span,
    nor a longer word, though an inflected form is the word; an English page using a glossary
    term its Ukrainian page lacks is named with the page, the term and the Ukrainian term. The
    twin with the words gone and the term present, by its stems, passes."""
    expected = _words_tree(tmp_path / "fault", faults=True)
    findings = check_record.check_words(tmp_path / "fault")

    assert all(f.check == "words" for f in findings)
    pairs = [f for f in findings if "reading room" in f.message.lower()]
    assert len(pairs) == 1
    assert "читальна кімната" in pairs[0].message
    assert "shelves" in pairs[0].path or "shelves" in pairs[0].message
    found = _by_line([f for f in findings if f not in pairs])
    assert set(found) == set(expected)
    for key, word in expected.items():
        assert any(word in message.lower() for message in found[key]), (key, found[key])

    _words_tree(tmp_path / "clean", faults=False)
    assert check_record.check_words(tmp_path / "clean") == []


# --- the command --------------------------------------------------------------------------------

FINDING_LINE = re.compile(r"^(?P<path>[^:]+):(?P<line>\d+): (?P<check>\w+): (?P<message>.+)$")


def test_the_command_reports_each_finding_and_their_count(tmp_path: Path) -> None:
    """`--root PATH CHECK`: one line per finding, `path:line: check: message`, then
    `N finding(s)`; exit 1 with a finding and 0 without."""
    expected = _pages_tree(tmp_path / "fault", faults=True)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path / "fault"), "pages"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, result.stderr
    *lines, last = result.stdout.strip().splitlines()
    assert last == f"{len(lines)} finding(s)"
    parsed = [FINDING_LINE.match(line) for line in lines]
    assert all(parsed), lines
    assert {m["path"] for m in parsed if m} == {PAGES}
    assert {m["check"] for m in parsed if m} == {"pages"}
    assert {int(m["line"]) for m in parsed if m} == set(expected)

    _pages_tree(tmp_path / "clean", faults=False)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path / "clean"), "pages"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip().splitlines()[-1] == "0 finding(s)"


def test_the_tree_passes() -> None:
    """The repository as it stands, every check: exit 0."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT)], cwd=REPO, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_every_exempt_prefix_names_a_route(check_record: ModuleType) -> None:
    """An exemption naming no route is itself a finding of the reader's: each prefix the routes
    check leaves out holds at least one route the resolver has."""
    import django
    from django.urls import URLPattern, URLResolver, get_resolver

    django.setup()

    def walk(patterns: list[Any], prefix: str = "") -> list[str]:
        found = []
        for pattern in patterns:
            if isinstance(pattern, URLResolver):
                found += walk(pattern.url_patterns, prefix + str(pattern.pattern))
            elif isinstance(pattern, URLPattern):
                found.append(prefix + str(pattern.pattern))
        return found

    paths = walk(get_resolver().url_patterns)
    for prefix, reason in check_record.EXEMPT_PREFIXES.items():
        assert reason.strip(), prefix
        assert any(path.startswith(prefix) for path in paths), prefix


def test_a_pending_citation_is_held_until_it_is_gone(
    check_record: ModuleType, monkeypatch: Any
) -> None:
    """A pending citation is printed and fails nothing while found; once corrected and not
    taken off the list, the list itself fails."""
    cited = "DL-" + "0001"
    found = check_record.Finding("docs/prd.md", 3, "ids", f"{cited} is superseded and cited")
    monkeypatch.setattr(check_record, "PENDING", {("docs/prd.md", cited): (1, "a reason")})

    failing, held, stale = check_record.pending([found])
    assert (failing, held, stale) == ([], [found], [])

    failing, held, stale = check_record.pending([])
    assert (failing, held, stale) == ([], [], [("docs/prd.md", cited)])

    # A second citation of the id in that file is not held: the entry names one.
    again = check_record.Finding("docs/prd.md", 9, "ids", f"{cited} is superseded and cited")
    failing, held, stale = check_record.pending([found, again])
    assert (len(failing), held, stale) == (2, [], [("docs/prd.md", cited)])


def test_a_glossary_pair_advises(check_record: ModuleType) -> None:
    """A pair's finding is advice: matched by stems, it cannot read inflection or a homograph."""
    pair = check_record.Finding("src/x.md", 0, "words", '"a" is on the English page but "b" is not')
    never = check_record.Finding("src/x.md", 4, "words", '"x" is a word never used')

    assert check_record.is_advice(pair) and not check_record.is_advice(never)


def test_a_promoted_row_and_a_named_successor_read_as_history(
    check_record: ModuleType, tmp_path: Path
) -> None:
    """A row promoted to an ADR still stands there, cited bare; a replaced row cited with its
    successor on the line or the line before reads as history; the same row cited bare does not."""
    active, promoted, replaced = "DL-" + "0201", "DL-" + "0202", "DL-" + "0203"
    adr = "ADR-" + "0201"
    _plant(
        tmp_path,
        {
            LOG: [
                "# Decision log",
                "",
                "| ID | Date | Question | Decision | Rationale | Impact | Status |",
                "|----|------|----------|----------|-----------|--------|--------|",
                f"| {active} | 2026-01-02 | q | d | r | i | active |",
                f"| {promoted} | 2026-01-01 | q | d | r | i | superseded — promoted to {adr} |",
                f"| {replaced} | 2026-01-01 | q | d | r | i | superseded — {active} |",
            ],
            f"docs/adr/{adr}-a-lamp.md": ["# A lamp"],
            "docs/prd.md": [
                f"The lamp is lit at dusk ({promoted}).",
                f"The shelf was moved ({active},",
                f"{replaced}) to the window.",
                f"The desk stands by the door ({replaced}).",
            ],
        },
    )

    findings = check_record.check_ids(tmp_path)

    assert [(f.path, f.line) for f in findings] == [("docs/prd.md", 4)]
    assert replaced in findings[0].message
