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
    # A mention is written with a document's number, not an entity's key.
    assert "[…]{.document #12}" in body
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
    assert 'data-help="/help/markdown/"' in (template / "editing" / "editor_mount.html").read_text()


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


def test_people_help_page(member_of: Any, settings: Any) -> None:
    """*People and access*: listed in the index and rendered in both languages, no message id
    shown."""
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "people_help_catalogue",
        Path(__file__).resolve().parents[1] / "review" / "test_catalogue.py",
    )
    assert spec is not None and spec.loader is not None
    catalogue = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(catalogue)
    ids = catalogue.message_ids(catalogue.CATALOGUE.read_text(encoding="utf-8"))
    client, _, _ = member_of("a.reader@example.test")

    for language, heading in (("en", "People and access"), ("uk", "Люди й доступ")):
        settings.LANGUAGE_CODE = language
        index = client.get("/help/").content.decode()
        page = client.get("/help/people/")
        body = page.content.decode()
        assert 'href="/help/people/"' in index, language
        assert page.status_code == 200 and f"<h1>{heading}</h1>" in body, language
        if language == "uk":
            leaked = [message for message in ids if message in catalogue.text_of(body)]
            assert leaked == [], leaked


def test_editing_together_help_page(member_of: Any, settings: Any) -> None:
    """*Editing together*: listed in the index and rendered in both languages, no message id
    shown."""
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "editing_together_catalogue",
        Path(__file__).resolve().parents[1] / "review" / "test_catalogue.py",
    )
    assert spec is not None and spec.loader is not None
    catalogue = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(catalogue)
    ids = catalogue.message_ids(catalogue.CATALOGUE.read_text(encoding="utf-8"))
    client, _, _ = member_of("a.reader@example.test")

    for language, heading in (("en", "Editing together"), ("uk", "Редагування разом")):
        settings.LANGUAGE_CODE = language
        index = client.get("/help/").content.decode()
        page = client.get("/help/editing-together/")
        body = page.content.decode()
        assert 'href="/help/editing-together/"' in index, language
        assert page.status_code == 200 and f"<h1>{heading}</h1>" in body, language
        if language == "uk":
            leaked = [message for message in ids if message in catalogue.text_of(body)]
            assert leaked == [], leaked


def test_history_help_page(member_of: Any, settings: Any) -> None:
    """*History, comparing and undoing*: listed in the index and rendered in both languages, no
    message id shown."""
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "history_catalogue",
        Path(__file__).resolve().parents[1] / "review" / "test_catalogue.py",
    )
    assert spec is not None and spec.loader is not None
    catalogue = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(catalogue)
    ids = catalogue.message_ids(catalogue.CATALOGUE.read_text(encoding="utf-8"))
    client, _, _ = member_of("a.reader@example.test")

    for language, heading in (
        ("en", "History, comparing and undoing"),
        ("uk", "Історія, порівняння і скасування"),
    ):
        settings.LANGUAGE_CODE = language
        index = client.get("/help/").content.decode()
        page = client.get("/help/history/")
        body = page.content.decode()
        assert 'href="/help/history/"' in index, language
        assert page.status_code == 200 and f"<h1>{heading}</h1>" in body, language
        if language == "uk":
            leaked = [message for message in ids if message in catalogue.text_of(body)]
            assert leaked == [], leaked


def test_images_marks_and_mentions_help(member_of: Any, settings: Any) -> None:
    """*Editing*, *Reading a document* and *Exporting* say how images, roles, actions and terms,
    and mentions work, in both languages, no message id shown."""
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "images_catalogue", Path(__file__).resolve().parents[1] / "review" / "test_catalogue.py"
    )
    assert spec is not None and spec.loader is not None
    catalogue = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(catalogue)
    ids = catalogue.message_ids(catalogue.CATALOGUE.read_text(encoding="utf-8"))
    client, _, _ = member_of("a.reader@example.test")
    sections = {
        "en": {
            "editing": ("Images", "Roles, actions and terms", "Mentions"),
            "reading": ("Mentions and generated views", "role directory", "see also"),
            "exporting": ("Images",),
        },
        "uk": {
            "editing": ("Зображення", "Ролі, дії й терміни", "Згадки"),
            "reading": ("Згадки й супровідні документи", "довідник ролей", "див. також"),
            "exporting": ("Зображення",),
        },
    }

    for language, pages in sections.items():
        settings.LANGUAGE_CODE = language
        for page, words in pages.items():
            body = client.get(f"/help/{page}/").content.decode()
            for word in words:
                assert word in body, (language, page, word)
            if language == "uk":
                leaked = [message for message in ids if message in catalogue.text_of(body)]
                assert leaked == [], (page, leaked)


def test_corpus_help_page(member_of: Any, settings: Any) -> None:
    """*Finding and organising documents*: listed in the index and rendered in both languages,
    no message id shown."""
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "corpus_catalogue",
        Path(__file__).resolve().parents[1] / "review" / "test_catalogue.py",
    )
    assert spec is not None and spec.loader is not None
    catalogue = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(catalogue)
    ids = catalogue.message_ids(catalogue.CATALOGUE.read_text(encoding="utf-8"))
    client, _, _ = member_of("a.reader@example.test")

    for language, heading, section in (
        ("en", "Finding and organising documents", "Comparing two documents"),
        ("uk", "Пошук і впорядкування документів", "Порівняння двох документів"),
    ):
        settings.LANGUAGE_CODE = language
        index = client.get("/help/").content.decode()
        page = client.get("/help/corpus/")
        body = page.content.decode()
        assert 'href="/help/corpus/"' in index, language
        assert page.status_code == 200 and f"<h1>{heading}</h1>" in body, language
        assert section in body, language
        # The reading page points at it, by its title.
        reading = client.get("/help/reading/").content.decode()
        assert section in reading and heading in reading, language
        if language == "uk":
            leaked = [message for message in ids if message in catalogue.text_of(body)]
            assert leaked == [], leaked


def test_parts_help_page(member_of: Any, settings: Any) -> None:
    """*Appendices and attachments*: listed in the index and rendered in both languages, no
    message id shown."""
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "parts_catalogue",
        Path(__file__).resolve().parents[1] / "review" / "test_catalogue.py",
    )
    assert spec is not None and spec.loader is not None
    catalogue = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(catalogue)
    ids = catalogue.message_ids(catalogue.CATALOGUE.read_text(encoding="utf-8"))
    client, _, _ = member_of("a.reader@example.test")

    for language, heading in (
        ("en", "Appendices and attachments"),
        ("uk", "Додатки й вкладені файли"),
    ):
        settings.LANGUAGE_CODE = language
        index = client.get("/help/").content.decode()
        page = client.get("/help/parts/")
        body = page.content.decode()
        assert 'href="/help/parts/"' in index, language
        assert page.status_code == 200 and f"<h1>{heading}</h1>" in body, language
        # The controls named as the panel draws them: arrows, their words in the tooltips.
        assert "↑" in body and "↓" in body, language
        if language == "uk":
            leaked = [message for message in ids if message in catalogue.text_of(body)]
            assert leaked == [], leaked


def test_template_and_styles_help_page(member_of: Any, settings: Any) -> None:
    """*Template and styles*: listed in the index and rendered in both languages, no message id
    shown; the editing and exporting pages name the title page's switch and its layout."""
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "styles_catalogue",
        Path(__file__).resolve().parents[1] / "review" / "test_catalogue.py",
    )
    assert spec is not None and spec.loader is not None
    catalogue = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(catalogue)
    ids = catalogue.message_ids(catalogue.CATALOGUE.read_text(encoding="utf-8"))
    client, _, _ = member_of("a.reader@example.test")

    for language, heading, layout, switch, text in (
        ("en", "Template and styles", "Title page layout", "Title page", "Title page text"),
        (
            "uk",
            "Шаблон і стилі",
            "Вигляд титульної сторінки",
            "Титульна сторінка",
            "Текст титульної сторінки",
        ),
    ):
        settings.LANGUAGE_CODE = language
        index = client.get("/help/").content.decode()
        page = client.get("/help/template-and-styles/")
        body = page.content.decode()
        assert 'href="/help/template-and-styles/"' in index, language
        assert page.status_code == 200 and f"<h1>{heading}</h1>" in body, language
        assert layout in body and "@page" in body, language
        editing = client.get("/help/editing/").content.decode()
        assert f"<em>{switch}</em>" in editing and f"<em>{text}</em>" in editing, language
        exporting = client.get("/help/exporting/").content.decode()
        assert layout in exporting and heading in exporting, language
        if language == "uk":
            leaked = [message for message in ids if message in catalogue.text_of(body)]
            assert leaked == [], leaked


def test_accountability_help_page(member_of: Any, settings: Any) -> None:
    """*Settings, access history and the audit log*: listed in the index and rendered in both
    languages, no message id shown, the controls named as the pages name them."""
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "accountability_catalogue",
        Path(__file__).resolve().parents[1] / "review" / "test_catalogue.py",
    )
    assert spec is not None and spec.loader is not None
    catalogue = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(catalogue)
    ids = catalogue.message_ids(catalogue.CATALOGUE.read_text(encoding="utf-8"))
    client, _, _ = member_of("a.reader@example.test")

    from django.utils import translation

    # The controls as the pages draw them, read from the catalogue in each language.
    controls = ("Attachment size cap", "Distinct approver check", "Access history", "Audit log")
    for language, heading in (
        ("en", "Settings, access history and the audit log"),
        ("uk", "Налаштування, історія доступу і журнал аудиту"),
    ):
        with translation.override(language):
            named = [translation.gettext(control) for control in controls]
            named.append(translation.gettext("Show edit authors"))
        settings.LANGUAGE_CODE = language
        index = client.get("/help/").content.decode()
        page = client.get("/help/accountability/")
        body = page.content.decode()
        assert 'href="/help/accountability/"' in index, language
        assert page.status_code == 200 and f"<h1>{heading}</h1>" in body, language
        for name in named:
            assert name in body, (language, name)
        if language == "uk":
            leaked = [message for message in ids if message in catalogue.text_of(body)]
            assert leaked == [], leaked


def test_the_help_reads_the_one_row_and_the_toolbar() -> None:
    """The help names the account page by the person's name in the menu row, signs out there,
    switches organisation from a list, and describes the toolbar's first three controls and
    *Clear formatting* (DL-0525, DL-0531)."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "src" / "editing" / "help"
    for language, gone, words in (
        (
            "en",
            ("*My account*", "switcher"),
            ("*Undo*, *Redo* and *Clear formatting*", "*Sign out*"),
        ),
        (
            "uk",
            ("*Мій обліковий запис*", "у перемикачі поруч із назвою організації", "Перейти"),
            ("*Скасувати*, *Повторити* й *Очистити форматування*", "*Вийти*"),
        ),
    ):
        text = "\n".join(
            p.read_text(encoding="utf-8") for p in sorted((root / language).glob("*.md"))
        )
        for word in gone:
            assert word not in text, (language, word)
        for word in words:
            assert word in text, (language, word)
