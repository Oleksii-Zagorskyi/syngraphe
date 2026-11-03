"""An appendix's editors (ADR-0006, DL-0418): the whole-appendix and section editors open on the
appendix's own file, capture into it, count against the draft's section editors across every
file, and close — writing nothing — once the draft no longer lists the appendix. Titles and people
are synthetic examples; text is invented English."""

from __future__ import annotations

import json
import re
from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

BODY = (
    "# One\n\nThe first sentence.\n\n# Two\n\nThe second sentence.\n\n"
    "# Three\n\nThe third sentence.\n\n# Four\n\nThe fourth sentence.\n"
)
APPENDIX = (
    "# Approval matrix\n\nThe first appendix sentence.\n\n"
    "## Thresholds\n\nThe threshold sentence.\n\n"
    "## Signatures\n\nThe signature sentence.\n"
)
LISTED = [
    {"number": 1, "title": "Request form (example)"},
    {"number": 2, "title": "Approval matrix (example)"},
]


def setup(
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    others: tuple[tuple[list[Any], Any], ...] = (),
) -> Any:
    """A document whose head lists appendices 1 and 2, held by an editor who may create and delete
    appendices, `others` linked before the hold as `(rights, membership)`; `(client, holder,
    document)`."""
    from access.rights import Right

    _, author, _ = member_of("the.author@example.test")
    client, holder, own = member_of("the.holder@example.test")
    document = new_document(author)
    rights = [Right.EDIT, Right.CREATE_APPENDIX, Right.DELETE_APPENDIX, Right.VIEW_PENDING]
    link_group(document, rights, [own], author)
    for granted, membership in others:
        link_group(document, granted, [membership], author)
    commit_version(
        document,
        author,
        BODY,
        files={
            "appendices/1.md": b"# Request form\n\nThe form sentence.\n",
            "appendices/2.md": APPENDIX.encode(),
        },
        appendices=LISTED,
    )
    assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
    return client, holder, document


def post(client: Any, path: str, data: dict[str, Any]) -> Any:
    return client.post(path, json.dumps(data), content_type="application/json")


def load(client: Any, document: Any, asked: str, appendix: int | None = None) -> Any:
    where = f"appendix/{appendix}/edit/load/" if appendix is not None else "edit/load/"
    return post(client, f"/document/{document.number}/{where}", {"range": asked})


def draft(tenant: Any, document: Any) -> Any:
    from editing import holds
    from editing.models import Draft

    with schema_context(tenant.number):
        return Draft.objects.get(hold=holds.open_hold(document))


def test_editors_open_on_the_appendix_file(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    from editing.models import OpenEditor

    client, _, document = setup(member_of, new_document, link_group, commit_version)
    assert load(client, document, "section:0").status_code == 200
    whole = load(client, document, "whole", appendix=2)
    assert whole.status_code == 200, whole.content
    assert whole.json()["body"] == APPENDIX
    with schema_context(migrated_tenant.number):
        editor = OpenEditor.objects.get(pk=whole.json()["editor"])
        assert editor.file == "appendices/2.md"
    post(client, f"/document/{document.number}/edit/close/", {"editor": whole.json()["editor"]})
    section = load(client, document, "section:1", appendix=2)
    assert section.status_code == 200, section.content
    assert section.json()["body"].startswith("## Thresholds")
    assert load(client, document, "whole", appendix=2).status_code == 409


def test_captures_land_in_the_appendix(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    client, _, document = setup(member_of, new_document, link_group, commit_version)
    opened = load(client, document, "section:1", appendix=2).json()
    typed = "## Thresholds\n\nThe threshold sentence, revised.\n\n"
    answer = post(
        client,
        f"/document/{document.number}/edit/capture/",
        {"editor": opened["editor"], "body": typed, "base_hash": opened["base_hash"]},
    )
    assert answer.status_code == 200, answer.content
    content = draft(migrated_tenant, document).content
    assert "The threshold sentence, revised." in content["appendices/2.md"]
    assert content["document.md"] == BODY
    shown = post(
        client,
        f"/document/{document.number}/edit/changes/",
        {"editor": opened["editor"], "body": "## Thresholds\n\nAnother wording.\n"},
    )
    assert shown.status_code == 200
    assert "Another wording." in shown.json()["html"]
    assert "The first sentence." not in shown.json()["html"]


def test_an_appendix_with_an_open_editor_is_not_deleted(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    from editing import parts

    client, holder, document = setup(member_of, new_document, link_group, commit_version)
    assert load(client, document, "whole", appendix=2).status_code == 200
    with schema_context(migrated_tenant.number), pytest.raises(parts.PartRefused) as refused:
        parts.delete_appendix(document, holder, 2)
    assert refused.value.reason == "editor_open"


def test_an_unlisted_appendix_takes_no_capture(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    """An editor whose appendix the draft no longer lists — a state no service leaves, crafted
    here — is closed by its next request, which writes nothing."""
    from editing.models import OpenEditor

    client, _, document = setup(member_of, new_document, link_group, commit_version)
    opened = load(client, document, "whole", appendix=2).json()
    held = draft(migrated_tenant, document)
    with schema_context(migrated_tenant.number):
        frontmatter = {**held.content["frontmatter"], "appendices": LISTED[:1]}
        content = {k: v for k, v in held.content.items() if k != "appendices/2.md"}
        held.content = {**content, "frontmatter": frontmatter}
        held.save()
    answer = post(
        client,
        f"/document/{document.number}/edit/capture/",
        {"editor": opened["editor"], "body": "# Typed\n", "base_hash": opened["base_hash"]},
    )
    assert answer.status_code == 409 and answer.json().get("closed") is True
    assert "appendices/2.md" not in draft(migrated_tenant, document).content
    with schema_context(migrated_tenant.number):
        assert OpenEditor.objects.get(pk=opened["editor"]).closed_at is not None
    again = load(client, document, "whole", appendix=2)
    assert again.status_code == 409 and again.json() == {"closed": True}


def test_the_section_cap_spans_files(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    client, _, document = setup(member_of, new_document, link_group, commit_version)
    for ordinal in range(3):
        assert load(client, document, f"section:{ordinal}").status_code == 200
    for ordinal in (1, 2):
        assert load(client, document, f"section:{ordinal}", appendix=2).status_code == 200
    sixth = load(client, document, "section:3")
    assert sixth.status_code == 409 and sixth.json() == {"too_many": True}
    assert load(client, document, "whole", appendix=1).status_code == 200


def test_a_draft_only_appendix_has_an_edit_tab(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    settings: Any,
) -> None:
    from editing import parts

    settings.LANGUAGE_CODE = "en"
    client, holder, document = setup(member_of, new_document, link_group, commit_version)
    with schema_context(migrated_tenant.number):
        number = parts.create_appendix(document, holder, title="Holiday calendar (example)")
    page = client.get(f"/document/{document.number}/appendix/{number}/edit/")
    assert page.status_code == 200
    html = page.content.decode()
    assert "Holiday calendar (example)" in re.sub(r"<[^>]+>", "", html.split("</h1>")[0])
    assert "data-parts-panel" in html
    # The document's path for the appendix: the draft opens its editor, and no version the
    # reader may open lists it yet, so no point opens its page.
    path = re.search(r'<nav class="path".*?</nav>', html, re.S)
    assert path
    assert f'href="/document/{document.number}/appendix/{number}/"' not in path.group(0)
    assert f'href="/document/{document.number}/appendix/{number}/edit/"' in path.group(0)
    assert f'data-load="/document/{document.number}/appendix/{number}/edit/load/"' in html
    assert "Holiday calendar" in html[html.index("data-draft-view") :]


def test_a_freeze_is_answered_before_the_hold(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    """A freeze closed to the person editing answers the appendix's tab as it answers the
    document's: no editor is offered."""
    from django.utils import timezone

    from editions.models import Freeze

    client, holder, document = setup(member_of, new_document, link_group, commit_version)
    with schema_context(migrated_tenant.number):
        Freeze.objects.create(document=document, frozen_by=holder, frozen_at=timezone.now())
    appendix = client.get(f"/document/{document.number}/appendix/2/edit/").content.decode()
    own = client.get(f"/document/{document.number}/edit/").content.decode()
    assert 'id="editor"' not in appendix
    assert 'id="editor"' not in own


def test_the_appendix_routes_are_closed_to_others(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
) -> None:
    from access.rights import Right

    reader_client, _, reading = member_of("a.reader@example.test")
    editor_client, _, editing = member_of("another.editor@example.test")
    stranger_client, _, _ = member_of("a.stranger@example.test")
    client, _, document = setup(
        member_of,
        new_document,
        link_group,
        commit_version,
        others=(([Right.VIEW_PENDING], reading), ([Right.EDIT], editing)),
    )
    m = document.number
    missing = stranger_client.get("/document/99999/").content
    assert reader_client.get(f"/document/{m}/appendix/2/edit/").status_code == 404
    assert load(editor_client, document, "whole", appendix=2).status_code == 404
    for path in (f"/document/{m}/appendix/2/edit/", f"/document/{m}/appendix/2/"):
        answer = stranger_client.get(path)
        assert answer.status_code == 404
        assert _uniform(answer.content) == _uniform(missing)
    assert load(stranger_client, document, "whole", appendix=2).status_code == 404


def _uniform(body: bytes) -> str:
    return re.sub(r'name="csrfmiddlewaretoken" value="[^"]*"', "", body.decode())


def test_an_unlisted_appendixs_heartbeat_and_changes_close(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    from editing.models import OpenEditor

    client, _, document = setup(member_of, new_document, link_group, commit_version)
    for path in ("heartbeat", "changes"):
        opened = load(client, document, "whole", appendix=2).json()
        held = draft(migrated_tenant, document)
        with schema_context(migrated_tenant.number):
            listed = {**held.content["frontmatter"], "appendices": LISTED[:1]}
            held.content = {**held.content, "frontmatter": listed}
            held.save()
        answer = post(
            client,
            f"/document/{document.number}/edit/{path}/",
            {"editor": opened["editor"], "body": "# Typed\n"},
        )
        assert answer.status_code == 409 and answer.json() == {"closed": True}, path
        with schema_context(migrated_tenant.number):
            assert OpenEditor.objects.get(pk=opened["editor"]).closed_at is not None
            held.content = {**held.content, "frontmatter": {**listed, "appendices": LISTED}}
            held.save()


def test_a_heartbeat_after_the_draft_is_gone_answers_closed(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    monkeypatch: Any,
) -> None:
    """Another tab finishes or discards the draft between the heartbeat's reading of its editor
    and of its draft: the heartbeat answers that the editor is closed, not an error."""
    from editing.models import Draft, OpenEditor
    from editing.views import capture

    client, _, document = setup(member_of, new_document, link_group, commit_version)
    opened = load(client, document, "whole", appendix=2).json()
    found = capture._own_editor

    def then_gone(request: Any, number: int) -> Any:
        hold_and_editor = found(request, number)
        with schema_context(migrated_tenant.number):
            Draft.objects.filter(hold__document=document).delete()
        return hold_and_editor

    monkeypatch.setattr(capture, "_own_editor", then_gone)
    answer = post(
        client, f"/document/{document.number}/edit/heartbeat/", {"editor": opened["editor"]}
    )
    assert answer.status_code == 409 and answer.json() == {"closed": True}
    with schema_context(migrated_tenant.number):
        assert not OpenEditor.objects.filter(pk=opened["editor"]).exists()
