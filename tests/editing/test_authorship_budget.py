"""The authorship worker's budget: one cold run over a forty-page, two-hundred-commit history in
under five seconds (DL-0135).

The corpus is the invented one of `tests/fixtures/corpus/`, its frontmatter rewritten as the
platform writes it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
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
BUDGET_SECONDS = 5.0


def git(repo: Path, *args: str, stdin: bytes | None = None) -> bytes:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    result = subprocess.run(
        ["git", "-C", str(repo), *args], input=stdin, env=env, capture_output=True, timeout=120
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    return result.stdout


def platform_frontmatter(text: str) -> str:
    """The corpus's document with its frontmatter as the platform writes it."""
    lines = text.split("\n")
    fields = dict(line.split(": ", 1) for line in lines[1:4])
    return bundle.render(
        bundle.Frontmatter(title=fields["title"], language=fields["language"]),
        "\n".join(lines[6:]),
    )


@pytest.fixture(scope="module")
def corpus(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """The Ukrainian corpus with the platform's frontmatter, as a bare repository, and its
    commits."""
    out = tmp_path_factory.mktemp("authorship-budget")
    generated, truth_path = out / "generated.git", out / "truth.json"
    result = subprocess.run(
        [sys.executable, str(CORPUS / "corpus.py"), "--lang", "ukr", "--repo", str(generated)]
        + ["--truth", str(truth_path)],
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    commits = json.loads(truth_path.read_text(encoding="utf-8"))["commits"]
    batch = git(
        generated,
        "cat-file",
        "--batch",
        stdin="".join(f"{c['sha']}:document.md\n" for c in commits).encode(),
    )
    repo = out / "corpus-ukr.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(repo)], check=True)
    stream, at = bytearray(), 0
    for mark, commit in enumerate(commits, 1):
        header_end = batch.index(b"\n", at)
        size = int(batch[at:header_end].split(b" ")[2])
        text = batch[header_end + 1 : header_end + 1 + size].decode("utf-8")
        at = header_end + 1 + size + 1
        data = platform_frontmatter(text).encode("utf-8")
        who = f"{commit['author']} <{commit['author']}@{DOMAIN}> {EPOCH + commit['n'] * 3600} +0000"
        stream += f"commit refs/heads/main\nmark :{mark}\nauthor {who}\ncommitter {who}\n".encode()
        stream += b"data 6\nCommit\n"
        if mark > 1:
            stream += f"from :{mark - 1}\n".encode()
        stream += f"M 100644 inline document.md\ndata {len(data)}\n".encode() + data + b"\n"
    marks = out / "marks"
    git(repo, "fast-import", "--quiet", f"--export-marks={marks}", stdin=bytes(stream))
    shas = dict(line.split(" ") for line in marks.read_text().splitlines())
    return {
        "repo": repo,
        "commits": [{**c, "sha": shas[f":{m}"]} for m, c in enumerate(commits, 1)],
    }


def test_cold_run_within_budget(
    corpus: dict[str, Any], migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    from documents.models import Version, VersionKind
    from editing import authorship
    from editing.models import LineAuthorship

    users = {n: member_of(f"corpus.author.{n}@example.test")[1] for n in (1, 2, 3)}
    document = make_document(title="Синтетичний корпус", created_by=users[1])
    with schema_context(migrated_tenant.number):
        versions = Version.objects.bulk_create(
            Version(
                document=document,
                commit_sha=commit["sha"],
                author=users[commit["author"]],
                summary="Commit",
                kind=VersionKind.CREATED if position == 0 else VersionKind.EDIT,
                committed_at=datetime.fromtimestamp(EPOCH + commit["n"] * 3600, UTC),
                created_by=users[commit["author"]],
                actor_kind="user",
            )
            for position, commit in enumerate(corpus["commits"])
        )
        head = versions[-1]
        assert not LineAuthorship.objects.exists()

        started = time.perf_counter()
        result = authorship.compute(document, head.commit_sha, repository_path=corpus["repo"])
        elapsed = time.perf_counter() - started

        assert result.base is None
        assert result.rows == LineAuthorship.objects.filter(version=head).count() > 1000
    print(f"cold run: {elapsed:.3f} s, {result.rows} rows, {result.moves} moves followed")
    assert elapsed < BUDGET_SECONDS
