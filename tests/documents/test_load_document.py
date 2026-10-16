"""A document loaded from a prepared folder (ST-0074, DL-0341 as DL-0348 narrows it):
created, its text and attachments committed as one content version, accepted as `0.1` by a named
rights-holder through the services the interface calls — no freeze, no edition, no tag. Every
check runs before anything is written; a failure after the creation leaves a document the
reconciler and the interface continue.

The folders are `tests/fixtures/load/` and copies of them altered here. People, groups and titles
are synthetic examples; every text is invented.
"""

from __future__ import annotations

import hashlib
import io
import re
import shutil
from pathlib import Path
from typing import Any

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from access.rights import Right
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

LOAD = Path(__file__).resolve().parents[1] / "fixtures" / "load"
PROCEDURE = LOAD / "procedure-ukr"
REGISTER = LOAD / "register-ukr"
LOADER = "operator.synthetic@example.test"


@pytest.fixture
def languages() -> None:
    from identity.models import Language

    Language.objects.get_or_create(code="uk", defaults={"label": "uk", "actor_kind": "system"})


@pytest.fixture
def group_holding(migrated_tenant: Any, member_of: Any, repo_root: Path, languages: None) -> Any:
    """`group_holding(*rights, member=True)`: the loader, a member of the tenant, and a new
    group holding `rights` — with the loader in it unless `member` is false; the group."""
    from access.models import AccessGroup

    _, loader, membership = member_of(LOADER)
    made = iter(range(1, 100))

    def make(*rights: Right, member: bool = True) -> Any:
        with schema_context(migrated_tenant.number):
            group = AccessGroup.objects.create(
                name=f"Operators {next(made)} (synthetic example)",
                created_by=loader,
                actor_kind="user",
            )
            for right in rights:
                group.grant(right, by=loader)
            if member:
                group.add_member(membership, by=loader)
        return group

    make.loader = loader  # type: ignore[attr-defined]
    return make


@pytest.fixture
def operators(group_holding: Any) -> Any:
    """The group DL-0348 asks of the loader: *create and edit* and *accept*."""
    return group_holding(Right.CREATE_AND_EDIT, Right.ACCEPT)


def load(tenant: Any, group: Any, *folders: Path) -> str:
    """`load_document` for `folders`; its standard output."""
    out = io.StringIO()
    call_command(
        "load_document",
        "--tenant",
        str(tenant.number),
        "--as",
        LOADER,
        "--group",
        str(group.pk),
        *[str(folder) for folder in folders],
        stdout=out,
    )
    return out.getvalue()


def copy(folder: Path, tmp_path: Path, name: str | None = None) -> Path:
    target = tmp_path / (name or folder.name)
    shutil.copytree(folder, target)
    return target


def refused(tenant: Any, group: Any, folder: Path) -> str:
    """The command refused for `folder`; its message."""
    with pytest.raises(CommandError) as error:
        load(tenant, group, folder)
    return str(error.value)


def assert_nothing_written(tenant: Any, repo_root: Path) -> None:
    from documents.models import Document

    with schema_context(tenant.number):
        assert not Document.objects.exists()
    directory = repo_root / f"tenant-{tenant.number}"
    written = sorted(p.name for p in directory.iterdir()) if directory.exists() else []
    assert not [name for name in written if name.startswith("document-")], written


def the_document(tenant: Any) -> Any:
    from documents.models import Document

    with schema_context(tenant.number):
        return Document.objects.select_related("language").get()


def kinds(tenant: Any, document: Any) -> list[tuple[str, str]]:
    """`(kind, sha)` of every commit on `main`, oldest first."""
    from documents import gitstore

    repo = gitstore.open_repository(tenant.number, document.number)
    return [(str(gitstore.kind_of(c.message)), str(c.id)) for c in gitstore.history(repo)]


def read(tenant: Any, document: Any, path: str, sha: str) -> bytes:
    from documents import gitstore

    return gitstore.read(gitstore.open_repository(tenant.number, document.number), path, sha)


def content_version(tenant: Any, document: Any) -> Any:
    from documents.models import Version

    with schema_context(tenant.number):
        return Version.objects.get(document=document, kind="reviewer_edit")


def test_folder_becomes_version_zero_one(
    migrated_tenant: Any, operators: Any, group_holding: Any
) -> None:
    from access.models import DocumentGroup
    from documents import gitstore
    from documents.models import Version
    from review.models import Acceptance

    out = load(migrated_tenant, operators, PROCEDURE)

    document = the_document(migrated_tenant)
    commits = kinds(migrated_tenant, document)
    assert [kind for kind, _ in commits] == ["created", "reviewer_edit", "acceptance"]
    content_sha = commits[1][1]
    read(migrated_tenant, document, "document.md", content_sha)
    assert read(migrated_tenant, document, "attachments/1", content_sha) == (
        (PROCEDURE / "scheme.txt").read_bytes()
    )
    repo = gitstore.open_repository(migrated_tenant.number, document.number)
    assert not [ref for ref in repo.references if ref.startswith("refs/tags/")]
    with schema_context(migrated_tenant.number):
        assert not Version.objects.filter(document=document, kind="approval").exists()
        acceptance = Acceptance.objects.get(version__document=document)
        assert acceptance.number == "0.1"
        assert acceptance.reviewer_id == group_holding.loader.pk
        assert DocumentGroup.objects.filter(document=document, group=operators).exists()
        assert document.title == "Порядок погодження закупівель (синтетичний приклад)"
        assert document.language_id == "uk"
    assert f"document {document.number} · version 0.1 · attachments: 1" in out.splitlines()


def test_attachments_stored_as_the_bundle_says(migrated_tenant: Any, operators: Any) -> None:
    from documents import bundle, parts
    from documents.models import PartIndex

    load(migrated_tenant, operators, PROCEDURE)

    document = the_document(migrated_tenant)
    version = content_version(migrated_tenant, document)
    data = (PROCEDURE / "scheme.txt").read_bytes()
    frontmatter, _ = bundle.parse(
        read(migrated_tenant, document, "document.md", version.commit_sha).decode("utf-8")
    )
    assert frontmatter.attachments == [
        {
            "number": 1,
            "title": "Схема погодження",
            "file_name": "scheme.txt",
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
        }
    ]
    with schema_context(migrated_tenant.number):
        rows = list(PartIndex.objects.filter(version=version, kind="attachment"))
        assert [(r.part_number, r.file_name, r.sha256, r.bytes) for r in rows] == [
            (1, "scheme.txt", hashlib.sha256(data).hexdigest(), len(data))
        ]
        listed = parts.attachments(version)
        assert [(a.number, a.title, a.file_name, a.bytes) for a in listed] == [
            (1, "Схема погодження", "scheme.txt", len(data))
        ]
        attachment, served = parts.read_attachment(migrated_tenant.number, document, version, 1)
    assert attachment.sha256 == hashlib.sha256(data).hexdigest()
    assert served == data


def test_body_normalised(migrated_tenant: Any, operators: Any) -> None:
    from documents import bundle
    from editing.normalizer import Lists, normalize
    from identity.models import Language

    load(migrated_tenant, operators, REGISTER)

    document = the_document(migrated_tenant)
    commits = kinds(migrated_tenant, document)
    created_sha, content_sha = commits[0][1], commits[1][1]
    _, created_body = bundle.parse(
        read(migrated_tenant, document, "document.md", created_sha).decode("utf-8")
    )
    frontmatter, body = bundle.parse(
        read(migrated_tenant, document, "document.md", content_sha).decode("utf-8")
    )
    source = (REGISTER / "document.md").read_text(encoding="utf-8")
    expected = normalize(
        created_body.encode("utf-8"), source, Lists.of(Language.objects.get(code="uk"))
    ).decode("utf-8")
    assert body == expected
    # The source's one line of two sentences is stored as two lines.
    lines = body.split("\n")
    assert "Реєстр заявок веде відповідальний виконавець підрозділу." in lines
    assert "Кожну заявку вносять до реєстру в день її надходження." in lines
    assert frontmatter.title == "Порядок ведення реєстру заявок (синтетичний приклад)"
    assert frontmatter.language == "uk"
    assert [a["file_name"] for a in frontmatter.attachments] == ["form.csv", "order.txt"]


def test_reader_downloads_loaded_files(
    migrated_tenant: Any, operators: Any, member_of: Any
) -> None:
    from access.models import AccessGroup, DocumentGroup

    out = load(migrated_tenant, operators, REGISTER)
    document = the_document(migrated_tenant)
    assert f"document {document.number} · version 0.1 · attachments: 2" in out.splitlines()
    client, _, membership = member_of("reader.synthetic@example.test")
    with schema_context(migrated_tenant.number):
        readers = AccessGroup.objects.create(
            name="Readers (synthetic example)", actor_kind="system"
        )
        readers.grant(Right.VIEW_ACCEPTED, by=None)
        readers.add_member(membership, by=None)
        DocumentGroup.link(document, readers, by=None)

    for number, name in ((1, "form.csv"), (2, "order.txt")):
        response = client.get(f"/document/{document.number}/attachment/{number}/")
        assert response.status_code == 200
        assert response.content == (REGISTER / name).read_bytes()
        assert f'filename="{name}"' in response["Content-Disposition"]


def test_folder_refusals_all_at_once(
    migrated_tenant: Any, operators: Any, tmp_path: Path, repo_root: Path
) -> None:
    folder = copy(PROCEDURE, tmp_path, "broken-ukr")
    yaml_text = (folder / "document.yaml").read_text(encoding="utf-8")
    (folder / "document.yaml").write_text(
        yaml_text
        + '  - file: "absent-plan.txt"\n    title: "Absent plan"\n'
        + 'author: "Synthetic author"\n',
        encoding="utf-8",
    )
    (folder / "unnamed-note.txt").write_text("A synthetic note.\n", encoding="utf-8")
    # A name beginning with a dot is ignored, as a Mac's `.DS_Store` is.
    (folder / ".DS_Store").write_bytes(b"\x00")

    message = refused(migrated_tenant, operators, folder)

    assert "broken-ukr" in message
    assert "author" in message
    assert "unnamed-note.txt" in message
    assert "absent-plan.txt" in message
    assert ".DS_Store" not in message
    assert_nothing_written(migrated_tenant, repo_root)


def test_whitelist_and_cap_refuse_before_writing(
    migrated_tenant: Any, operators: Any, tmp_path: Path, repo_root: Path
) -> None:
    from tenancy.models import Tenant

    body = (PROCEDURE / "document.md").read_text(encoding="utf-8")

    remote = copy(PROCEDURE, tmp_path, "remote-image")
    # The image on line 5 of the body.
    (remote / "document.md").write_text(
        "# General provisions\n\nThe section's text.\n\n![Scheme](https://example.test/scheme.png)\n",
        encoding="utf-8",
    )
    message = refused(migrated_tenant, operators, remote)
    assert "image-src" in message
    assert re.search(r"\b5\b", message)
    assert_nothing_written(migrated_tenant, repo_root)

    local = copy(PROCEDURE, tmp_path, "local-image")
    (local / "document.md").write_text(body + "\n![plan](images/plan.png)\n", encoding="utf-8")
    message = refused(migrated_tenant, operators, local)
    assert "images/plan.png" in message and "images arrive later" in message
    assert_nothing_written(migrated_tenant, repo_root)

    Tenant.objects.filter(pk=migrated_tenant.pk).update(attachment_max_bytes=100)
    large = copy(PROCEDURE, tmp_path, "large-file")
    (large / "scheme.txt").write_bytes(b"x" * 101)
    message = refused(migrated_tenant, operators, large)
    assert "scheme.txt" in message
    assert re.search(r"\b100\b", message)
    assert_nothing_written(migrated_tenant, repo_root)


def test_rights_checked_first(migrated_tenant: Any, group_holding: Any, repo_root: Path) -> None:
    without_accept = group_holding(Right.CREATE_AND_EDIT)

    message = refused(migrated_tenant, without_accept, PROCEDURE)

    assert "accept" in message.lower()
    assert_nothing_written(migrated_tenant, repo_root)

    # Every right held, but the loader is not in the group.
    not_in_it = group_holding(Right.CREATE_AND_EDIT, Right.ACCEPT, member=False)
    with pytest.raises(CommandError):
        load(migrated_tenant, not_in_it, PROCEDURE)
    assert_nothing_written(migrated_tenant, repo_root)


def test_frontmatter_refused(
    migrated_tenant: Any, operators: Any, tmp_path: Path, repo_root: Path
) -> None:
    folder = copy(PROCEDURE, tmp_path, "with-frontmatter")
    body = (folder / "document.md").read_text(encoding="utf-8")
    (folder / "document.md").write_text(
        '---\ntitle: "Synthetic title"\n---\n\n' + body, encoding="utf-8"
    )

    message = refused(migrated_tenant, operators, folder)

    assert "frontmatter" in message.lower()
    assert_nothing_written(migrated_tenant, repo_root)


def run_authorship(jobs: list[tuple[int, int, str]]) -> None:
    """Each job the suite recorded, run as the worker would run it."""
    from editing.tasks import compute_authorship

    for job in dict.fromkeys(jobs):
        compute_authorship(*job)


def reconcile_report(tenant: Any, document: Any) -> str:
    out = io.StringIO()
    call_command(
        "reconcile", "--tenant", str(tenant.number), "--document", str(document.number), stdout=out
    )
    return out.getvalue().strip()


def test_stop_after_create_is_continuable(
    migrated_tenant: Any,
    operators: Any,
    group_holding: Any,
    monkeypatch: pytest.MonkeyPatch,
    queued_authorship: list[tuple[int, int, str]],
) -> None:
    from documents.models import Document, DocumentState, Version
    from review import services as review
    from review.models import Acceptance

    real_accept = review.accept

    def failing(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("synthetic fault injected by the test")

    monkeypatch.setattr("review.services.accept", failing)
    # Whichever way the loader names it.
    monkeypatch.setattr("documents.loading.accept", failing, raising=False)

    with pytest.raises(CommandError) as error:
        load(migrated_tenant, operators, PROCEDURE)

    message = str(error.value)
    assert re.search(r"\bstep 4\b", message)
    assert "reconcile" in message
    document = the_document(migrated_tenant)
    assert [kind for kind, _ in kinds(migrated_tenant, document)] == ["created", "reviewer_edit"]
    with schema_context(migrated_tenant.number):
        assert Document.objects.get(pk=document.pk).state == DocumentState.ACTIVE
        version = Version.objects.get(document=document, kind="reviewer_edit")
        assert not Acceptance.objects.exists()
    assert (migrated_tenant.number, document.number, version.commit_sha) in queued_authorship

    run_authorship(queued_authorship)
    assert reconcile_report(migrated_tenant, document) == "nothing to report"
    with schema_context(migrated_tenant.number):
        acceptance = real_accept(document, group_holding.loader)
        assert acceptance.number == "0.1"


def test_run_stops_at_first_failure(migrated_tenant: Any, operators: Any, tmp_path: Path) -> None:
    from documents.models import Document

    invalid = copy(REGISTER, tmp_path, "invalid-register")
    (invalid / "order.txt").unlink()

    with pytest.raises(CommandError) as error:
        load(migrated_tenant, operators, PROCEDURE, invalid)

    assert "invalid-register" in str(error.value)
    with schema_context(migrated_tenant.number):
        titles = list(Document.objects.values_list("title", flat=True))
    assert titles == ["Порядок погодження закупівель (синтетичний приклад)"]


def test_load_leaves_nothing_to_reconcile(
    migrated_tenant: Any, operators: Any, queued_authorship: list[tuple[int, int, str]]
) -> None:
    load(migrated_tenant, operators, PROCEDURE)
    document = the_document(migrated_tenant)
    version = content_version(migrated_tenant, document)

    assert (migrated_tenant.number, document.number, version.commit_sha) in queued_authorship
    run_authorship(queued_authorship)
    assert reconcile_report(migrated_tenant, document) == "nothing to report"


# The review's findings, each reproduced before its fix.


def test_links_are_refused_not_followed(
    migrated_tenant: Any, operators: Any, tmp_path: Path, repo_root: Path
) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("A synthetic file outside the folder.\n", encoding="utf-8")
    folder = copy(PROCEDURE, tmp_path)
    (folder / "scheme.txt").unlink()
    (folder / "scheme.txt").symlink_to(outside)

    message = refused(migrated_tenant, operators, folder)

    assert "scheme.txt" in message and "link" in message
    assert_nothing_written(migrated_tenant, repo_root)


def test_linked_body_refused(
    migrated_tenant: Any, operators: Any, tmp_path: Path, repo_root: Path
) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text("# Synthetic section\n\nSynthetic text.\n", encoding="utf-8")
    folder = copy(PROCEDURE, tmp_path)
    (folder / "document.md").unlink()
    (folder / "document.md").symlink_to(outside)

    assert "document.md" in refused(migrated_tenant, operators, folder)
    assert_nothing_written(migrated_tenant, repo_root)


def test_template_body_without_attachments_refused_before_writing(
    migrated_tenant: Any, operators: Any, tmp_path: Path, repo_root: Path
) -> None:
    from documents.models import DocumentTemplate

    with schema_context(migrated_tenant.number):
        outline = DocumentTemplate.objects.get().outline
    folder = copy(PROCEDURE, tmp_path)
    (folder / "scheme.txt").unlink()
    (folder / "document.yaml").write_text(
        'title: "Empty synthetic document"\nlanguage: "uk"\n', encoding="utf-8"
    )
    (folder / "document.md").write_text(outline, encoding="utf-8")

    assert "nothing to load" in refused(migrated_tenant, operators, folder)
    assert_nothing_written(migrated_tenant, repo_root)


def test_subfolder_refused(
    migrated_tenant: Any, operators: Any, tmp_path: Path, repo_root: Path
) -> None:
    folder = copy(PROCEDURE, tmp_path)
    (folder / "images").mkdir()

    assert "images" in refused(migrated_tenant, operators, folder)
    assert_nothing_written(migrated_tenant, repo_root)


BASE_YAML = 'title: "Synthetic example"\nlanguage: "uk"\n'


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        (BASE_YAML + 'title: "Twice"\n', "document.yaml"),
        ('title: "Synthetic example"\nlanguage: "xx"\n', "language"),
        ('title: "Two\\nlines"\nlanguage: "uk"\n', "title"),
        (
            BASE_YAML + 'attachments:\n  - file: "../scheme.txt"\n    title: "Scheme"\n',
            "../scheme.txt",
        ),
        (
            BASE_YAML + 'attachments:\n  - file: "sub\\\\scheme.txt"\n    title: "Scheme"\n',
            "scheme.txt",
        ),
        (BASE_YAML + 'attachments:\n  - file: ".scheme.txt"\n    title: "Scheme"\n', ".scheme.txt"),
        (
            BASE_YAML
            + 'attachments:\n  - file: "scheme.txt"\n    title: "Scheme"\n'
            + '  - file: "scheme.txt"\n    title: "Again"\n',
            "named twice",
        ),
        (BASE_YAML + 'attachments:\n  - file: "scheme.txt"\n    title: "Two\\nlines"\n', "title"),
        (BASE_YAML + "1: x\nzz: y\n", "unknown keys"),
    ],
)
def test_description_refusals(
    migrated_tenant: Any,
    operators: Any,
    tmp_path: Path,
    repo_root: Path,
    description: str,
    expected: str,
) -> None:
    folder = copy(PROCEDURE, tmp_path)
    (folder / "document.yaml").write_text(description, encoding="utf-8")

    message = refused(migrated_tenant, operators, folder)

    assert expected in message
    assert "Traceback" not in message
    assert_nothing_written(migrated_tenant, repo_root)


def test_nfd_name_matches_its_nfc_description(
    migrated_tenant: Any, operators: Any, tmp_path: Path
) -> None:
    import unicodedata

    folder = copy(PROCEDURE, tmp_path)
    name = "схема й погодження.txt"
    (folder / "scheme.txt").rename(folder / unicodedata.normalize("NFD", name))
    (folder / "document.yaml").write_text(
        BASE_YAML
        + f'attachments:\n  - file: "{unicodedata.normalize("NFC", name)}"\n    title: "Scheme"\n',
        encoding="utf-8",
    )

    assert "attachments: 1" in load(migrated_tenant, operators, folder)


def test_inactive_loader_refused(
    migrated_tenant: Any, operators: Any, tmp_path: Path, repo_root: Path
) -> None:
    from identity.models import User

    User.objects.filter(email=LOADER).update(self_blocked=True)

    assert "not an active member" in refused(migrated_tenant, operators, copy(PROCEDURE, tmp_path))
    assert_nothing_written(migrated_tenant, repo_root)


def test_body_too_large_once_normalised_refused(
    migrated_tenant: Any, operators: Any, tmp_path: Path, repo_root: Path, monkeypatch: Any
) -> None:
    from editing.normalizer import TooLarge

    def too_large(*_: Any, **__: Any) -> bytes:
        raise TooLarge("synthetic")

    monkeypatch.setattr("documents.loading.normalize", too_large)

    assert "too large once normalised" in refused(
        migrated_tenant, operators, copy(PROCEDURE, tmp_path)
    )
    assert_nothing_written(migrated_tenant, repo_root)


def test_rerun_skips_what_is_loaded(migrated_tenant: Any, operators: Any) -> None:
    from documents.models import Document

    load(migrated_tenant, operators, PROCEDURE)
    output = load(migrated_tenant, operators, PROCEDURE, REGISTER)

    assert "already loaded" in output and "document 2 · version 0.1" in output
    with schema_context(migrated_tenant.number):
        assert Document.objects.count() == 2


def test_loaded_spans_are_declared(migrated_tenant: Any, operators: Any, tmp_path: Path) -> None:
    """A role the folder's body marks and nothing declares is declared in the loaded version's
    `entities.yaml`, from its words (DL-0440)."""
    from documents import entities

    folder = copy(REGISTER, tmp_path)
    body = folder / "document.md"
    body.write_text(
        body.read_text(encoding="utf-8") + "\n[The clerk]{.role #clerk} keeps the register.\n",
        encoding="utf-8",
    )

    load(migrated_tenant, operators, folder)

    document = the_document(migrated_tenant)
    content_sha = kinds(migrated_tenant, document)[1][1]
    declared = read(migrated_tenant, document, "entities.yaml", content_sha).decode("utf-8")
    assert entities.parse(declared) == [entities.Declared("role", "clerk", "The clerk")]


def test_declarations_over_the_cap_refuse_before_writing(
    migrated_tenant: Any,
    operators: Any,
    repo_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The declarations a body's spans would make are held to the cap a commit from the editor is
    held to, and checked before anything is written."""
    from documents import entities

    monkeypatch.setattr(entities, "MAX_BYTES", 200)
    folder = copy(REGISTER, tmp_path)
    body = folder / "document.md"
    marked = "".join(f"\n[Role {n}]{{.role #role-{n}}} keeps the register.\n" for n in range(8))
    body.write_text(body.read_text(encoding="utf-8") + marked, encoding="utf-8")

    message = refused(migrated_tenant, operators, folder)

    assert "entities.yaml" in message
    assert_nothing_written(migrated_tenant, repo_root)
