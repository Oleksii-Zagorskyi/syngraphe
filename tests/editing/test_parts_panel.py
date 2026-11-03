"""The parts panel on the edit tab (DL-0442): the draft's appendices and attachments, each control
drawn only to a person who holds its right, its forms staging the operations, and the draft's
attachment downloaded by the person whose draft it is (T-15). Every title, file name and person is
a synthetic example; file bytes are invented placeholders."""

from __future__ import annotations

import hashlib
import re
from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

BODY = "The first synthetic sentence.\n\nThe second synthetic sentence.\n"
FORM = b"a synthetic spreadsheet"
OWN = {"HTTP_SEC_FETCH_SITE": "same-origin"}


def _with_an_edit(tenant: int, document: Any) -> None:
    """The open hold's draft given an edit: a hold with no edits keeps nothing when it ends."""
    from editing.models import Draft

    with schema_context(tenant):
        draft = Draft.objects.get(hold__document=document, hold__released_at__isnull=True)
        body = draft.content["document.md"] + "\nAn invented sentence kept in the draft.\n"
        draft.content = {**draft.content, "document.md": body}
        draft.save()


def entry(number: int, data: bytes, title: str = "Request form (example)") -> dict[str, Any]:
    return {
        "number": number,
        "title": title,
        "file_name": f"form-{number}.xlsx",
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }


def with_parts(commit_version: Any, document: Any, user: Any) -> None:
    """Appendix 1 and attachment 1 committed on the document."""
    commit_version(
        document,
        user,
        BODY,
        files={"appendices/1.md": b"# Approval matrix (example)\n", "attachments/1": FORM},
        appendices=[{"number": 1, "title": "Approval matrix (example)"}],
        attachments=[entry(1, FORM)],
    )


def holding(client: Any, document: Any) -> Any:
    client.post(f"/document/{document.number}/edit/take/")
    return client.get(f"/document/{document.number}/edit/", **OWN)


def actions(page: Any) -> set[str]:
    """Every form action and download link the panel draws."""
    html = page.content.decode()
    panel = re.search(r"<aside[^>]*data-parts-panel.*?</aside>", html, re.S)
    assert panel, "no parts panel"
    return set(re.findall(r'(?:action|href)="(/document/\d+/edit/parts/[^"]*)"', panel.group(0)))


def draft_of(tenant: Any, document: Any) -> Any:
    from editing import holds
    from editing.models import Draft

    with schema_context(tenant.number):
        return Draft.objects.get(hold=holds.open_hold(document))


def test_controls_follow_the_rights(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
) -> None:
    from access.rights import PARTS, Right

    _, author, _ = member_of("the.author@example.test")
    every_client, _, every = member_of("every.right@example.test")
    edit_client, _, edit = member_of("edit.alone@example.test")
    document = new_document(author)
    link_group(document, [Right.EDIT, *PARTS], [every], author)
    link_group(document, [Right.EDIT], [edit], author)
    with_parts(commit_version, document, author)
    n = document.number
    base = f"/document/{n}/edit/parts/"
    everything = {
        f"{base}appendix/",
        f"{base}appendix/1/rename/",
        f"{base}appendix/1/delete/",
        f"{base}attachment/",
        f"{base}attachment/1/",
        f"{base}attachment/1/replace/",
        f"{base}attachment/1/rename/",
        f"{base}attachment/1/delete/",
    }

    assert actions(holding(every_client, document)) == everything
    every_client.post(f"/document/{n}/edit/discard/")
    assert actions(holding(edit_client, document)) == {
        f"{base}appendix/1/rename/",
        f"{base}attachment/1/",
        f"{base}attachment/1/rename/",
    }

    author_client, author_only, _ = member_of("only.author@example.test")
    own_document = new_document(author_only)
    with_parts(commit_version, own_document, author_only)
    m = own_document.number
    mine = f"/document/{m}/edit/parts/"
    assert actions(holding(author_client, own_document)) == {
        f"{mine}appendix/1/rename/",
        f"{mine}attachment/",
        f"{mine}attachment/1/",
        f"{mine}attachment/1/replace/",
        f"{mine}attachment/1/rename/",
    }


def test_moves_post_the_whole_order(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    two = [entry(1, FORM, "First (example)"), entry(2, FORM + b"2", "Second (example)")]
    commit_version(
        document,
        author,
        BODY,
        files={"attachments/1": FORM, "attachments/2": FORM + b"2"},
        attachments=two,
    )
    html = holding(client, document).content.decode()
    orders = re.findall(
        r'action="/document/\d+/edit/parts/attachments/order/".*?name="order" value="([^"]+)"',
        html,
        re.S,
    )
    assert orders == ["2,1", "2,1"]


def test_the_panel_is_drawn_for_the_one_who_will_hold(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
) -> None:
    from access.rights import Right

    _, author, _ = member_of("the.author@example.test")
    first_client, _, first = member_of("first.editor@example.test")
    second_client, _, second = member_of("second.editor@example.test")
    reader_client, _, reader = member_of("a.reader@example.test")
    document = new_document(author)
    link_group(document, [Right.EDIT], [first, second], author)
    link_group(document, [Right.VIEW_CANONICAL], [reader], author)
    with_parts(commit_version, document, author)

    before = first_client.get(f"/document/{document.number}/edit/", **OWN).content.decode()
    panel = re.search(r"<aside[^>]*data-parts-panel[^>]*>", before)
    assert panel and " hidden" in panel.group(0)
    assert "Approval matrix (example)" in before

    holding(first_client, document)
    other = second_client.get(f"/document/{document.number}/edit/", **OWN).content.decode()
    assert "data-parts-panel" not in other
    assert reader_client.get(f"/document/{document.number}/edit/").status_code == 404


def test_each_form_stages_its_operation(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
) -> None:
    from django.core.files.uploadedfile import SimpleUploadedFile

    from access.rights import PARTS, Right

    _, author, _ = member_of("the.author@example.test")
    client, _, own = member_of("the.editor@example.test")
    document = new_document(author)
    link_group(document, [Right.EDIT, *PARTS], [own], author)
    with_parts(commit_version, document, author)
    holding(client, document)
    base = f"/document/{document.number}/edit/parts/"

    def post(path: str, data: dict[str, Any]) -> None:
        answer = client.post(base + path, data)
        assert answer.status_code == 303, path
        assert answer["Location"] == f"/document/{document.number}/edit/"

    post("appendix/", {"title": "Holiday calendar (example)"})
    post("appendix/2/rename/", {"title": "Holiday table (example)"})
    post("appendices/order/", {"order": "2,1"})
    post("appendix/1/delete/", {})
    upload = SimpleUploadedFile("budget.xlsx", b"a synthetic budget")
    post("attachment/", {"title": "Budget model (example)", "file": upload})
    post("attachment/1/replace/", {"file": SimpleUploadedFile("form-new.xlsx", b"new bytes")})
    post("attachment/2/rename/", {"title": "Budget table (example)"})
    post("attachments/order/", {"order": "2,1"})
    post("attachment/1/delete/", {})

    lists = draft_of(migrated_tenant, document).content["frontmatter"]
    assert lists["appendices"] == [{"number": 2, "title": "Holiday table (example)"}]
    assert [(e["number"], e["title"]) for e in lists["attachments"]] == [
        (2, "Budget table (example)")
    ]


def test_refusals_are_named(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    settings: Any,
) -> None:
    from django.core.files.uploadedfile import SimpleUploadedFile

    from access.rights import Right
    from tenancy.models import Tenant

    settings.LANGUAGE_CODE = "en"
    Tenant.objects.filter(pk=migrated_tenant.pk).update(attachment_max_bytes=5 * 1024 * 1024)
    _, author, _ = member_of("the.author@example.test")
    client, _, own = member_of("the.editor@example.test")
    document = new_document(author)
    link_group(document, [Right.EDIT, Right.UPLOAD_ATTACHMENT], [own], author)
    holding(client, document)
    base = f"/document/{document.number}/edit/parts/"

    big = SimpleUploadedFile("Budget model.xlsx", b"x" * (6 * 1024 * 1024))
    answer = client.post(
        base + "attachment/", {"title": "Budget (example)", "file": big}, follow=True
    )
    assert "Budget model.xlsx is 6.0\xa0MB; this organisation’s limit is 5.0\xa0MB." in (
        answer.content.decode()
    )
    empty = SimpleUploadedFile("form.txt", b"synthetic")
    answer = client.post(base + "attachment/", {"title": " ", "file": empty}, follow=True)
    assert "A title is one line of text" in answer.content.decode()
    assert client.post(base + "appendix/", {}).status_code == 400
    assert client.get(base + "appendix/").status_code == 404
    assert client.post(base + "attachments/order/", {"order": "1;2"}).status_code == 400


def test_the_drafts_attachment_downloads_to_its_holder(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
) -> None:
    from django.core.files.uploadedfile import SimpleUploadedFile

    from access.rights import Right
    from audit.models import AuditEvent

    _, author, _ = member_of("the.author@example.test")
    client, _, own = member_of("the.editor@example.test")
    stranger_client, _, stranger = member_of("a.stranger@example.test")
    document = new_document(author)
    link_group(document, [Right.EDIT, Right.UPLOAD_ATTACHMENT], [own, stranger], author)
    with_parts(commit_version, document, author)
    holding(client, document)
    base = f"/document/{document.number}/edit/parts/"
    client.post(
        base + "attachment/",
        {"title": "Budget (example)", "file": SimpleUploadedFile("budget.xlsx", b"budget")},
    )

    for number, data, name in ((2, b"budget", "budget.xlsx"), (1, FORM, "form-1.xlsx")):
        answer = client.get(f"{base}attachment/{number}/")
        assert answer.status_code == 200
        assert answer.content == data
        assert answer["Content-Type"] == "application/octet-stream"
        assert answer["X-Content-Type-Options"] == "nosniff"
        assert "private" in answer["Cache-Control"]
        assert name in answer["Content-Disposition"]
    downloads = AuditEvent.objects.filter(action="attachment.downloaded").order_by("at")
    assert [e.after for e in downloads] == [
        {"number": document.number, "attachment": 2, "staged": True},
        {"number": document.number, "attachment": 1, "staged": True},
    ]
    assert stranger_client.get(f"{base}attachment/1/").status_code == 404
    assert client.get(f"{base}attachment/9/").status_code == 404


def kept(tenant: Any, document: Any, admin: Any) -> None:
    """The open hold force-released by an administrator: its draft kept for its owner."""
    from editing import holds, reservations

    _with_an_edit(tenant.number, document)
    with schema_context(tenant.number):
        reservations.force_release(holds.open_hold(document), admin)


def test_a_kept_drafts_files_download_to_its_owner(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
) -> None:
    from django.core.files.uploadedfile import SimpleUploadedFile

    from access.rights import Right
    from audit.models import AuditEvent

    _, author, _ = member_of("the.author@example.test")
    client, _, own = member_of("the.editor@example.test")
    other_client, _, other = member_of("another.editor@example.test")
    _, admin, _ = member_of("the.admin@example.test", is_tenant_admin=True)
    document = new_document(author)
    link_group(document, [Right.EDIT, Right.UPLOAD_ATTACHMENT], [own, other], author)
    holding(client, document)
    base = f"/document/{document.number}/edit/parts/"
    client.post(
        base + "attachment/",
        {"title": "Budget (example)", "file": SimpleUploadedFile("budget.xlsx", b"budget")},
    )
    kept(migrated_tenant, document, admin)

    answer = client.get(f"{base}attachment/1/")
    assert answer.status_code == 200 and answer.content == b"budget"
    event = AuditEvent.objects.filter(action="attachment.downloaded").get()
    assert event.after == {"number": document.number, "attachment": 1, "staged": True, "kept": True}
    assert other_client.get(f"{base}attachment/1/").status_code == 404


@pytest.mark.parametrize("change", ["replace", "delete"])
def test_a_kept_draft_serves_its_own_snapshot(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    queued_authorship: list[Any],
    change: str,
) -> None:
    from access.rights import PARTS, Right
    from editing import holds, parts, services

    _, author, _ = member_of("the.author@example.test")
    a_client, _, a = member_of("editor.a@example.test")
    b_client, b, b_membership = member_of("editor.b@example.test")
    other_client, _, other = member_of("another.member@example.test")
    _, admin, _ = member_of("the.admin@example.test", is_tenant_admin=True)
    document = new_document(author)
    link_group(document, [Right.EDIT, *PARTS], [a, b_membership, other], author)
    original = b"the original synthetic form"
    commit_version(
        document,
        author,
        BODY,
        files={"attachments/2": original},
        attachments=[entry(2, original)],
    )
    holding(a_client, document)
    kept(migrated_tenant, document, admin)
    with schema_context(migrated_tenant.number):
        hold = holds.take(document, b)
        if change == "replace":
            parts.replace_attachment(document, b, 2, file_name="other.xlsx", data=b"B's form")
        else:
            parts.delete_attachment(document, b, 2)
        services.commit_draft(hold, b, "B's change")

    answer = a_client.get(f"/document/{document.number}/edit/parts/attachment/2/")
    assert answer.status_code == 200
    assert answer.content == original
    assert "form-2.xlsx" in answer["Content-Disposition"]
    assert (
        other_client.get(f"/document/{document.number}/edit/parts/attachment/2/").status_code == 404
    )


def test_a_tab_opened_from_elsewhere_draws_the_panel_hidden(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    """Reached from another site, the tab offers *Start editing* before it takes the hold: the
    panel is drawn hidden all the same, so the take reveals it, and the layout's column is whole
    until then."""
    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    with_parts(commit_version, document, author)
    html = client.get(f"/document/{document.number}/edit/").content.decode()
    panel = re.search(r"<aside[^>]*data-parts-panel[^>]*>", html)
    assert panel and " hidden" in panel.group(0)


def test_nothing_is_read_before_the_upload_is_allowed(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    monkeypatch: pytest.MonkeyPatch,
    settings: Any,
) -> None:
    """A post by someone who may not edit, and a file over the limit, are refused before a byte
    of the upload is read into memory."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    from access.rights import Right
    from editing.views import parts as views
    from tenancy.models import Tenant

    settings.LANGUAGE_CODE = "en"
    read: list[str] = []
    real = views._bytes
    monkeypatch.setattr(views, "_bytes", lambda upload: read.append(upload.name) or real(upload))
    Tenant.objects.filter(pk=migrated_tenant.pk).update(attachment_max_bytes=1024 * 1024)
    _, author, _ = member_of("the.author@example.test")
    client, _, own = member_of("the.editor@example.test")
    reader_client, _, reader = member_of("a.reader@example.test")
    document = new_document(author)
    link_group(document, [Right.EDIT, Right.UPLOAD_ATTACHMENT], [own], author)
    link_group(document, [Right.VIEW_CANONICAL], [reader], author)
    holding(client, document)
    base = f"/document/{document.number}/edit/parts/"
    big = b"x" * (1024 * 1024 + 1)

    stranger = reader_client.post(
        base + "attachment/", {"title": "T (example)", "file": SimpleUploadedFile("a.bin", big)}
    )
    assert stranger.status_code == 404
    over = client.post(
        base + "attachment/",
        {"title": "T (example)", "file": SimpleUploadedFile("big.bin", big)},
        follow=True,
    )
    assert "big.bin is 1.0\xa0MB; this organisation’s limit is 1.0\xa0MB." in over.content.decode()
    assert read == []
    client.post(
        base + "attachment/", {"title": "T (example)", "file": SimpleUploadedFile("s.bin", b"s")}
    )
    assert read == ["s.bin"]


def test_a_withdrawal_and_the_appendix_moves_are_drawn(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    """The author of an author-only document deletes an attachment their draft uploaded — the
    right that added it (DL-0473) — and not one the head lists; two appendices move each way."""
    from editing import parts

    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    commit_version(
        document,
        author,
        BODY,
        files={
            "appendices/1.md": b"# One (example)\n",
            "appendices/2.md": b"# Two (example)\n",
            "attachments/1": FORM,
        },
        appendices=[
            {"number": 1, "title": "One (example)"},
            {"number": 2, "title": "Two (example)"},
        ],
        attachments=[entry(1, FORM)],
    )
    holding(client, document)
    with schema_context(migrated_tenant.number):
        parts.upload_attachment(
            document, author, title="Budget (example)", file_name="b.xlsx", data=b"budget"
        )
    page = client.get(f"/document/{document.number}/edit/", **OWN)
    drawn = actions(page)
    base = f"/document/{document.number}/edit/parts/"
    assert f"{base}attachment/2/delete/" in drawn
    assert f"{base}attachment/1/delete/" not in drawn
    orders = re.findall(
        r'action="/document/\d+/edit/parts/appendices/order/".*?name="order" value="([^"]+)"',
        page.content.decode(),
        re.S,
    )
    assert orders == ["2,1", "2,1"]


def test_a_part_never_sent_is_deleted_at_once(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, settings: Any
) -> None:
    """Deleting a part the draft added and never sent says it goes at once; deleting one the
    document holds says the document keeps it until the draft is finished."""
    from access.rights import PARTS, Right
    from editing import holds, parts

    settings.LANGUAGE_CODE = "en"
    client, author, own = member_of("the.author@example.test")
    document = new_document(author)
    link_group(document, [Right.EDIT, *PARTS], [own], author)
    with schema_context(migrated_tenant.number):
        holds.take(document, author)
        parts.create_appendix(document, author, title="Never sent (example)")
    page = client.get(f"/document/{document.number}/edit/").content.decode()
    assert "This appendix was never sent: it and its text are deleted at once." in page
    assert "the document keeps it until you finish editing" not in page
