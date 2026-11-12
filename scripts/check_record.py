"""Check the record's deterministic publishability rules: the ones a script can settle.

Usage, from the repository root:

    uv run python scripts/check_record.py [--root PATH] [CHECK ...]

`--root` is the tree read, the repository root by default; `CHECK` is any of `ids`,
`coverage`, `pages`, `help`, `routes`, `words`, `log`, and all seven run when none is given.
One line per finding, `path:line: check: message` (`line` 0 for a finding about a whole file), then
`N finding(s)`; exit 1 with any finding, 0 with none. The script reads and never writes.

- **ids** — every cited decision row, ADR, story, verification claim and backlog row exists,
  and no superseded decision row is cited as current outside the design record.
- **coverage** — `derive_coverage.py --check` passes: the coverage table is current.
- **pages** — in `pages.md`, each inventory row's stories are the stories of its section's
  regions.
- **help** — the help index's titles and `pages.md` § Help list the same pages.
- **routes** — every document address the resolver names is in the technical design's URLs
  bullet, and every other route is one the script knows to leave out.
- **words** — the glossary's never-used words are absent from the help pages and the `uk`
  catalogue, and a term on an English help page has its Ukrainian term on the Ukrainian one.
- **log** — across every decision log of the design record and the ADRs' frontmatter: a row
  that says it supersedes another is named by that row's status, and a status that names a row
  is matched by that row's claim; a row that supersedes an ADR is listed in the ADR's
  `superseded_by`, and each entry there exists; each status is `active`, `deferred`,
  `withdrawn`, `superseded — {rows}`, `superseded — promoted to {ADR}` (the ADR exists), or
  either of the last two `partly`, with an optional clause in parentheses; each row's id is
  unique. A row supersedes only by a verb in its Question's opening parenthetical —
  *supersedes*, *corrects*, *revises*, *rewrites* or *resolves*, never *refines* — so its own
  note that it was superseded is never misread.
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent

ADRS = "docs/adr"
STORIES = "docs/user-stories.md"
CLAIMS = "docs/verification-plan.md"
BACKLOG = "docs/backlog.md"
PAGES = "docs/interface/pages.md"
COVERAGE = "docs/interface/coverage.md"
MESSAGES = "src/editing/messages.py"
TECHNICAL_DESIGN = "docs/technical-design.md"
GLOSSARY = "docs/glossary.md"
HELP = "src/editing/help"
CATALOGUE = "src/shell/locale/uk/LC_MESSAGES/django.po"
URLS = "src/syngraphe/urls.py"

# The ids check: what is scanned, and what each kind of id looks like.
SCANNED_DIRS = ("src", "tests", "docs")
SCANNED_SUFFIXES = {".py", ".md", ".html", ".js", ".json", ".txt", ".yaml", ".yml", ".po", ".css"}
SKIPPED_DIRS = {"migrations", "__pycache__"}
DESIGN_RECORD_DIRS = ("docs/design-record/", "docs/adr/")
ID_PATTERNS = {
    "decision": re.compile(r"\bDL-(?:\d{4}|\d{1,2}-\d{3})\b"),
    "adr": re.compile(r"\bADR-\d{4}\b"),
    "story": re.compile(r"\bST-\d{4}\b"),
    "claim": re.compile(r"\bV-\d{2}\b"),
    "backlog": re.compile(r"\bB-\d{3}\b"),
}
DEFINED_IN = {
    "decision": "the decision logs",
    "adr": ADRS,
    "story": STORIES,
    "claim": CLAIMS,
    "backlog": BACKLOG,
}
DECISION_ROW = re.compile(r"^\| (DL-\S+) \|")
ADR_FILE = re.compile(r"^(ADR-\d{4})-.*\.md$")
STORY_DEFINITION = re.compile(r"\*\*(ST-\d{4})\*\*")
CLAIM_ID = re.compile(r"\bV-\d{2}\b")
CLAIM_ROW = re.compile(r"^\|\s*(V-\d{2})\b")
BACKLOG_HEADING = re.compile(r"^## (B-\d{3}) ")

# The pages check.
STORY_ID = re.compile(r"\bST-\d{4}\b")
PAGE_LINK = re.compile(r"\[([^\]]+)\]\(#([^)]+)\)")

# The help check.
HELP_HEADING = "## Help"

# The routes check: every top-level prefix the technical design's URLs bullet does not
# cover, with why it is left out. The framework's administration path joins at run time.
IN_SCOPE_PREFIXES = ("document/", "folder/", "search/", "compare/")
EXEMPT_PREFIXES = {
    "administration/": "the administration pages, described by pages.md § Administration",
    "notifications/": "the notifications page, described by pages.md § Notifications",
    "help/": "the help pages, described by pages.md § Help",
    "preferences/": "a person's own settings, not a document address",
    "account/": "a person's own account, not a document address",
    "reset/": "the password reset, not a document address",
    "invitation/": "accepting an invitation, not a document address",
    "signin/": "signing in, described by pages.md § Sign-in pages",
    "signout/": "signing out, not a document address",
    "setup/": "the first platform administrator, not a document address",
    "health/": "the health endpoint, operational",
    "organisation/": "choosing an organisation, not a document address",
    "editing/": "the editor's conformance page, a development aid",
    "in-edit/": "the In edit list, described by pages.md § In edit, In review",
    "in-review/": "the In review list, described by pages.md § In edit, In review",
    "my-reservations/": "a person's own reservations, not a document address",
    "document-styles/": "the document stylesheet, served to every page",
    "": "the root, which opens the document list",
}
URLS_BULLET = "- **URLs**"
BACKTICKED = re.compile(r"`([^`]+)`")
CONVERTER = re.compile(r"(<[^>]+>)")

# The words check.
NEVER_HEADING = "## Words we never use"
BOLD = re.compile(r"\*\*(.+?)\*\*")
UKRAINIAN_LINE = "Українською:"
CODE_SPAN = re.compile(r"`[^`]*`")
# A pair the owner has settled: a proposed term is still the agent's suggestion, and the help
# may say it otherwise until it is fixed.
# Any decision row or ADR an id names: what a superseded row's status says replaced it.
ANY_ID = re.compile(r"\b(?:DL-\d{1,2}-\d{3}|DL-\d{4}|ADR-\d{4})\b")
PAIR_LINE = re.compile(r"^\*\*([^*]+)\*\* · ([^·]+) · \*fixed\* — ")
# Four letters: Ukrainian inflects a noun's ending (група, групи), never its first letters.
STEM_LETTERS = 4


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    check: str
    message: str


def _read(root: Path, relative: str) -> str:
    path = root / relative
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _lines(root: Path, relative: str) -> list[str]:
    return _read(root, relative).splitlines()


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _anchor(heading: str) -> str:
    return re.sub(r"[^a-z0-9-]", "", heading.lower().replace(" ", "-"))


def _prose(lines: list[str]) -> Iterator[tuple[int, str]]:
    """Each line with its 1-based number, code spans blanked and fenced blocks skipped."""
    fenced = False
    for number, line in enumerate(lines, 1):
        if line.startswith("```"):
            fenced = not fenced
        elif not fenced:
            yield number, CODE_SPAN.sub(" ", line)


def _tables(lines: list[str], start: int, end: int) -> Iterator[tuple[list[str], int, list[str]]]:
    """Each body row of each table between the line indexes: its header, 1-based line, cells."""
    header: list[str] | None = None
    fenced = False
    for index in range(start, end):
        line = lines[index]
        if line.startswith("```"):
            fenced = not fenced
            header = None
        elif fenced:
            continue
        elif not line.startswith("|"):
            header = None
        elif header is None:
            header = _cells(line)
        elif not set(line) <= set("|-: "):
            yield header, index + 1, _cells(line)


def _section(lines: list[str], heading: str) -> tuple[int, int]:
    """The line indexes of the `## ` section with this heading: after its heading, up to
    the next `## ` heading; (0, 0) when there is none."""
    for index, line in enumerate(lines):
        if line.rstrip() == heading:
            end = index + 1
            while end < len(lines) and not lines[end].startswith("## "):
                end += 1
            return index + 1, end
    return 0, 0


# --- ids ----------------------------------------------------------------------------------


def _decisions(root: Path) -> dict[str, str]:
    """Each decision row's id and its lowercased status cell, across the open log and every
    release's closed one: the ids continue from one file to the next."""
    return {row.id: row.status.lower() for row in _rows(root)}


def _is_decision_log(relative: str) -> bool:
    path = PurePosixPath(relative)
    return path.parent.as_posix() == LOG_DIR and fnmatch(path.name, LOG_GLOB)


def _defined_ids(root: Path) -> dict[str, set[str]]:
    adrs = root / ADRS
    claims: set[str] = set()
    for line in _lines(root, CLAIMS):
        if line.startswith("#"):
            claims.update(CLAIM_ID.findall(line))
        row = CLAIM_ROW.match(line)
        if row:
            claims.add(row.group(1))
    return {
        "decision": set(_decisions(root)),
        "adr": {m.group(1) for p in adrs.iterdir() if (m := ADR_FILE.match(p.name))}
        if adrs.is_dir()
        else set(),
        "story": set(STORY_DEFINITION.findall(_read(root, STORIES))),
        "claim": claims,
        "backlog": {
            m.group(1) for line in _lines(root, BACKLOG) if (m := BACKLOG_HEADING.match(line))
        },
    }


def _scanned_files(root: Path) -> Iterator[Path]:
    for name in SCANNED_DIRS:
        folder = root / name
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob("*")):
            relative = path.relative_to(root)
            if (
                path.is_file()
                and path.suffix in SCANNED_SUFFIXES
                and not SKIPPED_DIRS & set(relative.parts[:-1])
            ):
                yield path


def _cites_as_current(relative: str) -> bool:
    """Whether a citation here must be of a current decision: the design record may cite
    a superseded row as history; code, tests and the other documents may not."""
    return not relative.startswith("docs/") or not relative.startswith(DESIGN_RECORD_DIRS)


def check_ids(root: Path) -> list[Finding]:
    defined = _defined_ids(root)
    # A row promoted to an ADR still stands, in the ADR; a replaced row is cited as history only
    # on a line that also names what replaced it.
    superseded = {
        decision: set(ANY_ID.findall(status.upper()))
        for decision, status in _decisions(root).items()
        if status.startswith("superseded") and "promoted to" not in status
    }
    findings: list[Finding] = []
    for path in _scanned_files(root):
        relative = path.relative_to(root).as_posix()
        current = _cites_as_current(relative)
        previous = ""
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            # A citation wrapped across two lines names its successor on either.
            nearby = previous + " " + line
            previous = line
            for kind, pattern in ID_PATTERNS.items():
                if kind == "decision" and _is_decision_log(relative):
                    continue
                for cited in dict.fromkeys(pattern.findall(line)):
                    if cited not in defined[kind]:
                        message = f"{cited} is not in {DEFINED_IN[kind]}"
                    elif (
                        cited in superseded
                        and current
                        and "supersed" not in line.lower()
                        and not superseded[cited] & set(ANY_ID.findall(nearby))
                    ):
                        message = f"{cited} is superseded and cited as current"
                    else:
                        continue
                    findings.append(Finding(relative, number, "ids", message))
    return findings


# --- coverage -----------------------------------------------------------------------------


def check_coverage(root: Path) -> list[Finding]:
    script = root / "scripts" / "derive_coverage.py"
    result = subprocess.run(
        [sys.executable, str(script), "--check"], cwd=root, capture_output=True, text=True
    )
    if result.returncode == 0:
        return []
    output = [line for line in (result.stdout + result.stderr).splitlines() if line.strip()]
    head = " / ".join(output[:5]) or "no output"
    return [Finding(COVERAGE, 0, "coverage", f"derive_coverage.py --check fails: {head}")]


# --- pages --------------------------------------------------------------------------------


def check_pages(root: Path) -> list[Finding]:
    lines = _lines(root, PAGES)
    anchors = {
        _anchor(line[3:].strip()): index for index, line in enumerate(lines) if line[:3] == "## "
    }
    start, end = _section(lines, "## Page inventory")
    findings: list[Finding] = []
    for header, number, cells in _tables(lines, start, end):
        link = PAGE_LINK.search(cells[0])
        if not link or "Stories" not in header:
            continue
        listed = set(STORY_ID.findall(cells[header.index("Stories")]))
        anchor = link.group(2)
        if anchor not in anchors:
            findings.append(Finding(PAGES, number, "pages", f"no section has the anchor #{anchor}"))
            continue
        heading = lines[anchors[anchor]]
        section_start, section_end = _section(lines, heading)
        found: set[str] = set()
        for table_header, _, row in _tables(lines, section_start, section_end):
            if "Stories" in table_header:
                found.update(STORY_ID.findall(row[table_header.index("Stories")]))
        parts = []
        if listed - found:
            parts.append(f"not in the section's regions: {', '.join(sorted(listed - found))}")
        if found - listed:
            parts.append(f"not in the row: {', '.join(sorted(found - listed))}")
        if parts:
            findings.append(Finding(PAGES, number, "pages", f"{link.group(1)}: {'; '.join(parts)}"))
    return findings


# --- help ---------------------------------------------------------------------------------


def _help_titles(root: Path) -> list[tuple[int, str]]:
    """Each `HELP_PAGES` value's translated literal with its line, read without Django."""
    titles: list[tuple[int, str]] = []
    source = _read(root, MESSAGES)
    if not source:
        return titles
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict)):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "HELP_PAGES" for t in node.targets):
            continue
        for value in node.value.values:
            if (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id == "_"
                and value.args
                and isinstance(value.args[0], ast.Constant)
                and isinstance(value.args[0].value, str)
            ):
                titles.append((value.lineno, value.args[0].value))
    return titles


def _help_list(lines: list[str]) -> tuple[int, str]:
    """The list of pages in the first paragraph under § Help, with the paragraph's line."""
    start, end = _section(lines, HELP_HEADING)
    index = start
    while index < end and not lines[index].strip():
        index += 1
    paragraph: list[str] = []
    while index < end and lines[index].strip():
        paragraph.append(lines[index].strip())
        index += 1
    text = " ".join(paragraph)
    first = index - len(paragraph) + 1 if paragraph else 0
    if ": " not in text:
        return first, ""
    text = text.split(": ", 1)[1]
    text = text.split(". ", 1)[0]
    return first, re.sub(r" — .*? — ", " ", text)


def _phrase(words: str) -> re.Pattern[str]:
    """The words as a whole phrase, any case, whitespace loosely."""
    joined = r"\s+".join(re.escape(word) for word in words.split())
    return re.compile(rf"(?<!\w){joined}(?!\w)", re.IGNORECASE)


def check_help(root: Path) -> list[Finding]:
    titles = _help_titles(root)
    line, listed = _help_list(_lines(root, PAGES))
    findings: list[Finding] = []
    # Longest title first, so a title that another one contains is never taken out of it.
    remainder = listed
    for number, title in sorted(titles, key=lambda t: -len(t[1])):
        pattern = _phrase(title)
        if pattern.search(remainder):
            remainder = pattern.sub(" ", remainder, count=1)
        else:
            findings.append(
                Finding(MESSAGES, number, "help", f'"{title}" is not in pages.md § Help')
            )
    for piece in remainder.split(","):
        rest = re.sub(r"\band\b", " ", piece, flags=re.IGNORECASE).strip()
        if rest:
            findings.append(
                Finding(PAGES, line, "help", f'"{rest}" in § Help is not a help page\'s title')
            )
    return findings


# --- routes -------------------------------------------------------------------------------


def _route_pattern(route: str) -> re.Pattern[str]:
    """The route as a regular expression: each converter one or more characters but `/`."""
    parts = (
        (r"\d+" if part.startswith("<int:") else "[^/]+")
        if part.startswith("<")
        else re.escape(part)
        for part in CONVERTER.split(route)
    )
    return re.compile("".join(parts))


def _design_paths(lines: list[str]) -> tuple[int, list[str]]:
    """The backticked paths of the URLs bullet, each after its `/` and before any `?`."""
    for index, line in enumerate(lines):
        if line.startswith(URLS_BULLET):
            paths = [p.removeprefix("/").split("?", 1)[0] for p in BACKTICKED.findall(line)]
            return index + 1, paths
    return 0, []


def check_routes(root: Path) -> list[Finding]:
    """Needs Django: the resolver is the real one, read through the project's settings."""
    source = root / "src" if (root / "src").is_dir() else ROOT / "src"
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "syngraphe.settings")
    import django
    from django.conf import settings
    from django.urls import URLResolver, get_resolver

    django.setup()
    exempt = dict(EXEMPT_PREFIXES)
    exempt[str(settings.DJANGO_ADMIN_PATH)] = "the framework's administration, never at its default"

    def routes(patterns: list[object], prefix: str) -> Iterator[tuple[str, str]]:
        for pattern in patterns:
            route = prefix + str(pattern.pattern)  # type: ignore[attr-defined]
            if isinstance(pattern, URLResolver):
                yield from routes(pattern.url_patterns, route)
            else:
                yield pattern.name, route  # type: ignore[attr-defined]

    def exempting(route: str) -> list[str]:
        return [p for p in exempt if (route == p if p == "" else route.startswith(p))]

    line, paths = _design_paths(_lines(root, TECHNICAL_DESIGN))
    findings: list[Finding] = []
    used: set[str] = set()
    for name, route in routes(get_resolver().url_patterns, ""):
        used.update(exempting(route))
        if not name:
            continue
        if route.startswith(IN_SCOPE_PREFIXES):
            pattern = _route_pattern(route)
            if not any(pattern.fullmatch(path) for path in paths):
                findings.append(
                    Finding(
                        TECHNICAL_DESIGN,
                        line,
                        "routes",
                        f"{name} ({route}) has no path in the URLs bullet",
                    )
                )
        elif not exempting(route):
            findings.append(
                Finding(
                    URLS,
                    0,
                    "routes",
                    f"{name} ({route}) is neither a document address nor an exempt prefix:"
                    " say where it belongs",
                )
            )
    # An exemption left behind by the routes it named would hide whatever comes to use it next.
    for prefix in sorted(set(exempt) - used):
        findings.append(Finding(URLS, 0, "routes", f"the exempt prefix {prefix!r} names no route"))
    return findings


# --- words --------------------------------------------------------------------------------


def _never_used(root: Path) -> tuple[list[str], list[str]]:
    """The English words and the Ukrainian stems of the glossary's § Words we never use."""
    lines = _lines(root, GLOSSARY)
    start, end = _section(lines, NEVER_HEADING)
    english: list[str] = []
    ukrainian: list[str] = []
    for line in lines[start:end]:
        # A paragraph's first bold span is its word list; emphasis later in it is prose.
        first = BOLD.search(line)
        if first:
            english.extend(word.strip() for word in first.group(1).split("·") if word.strip())
        if line.startswith(UKRAINIAN_LINE):
            rest = line[len(UKRAINIAN_LINE) :]
            ukrainian.extend(stem.strip() for stem in rest.split("·") if stem.strip())
    return english, ukrainian


def _inflected(word: str) -> re.Pattern[str]:
    """An English word in any of its forms: *save*, *saves*, *saved*, *saving*, *commits*,
    *committed* — its last letter doubled or dropped before an ending, as English spells it."""
    base = re.escape(word)
    if word.endswith("e"):
        forms = rf"{base}(?:s|d)?|{re.escape(word[:-1])}ing"
    else:
        forms = rf"{base}(?:s|es|ed|ing)?|{base}{re.escape(word[-1])}(?:ed|ing)"
    return re.compile(rf"(?<!\w)(?:{forms})(?!\w)", re.IGNORECASE)


def _stem_pattern(stem: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w){re.escape(stem)}", re.IGNORECASE)


def _term_pattern(term: str) -> re.Pattern[str]:
    """The Ukrainian term by each word's stem — its first letters, or the whole word if
    shorter — in order."""
    stems = [re.escape(word[:STEM_LETTERS]) + r"\w*" for word in term.split()]
    return re.compile(r"(?<!\w)" + r"\s+".join(stems), re.IGNORECASE)


def _pairs(root: Path) -> list[tuple[str, str]]:
    """Each glossary line's English and Ukrainian term; a term written with `/` is two."""
    pairs: list[tuple[str, str]] = []
    for line in _lines(root, GLOSSARY):
        match = PAIR_LINE.match(line)
        if not match:
            continue
        english = [t.strip() for t in match.group(1).split("/") if t.strip()]
        ukrainian = [t.strip() for t in match.group(2).split("/") if t.strip()]
        if len(english) == len(ukrainian):
            pairs.extend(zip(english, ukrainian, strict=True))
        else:
            pairs.extend((term, match.group(2).strip()) for term in english)
    return pairs


def _catalogue(lines: list[str]) -> Iterator[tuple[int, str, str]]:
    """Each line of the catalogue carrying text: its number, `msgid` or `msgstr`, the text."""
    field = ""
    for number, line in enumerate(lines, 1):
        if line.startswith("msgid"):
            field = "msgid"
        elif line.startswith("msgstr"):
            field = "msgstr"
        elif not line.startswith('"'):
            field = ""
            continue
        if field and '"' in line:
            text = line[line.index('"') + 1 : line.rindex('"')]
            yield number, field, CODE_SPAN.sub(" ", text)


def check_words(root: Path) -> list[Finding]:
    english, ukrainian = _never_used(root)
    english_patterns = [(word, _inflected(word)) for word in english]
    ukrainian_patterns = [(stem, _stem_pattern(stem)) for stem in ukrainian]
    findings: list[Finding] = []

    def scan(relative: str, lines: Iterator[tuple[int, str]], language: str) -> None:
        patterns = english_patterns if language == "en" else ukrainian_patterns
        for number, text in lines:
            for word, pattern in patterns:
                if pattern.search(text):
                    findings.append(
                        Finding(relative, number, "words", f'"{word}" is a word never used')
                    )

    for language in ("en", "uk"):
        folder = root / HELP / language
        if folder.is_dir():
            for page in sorted(folder.glob("*.md")):
                relative = page.relative_to(root).as_posix()
                scan(relative, _prose(page.read_text(encoding="utf-8").splitlines()), language)
    catalogue = list(_catalogue(_lines(root, CATALOGUE)))
    scan(CATALOGUE, ((n, t) for n, f, t in catalogue if f == "msgid"), "en")
    scan(CATALOGUE, ((n, t) for n, f, t in catalogue if f == "msgstr"), "uk")

    pairs = _pairs(root)
    english_folder = root / HELP / "en"
    if english_folder.is_dir():
        for page in sorted(english_folder.glob("*.md")):
            twin = root / HELP / "uk" / page.name
            if not twin.is_file():
                continue
            en_text = page.read_text(encoding="utf-8")
            uk_text = twin.read_text(encoding="utf-8")
            relative = twin.relative_to(root).as_posix()
            for en_term, uk_term in pairs:
                if _phrase(en_term).search(en_text) and not _term_pattern(uk_term).search(uk_text):
                    findings.append(
                        Finding(
                            relative,
                            0,
                            "words",
                            f'"{en_term}" is on the English page but "{uk_term}" is not here',
                        )
                    )
    return findings


# --- log ----------------------------------------------------------------------------------

LOG_GLOB = "decision-log*.md"
LOG_DIR = "docs/design-record"
ROW_ID = r"DL-\d+(?:-\d+)?"
ROW_IDS = re.compile(rf"\b{ROW_ID}\b")
ADR_IDS = re.compile(r"\bADR-\d{4}\b")
# The verbs by which a later row replaces an earlier one; *refines* keeps the old rule, so it is
# not among them.
SUPERSEDES = re.compile(r"\b(?:supersedes|corrects|revises|rewrites|resolves)\b", re.IGNORECASE)
# *Resolves* replaces a row only when its object is the row — `DL-0159`, `DL-0117's deferral`,
# `the title-page half of DL-0157` — never a question, a story, a contradiction or a tension.
RESOLVED_ROW = re.compile(rf"^\s+(?:the [\w -]+ half of )?{ROW_ID}\b")
# A clause ends at a semicolon or a sentence's end.
CLAUSE_END = re.compile(r";|\.\s")
PLAIN_STATUSES = {"active", "deferred", "withdrawn"}
# One status names one or more rows; only a partial supersession says which clause it replaced.
# A row whose decision now lives in an ADR names the ADR it was promoted to instead of rows.
SUPERSEDED_STATUS = re.compile(
    rf"^(?P<partly>partly )?superseded — (?:(?P<ids>{ROW_ID}(?:, {ROW_ID})*)"
    r"|promoted to (?P<adr>ADR-\d{4}))(?: \((?P<clause>[^()]+)\))?$"
)


@dataclass(frozen=True)
class Row:
    id: str
    path: str
    line: int
    question: str
    status: str


def _rows(root: Path) -> list[Row]:
    """Every decision row of every log in the design record, in file and line order."""
    rows: list[Row] = []
    folder = root / LOG_DIR
    if not folder.is_dir():
        return rows
    for log in sorted(folder.glob(LOG_GLOB)):
        relative = log.relative_to(root).as_posix()
        for number, line in enumerate(log.read_text(encoding="utf-8").splitlines(), 1):
            match = DECISION_ROW.match(line)
            if match:
                cells = _cells(line)
                question = cells[2] if len(cells) > 2 else ""
                rows.append(Row(match.group(1), relative, number, question, cells[-1]))
    return rows


def _opening(question: str) -> str:
    """The parenthetical a Question opens with, nested parentheses kept; empty without one."""
    if not question.startswith("("):
        return ""
    depth = 0
    for index, char in enumerate(question):
        depth += {"(": 1, ")": -1}.get(char, 0)
        if depth == 0:
            return question[1:index]
    return ""


def _superseded_by_row(question: str) -> tuple[set[str], set[str]]:
    """The rows and ADRs a Question says it supersedes, read only from the clauses of its opening
    parenthetical that use one of the verbs — so a row's own note that it was superseded by
    another is never read as superseding that other."""
    rows: set[str] = set()
    adrs: set[str] = set()
    for clause in CLAUSE_END.split(_opening(question)):
        verb = SUPERSEDES.search(clause)
        if not verb:
            continue
        named = clause[verb.end() :]
        if verb.group(0).lower() == "resolves" and not RESOLVED_ROW.match(named):
            continue
        rows.update(ROW_IDS.findall(named))
        adrs.update(ADR_IDS.findall(named))
    return rows, adrs


def _status_rows(status: str) -> set[str]:
    """The rows a supersession status names; empty for any other status."""
    match = SUPERSEDED_STATUS.match(status)
    return set(match.group("ids").split(", ")) if match and match.group("ids") else set()


def _adr_superseded_by(root: Path) -> dict[str, tuple[str, list[tuple[int, str]]]]:
    """Each ADR's file and the first id of each entry of its `superseded_by:` frontmatter."""
    adrs: dict[str, tuple[str, list[tuple[int, str]]]] = {}
    folder = root / ADRS
    if not folder.is_dir():
        return adrs
    for path in sorted(folder.iterdir()):
        name = ADR_FILE.match(path.name)
        if not name:
            continue
        relative = path.relative_to(root).as_posix()
        entries: list[tuple[int, str]] = []
        lines = path.read_text(encoding="utf-8").splitlines()
        inside = False
        for number, line in enumerate(lines[1:], 2):
            if line.strip() == "---":
                break
            if line.startswith("superseded_by:"):
                inside = True
                for cited in ANY_ID.findall(line):
                    entries.append((number, cited))
            elif inside and line.startswith("  - "):
                cited_ids = ANY_ID.findall(line)
                if cited_ids:
                    entries.append((number, cited_ids[0]))
            elif not line.startswith(" "):
                inside = False
        adrs[name.group(1)] = (relative, entries)
    return adrs


def check_log(root: Path) -> list[Finding]:
    rows = _rows(root)
    adrs = _adr_superseded_by(root)
    findings: list[Finding] = []
    first: dict[str, Row] = {}
    for row in rows:
        if row.id in first:
            seen = first[row.id]
            findings.append(
                Finding(row.path, row.line, "log", f"{row.id} is also at {seen.path}:{seen.line}")
            )
        else:
            first[row.id] = row
    for row in rows:
        status = SUPERSEDED_STATUS.match(row.status)
        if row.status not in PLAIN_STATUSES and not status:
            findings.append(
                Finding(
                    row.path,
                    row.line,
                    "log",
                    f'{row.id} has a status outside the set: "{row.status}"',
                )
            )
        if status and status.group("adr") and status.group("adr") not in adrs:
            findings.append(
                Finding(
                    row.path,
                    row.line,
                    "log",
                    f"{row.id} is promoted to {status.group('adr')}, which does not exist",
                )
            )
        replaced_rows, replaced_adrs = _superseded_by_row(row.question)
        for old in sorted(replaced_rows):
            if old not in first:
                findings.append(
                    Finding(
                        row.path, row.line, "log", f"{row.id} supersedes {old}, which no log holds"
                    )
                )
            elif row.id not in _status_rows(first[old].status):
                findings.append(
                    Finding(
                        row.path,
                        row.line,
                        "log",
                        f"{row.id} supersedes {old}, but {old}'s status does not name {row.id}",
                    )
                )
        for adr in sorted(replaced_adrs):
            listed = {cited for _, cited in adrs.get(adr, ("", []))[1]}
            if adr not in adrs:
                findings.append(
                    Finding(
                        row.path,
                        row.line,
                        "log",
                        f"{row.id} supersedes {adr}, which does not exist",
                    )
                )
            elif row.id not in listed:
                findings.append(
                    Finding(
                        row.path,
                        row.line,
                        "log",
                        f"{row.id} supersedes {adr}, but its superseded_by does not list {row.id}",
                    )
                )
        for new in sorted(_status_rows(row.status)):
            if new not in first:
                findings.append(
                    Finding(
                        row.path,
                        row.line,
                        "log",
                        f"{row.id}'s status names {new}, which no log holds",
                    )
                )
            elif row.id not in _superseded_by_row(first[new].question)[0]:
                findings.append(
                    Finding(
                        row.path,
                        row.line,
                        "log",
                        f"{row.id}'s status names {new}, "
                        f"but {new} does not say it supersedes {row.id}",
                    )
                )
    for adr, (relative, entries) in sorted(adrs.items()):
        for number, cited in entries:
            if cited not in first and cited not in adrs:
                findings.append(
                    Finding(
                        relative,
                        number,
                        "log",
                        f"{adr}'s superseded_by names {cited}, which does not exist",
                    )
                )
    return findings


# --- the script ---------------------------------------------------------------------------

CHECKS: dict[str, Callable[[Path], list[Finding]]] = {
    "ids": check_ids,
    "coverage": check_coverage,
    "pages": check_pages,
    "help": check_help,
    "routes": check_routes,
    "words": check_words,
    "log": check_log,
}


# Superseded rows cited as current whose correction needs the owner's reading — whether the claim
# still holds under what replaced the row — each printed as pending until it is decided, and
# failing the check once it is no longer found, so the list never outlives its findings.
WHY = "whether the claim still holds under what replaced the row"
PENDING: dict[tuple[str, str], tuple[int, str]] = {}


def pending(findings: list[Finding]) -> tuple[list[Finding], list[Finding], list[tuple[str, str]]]:
    """The findings that fail, those awaiting a decision, and the pending entries no longer as
    listed. An entry holds exactly as many citing lines as it names: a further citation of the id
    in that file, or one of them corrected, fails until the list says so."""
    found: dict[tuple[str, str], list[Finding]] = {}
    for finding in findings:
        key = (finding.path, finding.message.split()[0])
        if finding.check == "ids" and key in PENDING:
            found.setdefault(key, []).append(finding)
    held = [f for key, listed in found.items() if len(listed) == PENDING[key][0] for f in listed]
    failing = [f for f in findings if f not in held]
    stale = sorted(key for key in PENDING if len(found.get(key, [])) != PENDING[key][0])
    return failing, held, stale


def is_advice(finding: Finding) -> bool:
    """A glossary pair's finding: for a reader of the translation, never a failure."""
    return finding.check == "words" and "is on the English page" in finding.message


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Check the record's publishability rules.")
    parser.add_argument("--root", type=Path, default=ROOT, help="the tree to read")
    parser.add_argument("checks", nargs="*", metavar="CHECK", help=", ".join(CHECKS))
    args = parser.parse_args(argv)
    unknown = [check for check in args.checks if check not in CHECKS]
    if unknown:
        parser.error(f"unknown check(s): {', '.join(unknown)}; choose from {', '.join(CHECKS)}")
    root = args.root.resolve()
    if not root.is_dir():
        parser.error(f"no tree at {root}")
    findings: list[Finding] = []
    for name in args.checks or list(CHECKS):
        findings.extend(sorted(CHECKS[name](root), key=lambda f: (f.path, f.line, f.message)))
    # The pending list names the repository's own findings; a planted tree has none of them.
    repository = root == ROOT.resolve() and "ids" in (args.checks or list(CHECKS))
    failing, held, stale = pending(findings) if repository else (findings, [], [])
    # A glossary pair is matched by stems, which cannot read Ukrainian inflection or an English
    # homograph: its findings advise a reader and fail nothing.
    advice = [f for f in failing if is_advice(f)]
    failing = [f for f in failing if not is_advice(f)]
    for finding in failing:
        print(f"{finding.path}:{finding.line}: {finding.check}: {finding.message}")
    for finding in advice:
        print(f"{finding.path}:{finding.line}: advice: {finding.message}")
    for finding in held:
        print(f"{finding.path}:{finding.line}: pending: {finding.message}")
    for path, cited in stale:
        failing.append(Finding(path, 0, "ids", f"{cited} is pending but not cited as listed"))
        print(f"{path}:0: ids: {cited} is pending but not cited as listed")
    print(f"{len(failing)} finding(s)")
    return 1 if failing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
