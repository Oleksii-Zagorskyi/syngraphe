"""The repository layer on bare repositories: init, commit, read, diff, tag (ADR-0003, ADR-0011)."""

from __future__ import annotations

import uuid
from pathlib import Path

import pygit2
import pytest

from documents import gitstore
from documents.gitstore import Kind
from documents.identity import identity_for
from identity.models import User

pytestmark = pytest.mark.integration

CORPUS = Path(__file__).resolve().parents[1] / "fixtures" / "corpus"
AUTHOR = User(id=uuid.UUID("00000000-0000-4000-8000-000000000001"), email="a@example.test")


def corpus_sections(count: int) -> bytes:
    """The corpus document up to the end of its `count`-th `##` section."""
    text = (CORPUS / "document-ukr.md").read_text(encoding="utf-8")
    starts = [i for i, line in enumerate(text.splitlines(keepends=True)) if line.startswith("## ")]
    lines = text.splitlines(keepends=True)
    end = starts[count] if count < len(starts) else len(lines)
    return "".join(lines[:end]).encode("utf-8")


def test_init_bare_without_sample_hooks(repo_root: Path) -> None:
    repo = gitstore.init(tenant=3, document=12)

    path = repo_root / "tenant-3" / "document-12"
    assert Path(repo.path).resolve() == path.resolve()
    assert repo.is_bare
    assert repo.head_is_unborn
    hooks = path / "hooks"
    assert not hooks.exists() or not any(hooks.iterdir())


def test_init_refuses_an_existing_repository(repo_root: Path) -> None:
    gitstore.init(tenant=3, document=12)

    with pytest.raises(FileExistsError):
        gitstore.init(tenant=3, document=12)


def test_commit_read_diff_round_trip(repo_root: Path) -> None:
    repo = gitstore.init(tenant=3, document=12)
    sig = identity_for(AUTHOR)
    versions = [corpus_sections(n) for n in (1, 2, 3)]

    c1 = gitstore.commit(repo, {"document.md": versions[0]}, sig, "Section 1", Kind.CREATED)
    c2 = gitstore.commit(repo, {"document.md": versions[1]}, sig, "Section 2", Kind.EDIT)
    c3 = gitstore.commit(repo, {"document.md": versions[2]}, sig, "Section 3", Kind.EDIT)

    for sha, content in zip((c1, c2, c3), versions, strict=True):
        assert gitstore.read(repo, "document.md", sha) == content
    assert [p.id for p in repo[c3].parents] == [repo[c2].id]
    assert str(repo.references["refs/heads/main"].target) == c3
    added = {
        line.content
        for patch in gitstore.diff(repo, c1, c3)
        for hunk in patch.hunks
        for line in hunk.lines
        if line.origin == "+" and line.content.strip()
    }
    expected = set(versions[2].decode("utf-8").splitlines(keepends=True)) - set(
        versions[0].decode("utf-8").splitlines(keepends=True)
    )
    assert added == expected


def test_commit_carries_its_kind_as_a_trailer(repo_root: Path) -> None:
    repo = gitstore.init(tenant=3, document=12)

    sha = gitstore.commit(
        repo, {"document.md": b"# A\n"}, identity_for(AUTHOR), "Created", Kind.CREATED
    )

    message = repo[sha].message
    assert message.splitlines()[0] == "Created"
    assert message.rstrip().endswith("Kind: created")
    assert gitstore.kind_of(message) is Kind.CREATED


def test_commit_writes_nested_paths_and_keeps_the_rest(repo_root: Path) -> None:
    repo = gitstore.init(tenant=3, document=12)
    sig = identity_for(AUTHOR)
    gitstore.commit(repo, {"document.md": b"a\n", "passport.md": b"p\n"}, sig, "one", Kind.CREATED)

    sha = gitstore.commit(repo, {"appendices/1.md": b"# X\n"}, sig, "two", Kind.EDIT)

    assert gitstore.read(repo, "appendices/1.md", sha) == b"# X\n"
    assert gitstore.read(repo, "document.md", sha) == b"a\n"
    assert gitstore.read(repo, "passport.md", sha) == b"p\n"


def test_tag_is_annotated_with_identity(repo_root: Path) -> None:
    repo = gitstore.init(tenant=3, document=12)
    sha = gitstore.commit(
        repo, {"document.md": b"# A\n"}, identity_for(AUTHOR), "Created", Kind.CREATED
    )

    tag_id = gitstore.tag(repo, "2.0", sha, identity_for(AUTHOR), "edition 2.0")

    tag = repo[tag_id]
    assert isinstance(tag, pygit2.Tag)
    assert tag.tagger.name == str(AUTHOR.id)
    assert tag.tagger.email == f"{AUTHOR.id}@users.noreply.syngraphe.local"
    assert tag.message.strip() == "edition 2.0"
    assert str(repo.lookup_reference("refs/tags/2.0").peel(pygit2.Commit).id) == sha


def _repo_with_files(files: dict[str, bytes]) -> tuple[pygit2.Repository, str]:
    repo = gitstore.init(tenant=3, document=12)
    sha = gitstore.commit(repo, dict(files), identity_for(AUTHOR), "Created", Kind.CREATED)
    return repo, sha


def test_removing_the_last_file_of_a_directory_removes_the_directory(repo_root: Path) -> None:
    repo, _ = _repo_with_files({"document.md": b"a\n", "appendices/1.md": b"# X\n"})

    sha = gitstore.commit(repo, {"appendices/1.md": None}, identity_for(AUTHOR), "gone", Kind.EDIT)

    assert [entry.name for entry in repo[sha].peel(pygit2.Commit).tree] == ["document.md"]
    with pytest.raises(KeyError):
        gitstore.read(repo, "appendices/1.md", sha)


def test_commit_refuses_an_empty_or_unchanged_tree(repo_root: Path) -> None:
    repo, _ = _repo_with_files({"document.md": b"a\n"})

    with pytest.raises(ValueError):
        gitstore.commit(repo, {"document.md": None}, identity_for(AUTHOR), "none", Kind.EDIT)
    with pytest.raises(ValueError):
        gitstore.commit(repo, {"document.md": b"a\n"}, identity_for(AUTHOR), "same", Kind.EDIT)


def test_a_file_never_replaces_a_directory(repo_root: Path) -> None:
    repo, _ = _repo_with_files({"document.md": b"a\n", "appendices/1.md": b"# X\n"})

    for changes in ({"appendices": b"x"}, {"appendices": None}, {"document.md/x": b"x"}):
        with pytest.raises(ValueError):
            gitstore.commit(repo, changes, identity_for(AUTHOR), "type", Kind.EDIT)


@pytest.mark.parametrize(
    "path",
    ["../x", "/abs", ".git/config", ".GITMODULES", "a\\b", "a\nb", "a//b", " ", "..\u2215x", ""],
)
def test_commit_refuses_a_path_outside_the_document(repo_root: Path, path: str) -> None:
    repo, _ = _repo_with_files({"document.md": b"a\n"})

    with pytest.raises(ValueError):
        gitstore.commit(repo, {path: b"x"}, identity_for(AUTHOR), "path", Kind.EDIT)


@pytest.mark.parametrize(
    "message",
    ["summary\n\nKind: approval\x00", "summary\x1b[2J", "", "  \n", "text\nKind: approval"],
)
def test_a_message_cannot_forge_its_kind(repo_root: Path, message: str) -> None:
    repo, _ = _repo_with_files({"document.md": b"a\n"})

    with pytest.raises(ValueError):
        gitstore.commit(repo, {"document.md": b"b\n"}, identity_for(AUTHOR), message, Kind.EDIT)


def test_kind_of_reads_only_the_trailer() -> None:
    assert gitstore.kind_of("Summary\n\nKind: edit\n") is Kind.EDIT
    assert gitstore.kind_of("Summary\n\nKind: edit\nRefs: x\n") is Kind.EDIT
    assert gitstore.kind_of("Kind: edit\n") is None
    assert gitstore.kind_of("Summary\n\nKind: unknown\n") is None
    assert gitstore.kind_of("Summary\n") is None


def test_read_refuses_a_directory_and_a_short_id(repo_root: Path) -> None:
    repo, sha = _repo_with_files({"document.md": b"a\n", "appendices/1.md": b"# X\n"})

    with pytest.raises(KeyError):
        gitstore.read(repo, "appendices", sha)
    with pytest.raises(KeyError):
        gitstore.read(repo, "missing.md", sha)
    with pytest.raises(ValueError):
        gitstore.read(repo, "document.md", sha[:8])


def test_a_stale_parent_is_refused(repo_root: Path) -> None:
    repo, _ = _repo_with_files({"document.md": b"a\n"})
    stale = gitstore.open_repository(3, 12)
    gitstore.commit(repo, {"document.md": b"b\n"}, identity_for(AUTHOR), "first", Kind.EDIT)
    tree = stale.TreeBuilder().write()
    old_parent = [c.id for c in gitstore.history(stale)][0]

    with pytest.raises(pygit2.GitError):
        stale.create_commit(
            gitstore.MAIN, identity_for(AUTHOR), identity_for(AUTHOR), "x", tree, [old_parent]
        )


def test_history_is_oldest_first(repo_root: Path) -> None:
    repo, first = _repo_with_files({"document.md": b"a\n"})
    second = gitstore.commit(repo, {"document.md": b"b\n"}, identity_for(AUTHOR), "b", Kind.EDIT)

    assert [str(c.id) for c in gitstore.history(repo)] == [first, second]


def test_numbers_and_tag_names_are_checked(repo_root: Path) -> None:
    repo, sha = _repo_with_files({"document.md": b"a\n"})

    with pytest.raises(ValueError):
        gitstore.repository_path("../../etc", 1)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        gitstore.init(tenant=True, document=1)
    for name in ("main", "refs/heads/main", "2", "v2.0"):
        with pytest.raises(ValueError):
            gitstore.tag(repo, name, sha, identity_for(AUTHOR), "edition")


def test_init_leaves_nothing_behind_when_it_fails(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(gitstore.os, "rename", fail)

    with pytest.raises(OSError):
        gitstore.init(tenant=3, document=12)
    assert list((repo_root / "tenant-3").iterdir()) == []
