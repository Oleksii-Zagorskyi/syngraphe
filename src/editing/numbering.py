"""Version numbers, derived and never stored as the record (DL-0183, DL-0198, DL-0267, DL-0272).

An acceptance is `N.M`: N the canonical editions before it, M the acceptances since the last one; an
edition is `N.0`. Pending work is the later of the latest edition's and the latest acceptance's
number, a hyphen, and the count of content versions since it — `2.0-1` is the first version after
edition `2.0` (DL-0267); before the first acceptance that number is `0.0`, and the `created` commit
is not counted (DL-0268). The next acceptance's number is counted from the passport's sections,
pending work from the run; order within a document's history is read from git, since commit times
share seconds.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from documents.models import Document, Version, VersionKind

CONTENT = (VersionKind.EDIT, VersionKind.REVIEWER_EDIT)
BEFORE_ANY_ACCEPTANCE = "0.0"


def edition(document: Document) -> str | None:
    """The latest edition's number, or `None` before the first."""
    from editions.models import Edition
    from review.services import number_key

    numbers = Edition.objects.filter(version__document=document).values_list("number", flat=True)
    return max(numbers, key=number_key, default=None)


def accepted(document: Document) -> str:
    """The number pending work counts from: the later of the latest edition's and the latest
    acceptance's, `0.0` before either. The edition's version is the latest accepted one, so the
    run it counts is the same (DL-0267)."""
    from review.services import latest_acceptance, number_key

    acceptance = latest_acceptance(document)
    found = [n for n in (edition(document), acceptance and acceptance.number) if n]
    return max(found, key=number_key, default=BEFORE_ANY_ACCEPTANCE)


def content_versions(document: Document) -> int:
    """The content versions since the latest acceptance: the run, as the tab lists it."""
    from review.services import run

    return len(run(document))


def next_accepted(document: Document) -> str:
    """The number the document's next acceptance carries: `N` the editions made, `M` the
    acceptances since the latest one, plus one — `0.1` for the first (DL-0183) — read from the
    passport at the head."""
    from django.db import connection

    from documents import gitstore
    from review.services import next_number, passport_at
    from tenancy.schemas import current_tenant

    tenant_number = current_tenant(connection)
    if tenant_number is None:
        raise RuntimeError("a number is read inside a tenant's schema")
    repo = gitstore.open_repository(tenant_number, document.number)
    head = gitstore.head(repo)
    return next_number(passport_at(repo, head) if head is not None else [])


def pending(document: Document, *, ahead: int = 0) -> str:
    """The number the next content version will carry — or, with `ahead`, the one that many
    versions after it: a commit already made whose row is not derived yet."""
    return f"{accepted(document)}-{content_versions(document) + 1 + ahead}"


def latest(document: Document) -> str:
    """The number of the newest content version."""
    return f"{accepted(document)}-{content_versions(document)}"


# A version's number as a reader types it: `N.M`, or `N.M-X` for pending work (DL-0183, DL-0267).
NUMBER = re.compile(r"^(0|[1-9][0-9]{0,9})\.(0|[1-9][0-9]{0,9})(?:-([1-9][0-9]{0,9}))?$")


@dataclass(frozen=True)
class Numbered:
    """One commit of a document's history as its numbers read it: its kind, the number it shows,
    and — for a passport commit — the content version its section decides on."""

    sha: str
    kind: str
    number: str
    decides: str | None = None


@dataclass(frozen=True)
class History:
    """A document's history, oldest first, each commit numbered (`commits`), and every number a
    content version has ever carried — its pending number, the acceptance's, the edition's —
    mapped to its commit (`aliases`)."""

    commits: tuple[Numbered, ...]
    aliases: dict[str, str]

    def number(self, sha: str) -> str | None:
        return next((c.number for c in self.commits if c.sha == sha), None)


def history(document: Document) -> History:
    """The document's history numbered from git and the passport alone (DL-0183, DL-0267): the
    commits in git's order, each passport commit paired with its section in the passport at the
    head, since each appended one. A content version shows the highest stance it reached — the
    edition's number where it is an edition, else the acceptance's where it was accepted, else
    its pending number; `created` is `0.0` (DL-0358); a passport commit shows the number its
    section names, a return the number of the version it returned. `ValueError` when the passport
    does not read or disagrees with the commits."""
    from django.db import connection

    from documents import bundle, gitstore
    from review.services import PASSPORT
    from tenancy.schemas import current_tenant

    tenant_number = current_tenant(connection)
    if tenant_number is None:
        raise RuntimeError("a number is read inside a tenant's schema")
    repo = gitstore.open_repository(tenant_number, document.number)
    head = gitstore.head(repo)
    if head is None:
        return History((), {})
    sections = iter(bundle.passport_entries(gitstore.read(repo, PASSPORT, head).decode("utf-8")))
    kinds: list[tuple[str, str, bundle.PassportEntry | None]] = []
    content: set[str] = set()
    for commit in gitstore.history(repo):
        found = gitstore.kind_of(commit.message)
        if found is None:
            raise ValueError(f"a commit of no kind: {commit.id}")
        section = None
        if found in (gitstore.Kind.ACCEPTANCE, gitstore.Kind.RETURN, gitstore.Kind.APPROVAL):
            section = next(sections, None)
            if section is None or section.kind != found.value:
                raise ValueError(f"a passport commit without its section: {commit.id}")
            if section.version not in content:
                raise ValueError(f"a section naming no earlier content version: {commit.id}")
        else:
            content.add(str(commit.id))
        kinds.append((str(commit.id), found.value, section))
    if next(sections, None) is not None:
        raise ValueError("a passport section without its commit")

    shown: dict[str, str] = {}
    aliases: dict[str, str] = {}
    # A return shows the number the version it returned carried then, not one reached later.
    returned: dict[str, str] = {}
    base, count = BEFORE_ANY_ACCEPTANCE, 0
    for sha, kind, section in kinds:
        if kind == VersionKind.CREATED:
            shown[sha] = BEFORE_ANY_ACCEPTANCE
            aliases[BEFORE_ANY_ACCEPTANCE] = sha
        elif kind in CONTENT:
            count += 1
            shown[sha] = f"{base}-{count}"
            aliases[shown[sha]] = sha
        elif section is not None and kind == VersionKind.ACCEPTANCE and section.number:
            shown[section.version] = shown[sha] = section.number
            aliases[section.number] = section.version
            base, count = section.number, 0
        elif section is not None and kind == VersionKind.RETURN:
            returned[sha] = shown.get(section.version, "")
        elif section is not None and kind == VersionKind.APPROVAL:
            edition = section.edition or section.number or ""
            shown[section.version] = shown[sha] = edition
            aliases[edition] = section.version
            base, count = edition, 0
    commits = []
    for sha, kind, section in kinds:
        decides = section.version if section is not None else None
        number = returned[sha] if kind == VersionKind.RETURN else shown[sha]
        commits.append(Numbered(sha, kind, number, decides))
    return History(tuple(commits), aliases)


def number_of(document: Document, version: Version) -> str:
    """The number `version` shows: for a content version the highest stance it reached, for a
    passport commit the number its section names, for a return the number of the version it
    returned (DL-0183, DL-0267, DL-0358)."""
    found = history(document).number(version.commit_sha)
    if found is None:
        raise LookupError(f"not in the document's history: {version.commit_sha}")
    return found


def version_by_number(document: Document, number: str) -> Version | None:
    """The content version — or the `created` one — any of whose numbers is `number`: `0.0-3`
    and the `0.1` that accepted it are one version. Never a passport commit; `None` for a number
    no version carries."""
    if not NUMBER.fullmatch(number):
        return None
    sha = history(document).aliases.get(number)
    if sha is None:
        return None
    return Version.objects.filter(
        document=document, commit_sha=sha, kind__in=(VersionKind.CREATED, *CONTENT)
    ).first()
