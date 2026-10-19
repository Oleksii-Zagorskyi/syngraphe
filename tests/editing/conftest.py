"""Fixtures for the editing tests: the whitelist's case list, shared by the server's and the
editor's halves of the suite, and a created document with groups linked to it. Titles and group
names are synthetic examples."""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

CASES_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "whitelist" / "cases.json"


@pytest.fixture(scope="session")
def cases() -> list[dict[str, Any]]:
    """Every case of `tests/fixtures/whitelist/cases.json`, in its order."""
    with CASES_PATH.open(encoding="utf-8") as file:
        loaded: list[dict[str, Any]] = json.load(file)
    return loaded


@pytest.fixture(scope="session")
def expected_refusals() -> Callable[[dict[str, Any]], list[list[Any]]]:
    """A case's refusals as `[code, line]` pairs, the shape both halves compare."""
    return lambda case: [[r["code"], r["line"]] for r in case.get("refusals", [])]


@pytest.fixture
def new_document(migrated_tenant: Any, repo_root: Path) -> Callable[..., Any]:
    """A document created through the service — repository, `created` commit, rows — in the
    migrated tenant's root folder, reaching only its creator until a group is linked."""

    def make(user: Any, title: str = "Synthetic approval procedure") -> Any:
        from documents import services
        from documents.models import DocumentType, Folder
        from identity.models import Language
        from tenancy.schemas import schema_context

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
    """Link to a document a new group holding `rights`, with `memberships` as its members."""

    made = iter(range(1, 1000))

    def link(document: Any, rights: list[Any], memberships: list[Any], by: Any) -> Any:
        from access.models import AccessGroup, DocumentGroup
        from tenancy.schemas import schema_context

        with schema_context(migrated_tenant.number):
            group = AccessGroup.objects.create(
                name=f"Editors {next(made)}", created_by=by, actor_kind="user"
            )
            for right in rights:
                group.grant(right, by=by)
            for membership in memberships:
                group.add_member(membership, by=by)
            DocumentGroup.link(document, group, by=by)
        return group

    return link


# The review tests' `commit_version`, loaded from their conftest so versions are committed alike,
# with further files beside the body.
_spec = importlib.util.spec_from_file_location(
    "review_fixtures", Path(__file__).resolve().parents[1] / "review" / "conftest.py"
)
assert _spec is not None and _spec.loader is not None
_review = importlib.util.module_from_spec(_spec)
# Registered before it runs: its dataclass looks its own module up by name.
sys.modules[_spec.name] = _review
_spec.loader.exec_module(_review)

commit_version = _review.commit_version


@pytest.fixture
def canonical_pdf(
    migrated_tenant: Any, settings: Any, tmp_path: Path, queued_exports: list[tuple[Any, ...]]
) -> Callable[..., list[str]]:
    """`made(document, client, user)`: `document`, its edits accepted, frozen and made canonical
    by `user`, then exported as a canonical PDF by `client`, the job run as `render` runs it;
    each page's text, its whitespace folded."""
    from pypdf import PdfReader

    from tenancy.schemas import schema_context

    settings.EXPORT_ROOT = tmp_path / "exports"
    number = migrated_tenant.number

    def made(document: Any, client: Any, user: Any) -> list[str]:
        from editions import services as editions
        from rendering.export import job
        from rendering.models import ExportJob

        with schema_context(number):
            editions.freeze(document, user, "Synthetic reason")
            editions.make_canonical(document, user)
        asked = client.post(
            f"/document/{document.number}/export/",
            {"document": "on", "format": "pdf", "view": "canonical"},
        )
        assert asked.status_code == 302
        queued = queued_exports[-1][1]
        with schema_context(number):
            job.run(queued, number)
            row = ExportJob.objects.get(pk=queued)
        assert row.state == "done", row.failure_reason
        pages = PdfReader(str(Path(settings.EXPORT_ROOT) / row.artifact_ref)).pages
        return [" ".join(page.extract_text().split()) for page in pages]

    return made
