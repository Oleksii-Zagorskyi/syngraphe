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


def test_the_appendices_choices_follow_the_document(
    browser_server: str,
    page: Any,
    member_of: Any,
    new_document: Any,
    commit_version: Any,
    settings: Any,
) -> None:
    """*Embedded* and *separate* only with the document; appendices alone keep *Format* and go
    as one zip, as separate appendices do."""
    settings.LANGUAGE_CODE = "en"
    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    commit_version(
        document,
        author,
        "A synthetic sentence.\n",
        files={"appendices/1.md": b"# Forms\n\nAn appendix sentence.\n"},
        appendices=[{"number": 1, "title": "Synthetic forms"}],
    )
    session = client.cookies["sessionid"].value
    page.context.add_cookies([{"name": "sessionid", "value": session, "url": browser_server}])
    page.goto(f"{browser_server}/document/{document.number}/export/")
    page.check('input[name="view"][value="pending_edits"]')

    assert page.text_content(".delivery") == "Delivered as one file."
    page.check('input[name="appendices_mode"][value="separate"]')
    assert page.text_content(".delivery") == "Delivered as one zip."
    page.uncheck('input[name="document"]')
    assert page.is_disabled('input[name="appendices_mode"][value="embedded"]')
    assert page.is_enabled('input[name="format"][value="pdf"]')
    assert page.text_content(".delivery") == "Delivered as one zip."
    page.uncheck('input[name="appendices"]')
    assert page.is_disabled('input[name="format"][value="pdf"]')
    assert page.is_disabled('.export-dialog button[type="submit"]')


def test_an_appendixs_images_make_a_zip_only_with_the_appendices(
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
        document,
        author,
        "A synthetic sentence.\n",
        files={path: data, "appendices/1.md": f"# Plans\n\n![A plan]({path})\n".encode()},
        appendices=[{"number": 1, "title": "Synthetic plans"}],
    )
    session = client.cookies["sessionid"].value
    page.context.add_cookies([{"name": "sessionid", "value": session, "url": browser_server}])
    page.goto(f"{browser_server}/document/{document.number}/export/")
    page.check('input[name="view"][value="pending_edits"]')
    page.check('input[name="format"][value="markdown"]')

    assert page.text_content(".delivery") == "Delivered as one zip."
    page.uncheck('input[name="appendices"]')
    assert page.text_content(".delivery") == "Delivered as one file."
