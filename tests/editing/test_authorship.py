"""The authorship worker: per-line authorship for the head, from a blame bounded to the commits
since the cached version, the platform's move rule, and only the kept versions' rows (DL-0135,
DL-0266, ADR-0011).

The corpus is the invented one of `tests/fixtures/corpus/`, its frontmatter rewritten as the
platform writes it. Every other text here is a synthetic example.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from documents import bundle
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

CORPUS = Path(__file__).resolve().parents[1] / "fixtures" / "corpus"
DOMAIN = "users.noreply.syngraphe.local"
# The generator's fixed clock: commit `n` is dated `EPOCH + n` hours.
EPOCH = 1_800_000_000
# The corpus's own lines before its body: four of frontmatter between two delimiters, one blank.
CORPUS_PREFIX = 6
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
BLAME_LINE = re.compile(r"^\^?([0-9a-f]{40}) \d+ (\d+)")


def git(repo: Path, *args: str, stdin: bytes | None = None) -> bytes:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    result = subprocess.run(
        ["git", "-C", str(repo), *args], input=stdin, env=env, capture_output=True, timeout=120
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    return result.stdout


def import_history(repo: Path, commits: list[tuple[int, int, str]]) -> list[str]:
    """A new bare repository holding `document.md` at each of `commits` — `(author, n, text)`,
    dated like the corpus — through one `git fast-import`. Returns the commits' shas in order."""
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(repo)], check=True)
    stream = bytearray()
    for mark, (author, n, text) in enumerate(commits, 1):
        who = f"{author} <{author}@{DOMAIN}> {EPOCH + n * 3600} +0000"
        message = f"Commit {n}".encode()
        data = text.encode("utf-8")
        stream += f"commit refs/heads/main\nmark :{mark}\nauthor {who}\ncommitter {who}\n".encode()
        stream += f"data {len(message)}\n".encode() + message + b"\n"
        if mark > 1:
            stream += f"from :{mark - 1}\n".encode()
        stream += f"M 100644 inline document.md\ndata {len(data)}\n".encode() + data + b"\n"
    marks = repo / "marks"
    git(repo, "fast-import", "--quiet", f"--export-marks={marks}", stdin=bytes(stream))
    shas = dict(line.split(" ") for line in marks.read_text().splitlines())
    marks.unlink()
    return [shas[f":{mark}"] for mark in range(1, len(commits) + 1)]


def with_platform_frontmatter(text: str) -> tuple[str, int]:
    """The corpus's document with its frontmatter as the platform writes it — the corpus's own
    carries `synthetic: true`, which `bundle.parse` refuses — and how many lines that
    moves the body down."""
    lines = text.split("\n")
    assert lines[0] == lines[4] == "---" and lines[5] == ""
    fields = dict(line.split(": ", 1) for line in lines[1:4])
    body = "\n".join(lines[CORPUS_PREFIX:])
    rebuilt = bundle.render(
        bundle.Frontmatter(title=fields["title"], language=fields["language"]), body
    )
    return rebuilt, rebuilt[: len(rebuilt) - len(body)].count("\n") - CORPUS_PREFIX


@pytest.fixture(scope="module")
def corpus(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """The Ukrainian corpus, commit by commit, with the platform's frontmatter; its record; and
    the corpus's commits with their new shas."""
    out = tmp_path_factory.mktemp("authorship-corpus")
    generated, truth_path = out / "generated.git", out / "truth.json"
    result = subprocess.run(
        [sys.executable, str(CORPUS / "corpus.py"), "--lang", "ukr", "--repo", str(generated)]
        + ["--truth", str(truth_path)],
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    truth = json.loads(truth_path.read_text(encoding="utf-8"))
    batch = git(
        generated,
        "cat-file",
        "--batch",
        stdin="".join(f"{c['sha']}:document.md\n" for c in truth["commits"]).encode(),
    )
    texts, at = [], 0
    for _ in truth["commits"]:
        header_end = batch.index(b"\n", at)
        size = int(batch[at:header_end].split(b" ")[2])
        texts.append(batch[header_end + 1 : header_end + 1 + size].decode("utf-8"))
        at = header_end + 1 + size + 1
    rebuilt = [with_platform_frontmatter(text) for text in texts]
    repo = out / "corpus-ukr.git"
    shas = import_history(
        repo,
        [
            (c["author"], c["n"], text)
            for c, (text, _) in zip(truth["commits"], rebuilt, strict=True)
        ],
    )
    commits = [{**c, "sha": sha} for c, sha in zip(truth["commits"], shas, strict=True)]
    return {"repo": repo, "truth": truth, "commits": commits, "shift": rebuilt[-1][1]}


def authors(member_of: Any) -> dict[int, Any]:
    """The corpus's three authors as members of the tenant."""
    return {n: member_of(f"corpus.author.{n}@example.test")[1] for n in (1, 2, 3)}


def make_versions(document: Any, commits: list[dict[str, Any]], users: dict[int, Any]) -> list[Any]:
    """One version row per commit, as the commit path and the reconciler derive them."""
    from documents.models import Version, VersionKind

    return Version.objects.bulk_create(
        Version(
            document=document,
            commit_sha=commit["sha"],
            author=users[commit["author"]],
            summary=f"Commit {commit['n']}",
            kind=VersionKind.CREATED if position == 0 else VersionKind.EDIT,
            committed_at=datetime.fromtimestamp(EPOCH + commit["n"] * 3600, UTC),
            created_by=users[commit["author"]],
            actor_kind="user",
        )
        for position, commit in enumerate(commits)
    )


def accept(document: Any, version: Any, by: Any) -> Any:
    """An acceptance of `version`: a passport commit's row, just after it."""
    from documents.models import Version, VersionKind

    return Version.objects.create(
        document=document,
        commit_sha="a" * 40,
        author=by,
        summary="Погоджено",
        kind=VersionKind.ACCEPTANCE,
        committed_at=version.committed_at + timedelta(minutes=1),
        created_by=by,
        actor_kind="user",
    )


def expected_introductions(corpus: dict[str, Any]) -> dict[int, str]:
    """Every non-blank body line at the last commit and the commit that introduced it, from the
    record: a sentence by the commit that created it, a heading by the base commit of its
    section. Walks the blocks as the generator's `line_truth` does."""
    truth, shift = corpus["truth"], corpus["shift"]
    sha_of = {c["n"]: c["sha"] for c in corpus["commits"]}
    # The corpus's frontmatter, a blank line, the title, a blank line; the title is the first
    # base commit's.
    expected, line = {7 + shift: sha_of[1]}, 8
    for block in truth["blocks"]:
        if block["type"] == "heading":
            line += 1
            section = int(block["text"].split()[1].split(".")[0])
            expected[line + shift] = sha_of[(section - 1) // 4 + 1]
        else:
            for sid in block["ids"]:
                line += 1
                expected[line + shift] = sha_of[truth["sentences"][str(sid)]["created"]]
        line += 1
    return expected


def moved_lines(corpus: dict[str, Any]) -> list[int]:
    """The lines, at the last commit, of the sentences a move carried and no edit changed after."""
    truth, lines, line = corpus["truth"], [], 8
    for block in truth["blocks"]:
        if block["type"] == "heading":
            line += 1
        else:
            for sid in block["ids"]:
                line += 1
                if truth["sentences"][str(sid)].get("moved"):
                    lines.append(line + corpus["shift"])
        line += 1
    return lines


def plain_blame(repo: Path, commit: str) -> dict[int, str]:
    """git's own attribution, no move rule: line to commit."""
    out = git(repo, "blame", "--porcelain", commit, "--", "document.md").decode("utf-8")
    return {
        int(m.group(2)): m.group(1)
        for m in (BLAME_LINE.match(raw) for raw in out.split("\n") if not raw.startswith("\t"))
        if m
    }


def added_lines(repo: Path, old: str, new: str) -> list[int]:
    """The non-blank lines `new` added to `document.md`, by their number in `new`."""
    out = git(repo, "diff", "-U0", old, new, "--", "document.md").decode("utf-8").split("\n")
    lines = []
    for position, raw in enumerate(out):
        match = HUNK.match(raw)
        if match:
            start, count = int(match.group(1)), int(match.group(2) or 1)
            added = [r for r in out[position + 1 :] if r.startswith("+")][:count]
            lines.extend(start + i for i, text in enumerate(added) if text[1:].strip())
    return sorted(lines)


def rows_of(version: Any) -> dict[int, tuple[str, str, bool, Any]]:
    from editing.models import LineAuthorship

    return {
        row.line: (row.file, row.introduced_by.commit_sha, row.ambiguous_move, row.expires_at)
        for row in LineAuthorship.objects.filter(version=version).select_related("introduced_by")
    }


def test_agrees_with_the_record_including_moves(
    corpus: dict[str, Any], migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    from editing import authorship
    from editing.models import LineAuthorship

    users = authors(member_of)
    document = make_document(title="Синтетичний корпус", created_by=users[1])
    repo, shift = corpus["repo"], corpus["shift"]
    with schema_context(migrated_tenant.number):
        versions = make_versions(document, corpus["commits"], users)
        previous = None
        for version in versions:
            result = authorship.compute(document, version.commit_sha, repository_path=repo)
            # Cold once, then each run bounded by the one before it.
            assert result.base == previous
            previous = version.commit_sha
        head = versions[-1]

        assert set(LineAuthorship.objects.values_list("version", flat=True)) == {head.pk}
        rows = rows_of(head)
        expected = expected_introductions(corpus)
        # Every non-blank body line has its row, and nothing else: no blank line, no frontmatter.
        assert sorted(rows) == sorted(expected)
        assert min(rows) > bundle.render(bundle.Frontmatter("x", "uk"), "").count("\n")
        assert {line: row[1] for line, row in rows.items()} == expected
        assert {row[0] for row in rows.values()} == {"document.md"}
        assert not any(row[2] for row in rows.values())

        by_sha = {v.commit_sha: v.author_id for v in versions}
        for position, author in enumerate(corpus["truth"]["line_truth"], 1):
            if author is not None:
                assert by_sha[rows[position + shift][1]] == users[author].pk, position

        # The moves: git alone gives the mover the moved sentences; the rows do not.
        moved = moved_lines(corpus)
        plain = plain_blame(repo, head.commit_sha)
        taken_by_git = [line for line in moved if plain[line] != expected[line]]
        assert len(taken_by_git) > 20
        assert all(rows[line][1] == expected[line] for line in taken_by_git)

        # Idempotent, and the cold run agrees: with only the head's rows, recomputing is cold.
        again = authorship.compute(document, head.commit_sha, repository_path=repo)
        assert again.base is None
        assert rows_of(head) == rows


def test_bounded_blame_reuses_cache(
    corpus: dict[str, Any],
    migrated_tenant: Any,
    member_of: Any,
    make_document: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from editing import authorship
    from editing.models import LineAuthorship

    users = authors(member_of)
    document = make_document(title="Синтетичний корпус", created_by=users[1])
    repo, commits = corpus["repo"], corpus["commits"]
    after = next(i for i, c in enumerate(commits) if i > 100 and c["kind"] == "insert")
    with schema_context(migrated_tenant.number):
        versions = make_versions(document, commits, users)
        cached, new = versions[after - 1], versions[after]
        assert authorship.compute(document, cached.commit_sha, repository_path=repo).base is None
        # A mark planted in the cache on the title, which the insertion leaves alone: a bounded
        # blame carries it over, where a recomputation would correct it.
        title = min(rows_of(cached))
        LineAuthorship.objects.filter(version=cached, line=title).update(introduced_by=cached)

        calls: list[tuple[str, ...]] = []
        real = authorship._git

        def recording(repository: Path, *args: str) -> bytes:
            calls.append(args)
            return real(repository, *args)

        monkeypatch.setattr(authorship, "_git", recording)
        result = authorship.compute(document, new.commit_sha, repository_path=repo)

    blames = [call for call in calls if call[0] == "blame"]
    assert blames == [
        ("blame", "--porcelain", f"^{cached.commit_sha}", new.commit_sha, "--", "document.md")
    ]
    assert result.base == cached.commit_sha
    fresh = added_lines(repo, cached.commit_sha, new.commit_sha)
    assert fresh
    assert result.reattributed == {"document.md": tuple(fresh)}
    with schema_context(migrated_tenant.number):
        rows = rows_of(new)
    assert {line for line, row in rows.items() if row[1] == new.commit_sha} == set(fresh)
    assert rows[title][1] == cached.commit_sha


def test_rows_kept_for_head_and_accepted_only(
    corpus: dict[str, Any], migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    from editing import authorship
    from editing.models import LineAuthorship

    users = authors(member_of)
    document = make_document(title="Синтетичний корпус", created_by=users[1])
    repo = corpus["repo"]
    with schema_context(migrated_tenant.number):
        versions = make_versions(document, corpus["commits"], users)
        older, accepted, head = versions[49], versions[99], versions[100]
        accept(document, accepted, users[1])
        authorship.compute(document, accepted.commit_sha, repository_path=repo)
        authorship.compute(document, older.commit_sha, repository_path=repo)
        older_rows = LineAuthorship.objects.filter(version=older).count()
        assert older_rows and LineAuthorship.objects.filter(version=accepted).exists()
        # A row computed on demand for a historical page, kept until it expires (DL-0266): not
        # the worker's to delete.
        on_demand = LineAuthorship.objects.create(
            version=versions[20],
            file="document.md",
            line=9,
            introduced_by=versions[0],
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )

        result = authorship.compute(document, head.commit_sha, repository_path=repo)

        kept = LineAuthorship.objects.filter(expires_at__isnull=True)
        assert set(kept.values_list("version", flat=True)) == {head.pk, accepted.pk}
        assert result.deleted == older_rows
        assert result.rows == LineAuthorship.objects.filter(version=head).count()
        assert LineAuthorship.objects.filter(pk=on_demand.pk).exists()


SYNTHETIC = {
    "title": "# Синтетичний порядок ведення журналу",
    "twin": "Кожен запис зберігається в журналі протягом трьох років.",
    "a": "Відповідальна особа перевіряє журнал щотижня.",
    "rest": [
        "Журнал ведеться в електронній формі.",
        "Доступ до журналу мають лише призначені працівники.",
        "Кожна зміна запису позначається датою.",
        "Виправлення вносяться окремим записом.",
        "Записи не видаляються до кінця строку зберігання.",
    ],
    "d": "Порядок переглядається щороку.",
}


def synthetic_document(*paragraphs: list[str]) -> str:
    body = "\n\n".join([SYNTHETIC["title"], *("\n".join(p) for p in paragraphs)]) + "\n"
    return bundle.render(bundle.Frontmatter(title="Синтетичний приклад", language="uk"), body)


def synthetic_history(tmp_path: Path) -> tuple[Path, list[str], list[str]]:
    """Three commits of an invented document: the first author writes two paragraphs, the
    second adds a paragraph opening with the same sentence as the first paragraph, the third
    moves the first paragraph below the second."""
    s = SYNTHETIC
    first, second, moved = [s["twin"], s["a"]], s["rest"], [s["twin"], s["d"]]
    texts = [
        synthetic_document(first, second),
        synthetic_document(first, second, moved),
        synthetic_document(second, first, moved),
    ]
    repo = tmp_path / "synthetic.git"
    return repo, import_history(repo, [(n, n, t) for n, t in enumerate(texts, 1)]), texts


def test_ambiguity_recorded(
    tmp_path: Path, migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    from editing import authorship

    # Which of the two identical sentences moved, the text cannot say.
    s = SYNTHETIC
    repo, shas, texts = synthetic_history(tmp_path)
    users = authors(member_of)
    document = make_document(title="Синтетичний приклад", created_by=users[1])
    commits = [{"sha": sha, "author": n, "n": n} for n, sha in enumerate(shas, 1)]
    with schema_context(migrated_tenant.number):
        versions = make_versions(document, commits, users)
        for version in versions:
            authorship.compute(document, version.commit_sha, repository_path=repo)
        rows = rows_of(versions[-1])
        final = texts[-1].split("\n")
        twins = [n for n, text in enumerate(final, 1) if text == s["twin"]]
        assert len(twins) == 2
        assert {line for line, row in rows.items() if row[2]} == set(twins)
        # The first author's other sentence moved with it, unambiguously: still theirs.
        assert rows[final.index(s["a"]) + 1][1:3] == (shas[0], False)
        assert rows[final.index(s["d"]) + 1][1:3] == (shas[1], False)
        assert all(rows[final.index(t) + 1][1:3] == (shas[0], False) for t in s["rest"])
        # Not guessed: the moved twin keeps what blame says, the commit that wrote it there.
        assert sorted(rows[line][1] for line in twins) == sorted([shas[1], shas[2]])

        # The cold run reaches the same rows.
        assert authorship.compute(document, shas[2], repository_path=repo).base is None
        assert rows_of(versions[-1]) == rows


def test_a_commit_without_its_version_stops_the_computation(
    tmp_path: Path, migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    from editing import authorship
    from editing.models import LineAuthorship

    repo, shas, _ = synthetic_history(tmp_path)
    users = authors(member_of)
    document = make_document(title="Синтетичний приклад", created_by=users[1])
    commits = [{"sha": sha, "author": n, "n": n} for n, sha in enumerate(shas, 1)]
    with schema_context(migrated_tenant.number):
        # The second commit's row not yet derived.
        make_versions(document, [commits[0], commits[2]], users)
        with pytest.raises(authorship.VersionMissing) as raised:
            authorship.compute(document, shas[2], repository_path=repo)
        assert raised.value.commits == (shas[1],)
        with pytest.raises(authorship.VersionMissing):
            authorship.compute(document, shas[1], repository_path=repo)
        assert not LineAuthorship.objects.exists()


def test_an_incomplete_cache_is_computed_cold(
    tmp_path: Path, migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    from editing import authorship
    from editing.models import LineAuthorship

    repo, shas, _ = synthetic_history(tmp_path)
    users = authors(member_of)
    document = make_document(title="Синтетичний приклад", created_by=users[1])
    commits = [{"sha": sha, "author": n, "n": n} for n, sha in enumerate(shas, 1)]
    with schema_context(migrated_tenant.number):
        versions = make_versions(document, commits, users)
        for version in versions:
            authorship.compute(document, version.commit_sha, repository_path=repo)
        expected = rows_of(versions[2])
        authorship.compute(document, shas[1], repository_path=repo)
        LineAuthorship.objects.filter(version=versions[1], line=min(rows_of(versions[1]))).delete()
        LineAuthorship.objects.filter(version=versions[2]).delete()

        result = authorship.compute(document, shas[2], repository_path=repo)

        assert result.base == shas[1]
        assert rows_of(versions[2]) == expected


def test_the_reconciler_requeues_an_edit_without_rows_and_the_task_writes_them(
    migrated_tenant: Any, member_of: Any, repo_root: Path, queued_authorship: list[Any]
) -> None:
    """An edit whose authorship job was lost is asked for again by the reconciler; the task, run
    as the worker runs it, writes the rows, and the reconciler has nothing left to ask."""
    from documents import bundle, gitstore, reconcile, services
    from documents.identity import identity_for
    from documents.locks import document_lock
    from documents.models import DocumentType, Folder
    from editing.models import LineAuthorship
    from editing.tasks import compute_authorship
    from identity.models import Language

    _, user, _ = member_of("the.author@example.test")
    Language.objects.get_or_create(code="uk", defaults={"label": "uk", "actor_kind": "system"})
    with schema_context(migrated_tenant.number):
        document = services.create_document(
            user,
            "Синтетичний порядок",
            "uk",
            DocumentType.objects.get(code="document"),
            Folder.objects.get(number=1),
        )
        repo = gitstore.open_repository(migrated_tenant.number, document.number)
        head = gitstore.head(repo)
        assert head is not None
        frontmatter, body = bundle.parse(gitstore.read(repo, "document.md", head).decode())
        with document_lock(migrated_tenant.number, document.number):
            sha = gitstore.commit(
                repo,
                {"document.md": bundle.render(frontmatter, body + "\nНове речення.\n").encode()},
                identity_for(user),
                "Edited",
                gitstore.Kind.EDIT,
            )
        services.derive_version(document, gitstore.commit_at(repo, sha), user)

    findings = reconcile.run(tenant=migrated_tenant.number, repair=True)
    assert [(f.kind, f.detail, f.repaired) for f in findings] == [("authorship_missing", sha, True)]
    assert queued_authorship == [(migrated_tenant.number, document.number, sha)]

    assert compute_authorship(migrated_tenant.number, document.number, sha) > 0
    with schema_context(migrated_tenant.number):
        assert LineAuthorship.objects.filter(version__commit_sha=sha).exists()
    assert reconcile.run(tenant=migrated_tenant.number) == []


def test_git_variables_of_the_process_never_reach_the_blame(
    migrated_tenant: Any,
    member_of: Any,
    repo_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A `GIT_DIR` inherited from the process is ignored, and a repository git reports as another
    account's is still read: the platform's configuration alone shapes the blame."""
    from documents import gitstore, services
    from documents.models import DocumentType, Folder
    from editing import authorship
    from identity.models import Language

    _, user, _ = member_of("the.author@example.test")
    Language.objects.get_or_create(code="uk", defaults={"label": "uk", "actor_kind": "system"})
    other = tmp_path / "other.git"
    subprocess.run(["git", "init", "--bare", "-q", str(other)], check=True)
    monkeypatch.setenv("GIT_DIR", str(other))
    monkeypatch.setenv("GIT_TEST_ASSUME_DIFFERENT_OWNER", "1")
    with schema_context(migrated_tenant.number):
        document = services.create_document(
            user,
            "Синтетичний порядок",
            "uk",
            DocumentType.objects.get(code="document"),
            Folder.objects.get(number=1),
        )
        head = gitstore.head(gitstore.open_repository(migrated_tenant.number, document.number))
        assert head is not None
        result = authorship.compute(
            document,
            head,
            repository_path=gitstore.repository_path(migrated_tenant.number, document.number),
        )
    assert result.rows > 0
