"""Fixtures for the review tests: a created document with groups linked to it, versions committed
on it as a given person and kind, an acceptance written straight to the passport and the rows, the
cast of a review, a reader of the document's repository, and the generated Ukrainian corpus.

People, group names and titles are synthetic examples; every text is invented.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from tenancy.schemas import schema_context

CONTENT_KINDS = ("edit", "reviewer_edit")


@pytest.fixture
def new_document(migrated_tenant: Any, repo_root: Path) -> Callable[..., Any]:
    """A document created through the service — repository, `created` commit, rows — in the
    migrated tenant's root folder, reaching only its creator until a group is linked."""

    def make(user: Any, title: str = "Synthetic approval procedure") -> Any:
        from documents import services
        from documents.models import DocumentType, Folder
        from identity.models import Language

        Language.objects.get_or_create(code="uk", defaults={"label": "uk", "actor_kind": "system"})
        with schema_context(migrated_tenant.number):
            return services.create_document(
                user,
                title,
                "uk",
                DocumentType.objects.get(code="document"),
                Folder.objects.get(number=1),
            )

    return make


@pytest.fixture
def link_group(migrated_tenant: Any) -> Callable[..., Any]:
    """Link to a document a new group holding `rights`, with `memberships` as its members. The
    group's name is a synthetic example."""

    made = iter(range(1, 1000))

    def link(document: Any, rights: list[Any], memberships: list[Any], by: Any) -> Any:
        from access.models import AccessGroup, DocumentGroup

        with schema_context(migrated_tenant.number):
            group = AccessGroup.objects.create(
                name=f"Synthetic group {next(made)}", created_by=by, actor_kind="user"
            )
            for right in rights:
                group.grant(right, by=by)
            for membership in memberships:
                group.add_member(membership, by=by)
            DocumentGroup.link(document, group, by=by)
        return group

    return link


@pytest.fixture
def commit_version(migrated_tenant: Any) -> Callable[..., Any]:
    """Commit `body` as the body of `document.md` on the document's head, as `user`, with the
    kind given — `edit` or `reviewer_edit` — rather than decided from the rights as a finish
    decides it; derive its `VERSION` row; return the row. `body` is in the normal form: one
    sentence per line, a blank line between paragraphs. `files` are further paths written, or
    removed by `None`, in the same commit; `appendices` and `attachments`, when given, replace the
    frontmatter's lists of them."""

    def commit(
        document: Any,
        user: Any,
        body: str,
        kind: str = "edit",
        *,
        summary: str = "Synthetic edit",
        files: Mapping[str, bytes | None] | None = None,
        appendices: list[dict[str, Any]] | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> Any:
        from documents import gitstore, services
        from documents.identity import identity_for
        from documents.locks import document_lock
        from editing import holds

        assert kind in CONTENT_KINDS, kind
        number = migrated_tenant.number
        with schema_context(number):
            repo = gitstore.open_repository(number, document.number)
            with document_lock(number, document.number):
                head = gitstore.head(repo)
                assert head is not None
                frontmatter, _ = holds.split(gitstore.read(repo, holds.BODY, head).decode())
                if appendices is not None:
                    frontmatter["appendices"] = appendices
                if attachments is not None:
                    frontmatter["attachments"] = attachments
                sha = gitstore.commit(
                    repo,
                    {holds.BODY: holds.join(frontmatter, body).encode("utf-8"), **(files or {})},
                    identity_for(user),
                    summary,
                    gitstore.Kind(kind),
                )
                return services.derive_version(document, gitstore.commit_at(repo, sha), user)

    return commit


@pytest.fixture
def accepted_directly(migrated_tenant: Any) -> Callable[..., Any]:
    """An acceptance of the document's newest content version by `reviewer`, written without the
    acceptance service: the passport section appended and committed as `acceptance`, its
    `VERSION` row derived, the `ACCEPTANCE` row written with nothing left to disclose. For the
    tests that need an accepted base, not for the tests of accepting."""

    def accept(document: Any, reviewer: Any) -> Any:
        from django.utils import timezone

        from documents import bundle, gitstore, services
        from documents.identity import identity_for
        from documents.locks import document_lock
        from documents.models import Version
        from review.models import Acceptance

        number = migrated_tenant.number
        with schema_context(number):
            repo = gitstore.open_repository(number, document.number)
            with document_lock(number, document.number):
                head = gitstore.head(repo)
                assert head is not None
                content = [
                    commit
                    for commit in gitstore.history(repo)
                    if gitstore.kind_of(commit.message)
                    in (gitstore.Kind.CREATED, gitstore.Kind.EDIT, gitstore.Kind.REVIEWER_EDIT)
                ]
                passport = gitstore.read(repo, "passport.md", head).decode("utf-8")
                earlier = [e for e in bundle.passport_entries(passport) if e.kind == "acceptance"]
                # No edition in these tests, so the number is 0.M.
                accepted_number = f"0.{len(earlier) + 1}"
                now = timezone.now().replace(microsecond=0)
                entry = bundle.PassportEntry(
                    kind="acceptance",
                    number=accepted_number,
                    at=now,
                    by=str(reviewer.pk),
                    version=str(content[-1].id),
                )
                sha = gitstore.commit(
                    repo,
                    {"passport.md": bundle.append_passport(passport, entry).encode("utf-8")},
                    identity_for(reviewer, at=now),
                    f"Accepted as {accepted_number}",
                    gitstore.Kind.ACCEPTANCE,
                )
                version = services.derive_version(document, gitstore.commit_at(repo, sha), reviewer)
            accepted_from = Version.objects.get(
                document=document,
                commit_sha=earlier[-1].version if earlier else str(content[0].id),
            )
            return Acceptance.objects.create(
                version=version,
                accepted_from=accepted_from,
                number=accepted_number,
                reviewer=reviewer,
                at=now,
                notices_computed_at=now,
            )

    return accept


@dataclass
class Cast:
    """The people of a review and their document: editors in one linked group holding `edit`,
    reviewers in another holding `accept`; the document created by the first editor, or by the
    first reviewer when there is none."""

    document: Any
    people: dict[str, Any]
    memberships: dict[str, Any]
    groups: dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, name: str) -> Any:
        return self.people[name]


@pytest.fixture
def cast(member_of: Any, new_document: Any, link_group: Any) -> Callable[..., Cast]:
    """`cast(editors=("a", "b"), reviewers=("r",))`: the members, each signed in as
    `<name>.synthetic@example.test`, and a document linked to a group per role that has anyone
    in it. A cast with no reviewer is a document no linked group holds *accept* on."""

    def make(editors: tuple[str, ...] = ("a",), reviewers: tuple[str, ...] = ("r",)) -> Cast:
        from access.rights import Right

        people: dict[str, Any] = {}
        memberships: dict[str, Any] = {}
        for name in (*editors, *reviewers):
            _, people[name], memberships[name] = member_of(f"{name}.synthetic@example.test")
        creator = people[(editors or reviewers)[0]]
        document = new_document(creator)
        made = Cast(document, people, memberships)
        if editors:
            made.groups["editors"] = link_group(
                document, [Right.EDIT], [memberships[n] for n in editors], creator
            )
        if reviewers:
            made.groups["reviewers"] = link_group(
                document, [Right.ACCEPT], [memberships[n] for n in reviewers], creator
            )
        return made

    return make


class DocumentRepository:
    """Read-only access to a document's repository, for assertions."""

    def __init__(self, tenant_number: int) -> None:
        self.tenant_number = tenant_number

    def _repo(self, document: Any) -> Any:
        from documents import gitstore

        return gitstore.open_repository(self.tenant_number, document.number)

    def head(self, document: Any) -> str:
        from documents import gitstore

        head = gitstore.head(self._repo(document))
        assert head is not None
        return head

    def read(self, document: Any, path: str = "document.md", commit: str | None = None) -> str:
        """The file at `commit`, or at the head."""
        from documents import gitstore

        at = commit if commit is not None else self.head(document)
        return gitstore.read(self._repo(document), path, at).decode("utf-8")

    def lines(self, document: Any, commit: str, path: str = "document.md") -> list[str]:
        """The file's lines at `commit`, the frontmatter included: line `n` is `lines[n - 1]`."""
        return self.read(document, path, commit).split("\n")

    def kinds(self, document: Any) -> list[str]:
        """The kind of every commit on `main`, oldest first."""
        from documents import gitstore

        return [
            str(gitstore.kind_of(commit.message))
            for commit in gitstore.history(self._repo(document))
        ]

    def parent(self, document: Any, commit: str) -> str:
        from documents import gitstore

        return str(gitstore.commit_at(self._repo(document), commit).parents[0].id)


@pytest.fixture
def repository(migrated_tenant: Any) -> DocumentRepository:
    return DocumentRepository(migrated_tenant.number)


@pytest.fixture(scope="session")
def corpus_ukr(
    tmp_path_factory: pytest.TempPathFactory, ukrainian_corpus: Callable[[Path], tuple[Path, Path]]
) -> dict[str, Any]:
    """The Ukrainian history as a bare repository, and its record of who wrote what."""
    repo, truth = ukrainian_corpus(tmp_path_factory.mktemp("review-corpus"))
    return {"repo": repo, "truth": json.loads(truth.read_text(encoding="utf-8"))}
