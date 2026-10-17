"""The export dialog's delivery line follows the choices (DL-0193): a Markdown export of a text
that shows images is one zip, a PDF of it one file. People are synthetic examples; the text is
invented."""

from __future__ import annotations

import hashlib
from typing import Any

import pytest

pytestmark = pytest.mark.browser


def test_markdown_with_images_reads_one_zip(
    browser_server: str,
    page: Any,
    member_of: Any,
    new_document: Any,
    commit_version: Any,
    invented_image: Any,
    settings: Any,
) -> None:
    from editing import images

    settings.LANGUAGE_CODE = "en"
    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    data = images.check(invented_image("png")).data
    path = f"images/{hashlib.sha256(data).hexdigest()}.png"
    commit_version(
        document, author, f"A synthetic sentence.\n\n![A plan]({path})\n", files={path: data}
    )
    session = client.cookies["sessionid"].value
    page.context.add_cookies([{"name": "sessionid", "value": session, "url": browser_server}])
    page.goto(f"{browser_server}/document/{document.number}/export/")

    page.check('input[name="view"][value="pending_edits"]')
    page.check('input[name="format"][value="markdown"]')
    assert page.text_content(".delivery") == "Delivered as one zip."
    page.check('input[name="format"][value="pdf"]')
    assert page.text_content(".delivery") == "Delivered as one file."
