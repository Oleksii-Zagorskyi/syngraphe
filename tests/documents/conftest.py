"""The generated corpus, a copy of the run's own in a temporary directory."""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture(scope="session")
def corpus_ukr(
    tmp_path_factory: pytest.TempPathFactory, ukrainian_corpus: Callable[[Path], tuple[Path, Path]]
) -> dict[str, Any]:
    """The Ukrainian history as a bare repository, and its record of who wrote what."""
    repo, truth = ukrainian_corpus(tmp_path_factory.mktemp("corpus"))
    return {"repo": repo, "truth": json.loads(truth.read_text(encoding="utf-8"))}


class DirStore:
    """A backup store in a local directory, standing in for the off-host one."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.puts: list[str] = []

    def put(self, local: Path, name: str) -> None:
        target = self.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(local.read_bytes())
        self.puts.append(name)

    def names(self, prefix: str) -> list[str]:
        base = self.root / prefix
        if not base.exists():
            return []
        return sorted(str(p.relative_to(self.root)) for p in base.rglob("*") if p.is_file())

    def get(self, name: str) -> bytes:
        return (self.root / name).read_bytes()

    def delete(self, name: str) -> None:
        (self.root / name).unlink()


@pytest.fixture
def store(tmp_path: Path) -> DirStore:
    root = tmp_path / "store"
    root.mkdir()
    return DirStore(root)


@pytest.fixture
def state_dir(tmp_path: Path, settings: Any) -> Path:
    directory = tmp_path / "backup-state"
    directory.mkdir()
    settings.BACKUP_STATE_DIR = directory
    return directory


# The alpha preview (DL-0348): an operator whose group creates and accepts, readers whose
# groups hold one viewing right, and a document accepted as `0.1` whose version carries attachments
# as `with-parts-ukr/` lays them. People, group names and titles are synthetic examples; every
# text is invented.

OPERATOR = "operator.synthetic@example.test"
WITH_PARTS = Path(__file__).resolve().parents[1] / "fixtures" / "documents" / "with-parts-ukr"
PARTS_TITLE = "Положення про облік доступів (синтетичний приклад)"


def _with_parts_body() -> str:
    from documents import bundle

    _, body = bundle.parse((WITH_PARTS / "document.md").read_text(encoding="utf-8"))
    return body


def _scheme() -> tuple[str, str, bytes]:
    """Attachment 1 of `with-parts-ukr/`: its title, its file name and its bytes."""
    return ("Схема погодження", "scheme.txt", (WITH_PARTS / "attachments" / "1").read_bytes())


@pytest.fixture
def operator(migrated_tenant: Any, member_of: Any, repo_root: Path) -> Any:
    """The operator: a member of *Operators* (a synthetic example), a group holding *create and
    edit* and *accept*, linked to nothing yet. `.client`, `.user`, `.membership`, `.group`."""
    from types import SimpleNamespace

    from access.models import AccessGroup
    from access.rights import Right
    from tenancy.schemas import schema_context

    client, user, membership = member_of(OPERATOR)
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(
            name="Operators (synthetic example)", created_by=user, actor_kind="user"
        )
        group.grant(Right.CREATE_AND_EDIT, by=user)
        group.grant(Right.ACCEPT, by=user)
        group.add_member(membership, by=user)
    return SimpleNamespace(client=client, user=user, membership=membership, group=group)


@pytest.fixture
def reader_in(migrated_tenant: Any, member_of: Any) -> Any:
    """`reader_in(right, *documents)`: a member of a new group holding `right` alone, linked to
    each document given; `(client, user)`. The group's name and the address are synthetic."""
    from access.models import AccessGroup, DocumentGroup
    from tenancy.schemas import schema_context

    made = iter(range(1, 1000))

    def make(right: Any, *documents: Any) -> tuple[Any, Any]:
        n = next(made)
        client, user, membership = member_of(f"reader{n}.synthetic@example.test")
        with schema_context(migrated_tenant.number):
            group = AccessGroup.objects.create(
                name=f"Readers {n} (synthetic example)", actor_kind="system"
            )
            group.grant(right, by=None)
            group.add_member(membership, by=None)
            for document in documents:
                DocumentGroup.link(document, group, by=None)
        return client, user

    return make


@pytest.fixture
def commit_parts(migrated_tenant: Any) -> Any:
    """`commit_parts(document, user, body, attachments, tamper=False)`: one `reviewer_edit`
    version whose `document.md` holds `body` and lists `attachments` — `(title, file_name, data)`,
    numbered from 1 — each committed at `attachments/<n>` through `gitstore.commit`, as
    `with-parts-ukr/` lays them; its row and caches derived. With `tamper`, each blob differs
    from the hash and size its entry records. Returns the `VERSION` row."""
    import dataclasses
    import hashlib

    from documents import bundle, gitstore, services
    from documents.identity import identity_for
    from documents.locks import document_lock
    from tenancy.schemas import schema_context

    def commit(
        document: Any,
        user: Any,
        body: str,
        attachments: list[tuple[str, str, bytes]],
        *,
        tamper: bool = False,
    ) -> Any:
        number = migrated_tenant.number
        with schema_context(number):
            repo = gitstore.open_repository(number, document.number)
            with document_lock(number, document.number):
                head = gitstore.head(repo)
                assert head is not None
                frontmatter, _ = bundle.parse(gitstore.read(repo, "document.md", head).decode())
                entries = [
                    {
                        "number": n,
                        "title": title,
                        "file_name": file_name,
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "bytes": len(data),
                    }
                    for n, (title, file_name, data) in enumerate(attachments, 1)
                ]
                text = bundle.render(dataclasses.replace(frontmatter, attachments=entries), body)
                files = {"document.md": text.encode("utf-8")}
                for n, (_, _, data) in enumerate(attachments, 1):
                    files[f"attachments/{n}"] = data + (b" altered" if tamper else b"")
                sha = gitstore.commit(
                    repo,
                    files,
                    identity_for(user),
                    "Synthetic edit",
                    gitstore.Kind.REVIEWER_EDIT,
                )
                return services.derive_version(document, gitstore.commit_at(repo, sha), user)

    return commit


@pytest.fixture
def accepted_with_parts(migrated_tenant: Any, operator: Any, commit_parts: Any) -> Any:
    """`accepted_with_parts(attachments=None, tamper=False)`: a document created by the operator,
    linked to *Operators*, one version with `with-parts-ukr/`'s body and attachments —
    `scheme.txt` by default — accepted as `0.1` through the acceptance service. `.document`,
    `.version` (the accepted content version), `.acceptance`, `.body`, `.attachments`."""
    from types import SimpleNamespace

    from access.models import DocumentGroup
    from documents import services
    from documents.models import DocumentType, Folder
    from identity.models import Language
    from review import services as review
    from tenancy.schemas import schema_context

    def make(
        attachments: list[tuple[str, str, bytes]] | None = None, *, tamper: bool = False
    ) -> Any:
        parts = [_scheme()] if attachments is None else attachments
        body = _with_parts_body()
        Language.objects.get_or_create(code="uk", defaults={"label": "uk", "actor_kind": "system"})
        with schema_context(migrated_tenant.number):
            document = services.create_document(
                operator.user,
                PARTS_TITLE,
                "uk",
                DocumentType.objects.get(code="document"),
                Folder.objects.get(number=1),
            )
            DocumentGroup.link(document, operator.group, by=operator.user)
        version = commit_parts(document, operator.user, body, parts, tamper=tamper)
        with schema_context(migrated_tenant.number):
            acceptance = review.accept(document, operator.user)
        return SimpleNamespace(
            document=document,
            version=version,
            acceptance=acceptance,
            body=body,
            attachments=parts,
        )

    return make


# The review tests' `new_document` and `commit_version`, loaded from their conftest so documents
# are built and versions committed alike, with further files beside the body.
_spec = importlib.util.spec_from_file_location(
    "review_fixtures", Path(__file__).resolve().parents[1] / "review" / "conftest.py"
)
assert _spec is not None and _spec.loader is not None
_review = importlib.util.module_from_spec(_spec)
# Registered before it runs: its dataclass looks its own module up by name.
sys.modules[_spec.name] = _review
_spec.loader.exec_module(_review)

new_document = _review.new_document
commit_version = _review.commit_version
