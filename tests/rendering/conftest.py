"""Fixtures for the rendering tests: the editions tests' cast and versions, loaded from their own
conftest so a document reaches an edition here as it does there.

People, group names and titles are synthetic examples; every text is invented.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tenancy.schemas import schema_context

_spec = importlib.util.spec_from_file_location(
    "editions_fixtures", Path(__file__).resolve().parents[1] / "editions" / "conftest.py"
)
assert _spec is not None and _spec.loader is not None
_editions = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _editions
_spec.loader.exec_module(_editions)

new_document = _editions.new_document
link_group = _editions.link_group
commit_version = _editions.commit_version
edition_cast = _editions.edition_cast


@pytest.fixture
def exports(
    settings: Any, tmp_path: Path, queued_exports: list[tuple[Any, ...]]
) -> list[tuple[Any, ...]]:
    """The exports root in a scratch folder, and what was queued, from the suite's own guard: a
    test runs a job itself, in its tenant's schema."""
    settings.EXPORT_ROOT = tmp_path / "exports"
    return queued_exports


# --- the export tests' documents, readers and jobs ----------------------------------------------

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "render"
FIRST = "# General provisions\n\nA request for approval is made in writing.\n"
SECOND = FIRST + "\nA copy of the decision goes to the applicant that day.\n"
THIRD = SECOND + "\nThe register of requests is kept by the officer in charge.\n"
FOURTH = THIRD + "\nA request is considered within ten days.\n"


def canonical(tenant: int, people: Any, commit_version: Any, body: str) -> Any:
    """`body` committed, accepted and made canonical; the edition."""
    from editions import services as editions
    from review import services as review

    commit_version(people.document, people["a"], body, "edit")
    with schema_context(tenant):
        review.accept(people.document, people["r"])
        editions.freeze(people.document, people["p"], "Synthetic reason")
        return editions.make_canonical(people.document, people["p"])


def reader(member_of: Any, link_group: Any, people: Any, rights: list[Any], name: str) -> Any:
    """`(client, user)` for a member whose one group on the document holds `rights`."""
    client, user, membership = member_of(f"{name}.synthetic@example.test")
    link_group(people.document, rights, [membership], people["a"])
    return client, user


def run_job(tenant: int, job_id: Any) -> Any:
    """The job run in its tenant, as the render worker runs it; the row after."""
    from rendering.export import job
    from rendering.models import ExportJob

    with schema_context(tenant):
        job.run(job_id, tenant)
        return ExportJob.objects.select_related("document").get(pk=job_id)


def attach(tenant: int, people: Any, body: str, data: bytes, *, title_page: bool = False) -> Any:
    """`body` committed with one attachment, `time-limits.txt` holding `data` — and the title page
    switched on when asked — as the editor; the version."""
    import hashlib

    from documents import bundle, gitstore, services
    from documents.identity import identity_for
    from documents.locks import document_lock

    document = people.document
    with schema_context(tenant):
        repo = gitstore.open_repository(tenant, document.number)
        with document_lock(tenant, document.number):
            head = gitstore.head(repo)
            assert head is not None
            frontmatter, _ = bundle.parse(gitstore.read(repo, "document.md", head).decode())
            frontmatter.title_page = title_page
            frontmatter.attachments = [
                {
                    "number": 1,
                    "title": "List of time limits",
                    "file_name": "time-limits.txt",
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "bytes": len(data),
                }
            ]
            sha = gitstore.commit(
                repo,
                {"document.md": bundle.render(frontmatter, body).encode(), "attachments/1": data},
                identity_for(people["a"]),
                "Synthetic edit with a file",
                gitstore.Kind.EDIT,
            )
            return services.derive_version(document, gitstore.commit_at(repo, sha), people["a"])


def switched(tenant: int, people: Any, **changes: Any) -> None:
    """The head's frontmatter changed as `changes` say, committed as the editor."""
    import dataclasses

    from documents import bundle, gitstore, services
    from documents.identity import identity_for
    from documents.locks import document_lock

    document = people.document
    with schema_context(tenant):
        repo = gitstore.open_repository(tenant, document.number)
        with document_lock(tenant, document.number):
            head = gitstore.head(repo)
            assert head is not None
            frontmatter, body = bundle.parse(gitstore.read(repo, "document.md", head).decode())
            changed = dataclasses.replace(frontmatter, **changes)
            sha = gitstore.commit(
                repo,
                {"document.md": bundle.render(changed, body).encode()},
                identity_for(people["a"]),
                "Synthetic change of the frontmatter",
                gitstore.Kind.EDIT,
            )
            services.derive_version(document, gitstore.commit_at(repo, sha), people["a"])


@pytest.fixture
def kit() -> SimpleNamespace:
    """The export tests' texts and helpers: `canonical`, `reader`, `run_job`, `attach`,
    `switched`, the fixtures' folder."""
    return SimpleNamespace(
        FIXTURES=FIXTURES,
        FIRST=FIRST,
        SECOND=SECOND,
        THIRD=THIRD,
        FOURTH=FOURTH,
        canonical=canonical,
        reader=reader,
        run_job=run_job,
        attach=attach,
        switched=switched,
    )


def canonical_with(
    tenant: int, people: Any, commit_version: Any, body: str, files: dict[str, bytes | None]
) -> Any:
    """`body` committed with `files` beside it, accepted and made canonical; the edition."""
    from editions import services as editions
    from review import services as review

    commit_version(people.document, people["a"], body, "edit", files=files)
    with schema_context(tenant):
        review.accept(people.document, people["r"])
        editions.freeze(people.document, people["p"], "Synthetic reason")
        return editions.make_canonical(people.document, people["p"])


@pytest.fixture
def pictures(invented_image: Any) -> SimpleNamespace:
    """Invented images for the rendering tests, each with the path it is stored at and the
        paragraph that shows it: `make(shade, kind="png", **more)`, `more` the width, height and
    orientation `invented_image` takes; and `canonical_with`."""
    import hashlib

    def make(shade: int, kind: str = "png", **more: Any) -> SimpleNamespace:
        from editing import images

        data = images.check(invented_image(kind, shade=shade, **more)).data
        ext = {"png": "png", "jpeg": "jpg", "gif": "gif"}[kind]
        path = f"images/{hashlib.sha256(data).hexdigest()}.{ext}"
        return SimpleNamespace(
            data=data,
            path=path,
            name=path[7:],
            paragraph=f"\n![A synthetic plan {shade}]({path})\n",
        )

    return SimpleNamespace(make=make, canonical_with=canonical_with)
