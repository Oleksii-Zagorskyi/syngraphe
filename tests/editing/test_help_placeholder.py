"""Help as work in progress: one key turns every help page into its heading and one message
(DL-0344)."""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_every_page_is_work_in_progress(member_of: Any, settings: Any) -> None:
    from editing.messages import HELP_PAGES

    settings.HELP_WORK_IN_PROGRESS = True
    settings.LANGUAGE_CODE = "uk"
    client, _, _ = member_of("a.reader@example.test")
    for path in ["/help/", *(f"/help/{slug}/" for slug in HELP_PAGES)]:
        response = client.get(path)
        body = response.content.decode()
        assert response.status_code == 200, path
        article = body.split("<article>")[1].split("</article>")[0]
        assert article.strip() == "<p>в роботі</p>", path
        nav = body.split('<nav class="help-pages">')[1].split("</nav>")[0]
        assert "Довідка" in nav and "<ul>" not in nav and "<a " not in nav, path


def test_off_shows_the_pages(member_of: Any, settings: Any) -> None:
    settings.HELP_WORK_IN_PROGRESS = False
    settings.LANGUAGE_CODE = "uk"
    client, _, _ = member_of("a.reader@example.test")
    assert "<h1>Редагування</h1>" in client.get("/help/editing/").content.decode()


def test_unknown_slug_still_missing(member_of: Any, settings: Any) -> None:
    settings.HELP_WORK_IN_PROGRESS = True
    client, _, _ = member_of("a.reader@example.test")
    assert client.get("/help/nothing/").status_code == 404
