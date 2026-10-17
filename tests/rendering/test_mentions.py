"""Mentions read where the reader may follow them (ST-0043, DL-0436, DL-0084, ASR-16): a mention is
a link to a document its reader may read while it is active, and its words alone otherwise — an
archived document, one they may not read, a number that names none — with no title, no mark and
no message, on every page that draws a document's text; an export carries the words alone, the
Markdown the span. People and titles are synthetic examples; text is invented."""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any

import pytest

from access.rights import Right
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

FORM = "https://forms.example.test/request"
GUIDE = "https://forms.example.test/travel"


def mentioning(open_: int, closed: int, *, words: str = "follow", now: str = "") -> str:
    """A body mentioning `open_` and `closed`, each also holding a link of its own; `now` changes
    the sentences that hold the links."""
    return (
        "# General provisions\n\n"
        f"Payments {words} [the payment rules]{{.document #{open_}}} and "
        f"[the travel rules]{{.document #{closed}}}.\n"
        f"{now}Use [[the request form]({FORM})]{{.document #{open_}}}.\n"
        f"{now}Read [[the travel guide]({GUIDE})]{{.document #{closed}}}.\n"
    )


def filtered(page: str, open_: int, closed: int, where: str) -> None:
    """`page` links the mention of `open_` and draws `closed`'s as its words, every anchor closed
    and none inside another: the link inside the followed mention reads as its words, the one
    inside the plain mention stays a link."""
    assert f'<a class="mention" href="/document/{open_}/">' in page, where
    assert f"/document/{closed}/" not in page, where
    # Its words between the text around it: no element, no class, no attribute.
    assert re.search(r"(?:<ins>|<del>|\s|and )the travel rules(?:</ins>|</del>)?\.", page), where
    assert "entity-document" not in page and f'data-id="{closed}"' not in page, where
    assert FORM not in page and GUIDE in page, where
    assert page.count("<a ") == page.count("</a>"), where
    assert not re.search(r"<a [^>]*>(?:(?!</a>).)*<a ", page, re.S), where


def targets(new_document: Any, owner: Any, count: int) -> list[Any]:
    return [new_document(owner, f"Synthetic target {n}") for n in range(count)]


def test_only_active_readable_targets_link(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from documents.models import Document, DocumentState
    from rendering import mentions, reading
    from rendering.renderer import render

    _, reader, membership = member_of("the.reader@example.test")
    _, owner, _ = member_of("the.owner@example.test")
    here = new_document(owner)
    readable, unreadable, archived = targets(new_document, owner, 3)
    for document in (here, readable, archived):
        link_group(document, [Right.VIEW_ACCEPTED], [membership], owner)
    missing = 4096
    numbers = [readable.number, unreadable.number, archived.number, missing]
    body = "".join(f"See [the rules {n}]{{.document #{n}}}.\n" for n in numbers)
    with schema_context(migrated_tenant.number):
        Document.objects.filter(pk=archived.pk).update(state=DocumentState.ARCHIVED)

        assert mentions.reachable(reader, numbers) == {readable.number}
        assert [m.number for m in mentions.targets(body)] == numbers
        html = render(body, context=reading.context(reader, here, body, images=None))
        # A fixed number of queries, whatever the count of numbers.
        with CaptureQueriesContext(connection) as one:
            mentions.reachable(reader, numbers[:1])
        with CaptureQueriesContext(connection) as all_:
            mentions.reachable(reader, numbers)

    assert html.count('<a class="mention"') == 1
    assert f'<a class="mention" href="/document/{readable.number}/">the rules' in html
    for number in numbers[1:]:
        assert f"See the rules {number}." in html and f"/document/{number}/" not in html
    assert "title=" not in html and "entity-document" not in html and "data-id" not in html
    assert len(all_.captured_queries) == len(one.captured_queries)


def test_a_number_only_another_organisation_holds_is_not_followed(
    migrated_tenant: Any, member_of: Any, new_document: Any, make_tenant_schema: Any
) -> None:
    """A mention is read in the organisation of the text that holds it: a number naming a
    document only another organisation holds — one its reader may read there — is words alone."""
    from documents.models import Document, DocumentType, Folder, next_document_number
    from identity.models import Language, Membership
    from rendering import mentions

    _, owner, _ = member_of("the.owner@example.test")
    new_document(owner)
    other = make_tenant_schema("Another Example Org")
    Membership.objects.create(tenant=other, user=owner, actor_kind="system")
    Language.objects.get_or_create(code="uk", defaults={"label": "uk", "actor_kind": "system"})
    with schema_context(other.number):
        for _ in range(3):
            there = Document.objects.create(
                number=next_document_number(),
                title="Synthetic document elsewhere",
                language_id="uk",
                document_type=DocumentType.objects.get(code="document"),
                folder=Folder.objects.get(number=1),
                created_by=owner,
                actor_kind="user",
                author_only=True,
                state="active",
            )
        assert mentions.reachable(owner, [there.number]) == {there.number}
    with schema_context(migrated_tenant.number):
        assert not Document.objects.filter(number=there.number).exists()
        assert mentions.reachable(owner, [there.number]) == frozenset()


def test_an_archived_target_is_plain_for_administrators(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    from documents.models import Document, DocumentState

    client, admin, membership = member_of("the.admin@example.test", is_tenant_admin=True)
    _, owner, _ = member_of("the.owner@example.test")
    here = new_document(owner)
    (archived,) = targets(new_document, owner, 1)
    for document in (here, archived):
        link_group(document, [Right.VIEW_PENDING], [membership], owner)
    commit_version(here, owner, f"See [the archived rules]{{.document #{archived.number}}}.\n")
    with schema_context(migrated_tenant.number):
        Document.objects.filter(pk=archived.pk).update(state=DocumentState.ARCHIVED)

    page = client.get(f"/document/{here.number}/").content.decode()

    assert "the archived rules" in page
    assert 'class="mention"' not in page


def test_every_surface_filters_mentions(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    queued_authorship: list[Any],
    settings: Any,
) -> None:
    """The View tab, the historical page, compare, pending edits, the edit tab's drawn text — before
    a hold and the holder's — *my edits*, the send-for-review screen, the
    stopped editor and a kept draft's changes, as a reader of the one target alone; the mentioning
    sentence's words changed between the versions."""
    from editing.models import Draft, Hold

    settings.LANGUAGE_CODE = "en"
    client, author, membership = member_of("the.author@example.test")
    _, other, other_membership = member_of("the.other@example.test")
    admin, _, _ = member_of("the.admin@example.test", is_tenant_admin=True)
    _, owner, _ = member_of("the.owner@example.test")
    here = new_document(author)
    link_group(here, [Right.EDIT, Right.VIEW_ALL_HISTORY], [membership, other_membership], author)
    open_, closed = targets(new_document, owner, 2)
    link_group(open_, [Right.VIEW_ACCEPTED], [membership], owner)
    a, b = open_.number, closed.number
    assert here.number not in (a, b)
    commit_version(here, author, mentioning(a, b))
    commit_version(here, author, mentioning(a, b, words="always follow"))
    number = here.number

    pages = {
        "view": f"/document/{number}/",
        "historical": f"/document/{number}/version/0.0-1/",
        "compare": f"/document/{number}/compare/?from=0.0-1&to=0.0-2",
        "pending": f"/document/{number}/pending/",
    }
    for where, address in pages.items():
        filtered(client.get(address).content.decode(), a, b, where)

    # Reached from elsewhere, the tab takes nothing and draws the head's text.
    filtered(client.get(f"/document/{number}/edit/").content.decode(), a, b, "before a hold")
    assert client.post(f"/document/{number}/edit/take/").status_code == 200
    filtered(client.get(f"/document/{number}/edit/").content.decode(), a, b, "edit tab")
    with schema_context(migrated_tenant.number):
        hold = Hold.objects.get(document=here, released_at__isnull=True)
        draft = Draft.objects.get(hold=hold)
        draft.content = {**draft.content, "document.md": mentioning(a, b, words="must follow")}
        draft.save()
    for page in ("my-edits/", "edit/finish/"):
        filtered(client.get(f"/document/{number}/{page}").content.decode(), a, b, page)

    loaded = client.post(
        f"/document/{number}/edit/load/",
        data=json.dumps({"range": "whole"}),
        content_type="application/json",
    ).json()
    typed = client.post(
        f"/document/{number}/edit/changes/",
        data=json.dumps({"editor": loaded["editor"], "body": mentioning(a, b, words="now follow")}),
        content_type="application/json",
    ).json()
    filtered(typed["html"], a, b, "stopped editor")

    admin.post(f"/document/{number}/edit/force-release/", {"hold": str(hold.pk)})
    commit_version(here, other, mentioning(a, b, words="still follow"))
    filtered(client.get(f"/document/{number}/edit/").content.decode(), a, b, "kept draft")


def test_a_notice_filters_mentions(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
) -> None:
    from django.test import Client

    from notifications.models import Notification
    from review import services

    people = edition_cast(editors=("a",), reviewers=("r",), approvers=())
    _, owner, _ = member_of("the.owner@example.test")
    open_, closed = targets(new_document, owner, 2)
    link_group(open_, [Right.VIEW_ACCEPTED], [people.memberships["a"]], owner)
    a, b = open_.number, closed.number
    commit_version(people.document, people["a"], mentioning(a, b), "edit")
    commit_version(
        people.document,
        people["r"],
        mentioning(a, b, words="always follow", now="Now "),
        "reviewer_edit",
    )
    with schema_context(migrated_tenant.number):
        services.accept(people.document, people["r"])
        notification = Notification.objects.get(user=people["a"], event="correction_notice")
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(people["a"])
    session = client.session
    session["tenant_number"] = migrated_tenant.number
    session.save()

    page = client.get(f"/notifications/{notification.pk}/").content.decode()

    filtered(page, a, b, "notice")


def test_exports_carry_the_words(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    new_document: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
    settings: Any,
) -> None:
    """PDF and DOCX, clean and marked, carry a mention's words alone for a reader of both targets;
    the Markdown export carries the span as written."""
    from pypdf import PdfReader

    people = edition_cast()
    _, owner, _ = member_of("the.owner@example.test")
    first, second = targets(new_document, owner, 2)
    a, b = first.number, second.number
    kit.canonical(migrated_tenant.number, people, commit_version, mentioning(a, b))
    commit_version(people.document, people["a"], mentioning(a, b, words="always follow"), "edit")
    client, user = kit.reader(member_of, link_group, people, [Right.VIEW_PENDING], "exporter")
    from identity.models import Membership

    membership = Membership.objects.get(user=user, tenant=migrated_tenant)
    for target in (first, second):
        link_group(target, [Right.VIEW_ACCEPTED], [membership], owner)

    choices = [
        {"format": "pdf", "view": "canonical"},
        {"format": "docx", "view": "canonical"},
        {"format": "pdf", "view": "pending_edits", "changes-pending_edits": "marked"},
        {"format": "docx", "view": "pending_edits", "changes-pending_edits": "marked"},
        {"format": "markdown", "view": "canonical"},
    ]
    produced: list[Path] = []
    for choice in choices:
        response = client.post(
            f"/document/{people.document.number}/export/", {"document": "on", **choice}
        )
        assert response.status_code == 302, choice
        job = kit.run_job(migrated_tenant.number, exports[-1][1])
        assert job.state == "done", (choice, job.failure_reason)
        produced.append(Path(settings.EXPORT_ROOT) / job.artifact_ref)

    for path in produced[0], produced[2]:
        pdf = PdfReader(str(path))
        text = " ".join(" ".join(page.extract_text() for page in pdf.pages).split())
        assert "the payment rules" in text and "the request form" in text, path.name
        uris = [
            str(annotation.get_object().get("/A", {}).get("/URI", ""))
            for page in pdf.pages
            for annotation in page.get("/Annots") or []
        ]
        # A mention links nowhere in a file; a link of the text's own stays one.
        assert not any("/document/" in uri for uri in uris), uris
    for path in produced[1], produced[3]:
        with zipfile.ZipFile(path) as docx:
            xml = docx.read("word/document.xml").decode()
            relations = docx.read("word/_rels/document.xml.rels").decode()
        assert "the payment rules" in xml and "/document/" not in relations, path.name
    markdown = produced[4].read_text(encoding="utf-8")
    assert f"[the payment rules]{{.document #{a}}}" in markdown
