"""Finishing an editing session (DL-0222, DL-0261, DL-0321, DL-0322): the screen shows the changes,
the summary and the number to come; *send for review* commits one version of kind `edit` under the
lock and ends the session; a draft equal to the head makes nothing; the screen and *my edits* list
the roles, actions and terms the commit changes. People and titles are synthetic examples; the
text is invented."""

from __future__ import annotations

import re
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
    "# Terms\n\nThe first term.\nThe second term.\n\n"
    "# Approval\n\nThe first approval rule.\nThe second approval rule.\n"
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
                "Text",
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
    edited = BODY.replace("The second term.", "The second changed term.").replace(
        "The first approval rule.", "The first new approval rule."
    )
    set_draft(migrated_tenant, document, edited)

    page = client.get(f"/document/{document.number}/edit/finish/")
    body = page.content.decode()
    assert page.status_code == 200
    assert "The second <ins>changed </ins>term" in body and "The first <ins>new </ins>" in body
    assert 'value="Sections touched: Terms; Approval"' in body
    assert "the version waits as 0.0-2" in body


def test_finish_refused_while_an_editor_is_open(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    client, _, document = holding(migrated_tenant, member_of, new_document, BODY)
    client.post(f"/document/{document.number}/edit/load/")
    assert client.get(f"/document/{document.number}/edit/finish/").status_code == 409
    sent = client.post(f"/document/{document.number}/edit/send/", {"summary": "Changes"})
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
        migrated_tenant, document, BODY.replace("The second term.", "The second term. A new one.")
    )

    sent = client.post(f"/document/{document.number}/edit/send/", {"summary": "Terms clarified"})
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
    assert commit.message.splitlines()[0] == "Terms clarified"
    assert "The second term.\nA new one." in stored
    assert (version.kind, version.author_id, version.summary) == (
        "edit",
        author.pk,
        "Terms clarified",
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
    sent = client.post(f"/document/{document.number}/edit/send/", {"summary": "Nothing"})
    assert sent.status_code == 400
    assert "Nothing changed" in sent.content.decode()
    with schema_context(migrated_tenant.number):
        after = gitstore.head(gitstore.open_repository(migrated_tenant.number, document.number))
    assert after == before


def test_a_summary_a_commit_cannot_carry_is_refused(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    client, _, document = holding(migrated_tenant, member_of, new_document, BODY)
    set_draft(migrated_tenant, document, BODY.replace("The first term.", "An altered term."))
    # Every character a line splits on, and every control character git refuses, is refused on
    # the form, never by the commit.
    for summary in (
        "",
        "Kind: edit",
        "line\nsecond",
        "x" * 501,
        "line\x0bsecond",
        "line\x00",
        "line\x85Kind: approval",
        "first\u2028second",
        "line\x1bwith a control",
    ):
        sent = client.post(f"/document/{document.number}/edit/send/", {"summary": summary})
        assert sent.status_code == 400, summary


@pytest.mark.budget
def test_finish_within_budget(migrated_tenant: Any, member_of: Any, new_document: Any) -> None:
    """ASR-21's five seconds for finishing, on the forty-page corpus with one sentence changed."""
    text = CORPUS.read_text(encoding="utf-8")
    body = text.partition("\n---\n")[2].removeprefix("\n")
    client, _, document = holding(migrated_tenant, member_of, new_document, body)
    original = "Керівник напряму надає реєстр наданих доступів."
    set_draft(migrated_tenant, document, body.replace(original, original.replace("надає", "веде")))
    started = time.perf_counter()
    sent = client.post(f"/document/{document.number}/edit/send/", {"summary": "A clarification"})
    elapsed = time.perf_counter() - started
    assert sent.status_code == 302
    assert elapsed < 5.0, elapsed


def test_my_edits_tab_shows_the_draft_to_its_holder(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    client, _, document = holding(migrated_tenant, member_of, new_document, BODY)
    set_draft(migrated_tenant, document, BODY.replace("The second term.", "Another second term."))
    body = client.get(f"/document/{document.number}/my-edits/").content.decode()
    assert "<ins>" in body
    # The page stands on the holder's draft point (DL-0518).
    assert 'data-go="draft" aria-current="location"' in body
    other, _, _ = member_of("another.editor@example.test")
    assert other.get(f"/document/{document.number}/my-edits/").status_code == 404


def test_marked_text_renders_in_the_changes(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    """A span of either kind in the text: the changes render, the span as its class."""
    marked = BODY.replace("The first term.", "The [first]{.underline} [term]{.term}.")
    client, _, document = holding(migrated_tenant, member_of, new_document, marked)
    set_draft(migrated_tenant, document, marked.replace("The second term.", "Another second one."))
    for route in ("edit/finish/", "my-edits/"):
        page = client.get(f"/document/{document.number}/{route}")
        body = page.content.decode()
        assert page.status_code == 200, route
        assert '<span class="underline">first</span>' in body
        assert '<span class="entity entity-term">term</span>' in body


def test_a_draft_the_whitelist_refuses_is_named_not_committed(
    migrated_tenant: Any, member_of: Any, new_document: Any, settings: Any
) -> None:
    from documents import gitstore

    settings.LANGUAGE_CODE = "en"
    client, _, document = holding(migrated_tenant, member_of, new_document, BODY)
    set_draft(migrated_tenant, document, BODY + "\n##### A heading too deep\n")
    with schema_context(migrated_tenant.number):
        before = gitstore.head(gitstore.open_repository(migrated_tenant.number, document.number))
    for response in (
        client.get(f"/document/{document.number}/edit/finish/"),
        client.get(f"/document/{document.number}/my-edits/"),
        client.post(f"/document/{document.number}/edit/send/", {"summary": "Changes"}),
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
    set_draft(migrated_tenant, document, BODY.replace("The second term.", "A second, new one."))
    first = client.post(f"/document/{document.number}/edit/send/", {"summary": "Changes"})
    second = client.post(f"/document/{document.number}/edit/send/", {"summary": "Changes"})
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
    set_draft(migrated_tenant, document, "A text that will not be.\n")
    with schema_context(migrated_tenant.number):
        before = gitstore.head(gitstore.open_repository(migrated_tenant.number, document.number))
    real_lock = services.document_lock

    def removed_first(*args: Any, **kwargs: Any) -> Any:
        with schema_context(migrated_tenant.number):
            group.remove_member(membership, by=author)
        return real_lock(*args, **kwargs)

    monkeypatch.setattr(services, "document_lock", removed_first)
    sent = editor.post(f"/document/{document.number}/edit/send/", {"summary": "Changes"})

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
    set_draft(migrated_tenant, document, BODY.replace("The second term.", "A second, new one."))

    sent = client.post(f"/document/{document.number}/edit/send/", {"summary": "Changes"})

    assert sent.status_code == 302
    with schema_context(migrated_tenant.number):
        assert Version.objects.filter(document=document, kind="edit").count() == 2


def test_the_drafted_summary_fits_its_limit(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    from editing import summary

    old = "".join(f"# Section with a long name, number {n}\n\nSentence {n}.\n\n" for n in range(40))
    new = old.replace("Sentence", "Another sentence")
    drafted = summary.drafted(old, new)
    assert len(drafted) <= summary.SUMMARY_MAX
    assert summary.problem(drafted) is None and drafted.endswith("…")


def test_a_draft_typography_carries_over_the_ceiling_is_refused_as_too_large(
    migrated_tenant: Any, member_of: Any, new_document: Any, settings: Any
) -> None:
    """A draft just under the size ceiling whose straight quotes become «…» — two bytes each —
    is refused as too large, never answered with an error (DL-0329)."""
    from editing.markdown import load_spec

    settings.LANGUAGE_CODE = "en"
    ceiling = load_spec().max_bytes
    client, _, document = holding(migrated_tenant, member_of, new_document, BODY)
    paragraph = 'He said "yes" and went on.\n\n'
    body = BODY + "\n"
    while len((body + paragraph).encode("utf-8")) <= ceiling:
        body += paragraph
    assert len(body.encode("utf-8")) <= ceiling
    set_draft(migrated_tenant, document, body)

    for response in (
        client.get(f"/document/{document.number}/edit/finish/"),
        client.post(f"/document/{document.number}/edit/send/", {"summary": "Changes"}),
    ):
        assert response.status_code == 409
        assert "a text longer than the platform accepts" in response.content.decode()


def test_the_finishing_screen_lists_entity_changes(
    migrated_tenant: Any, member_of: Any, new_document: Any, settings: Any
) -> None:
    """The send-for-review screen and *my edits* list the roles, actions and terms the draft adds,
    relabels or removes — a span typed with a key the draft does not declare listed *added* with
    its words, as the commit will declare it (DL-0440)."""
    from editing.models import Draft

    settings.LANGUAGE_CODE = "en"
    client, _, document = holding(migrated_tenant, member_of, new_document, BODY)
    with schema_context(migrated_tenant.number):
        draft = Draft.objects.get(hold__document=document)
        draft.content = {
            **draft.content,
            "document.md": BODY.replace(
                "The first term.", "The first term binds [the treasurer]{.role #treasurer}."
            ),
            "entities.yaml": '- kind: "term"\n  key: "term-1"\n  label: "ten days"\n',
        }
        draft.save()

    for address in ("edit/finish/", "my-edits/"):
        page = client.get(f"/document/{document.number}/{address}").content.decode()
        treasurer = row(page, "treasurer")
        days = row(page, "term-1")
        assert "the treasurer" in treasurer and "added" in treasurer, address
        assert "declared with your version" in treasurer, address
        assert "ten days" in days and "added" in days, address
        assert "declared with your version" not in days, address


def row(page: str, key: str) -> str:
    """The entity changes' row for `key`."""
    found = re.search(rf'<tr data-kind="[a-z]+" data-key="{key}">.*?</tr>', page, re.S)
    assert found, key
    return found.group(0)
