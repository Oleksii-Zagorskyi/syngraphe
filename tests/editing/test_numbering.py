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
