"""The document repositories: one bare repository per document at `tenant-N/document-M/`, written
and read through pygit2 and nothing else (ADR-0003, ADR-0008, ADR-0011).

Blame is not here: it uses the git binary (ADR-0011). Callers hold the document's writer lock
(`documents.locks`) across every write.
"""

from __future__ import annotations

import os
import re
import secrets
import shutil
import tempfile
from collections.abc import Iterator, Mapping
from enum import StrEnum
from pathlib import Path

import pygit2
from django.conf import settings

from documents.locks import checked_number, tenant_directory

# The repositories are the application's own, under a root no other account can enter. A shared
# folder can report a directory just renamed into place as another user's, which fails libgit2's
# check that a repository belongs to whoever opens it.
pygit2.option(pygit2.enums.Option.SET_OWNER_VALIDATION, False)

MAIN = "refs/heads/main"
TRAILER = re.compile(r"^Kind: (?P<kind>[a-z_]+)$")
# One path component: no leading dot, nothing a shell, a line-oriented parser or another
# filesystem reads specially.
COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
# Every control character but the line feed and the tab; libgit2 cuts a message at a NUL.
CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
SHA = re.compile(r"^[0-9a-f]{40}$")
EDITION = re.compile(r"^[0-9]+\.[0-9]+$")
TRAILER_NAME = re.compile(r"^[A-Z][A-Za-z-]{0,39}$")


class Kind(StrEnum):
    """What a commit is: the values of a version's kind (DL-0260, DL-0268), carried by the commit
    so that its row can be derived from the commit alone (DL-0111)."""

    CREATED = "created"
    EDIT = "edit"
    REVIEWER_EDIT = "reviewer_edit"
    ACCEPTANCE = "acceptance"
    RETURN = "return"
    APPROVAL = "approval"


def repository_path(tenant_number: int, document_number: int) -> Path:
    """Named by the tenant's and the document's numbers, never by a title (ADR-0008)."""
    root = Path(settings.GIT_REPO_ROOT)
    return (
        root
        / f"tenant-{checked_number(tenant_number)}"
        / f"document-{checked_number(document_number)}"
    )


REPOSITORY_NAME = re.compile(r"^document-(?P<number>[1-9][0-9]{0,9})$")
TENANT_NAME = re.compile(r"^tenant-(?P<number>[1-9][0-9]{0,9})$")


def repositories() -> list[tuple[int, int]]:
    """Every repository under the root as `(tenant, document)`, never through a symbolic link."""
    root = Path(settings.GIT_REPO_ROOT)
    found = []
    for tenant in sorted(root.iterdir()) if root.is_dir() else []:
        tenant_match = TENANT_NAME.match(tenant.name)
        if tenant_match is None or tenant.is_symlink() or not tenant.is_dir():
            continue
        for entry in tenant.iterdir():
            match = REPOSITORY_NAME.match(entry.name)
            if match and not entry.is_symlink() and entry.is_dir():
                found.append((int(tenant_match.group("number")), int(match.group("number"))))
    return sorted(found)


def _name(tenant: int, document: int) -> str:
    return f"tenant-{tenant}/document-{document}"


def init(tenant: int, document: int) -> pygit2.Repository:
    """Create the document's bare repository, with `main` as its unborn head and no sample hooks.

    The repository is built beside its final name and renamed into place, so the path holds either
    a whole repository or nothing. Raises `FileExistsError` when a repository is already there.
    """
    path = repository_path(tenant, document)
    if path.exists():
        raise FileExistsError(_name(tenant, document))
    directory = tenant_directory(tenant)
    building = directory / f".document-{document}.init-{secrets.token_hex(4)}"
    try:
        # An empty template made for the call, so the repository carries none of git's samples.
        with tempfile.TemporaryDirectory() as template:
            pygit2.init_repository(
                str(building), bare=True, initial_head="main", template_path=template
            )
        os.rename(building, path)
    except BaseException:
        shutil.rmtree(building, ignore_errors=True)
        raise
    return open_repository(tenant, document)


def open_repository(tenant: int, document: int) -> pygit2.Repository:
    """The document's repository; `pygit2.GitError` when it does not exist."""
    path = repository_path(tenant, document)
    if not path.is_dir():
        raise pygit2.GitError(f"no repository at {_name(tenant, document)}")
    return pygit2.Repository(
        str(path),
        pygit2.enums.RepositoryOpenFlag.NO_SEARCH | pygit2.enums.RepositoryOpenFlag.BARE,
    )


def _checked_path(path: str) -> list[str]:
    parts = path.split("/")
    if not all(COMPONENT.match(part) for part in parts):
        raise ValueError(f"not a path inside a document: {path!r}")
    return parts


def _checked_message(message: str) -> str:
    if CONTROL.search(message):
        raise ValueError("a message holds a control character")
    lines = message.strip().splitlines()
    if not lines or not lines[0].strip():
        raise ValueError("a message starts with its summary")
    if any(TRAILER.match(line) for line in lines):
        raise ValueError("a message never writes its own kind")
    return message.strip()


def _oid(sha: str) -> pygit2.Oid:
    if not SHA.match(sha):
        raise ValueError(f"not a full commit id: {sha!r}")
    return pygit2.Oid(hex=sha)


def _write_tree(
    repo: pygit2.Repository, base: pygit2.Tree | None, changes: Mapping[str, bytes | None]
) -> pygit2.Oid | None:
    """The tree `base` becomes with `changes` applied; `None` for a tree left empty.

    A file never replaces a directory or the reverse: that would drop every file below it.
    """
    builder = repo.TreeBuilder(base) if base is not None else repo.TreeBuilder()
    nested: dict[str, dict[str, bytes | None]] = {}
    for path, content in changes.items():
        head, *rest = _checked_path(path)
        existing = builder.get(head)
        if rest:
            if existing is not None and existing.filemode != pygit2.enums.FileMode.TREE:
                raise ValueError(f"{head!r} is a file, not a directory")
            nested.setdefault(head, {})["/".join(rest)] = content
            continue
        if existing is not None and existing.filemode == pygit2.enums.FileMode.TREE:
            raise ValueError(f"{head!r} is a directory, not a file")
        if content is None:
            if existing is not None:
                builder.remove(head)
        else:
            builder.insert(head, repo.create_blob(content), pygit2.enums.FileMode.BLOB)
    for name, subchanges in nested.items():
        entry = base[name] if base is not None and name in base else None
        subtree = entry.peel(pygit2.Tree) if entry is not None else None
        oid = _write_tree(repo, subtree, subchanges)
        if oid is None:
            if builder.get(name) is not None:
                builder.remove(name)
        else:
            builder.insert(name, oid, pygit2.enums.FileMode.TREE)
    if len(builder) == 0:
        return None
    return builder.write()


def message_with_kind(message: str, kind: Kind, trailers: Mapping[str, str] | None = None) -> str:
    """The message, its first line the summary, and one paragraph of trailers: `trailers` in
    order, then `Kind:` last."""
    lines = []
    for name, value in (trailers or {}).items():
        # Every character `kind_of`'s split breaks a line on, not the newline alone.
        one_line = len(value.splitlines()) == 1
        if name == "Kind" or not TRAILER_NAME.match(name) or CONTROL.search(value) or not one_line:
            raise ValueError(f"not a trailer: {name!r}")
        lines.append(f"{name}: {value}\n")
    return f"{_checked_message(message)}\n\n{''.join(lines)}Kind: {kind.value}\n"


def kind_of(message: str) -> Kind | None:
    """The kind named by the trailers of a commit message — its last paragraph — or `None`."""
    paragraphs = message.strip().split("\n\n")
    if len(paragraphs) < 2:
        return None
    for line in paragraphs[-1].splitlines():
        match = TRAILER.match(line)
        if match:
            try:
                return Kind(match.group("kind"))
            except ValueError:
                return None
    return None


def commit(
    repo: pygit2.Repository,
    tree_changes: Mapping[str, bytes | None],
    author: pygit2.Signature,
    message: str,
    kind: Kind,
    trailers: Mapping[str, str] | None = None,
) -> str:
    """Commit `tree_changes` — a path to its new bytes, or `None` to remove it — on top of `main`,
    and move `main` to it. Author and committer are both `author`. Returns the commit's sha.

    Refuses a change that alters nothing or leaves no file. libgit2 refuses the ref update when
    `main` moved since it was read, so a writer without the lock fails rather than forks.
    """
    ref = repo.references.get(MAIN)
    parent = ref.peel(pygit2.Commit) if ref is not None else None
    base = parent.tree if parent is not None else None
    tree = _write_tree(repo, base, tree_changes)
    if tree is None:
        raise ValueError("a commit leaves the document with no file")
    if base is not None and tree == base.id:
        raise ValueError("a commit that changes nothing")
    parents = [parent.id] if parent is not None else []
    oid = repo.create_commit(
        MAIN, author, author, message_with_kind(message, kind, trailers), tree, parents
    )
    return str(oid)


def read(repo: pygit2.Repository, path: str, commit: str) -> bytes:
    """The bytes of the file `path` at `commit`; `KeyError` when no file has that path there."""
    tree = repo[_oid(commit)].peel(pygit2.Commit).tree
    _checked_path(path)
    try:
        entry = tree[path]
    except KeyError:
        raise KeyError(path) from None
    if not isinstance(entry, pygit2.Blob):
        raise KeyError(path)
    return entry.data


def diff(repo: pygit2.Repository, a: str, b: str) -> pygit2.Diff:
    """What changed from commit `a` to commit `b`."""
    return repo.diff(repo[_oid(a)].peel(pygit2.Commit), repo[_oid(b)].peel(pygit2.Commit))


def tag(
    repo: pygit2.Repository, name: str, commit: str, tagger: pygit2.Signature, message: str
) -> str:
    """An annotated tag `N.M` on `commit`, carrying the acting user's identity. Returns its id."""
    if not EDITION.match(name):
        raise ValueError(f"not an edition number: {name!r}")
    if CONTROL.search(message) or not message.strip():
        raise ValueError("a tag's message is one or more lines of text")
    oid = repo.create_tag(
        name, _oid(commit), pygit2.enums.ObjectType.COMMIT, tagger, message.strip()
    )
    return str(oid)


def commit_at(repo: pygit2.Repository, sha: str) -> pygit2.Commit:
    """The commit `sha`."""
    return repo[_oid(sha)].peel(pygit2.Commit)


def head(repo: pygit2.Repository) -> str | None:
    """The sha `main` points at, or `None` before the first commit."""
    ref = repo.references.get(MAIN)
    return None if ref is None else str(ref.peel(pygit2.Commit).id)


def history(repo: pygit2.Repository) -> Iterator[pygit2.Commit]:
    """Every commit on `main`, oldest first."""
    ref = repo.references.get(MAIN)
    if ref is None:
        return iter(())
    return iter(
        repo.walk(ref.target, pygit2.enums.SortMode.TOPOLOGICAL | pygit2.enums.SortMode.REVERSE)
    )
