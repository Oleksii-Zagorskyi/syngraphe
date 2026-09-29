"""Finishing an editing session (DL-0222, DL-0261, DL-0321, DL-0322): the screen shows the changes,
the summary and the number to come; *send for review* commits one version of kind `edit` under the
lock and ends the session; a draft equal to the head makes nothing. People and titles are synthetic
examples; the text is invented."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

CORPUS = Path(__file__).resolve().parents[1] / "fixtures" / "corpus" / "document-ukr.md"
BODY = (
    "# Умови\n\nПерше речення умов.\nДруге речення умов.\n\n"
    "# Погодження\n\nПерше речення погодження.\nДруге речення погодження.\n"
)


def holding(migrated_tenant: Any, member_of: Any, new_document: Any, body: str) -> tuple[Any, ...]:
    """A document whose head holds `body`, taken by its author, the draft as the head."""
    from documents import bundle, gitstore, services
    from documents.identity import identity_for
    from documents.locks import document_lock

    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    with schema_context(migrated_tenant.number):
        repo = gitstore.open_repository(migrated_tenant.number, document.number)
        head = gitstore.head(repo)
        assert head is not None
        frontmatter, _ = bundle.parse(gitstore.read(repo, "document.md", head).decode())
        with document_lock(migrated_tenant.number, document.number):
            sha = gitstore.commit(
                repo,
                {"document.md": bundle.render(frontmatter, body).encode()},
                identity_for(author),
                "Текст",
                gitstore.Kind.EDIT,
            )
        services.derive_version(document, gitstore.commit_at(repo, sha), author)
    assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
    return client, author, document


def set_draft(migrated_tenant: Any, document: Any, body: str) -> None:
    from editing.models import Draft

    with schema_context(migrated_tenant.number):
        draft = Draft.objects.get(hold__document=document)
        draft.content = {**draft.content, "document.md": body}
        draft.save()


def test_screen_shows_changes_summary_and_number(
    migrated_tenant: Any, member_of: Any, new_document: Any, settings: Any
) -> None:
    settings.LANGUAGE_CODE = "en"
    client, _, document = holding(migrated_tenant, member_of, new_document, BODY)
    edited = BODY.replace("Друге речення умов.", "Друге змінене речення умов.").replace(
        "Перше речення погодження.", "Перше нове речення погодження."
    )
    set_draft(migrated_tenant, document, edited)

    page = client.get(f"/document/{document.number}/edit/finish/")
    body = page.content.decode()
    assert page.status_code == 200
    assert "Друге <ins>змінене </ins>речення" in body and "Перше <ins>нове </ins>" in body
    assert 'value="Sections touched: Умови; Погодження"' in body
    assert "the version waits as 0.0-2" in body


def test_finish_refused_while_an_editor_is_open(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    client, _, document = holding(migrated_tenant, member_of, new_document, BODY)
    client.post(f"/document/{document.number}/edit/load/")
    assert client.get(f"/document/{document.number}/edit/finish/").status_code == 409
    sent = client.post(f"/document/{document.number}/edit/send/", {"summary": "Зміни"})
    assert sent.status_code == 409


def test_send_for_review_commits_one_version(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    queued_authorship: list[Any],
    settings: Any,
) -> None:
    from audit.models import AuditEvent
    from documents import gitstore
    from documents.models import Version
    from editing.models import Draft, Hold

    settings.LANGUAGE_CODE = "en"
    client, author, document = holding(migrated_tenant, member_of, new_document, BODY)
    set_draft(
        migrated_tenant, document, BODY.replace("Друге речення умов.", "Друге речення. Нове.")
    )

    sent = client.post(f"/document/{document.number}/edit/send/", {"summary": "Уточнено умови"})
    assert sent.status_code == 302 and sent["Location"] == f"/document/{document.number}/"
    with schema_context(migrated_tenant.number):
        repo = gitstore.open_repository(migrated_tenant.number, document.number)
        head = gitstore.head(repo)
        assert head is not None
        commit = gitstore.commit_at(repo, head)
        version = Version.objects.get(commit_sha=head)
        hold = Hold.objects.get(document=document)
        assert not Draft.objects.filter(hold=hold).exists()
        stored = gitstore.read(repo, "document.md", head).decode()
    trailers = commit.message.strip().split("\n\n")[-1].splitlines()
    assert trailers[0].startswith("Normalizer: 1@") and trailers[-1] == "Kind: edit"
    assert commit.message.splitlines()[0] == "Уточнено умови"
    assert "Друге речення.\nНове." in stored
    assert (version.kind, version.author_id, version.summary) == (
        "edit",
        author.pk,
        "Уточнено умови",
    )
    assert (hold.release_kind, hold.released_by) == ("finished", None)
    assert queued_authorship == [(migrated_tenant.number, document.number, head)]
    assert AuditEvent.objects.filter(action="document.version_committed").count() == 1
    page = client.get(sent["Location"]).content.decode()
    assert "Sent for review — the version waits as 0.0-2." in page
    tab = client.get(f"/document/{document.number}/edit/")
    assert tab.status_code == 200 and 'class="held"' not in tab.content.decode()


def test_empty_version_refused(
    migrated_tenant: Any, member_of: Any, new_document: Any, settings: Any
) -> None:
    from documents import gitstore

    settings.LANGUAGE_CODE = "en"
    client, _, document = holding(migrated_tenant, member_of, new_document, BODY)
    set_draft(migrated_tenant, document, BODY.replace("\n\n", "\n\n\n", 1))
    with schema_context(migrated_tenant.number):
        before = gitstore.head(gitstore.open_repository(migrated_tenant.number, document.number))
    sent = client.post(f"/document/{document.number}/edit/send/", {"summary": "Нічого"})
    assert sent.status_code == 400
    assert "Nothing changed" in sent.content.decode()
    with schema_context(migrated_tenant.number):
        after = gitstore.head(gitstore.open_repository(migrated_tenant.number, document.number))
    assert after == before


def test_a_summary_a_commit_cannot_carry_is_refused(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    client, _, document = holding(migrated_tenant, member_of, new_document, BODY)
    set_draft(migrated_tenant, document, BODY.replace("Перше речення умов.", "Змінене речення."))
    # Every character a line splits on, and every control character git refuses, is refused on
    # the form, never by the commit.
    for summary in (
        "",
        "Kind: edit",
        "рядок\nдругий",
        "а" * 501,
        "рядок\x0bдругий",
        "рядок\x00",
        "рядок\x85Kind: approval",
        "Перше\u2028друге",
        "рядок\x1bз керуванням",
    ):
        sent = client.post(f"/document/{document.number}/edit/send/", {"summary": summary})
        assert sent.status_code == 400, summary


def test_finish_within_budget(migrated_tenant: Any, member_of: Any, new_document: Any) -> None:
    """ASR-21's five seconds for finishing, on the forty-page corpus with one sentence changed."""
    text = CORPUS.read_text(encoding="utf-8")
    body = text.partition("\n---\n")[2].removeprefix("\n")
    client, _, document = holding(migrated_tenant, member_of, new_document, body)
    original = "Керівник напряму надає реєстр наданих доступів."
    set_draft(migrated_tenant, document, body.replace(original, original.replace("надає", "веде")))
    started = time.perf_counter()
    sent = client.post(f"/document/{document.number}/edit/send/", {"summary": "Уточнення"})
    elapsed = time.perf_counter() - started
    assert sent.status_code == 302
    assert elapsed < 5.0, elapsed


def test_my_edits_tab_shows_the_draft_to_its_holder(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    client, _, document = holding(migrated_tenant, member_of, new_document, BODY)
    set_draft(migrated_tenant, document, BODY.replace("Друге речення умов.", "Друге інше речення."))
    body = client.get(f"/document/{document.number}/my-edits/").content.decode()
    assert "<ins>" in body and f'href="/document/{document.number}/my-edits/"' in body
    other, _, _ = member_of("another.editor@example.test")
    assert other.get(f"/document/{document.number}/my-edits/").status_code == 404


def test_marked_text_renders_in_the_changes(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    """A span of either kind in the text: the changes render, the span as its class."""
    marked = BODY.replace("Перше речення умов.", "Перше [речення]{.underline} [умов]{.term}.")
    client, _, document = holding(migrated_tenant, member_of, new_document, marked)
    set_draft(migrated_tenant, document, marked.replace("Друге речення умов.", "Друге інше."))
    for route in ("edit/finish/", "my-edits/"):
        page = client.get(f"/document/{document.number}/{route}")
        body = page.content.decode()
        assert page.status_code == 200, route
        assert '<span class="underline">речення</span>' in body
        assert '<span class="entity entity-term">умов</span>' in body


def test_a_draft_the_whitelist_refuses_is_named_not_committed(
    migrated_tenant: Any, member_of: Any, new_document: Any, settings: Any
) -> None:
    from documents import gitstore

    settings.LANGUAGE_CODE = "en"
    client, _, document = holding(migrated_tenant, member_of, new_document, BODY)
    set_draft(migrated_tenant, document, BODY + "\n##### Надто глибокий заголовок\n")
    with schema_context(migrated_tenant.number):
        before = gitstore.head(gitstore.open_repository(migrated_tenant.number, document.number))
    for response in (
        client.get(f"/document/{document.number}/edit/finish/"),
        client.get(f"/document/{document.number}/my-edits/"),
        client.post(f"/document/{document.number}/edit/send/", {"summary": "Зміни"}),
    ):
        body = response.content.decode()
        assert response.status_code == 409
        assert "line 11: a heading below depth four" in body and 'href="/help/markdown/"' in body
    with schema_context(migrated_tenant.number):
        after = gitstore.head(gitstore.open_repository(migrated_tenant.number, document.number))
    assert after == before


def test_a_second_send_lands_on_the_document(
    migrated_tenant: Any, member_of: Any, new_document: Any, queued_authorship: list[Any]
) -> None:
    """A double click: the second request finds the hold finished and follows the first."""
    client, _, document = holding(migrated_tenant, member_of, new_document, BODY)
    set_draft(migrated_tenant, document, BODY.replace("Друге речення умов.", "Друге нове."))
    first = client.post(f"/document/{document.number}/edit/send/", {"summary": "Зміни"})
    second = client.post(f"/document/{document.number}/edit/send/", {"summary": "Зміни"})
    assert first.status_code == second.status_code == 302
    assert second["Location"] == f"/document/{document.number}/"


def test_send_decides_the_right_under_the_lock(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The holder removed from their group while *send* waits for the lock commits nothing."""
    from access.rights import Right
    from documents import gitstore
    from editing import services

    _, author, own = member_of("the.author@example.test")
    editor, _, membership = member_of("an.editor@example.test")
    document = new_document(author)
    group = link_group(document, [Right.EDIT], [own, membership], author)
    assert editor.post(f"/document/{document.number}/edit/take/").status_code == 200
    set_draft(migrated_tenant, document, "Текст, якого не буде.\n")
    with schema_context(migrated_tenant.number):
        before = gitstore.head(gitstore.open_repository(migrated_tenant.number, document.number))
    real_lock = services.document_lock

    def removed_first(*args: Any, **kwargs: Any) -> Any:
        with schema_context(migrated_tenant.number):
            group.remove_member(membership, by=author)
        return real_lock(*args, **kwargs)

    monkeypatch.setattr(services, "document_lock", removed_first)
    sent = editor.post(f"/document/{document.number}/edit/send/", {"summary": "Зміни"})

    assert sent.status_code == 404
    with schema_context(migrated_tenant.number):
        after = gitstore.head(gitstore.open_repository(migrated_tenant.number, document.number))
    assert after == before


def test_a_broker_failure_after_the_commit_still_reports_the_version(
    migrated_tenant: Any, member_of: Any, new_document: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from documents.models import Version
    from editing import tasks

    def unreachable(*_: Any) -> None:
        raise ConnectionError("the broker is unreachable")

    monkeypatch.setattr(tasks, "queue_authorship", unreachable)
    client, _, document = holding(migrated_tenant, member_of, new_document, BODY)
    set_draft(migrated_tenant, document, BODY.replace("Друге речення умов.", "Друге нове."))

    sent = client.post(f"/document/{document.number}/edit/send/", {"summary": "Зміни"})

    assert sent.status_code == 302
    with schema_context(migrated_tenant.number):
        assert Version.objects.filter(document=document, kind="edit").count() == 2


def test_the_drafted_summary_fits_its_limit(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    from editing import summary

    old = "".join(f"# Розділ з довгою назвою номер {n}\n\nРечення {n}.\n\n" for n in range(40))
    new = old.replace("Речення", "Інше речення")
    drafted = summary.drafted(old, new)
    assert len(drafted) <= summary.SUMMARY_MAX
    assert summary.problem(drafted) is None and drafted.endswith("…")
