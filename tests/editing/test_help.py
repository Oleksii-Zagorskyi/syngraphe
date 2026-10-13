"""The help pages: shipped Markdown in the interface's language, and the page of what the editor
accepts, built from the specification and listing its every construct (DL-0171, DL-0195)."""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_allowed_markdown_generated_from_spec(member_of: Any, settings: Any) -> None:
    from editing.markdown import load_spec
    from editing.messages import CONSTRUCTS

    settings.LANGUAGE_CODE = "en"
    client, _, _ = member_of("a.reader@example.test")
    page = client.get("/help/markdown/")
    body = page.content.decode()
    assert page.status_code == 200
    spec = load_spec()
    for code in spec.refusals:
        assert str(CONSTRUCTS[code]) in body, code
    for kind in spec.callout_types:
        assert kind in body
    assert f"down to level {spec.heading_max_depth}" in body
    assert f"down to {spec.list_max_depth} levels" in body
    assert "<script" not in body.split("<main")[1]
    # Nothing else: the refusals table has one row per refusal and conversion, no more.
    from editing.views.help import refused

    refusals_table = body.split('<table class="help-table">')[2].split("</table>")[0]
    assert refusals_table.count("<tr>") - 1 == len(refused(spec))


def test_the_shipped_pages_render_in_the_interface_language(member_of: Any, settings: Any) -> None:
    client, _, _ = member_of("a.reader@example.test")
    settings.LANGUAGE_CODE = "uk"
    assert "<h1>Редагування</h1>" in client.get("/help/editing/").content.decode()
    index = client.get("/help/").content.decode()
    assert 'href="/help/markdown/"' in index
    assert client.get("/help/nothing-here/").status_code == 404


def test_every_paste_refusal_links_to_the_page() -> None:
    from pathlib import Path

    template = Path(__file__).resolve().parents[2] / "src" / "editing" / "templates"
    assert 'data-help="/help/markdown/"' in (template / "editing" / "edit_tab.html").read_text()


def test_the_index_opens_on_reading_a_document(member_of: Any, settings: Any) -> None:
    """`/help/` is never an empty page beside its list: it opens on *Reading a document*, the page
    every person can use, the list beside it (DL-0365)."""
    import re

    client, _, _ = member_of("a.reader@example.test")
    settings.LANGUAGE_CODE = "uk"
    index = client.get("/help/").content.decode()
    reading = client.get("/help/reading/").content.decode()

    def article(body: str) -> str:
        found = re.search(r"<article>(.*?)</article>", body, re.S)
        assert found is not None
        return found.group(1).strip()

    assert article(index)
    assert article(index) == article(reading)
    assert 'href="/help/markdown/"' in index


def test_the_notifications_and_mail_pages(member_of: Any, settings: Any) -> None:
    """Both listed in the index and rendered in the interface's language, no message id shown."""
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "help_catalogue", Path(__file__).resolve().parents[1] / "review" / "test_catalogue.py"
    )
    assert spec is not None and spec.loader is not None
    catalogue = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(catalogue)
    ids = catalogue.message_ids(catalogue.CATALOGUE.read_text(encoding="utf-8"))

    client, _, _ = member_of("a.reader@example.test")
    settings.LANGUAGE_CODE = "uk"
    index = client.get("/help/").content.decode()
    for slug, heading in (("notifications", "Сповіщення"), ("mail", "Пошта")):
        assert f'href="/help/{slug}/"' in index, slug
        page = client.get(f"/help/{slug}/")
        assert page.status_code == 200, slug
        body = page.content.decode()
        assert f"<h1>{heading}</h1>" in body, slug
        leaked = [message for message in ids if message in catalogue.text_of(body)]
        assert leaked == [], (slug, leaked)
