"""The correction notice (ADR-0001, ADR-0014, DL-0113): at acceptance, for every `reviewer_edit`
version of the run and the acceptor's own versions, each line another author of the run wrote that
the version replaced or removed — or removed and the version restored — is one entry; one notice
per author, one notification per notice; moved lines, the accepted base's lines, an editor's
versions and the changer's own lines generate nothing; references only, never text.

People and groups are synthetic examples; the texts are invented. The corpus is the invented one
of `tests/fixtures/corpus/`.
"""

from __future__ import annotations

import os
import subprocess
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pytest

from notifications.models import Notification
from review import notices, services
from review.models import Acceptance, CorrectionLine, CorrectionNotice
from tenancy.schemas import schema_context

HEADING = "# Загальні положення\n\n"


def body(*paragraphs: tuple[str, ...]) -> str:
    """A body in the normal form under the created commit's heading: one sentence per line, a
    blank line between paragraphs."""
    return HEADING + "\n".join("\n".join(p) + "\n" for p in paragraphs)


def span(range_: str) -> list[int]:
    """The line numbers a range names: `"12"`, `"12-14"`, or none for `""`."""
    if not range_:
        return []
    first, _, last = range_.partition("-")
    return list(range(int(first), int(last or first) + 1))


def texts_at(lines: list[str], range_: str) -> list[str]:
    # Ranges count the lines of the whole file, its frontmatter included, as git does
    # and as `LINE_AUTHORSHIP.line` does.
    return [lines[n - 1] for n in span(range_)]


def assert_no_text(rows: Iterable[Any], texts: Iterable[str]) -> None:
    """No stored value of any row carries a wording (DL-0113)."""
    wordings = [text for text in texts if text]
    for row in rows:
        for column in row._meta.concrete_fields:
            value = getattr(row, column.attname)
            if isinstance(value, str):
                assert not any(text in value for text in wordings), (column.name, value)


# --- through `accept` -------------------------------------------------------------------------

A_BASE_1 = "Цей порядок описує погодження синтетичних документів."
A_BASE_2 = "Кожен документ має одного відповідального автора."
A_BASE_3 = "Автор готує текст і подає його на розгляд."
A_BASE_4 = "Погоджувач читає всі зміни від останнього погодження."
A_BASE_5 = "Погоджений текст стає основою наступних змін."
A_BASE_6 = "Кожне погодження записується до паспорта документа."
A_RUN_1 = "Кожен синтетичний документ має одного відповідального автора."
A_RUN_2 = "Автор готує текст і надсилає його на розгляд."
A_RUN_3 = "Кожне погодження записується до паспорта синтетичного документа."
R_1 = "Кожен синтетичний документ має автора і рецензента."
R_2 = "Автор готує текст, а рецензент його перевіряє."
R_3 = "Погоджений текст стає основою для всіх наступних змін."


@pytest.mark.integration
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_one_notice_per_author_run_lines_only(
    migrated_tenant: Any,
    cast: Any,
    commit_version: Any,
    repository: Any,
    queued_authorship: list[Any],
) -> None:
    people = cast(editors=("a",), reviewers=("r",))
    document, author, reviewer = people.document, people["a"], people["r"]
    commit_version(
        document, author, body((A_BASE_1, A_BASE_2), (A_BASE_3, A_BASE_4), (A_BASE_5, A_BASE_6))
    )
    with schema_context(migrated_tenant.number):
        services.accept(document, reviewer)
    # A's version changes three lines; R's replaces two of them and one of A's base lines.
    by_author = commit_version(
        document, author, body((A_BASE_1, A_RUN_1), (A_RUN_2, A_BASE_4), (A_BASE_5, A_RUN_3))
    )
    by_reviewer = commit_version(
        document,
        reviewer,
        body((A_BASE_1, R_1), (R_2, A_BASE_4), (R_3, A_RUN_3)),
        "reviewer_edit",
    )

    with schema_context(migrated_tenant.number):
        acceptance = services.accept(document, reviewer)
        acceptance = Acceptance.objects.get(pk=acceptance.pk)
        assert acceptance.notices_computed_at is not None
        notice = CorrectionNotice.objects.get(acceptance=acceptance)
        assert notice.author_id == author.pk
        lines = list(CorrectionLine.objects.filter(notice=notice))
        notifications = list(Notification.objects.filter(event="correction_notice"))
    assert len(lines) == 2
    assert {line.changing_version_id for line in lines} == {by_reviewer.pk}
    assert {line.author_version_id for line in lines} == {by_author.pk}
    assert {(line.entry, line.file) for line in lines} == {("line", "document.md")}
    written = repository.lines(document, by_author.commit_sha)
    assert sorted(t for line in lines for t in texts_at(written, line.range_before)) == sorted(
        [A_RUN_1, A_RUN_2]
    )
    accepted = repository.lines(document, by_reviewer.commit_sha)
    assert {t for line in lines for t in texts_at(accepted, line.range_after)} == {R_1, R_2}
    # One notification, for A alone: none for the base line, none for R.
    assert len(notifications) == 1
    notification = notifications[0]
    assert notification.user_id == author.pk
    assert notification.document_id == document.pk
    assert (notification.category, notification.event) == ("document", "correction_notice")
    assert notification.correction_notice_id == notice.pk
    assert notification.version_id == acceptance.version_id
    assert notification.created_at == notice.at and notification.facts == {}
    assert_no_text([notice, *lines, notification], [A_RUN_1, A_RUN_2, A_BASE_5, R_1, R_2, R_3])


@pytest.mark.integration
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_moved_lines_generate_nothing(
    migrated_tenant: Any, cast: Any, commit_version: Any, queued_authorship: list[Any]
) -> None:
    people = cast(editors=("a",), reviewers=("b",))
    document, author, reviewer = people.document, people["a"], people["b"]
    first = (A_BASE_1, A_BASE_2, A_BASE_3)
    second = (A_BASE_4, A_BASE_5)
    commit_version(document, author, body(first, second))
    # B moves A's paragraph verbatim.
    commit_version(document, reviewer, body(second, first), "reviewer_edit")

    with schema_context(migrated_tenant.number):
        acceptance = services.accept(document, reviewer)
        assert Acceptance.objects.get(pk=acceptance.pk).notices_computed_at is not None
        assert not CorrectionNotice.objects.exists()
        assert not CorrectionLine.objects.exists()
        assert not Notification.objects.filter(event="correction_notice").exists()


@pytest.mark.integration
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_editors_versions_generate_nothing(
    migrated_tenant: Any, cast: Any, commit_version: Any, queued_authorship: list[Any]
) -> None:
    people = cast(editors=("a", "c"), reviewers=("r",))
    document = people.document
    commit_version(document, people["a"], body((A_BASE_1, A_BASE_2)))
    # C, an editor without *accept*, replaces A's line: an ordinary edit.
    commit_version(document, people["c"], body((A_BASE_1, A_RUN_1)), "edit")

    with schema_context(migrated_tenant.number):
        acceptance = services.accept(document, people["r"])
        assert Acceptance.objects.get(pk=acceptance.pk).notices_computed_at is not None
        assert not CorrectionNotice.objects.exists()
        assert not Notification.objects.filter(event="correction_notice").exists()


@pytest.mark.integration
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_acceptors_own_versions_count(
    migrated_tenant: Any,
    cast: Any,
    commit_version: Any,
    link_group: Any,
    repository: Any,
    queued_authorship: list[Any],
) -> None:
    from access.rights import Right

    people = cast(editors=("a", "b"), reviewers=())
    document, acceptor, author = people.document, people["a"], people["b"]
    written = commit_version(document, author, body((A_BASE_1, A_BASE_2)))
    # A rewrites B's line as an editor, then is given *accept* and accepts.
    rewritten = commit_version(document, acceptor, body((A_BASE_1, A_RUN_1)), "edit")
    link_group(document, [Right.ACCEPT], [people.memberships["a"]], acceptor)

    with schema_context(migrated_tenant.number):
        acceptance = services.accept(document, acceptor)
        notice = CorrectionNotice.objects.get(acceptance=acceptance)
        line = CorrectionLine.objects.get(notice=notice)
        notification = Notification.objects.get(event="correction_notice")
    assert notice.author_id == author.pk
    assert (line.entry, line.changing_version_id, line.author_version_id) == (
        "line",
        rewritten.pk,
        written.pk,
    )
    assert texts_at(repository.lines(document, written.commit_sha), line.range_before) == [A_BASE_2]
    assert (notification.user_id, notification.correction_notice_id) == (author.pk, notice.pk)


@pytest.mark.integration
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_restored_line(
    migrated_tenant: Any,
    cast: Any,
    commit_version: Any,
    repository: Any,
    queued_authorship: list[Any],
) -> None:
    people = cast(editors=("a", "b"), reviewers=("r",))
    document, remover, reviewer = people.document, people["a"], people["r"]
    whole = body((A_BASE_1, A_BASE_2, A_BASE_3))
    # B writes the line, A removes it, R's version restores it.
    written = commit_version(document, people["b"], whole)
    removed = commit_version(document, remover, body((A_BASE_1, A_BASE_3)))
    restored = commit_version(document, reviewer, whole, "reviewer_edit")

    with schema_context(migrated_tenant.number):
        acceptance = services.accept(document, reviewer)
        notice = CorrectionNotice.objects.get(acceptance=acceptance)
        line = CorrectionLine.objects.get(notice=notice)
        notification = Notification.objects.get(event="correction_notice")
    assert notice.author_id == remover.pk
    assert line.entry == "restored"
    # The remover as the author, the removing version as `author_version`, the line's range in
    # that version's parent as `range_before` (ADR-0014).
    assert (line.changing_version_id, line.author_version_id) == (restored.pk, removed.pk)
    assert texts_at(repository.lines(document, written.commit_sha), line.range_before) == [A_BASE_2]
    assert notification.user_id == remover.pk
    assert_no_text([notice, line, notification], [A_BASE_2])


# --- the repository-level core, against the corpus --------------------------------------------

GIT_ENV = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
ACCEPTOR = 1


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], env=GIT_ENV, capture_output=True, timeout=120
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    return result.stdout.decode("utf-8")


def removed_later(repo: Path, after: str, tip: str) -> set[str]:
    """Every line some commit after `after` up to `tip` removed from `document.md`."""
    out = git(
        repo, "log", "-p", "-U0", "--no-color", "--format=", f"{after}..{tip}", "--", "document.md"
    )
    return {
        line[1:] for line in out.split("\n") if line.startswith("-") and not line.startswith("---")
    }


@pytest.mark.integration
def test_agrees_with_the_record(corpus_ukr: dict[str, Any]) -> None:
    """Every tag an acceptance point, author 1 the sole holder of *accept*: per interval, the
    entries are the record's sentences rewritten or deleted by author 1 that another author
    created inside the interval — the run, never the base — grouped per author."""
    repo, truth = corpus_ukr["repo"], corpus_ukr["truth"]
    sha = {c["n"]: c["sha"] for c in truth["commits"]}
    author_of = {c["n"]: c["author"] for c in truth["commits"]}
    number_of = {c["sha"]: c["n"] for c in truth["commits"]}
    tagged = git(repo, "for-each-ref", "--format=%(*objectname)", "refs/tags").split()
    points = sorted(number_of[commit] for commit in tagged)
    assert len(points) == 20
    # The first interval's base is the root commit, whose lines generate nothing.
    bounds = [1, *points]
    lines_cache: dict[str, list[str]] = {}

    def lines(commit: str) -> list[str]:
        if commit not in lines_cache:
            lines_cache[commit] = git(repo, "show", f"{commit}:document.md").split("\n")
        return lines_cache[commit]

    found = 0
    for low, high in zip(bounds, bounds[1:], strict=False):
        base, tip = sha[low], sha[high]
        run = [
            notices.RunCommit(sha=sha[n], parent=sha[n - 1], author=author_of[n])
            for n in range(low + 1, high + 1)
        ]
        covered = {sha[n] for n in range(low + 1, high + 1) if author_of[n] == ACCEPTOR}
        # `entries` reads `document.md` as lines and does not parse its frontmatter,
        # which in the corpus carries a key of its own.
        got = notices.entries(repo, base=base, run=run, covered=covered)

        expected: dict[int, set[tuple[str, str, str]]] = defaultdict(set)
        sentence_of: dict[tuple[int, str, str, str], dict[str, Any]] = {}
        for sentence in truth["sentences"].values():
            if (
                sentence["status"] in ("rewritten", "deleted")
                and sentence["changed_by"] == ACCEPTOR
                and sentence["author"] != ACCEPTOR
                and low < sentence["created"] <= high
                and low < sentence["changed_at"] <= high
            ):
                key = (sha[sentence["created"]], sha[sentence["changed_at"]], sentence["text"])
                expected[sentence["author"]].add(key)
                sentence_of[(sentence["author"], *key)] = sentence

        actual: dict[int, set[tuple[str, str, str]]] = defaultdict(set)
        keys = []
        for entry in got:
            assert entry.kind == "line", entry
            assert entry.changer == ACCEPTOR and entry.author != entry.changer, entry
            assert entry.changing_version in covered, entry
            for text in texts_at(lines(entry.author_version), entry.range_before):
                key = (entry.author_version, entry.changing_version, text)
                keys.append((entry.author, *key))
                actual[entry.author].add(key)
        assert len(keys) == len(set(keys)), (low, high)
        assert dict(actual) == dict(expected), (low, high)
        found += sum(len(keys_of) for keys_of in expected.values())

        # `range_after`: empty for a removal; for a replacement no later version of the interval
        # touched, the replacement's line in the accepted version.
        later_removed: dict[str, set[str]] = {}
        for entry in got:
            for text in texts_at(lines(entry.author_version), entry.range_before):
                sentence = sentence_of[
                    (entry.author, entry.author_version, entry.changing_version, text)
                ]
                if sentence["status"] == "deleted":
                    assert entry.range_after == "", entry
                    continue
                replacement = truth["sentences"][str(sentence["replaced_by"])]["text"]
                if entry.changing_version not in later_removed:
                    later_removed[entry.changing_version] = removed_later(
                        repo, entry.changing_version, tip
                    )
                if replacement not in later_removed[entry.changing_version]:
                    assert replacement in texts_at(lines(tip), entry.range_after), entry
    # The record holds entries to find, not only lines that generate nothing.
    assert found > 0
