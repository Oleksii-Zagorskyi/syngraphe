"""A draft's part changes shown to the person editing (DL-0168, ASR-04): on *my edits* and the
finishing screen, the body's changes, then each changed appendix under its title, then the draft's
part operations with their files; the drafted summary names the changed appendices; a refusal at
finish names the appendix or the part. Titles and people are synthetic examples; text is invented
English and file bytes are placeholders."""

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

BODY = "# Purpose\n\nThe first synthetic sentence.\n"
ONE = "# Appendix one\n\nThe appendix sentence.\n"
FORM = b"a synthetic form"


def entry(number: int, data: bytes, title: str = "Request form (example)") -> dict[str, Any]:
    return {
        "number": number,
        "title": title,
        "file_name": f"form-{number}.xlsx",
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }


def scene(member_of: Any, new_document: Any, link_group: Any, commit_version: Any) -> Any:
    """A document listing appendix 1 and attachment 2, held by an editor with every part right;
    `(client, holder, document)`."""
    from access.rights import PARTS, Right

    _, author, _ = member_of("the.author@example.test")
    client, holder, own = member_of("the.holder@example.test")
    document = new_document(author)
    link_group(document, [Right.EDIT, *PARTS], [own], author)
    commit_version(
        document,
        author,
        BODY,
        files={"appendices/1.md": ONE.encode(), "attachments/2": FORM},
        appendices=[{"number": 1, "title": "Appendix one (example)"}],
        attachments=[entry(2, FORM)],
    )
    assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
    return client, holder, document


def flat(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def test_the_draft_shows_appendices_and_parts(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    settings: Any,
) -> None:
    from editing import holds, parts
    from editing.models import Draft

    settings.LANGUAGE_CODE = "en"
    client, holder, document = scene(member_of, new_document, link_group, commit_version)
    with schema_context(migrated_tenant.number):
        draft = Draft.objects.get(hold=holds.open_hold(document))
        draft.content = {
            **draft.content,
            "document.md": "# Purpose\n\nThe first synthetic sentence, revised.\n",
            "appendices/1.md": "# Appendix one\n\nThe appendix sentence, revised.\n",
        }
        draft.save()
        added = parts.create_appendix(document, holder, title="Appendix three (example)")
        parts.replace_attachment(document, holder, 2, file_name="form-new.xlsx", data=b"new")
    m = document.number
    for path in (f"/document/{m}/my-edits/", f"/document/{m}/edit/finish/"):
        html = client.get(path).content.decode()
        # The finishing screen's summary, which names the parts, stands above the changes.
        html = html.rsplit("</form>", 1)[-1] if path.endswith("finish/") else html
        text = flat(html)
        assert text.index("revised.") < text.index("Appendix one (example)"), path
        one = html[html.index("Appendix one (example)") :]
        assert "<ins>" in one and "revised" in one
        assert text.index("Appendix one (example)") < text.index("Appendix three (example)")
        assert "📎 Request form (example) replaced" in text
        assert f'href="/document/{m}/edit/parts/attachment/2/"' in html
        assert f'href="/document/{m}/appendix/{added}/edit/"' in html
    finish = client.get(f"/document/{m}/edit/finish/").content.decode()
    summary = re.search(r'<textarea id="summary" name="summary"[^>]*>([^<]*)</textarea>', finish)
    assert summary and "Appendix one (example)" in summary.group(1)


def test_refusals_at_finish_name_the_part(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    settings: Any,
) -> None:
    from access.rights import Right
    from editing import holds, parts
    from editing.models import Draft

    settings.LANGUAGE_CODE = "en"
    client, holder, document = scene(member_of, new_document, link_group, commit_version)
    m = document.number
    with schema_context(migrated_tenant.number):
        draft = Draft.objects.get(hold=holds.open_hold(document))
        draft.content = {**draft.content, "appendices/1.md": "No heading here.\n"}
        draft.save()
    answer = client.post(f"/document/{m}/edit/send/", {"summary": "A change"})
    assert answer.status_code == 409
    assert "“Appendix one (example)”" in answer.content.decode()

    with schema_context(migrated_tenant.number):
        draft = Draft.objects.get(hold=holds.open_hold(document))
        draft.content = {**draft.content, "appendices/1.md": ONE}
        draft.save()
        parts.upload_attachment(
            document, holder, title="Budget (example)", file_name="b.xlsx", data=b"b"
        )
        from access.models import AccessGroup

        for group in AccessGroup.objects.all():
            group.revoke(Right.UPLOAD_ATTACHMENT, by=document.created_by)
    lost = client.post(f"/document/{m}/edit/send/", {"summary": "A change"})
    assert lost.status_code == 409
    assert "«Budget (example)»" in lost.content.decode()


def test_a_kept_drafts_appendix_image_survives_its_removal(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    invented_image: Any,
    queued_authorship: list[Any],
) -> None:
    """A's kept draft shows appendix 2's image X in its changes, served from the draft's base
    after B's version dropped it from the head."""
    from access.rights import Right
    from editing import holds, reservations, services
    from editing.models import Draft

    _, author, _ = member_of("the.author@example.test")
    a_client, a, a_member = member_of("editor.a@example.test")
    _, b, b_member = member_of("editor.b@example.test")
    other_client, _, other = member_of("another.member@example.test")
    _, admin, _ = member_of("the.admin@example.test", is_tenant_admin=True)
    document = new_document(author)
    link_group(document, [Right.EDIT, Right.VIEW_PENDING], [a_member, b_member, other], author)
    x = invented_image("png")
    name = f"images/{hashlib.sha256(x).hexdigest()}.png"
    commit_version(
        document,
        author,
        BODY,
        files={
            "appendices/2.md": f"# Two\n\nA sentence.\n\n![A plan]({name})\n".encode(),
            name: x,
        },
        appendices=[{"number": 2, "title": "Appendix two (example)"}],
    )
    m = document.number
    with schema_context(migrated_tenant.number):
        hold = holds.take(document, a)
        draft = Draft.objects.get(hold=hold)
        draft.content = {
            **draft.content,
            "appendices/2.md": f"# Two\n\nA sentence, changed.\n\n![A plan]({name})\n",
        }
        draft.save()
        reservations.force_release(hold, admin)
        hold = holds.take(document, b)
        draft = Draft.objects.get(hold=hold)
        draft.content = {**draft.content, "appendices/2.md": "# Two\n\nA sentence.\n"}
        draft.save()
        services.commit_draft(hold, b, "The plan removed")

    page = a_client.get(f"/document/{m}/edit/").content.decode()
    src = f"/document/{m}/edit/image/{name.removeprefix('images/')}/"
    assert "Appendix two (example)" in page
    # The body's changes first, then the appendix's under its title.
    assert page.index('class="changes document-text"') < page.index('class="appendix-changes"')
    assert f'src="{src}"' in page
    assert a_client.get(src).content == x
    assert other_client.get(src).status_code == 404


def test_a_kept_drafts_rows_link_what_exists(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    queued_authorship: list[Any],
    settings: Any,
) -> None:
    """A kept draft that deleted an attachment and added an appendix, the head moved since: the
    deletion's *last version* is linked at the version compared with, and the added appendix,
    which no version holds, has no *open* link."""
    from access.rights import PARTS, Right
    from editing import holds, parts, reservations, services
    from editing.models import Draft

    settings.LANGUAGE_CODE = "en"
    _, author, _ = member_of("the.author@example.test")
    a_client, a, a_member = member_of("editor.a@example.test")
    _, b, b_member = member_of("editor.b@example.test")
    _, admin, _ = member_of("the.admin@example.test", is_tenant_admin=True)
    document = new_document(author)
    link_group(document, [Right.EDIT, Right.VIEW_PENDING, *PARTS], [a_member, b_member], author)
    commit_version(
        document, author, BODY, files={"attachments/2": FORM}, attachments=[entry(2, FORM)]
    )
    m = document.number
    with schema_context(migrated_tenant.number):
        hold = holds.take(document, a)
        parts.delete_attachment(document, a, 2)
        added = parts.create_appendix(document, a, title="Draft-only appendix (example)")
        reservations.force_release(hold, admin)
        hold = holds.take(document, b)
        draft = Draft.objects.get(hold=hold)
        draft.content = {**draft.content, "document.md": BODY + "\nA later sentence.\n"}
        draft.save()
        services.commit_draft(hold, b, "A later sentence")
    page = a_client.get(f"/document/{m}/edit/").content.decode()
    table = page[page.index('class="part-changes"') :]
    assert "📎 Request form (example) deleted" in flat(table)
    head = re.search(r'<option value="([^"]+)"', page)
    assert f'href="/document/{m}/version/' in table and ">last version</a>" in table
    assert f'href="/document/{m}/appendix/{added}/"' not in table
    assert head is not None
