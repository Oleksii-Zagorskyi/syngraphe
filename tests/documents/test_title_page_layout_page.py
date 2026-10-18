"""Administration › template › title page layout (DL-0462, DL-0475, DL-0476): which details the
title page shows, in which order and alignment, the approval line always among them; saved checked
and audited, and reset to the default form.

People are synthetic examples."""

from __future__ import annotations

import html
import json
import re
from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

PAGE = "/administration/tenant/template/title-page/"


@pytest.fixture(autouse=True)
def english(settings: Any) -> None:
    settings.LANGUAGE_CODE = "en"


def _layout(migrated_tenant: Any) -> str:
    from documents.models import DocumentTemplate

    with schema_context(migrated_tenant.number):
        return str(DocumentTemplate.objects.get().title_page_layout)


def test_only_administrators_open_the_layout(migrated_tenant: Any, member_of: Any) -> None:
    admin, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    member, _, _ = member_of("a.member@example.test")

    page = html.unescape(admin.get(PAGE).content.decode())

    for detail in (
        "Title",
        "Document number",
        "Type",
        "Edition",
        "Approved by",
        "Approval date",
        "The document's own title-page text",
    ):
        assert detail in page, detail
    assert "Always shown: the approval, or that the text is not approved" in page
    assert 'name="show_approval"' not in page
    section = page.split('id="title-page-layout"', 1)[1]
    assert "logo" not in section.lower()
    assert 'href="/administration/tenant/template/"' in page
    assert member.get(PAGE).status_code == 404
    assert member.post(PAGE, {"align": "left"}).status_code == 404
    # The template's page links here.
    assert f'href="{PAGE}"' in admin.get("/administration/tenant/template/").content.decode()


def test_the_layout_is_saved_checked_and_audited(migrated_tenant: Any, member_of: Any) -> None:
    from audit.models import AuditEvent

    admin, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)

    clash = admin.post(
        PAGE,
        {
            "show_title": "on",
            "position_title": "2",
            "show_number": "on",
            "position_number": "2",
            "position_approval": "3",
            "align": "left",
        },
    )
    saved = admin.post(
        PAGE,
        {
            "show_number": "on",
            "position_number": "1",
            "show_title": "on",
            "position_title": "2",
            "show_type": "on",
            "position_type": "3",
            "position_approval": "4",
            "position_edition": "5",
            "align": "centre",
        },
    )
    stored = _layout(migrated_tenant)
    shown = admin.get(PAGE).content.decode()
    unplaced = admin.post(PAGE, {"show_title": "on", "position_approval": "1", "align": "left"})
    unknown = admin.post(PAGE, {"position_approval": "1", "align": "middle"})
    reset = admin.post(PAGE, {"action": "reset"})

    assert clash.status_code == 400
    assert "Two details are at position 2" in html.unescape(clash.content.decode())
    assert saved.status_code == 303 and saved["Location"] == PAGE
    # The edition was given a position but not shown: left out.
    assert json.loads(stored) == {
        "items": ["number", "title", "type", "approval"],
        "align": "centre",
    }
    # The page reads the stored layout back: positions, the details shown, the alignment.
    assert re.search(r'name="position_number"[^>]*>.*?<option value="1" selected>', shown, re.S)
    assert re.search(r'name="position_title"[^>]*>.*?<option value="2" selected>', shown, re.S)
    assert re.search(r'name="show_type"[^>]*checked', shown)
    assert not re.search(r'name="show_edition"[^>]*checked', shown)
    assert '<option value="centre" selected>' in shown
    assert unplaced.status_code == 400
    assert "Give each shown detail a position." in html.unescape(unplaced.content.decode())
    assert unknown.status_code == 400
    assert "Select a valid choice" in html.unescape(unknown.content.decode())
    assert reset.status_code == 303
    assert _layout(migrated_tenant) == ""
    events = list(AuditEvent.objects.filter(action="template.changed").order_by("at"))
    assert [(e.before["title_page_layout"], e.after["title_page_layout"]) for e in events] == [
        ("", stored),
        (stored, ""),
    ]
