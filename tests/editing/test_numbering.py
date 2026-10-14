"""The number pending work carries, and the number an acceptance gives (DL-0183, DL-0198, DL-0267,
DL-0268, DL-0272). People, titles and texts are synthetic examples."""

from __future__ import annotations

from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]


def test_pending_number(migrated_tenant: Any, member_of: Any, new_document: Any) -> None:
    from documents import bundle, gitstore, services
    from documents.identity import identity_for
    from documents.locks import document_lock
    from editing import numbering

    _, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    with schema_context(migrated_tenant.number):
        assert numbering.pending(document) == "0.0-1"
        repo = gitstore.open_repository(migrated_tenant.number, document.number)
        for n in range(2):
            head = gitstore.head(repo)
            assert head is not None
            frontmatter, body = bundle.parse(gitstore.read(repo, "document.md", head).decode())
            with document_lock(migrated_tenant.number, document.number):
                sha = gitstore.commit(
                    repo,
                    {"document.md": bundle.render(frontmatter, f"{body}Речення {n}.\n").encode()},
                    identity_for(author),
                    "Правка",
                    gitstore.Kind.EDIT,
                )
            services.derive_version(document, gitstore.commit_at(repo, sha), author)
        assert numbering.pending(document) == "0.0-3"
        assert numbering.latest(document) == "0.0-2"


def test_n_m(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    queued_authorship: list[Any],
) -> None:
    """The number the next acceptance carries (DL-0183): `N` the editions, counted from the
    passport's `approval` sections; `M` the acceptances since the last edition, plus one."""
    from django.utils import timezone

    from access.rights import Right
    from documents import bundle, gitstore, services
    from documents.identity import identity_for
    from documents.locks import document_lock
    from editing import holds, numbering
    from review import services as review

    _, reviewer, membership = member_of("the.reviewer@example.test")

    def commit(document: Any, path: str, text: str, kind: gitstore.Kind) -> str:
        repo = gitstore.open_repository(migrated_tenant.number, document.number)
        with document_lock(migrated_tenant.number, document.number):
            sha = gitstore.commit(
                repo, {path: text.encode()}, identity_for(reviewer), "Синтетична правка", kind
            )
            services.derive_version(document, gitstore.commit_at(repo, sha), reviewer)
        return sha

    def body_of(document: Any, text: str) -> str:
        repo = gitstore.open_repository(migrated_tenant.number, document.number)
        head = gitstore.head(repo)
        assert head is not None
        frontmatter, _ = holds.split(gitstore.read(repo, holds.BODY, head).decode())
        return holds.join(frontmatter, text)

    # Editions 0, acceptances 2.
    accepted = new_document(reviewer, "Синтетичний порядок А")
    link_group(accepted, [Right.ACCEPT], [membership], reviewer)
    with schema_context(migrated_tenant.number):
        for sentence in ("Перше синтетичне речення.\n", "Друге синтетичне речення.\n"):
            text = body_of(accepted, f"# Загальні положення\n\n{sentence}")
            commit(accepted, holds.BODY, text, gitstore.Kind.REVIEWER_EDIT)
            review.accept(accepted, reviewer)
        assert numbering.next_accepted(accepted) == "0.3"

    # Editions 1, acceptances 0.
    canonical = new_document(reviewer, "Синтетичний порядок Б")
    link_group(canonical, [Right.ACCEPT], [membership], reviewer)
    with schema_context(migrated_tenant.number):
        repo = gitstore.open_repository(migrated_tenant.number, canonical.number)
        head = gitstore.head(repo)
        assert head is not None
        passport = gitstore.read(repo, "passport.md", head).decode()
        entry = bundle.PassportEntry(
            kind="approval",
            number="1.0",
            at=timezone.now().replace(microsecond=0),
            by=str(reviewer.pk),
            version=head,
            edition="1.0",
        )
        commit(
            canonical,
            "passport.md",
            bundle.append_passport(passport, entry),
            gitstore.Kind.APPROVAL,
        )
        assert numbering.next_accepted(canonical) == "1.1"


@pytest.mark.fast
def test_the_number_follows_the_passport() -> None:
    """`M` restarts after each edition: 0.1, 0.2, then edition 1.0, then 1.1."""
    from datetime import UTC, datetime

    from documents import bundle
    from review.services import next_number

    def entry(kind: str, number: str) -> bundle.PassportEntry:
        return bundle.PassportEntry(
            kind=kind,
            number=number,
            at=datetime(2026, 9, 29, tzinfo=UTC),
            by="7f0c2a52-3f55-4c1e-9d1b-2f4a6b8c0d11",
            version="0" * 40,
            edition="1.0" if kind == "approval" else None,
        )

    assert next_number([]) == "0.1"
    two = [entry("acceptance", "0.1"), entry("acceptance", "0.2")]
    assert next_number(two) == "0.3"
    assert next_number([*two, entry("approval", "1.0")]) == "1.1"
    assert next_number([*two, entry("approval", "1.0"), entry("acceptance", "1.1")]) == "1.2"


# --- every number a version carries, read both ways (DL-0358) ------------------------------------
# The fixtures below are copied from `tests/review/conftest.py` and `tests/editions/conftest.py`:
# a version committed as a given person and kind, and the cast of an edition. People, groups and
# texts are synthetic examples; every address ends in `@example.test`.

STANDARD_REASON = "Synthetic reason: waiting for the board's decision"
STANDARD_FIRST = "# General provisions\n\nA request for approval is made in writing.\n"
STANDARD_SECOND = STANDARD_FIRST + "\nThe applicant attaches a synthetic record of service.\n"
STANDARD_THIRD = STANDARD_FIRST + "\nA request is considered within ten days.\n"
STANDARD_FOURTH = STANDARD_THIRD + "\nA copy of the decision goes to the applicant that day.\n"
STANDARD_FIFTH = STANDARD_FOURTH + "\nThe register of requests is kept by the officer in charge.\n"
STANDARD_SIXTH = STANDARD_FIFTH + "\nRequests are considered in the order they arrive.\n"


@pytest.fixture
def commit_version(migrated_tenant: Any) -> Any:
    """Commit `body` as the body of `document.md` on the document's head, as `user`, with the
    kind given; derive its `VERSION` row; return the row."""

    def commit(document: Any, user: Any, body: str, kind: str = "edit") -> Any:
        from documents import gitstore, services
        from documents.identity import identity_for
        from documents.locks import document_lock
        from editing import holds

        number = migrated_tenant.number
        with schema_context(number):
            repo = gitstore.open_repository(number, document.number)
            with document_lock(number, document.number):
                head = gitstore.head(repo)
                assert head is not None
                frontmatter, _ = holds.split(gitstore.read(repo, holds.BODY, head).decode())
                sha = gitstore.commit(
                    repo,
                    {holds.BODY: holds.join(frontmatter, body).encode("utf-8")},
                    identity_for(user),
                    "Synthetic edit",
                    gitstore.Kind(kind),
                )
                return services.derive_version(document, gitstore.commit_at(repo, sha), user)

    return commit


@pytest.fixture
def edition_cast(member_of: Any, new_document: Any, link_group: Any) -> Any:
    """A document linked to one group per role — `edit`, `accept`, and `freeze` with
    `make_canonical` — each member `<name>.synthetic@example.test`; a namespace of the document
    and the people by name."""
    from types import SimpleNamespace

    def make(
        editors: tuple[str, ...] = ("a",),
        reviewers: tuple[str, ...] = ("r",),
        approvers: tuple[str, ...] = ("p",),
    ) -> Any:
        from access.rights import Right

        people: dict[str, Any] = {}
        memberships: dict[str, Any] = {}
        for name in dict.fromkeys((*editors, *reviewers, *approvers)):
            _, people[name], memberships[name] = member_of(f"{name}.synthetic@example.test")
        creator = people[(editors or reviewers or approvers)[0]]
        document = new_document(creator)
        for names, rights in (
            (editors, [Right.EDIT]),
            (reviewers, [Right.ACCEPT]),
            (approvers, [Right.FREEZE, Right.MAKE_CANONICAL]),
        ):
            if names:
                link_group(document, rights, [memberships[n] for n in names], creator)
        return SimpleNamespace(document=document, people=people)

    return make


def standard_history(tenant: Any, edition_cast: Any, commit_version: Any) -> Any:
    """Created (`0.0`); three edits by `a` (`0.0-1` to `0.0-3`); accepted by `r` as `0.1`; a
    freeze and its unfreeze; one edit (`0.1-1`) accepted as `0.2`; a freeze and *make canonical*
    (`1.0`, approving `0.1-1`); two edits by `a` and `b` (`1.0-1`, `1.0-2`). `.versions` by
    pending number; `.acceptances`, `.edition`."""
    from types import SimpleNamespace

    from documents.models import Version
    from editions import services as editions
    from review import services as review

    cast = edition_cast(editors=("a", "b"))
    document, people = cast.document, cast.people
    versions: dict[str, Any] = {}
    with schema_context(tenant.number):
        versions["0.0"] = Version.objects.get(document=document, kind="created")
    versions["0.0-1"] = commit_version(document, people["a"], STANDARD_FIRST)
    versions["0.0-2"] = commit_version(document, people["a"], STANDARD_SECOND)
    versions["0.0-3"] = commit_version(document, people["a"], STANDARD_THIRD)
    with schema_context(tenant.number):
        first = review.accept(document, people["r"])
        editions.freeze(document, people["p"], STANDARD_REASON)
        editions.end_freeze(document, user=people["p"])
    versions["0.1-1"] = commit_version(document, people["a"], STANDARD_FOURTH)
    with schema_context(tenant.number):
        second = review.accept(document, people["r"])
        editions.freeze(document, people["p"], STANDARD_REASON)
        edition = editions.make_canonical(document, people["p"])
    versions["1.0-1"] = commit_version(document, people["a"], STANDARD_FIFTH)
    versions["1.0-2"] = commit_version(document, people["b"], STANDARD_SIXTH)
    return SimpleNamespace(
        document=document,
        people=people,
        versions=versions,
        acceptances=(first, second),
        edition=edition,
    )


def test_numbers_resolve_both_ways(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any
) -> None:
    """Each version row shows one number — a content version the highest stance it reached, a
    passport commit the number its section names — and every number a content version carried
    finds it again; a number finds no passport commit and nothing no version carries."""
    from documents.models import Version
    from editing.numbering import number_of, version_by_number

    history = standard_history(migrated_tenant, edition_cast, commit_version)
    document, v = history.document, history.versions
    first, second = history.acceptances
    content = {"created", "edit", "reviewer_edit"}

    with schema_context(migrated_tenant.number):
        rows = list(Version.objects.filter(document=document))
        shown = {row.pk: number_of(document, row) for row in rows}
        assert len(rows) == 10
        assert {pending: shown[row.pk] for pending, row in v.items()} == {
            "0.0": "0.0",
            "0.0-1": "0.0-1",
            "0.0-2": "0.0-2",
            "0.0-3": "0.1",
            "0.1-1": "1.0",
            "1.0-1": "1.0-1",
            "1.0-2": "1.0-2",
        }
        assert shown[first.version.pk] == "0.1"
        assert shown[second.version.pk] == "0.2"
        assert shown[history.edition.approval_version.pk] == "1.0"

        for row in rows:
            found = version_by_number(document, shown[row.pk])
            assert found is not None, shown[row.pk]
            assert found.kind in content, (shown[row.pk], found.kind)
            if row.kind in content:
                assert found.pk == row.pk, shown[row.pk]
        assert version_by_number(document, "0.2").pk == v["0.1-1"].pk
        assert version_by_number(document, "0.0-3").pk == v["0.0-3"].pk
        assert version_by_number(document, "0.1").pk == v["0.0-3"].pk
        assert version_by_number(document, "0.1-1").pk == v["0.1-1"].pk
        assert version_by_number(document, "1.0").pk == v["0.1-1"].pk
        assert version_by_number(document, "0.0").pk == v["0.0"].pk
        assert version_by_number(document, "9.9") is None
        assert version_by_number(document, "0.0-0") is None
