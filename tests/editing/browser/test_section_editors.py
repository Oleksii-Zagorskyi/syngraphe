"""Section editors in Chromium (DL-0167): the tab opens on the draft as text, *edit* beside each
heading; editors over one section stop the later one, its text kept and shown as changes; a heading
typed into a section becomes a section of its own once the editor closes; finishing waits for every
editor. Invented text."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = pytest.mark.browser

BODY = (
    "An introductory sentence.\n\n"
    "# First section\n\nThe first sentence of the first section.\n\n"
    "# Second section\n\nThe first sentence of the second section.\n"
)
CORPUS = Path(__file__).resolve().parents[2] / "fixtures" / "corpus" / "document-ukr.md"
OFFERED = "() => document.getElementById('editor').offered !== undefined"
LATER = "document.querySelector('button[data-command=edit-section][data-ordinal=\"1\"]')"


def section(ordinal: int) -> str:
    return f"document.querySelector('.section-editor[data-ordinal=\"{ordinal}\"]')?.editor"


@pytest.fixture
def tab(
    browser_server: str, page: Any, migrated_tenant: Any, member_of: Any, new_document: Any
) -> Iterator[Callable[[str], tuple[Any, str]]]:
    """The edit tab of a new document as its author, over a draft of `body`, the editors offered
    and none open; the document and the tab's address. Every open editor is finished on
    teardown."""

    def open_tab(body: str) -> tuple[Any, str]:
        from editing.models import Draft

        client, author, _ = member_of("the.author@example.test")
        document = new_document(author)
        assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
        with schema_context(migrated_tenant.number):
            draft = Draft.objects.get(hold__document=document)
            draft.content = {**draft.content, "document.md": body}
            draft.save()
        session = client.cookies["sessionid"].value
        page.context.add_cookies([{"name": "sessionid", "value": session, "url": browser_server}])
        url = f"{browser_server}/document/{document.number}/edit/"
        page.goto(url)
        page.wait_for_function(OFFERED)
        return document, url

    yield open_tab
    for open_page in list(page.context.pages):
        if open_page.is_closed():
            continue
        try:
            open_page.wait_for_load_state("networkidle")
            open_page.evaluate(
                """async () => {
                  for (const e of document.querySelectorAll('.section-editor, #editor')) {
                    if (e.editor?.capture) await e.editor.capture.finish().catch(() => null);
                  }
                }"""
            )
        finally:
            open_page.close()


def open_section(page: Any, ordinal: int) -> None:
    page.click(f"button[data-command=edit-section][data-ordinal='{ordinal}']")
    page.wait_for_function(f"() => {section(ordinal)} !== undefined")


def type_into(page: Any, ordinal: int, text: str) -> None:
    editor = section(ordinal)
    page.evaluate(f"{editor}.select({editor}.view.state.doc.content.size - 1)")
    page.evaluate(f"{editor}.view.focus()")
    page.keyboard.type(text, delay=10)


def test_the_tab_opens_on_the_text(tab: Any, page: Any) -> None:
    """No editor until one is chosen; *edit* beside each heading and *edit whole document*."""
    tab(BODY)
    assert page.evaluate("document.getElementById('editor').editor") is None
    assert page.locator("button[data-command=edit-section]").count() == 2
    assert page.locator("button[data-command=edit-whole]").is_enabled()
    assert page.locator(".ProseMirror").count() == 0


def test_the_stopped_editor_keeps_its_text(tab: Any, page: Any) -> None:
    """Two tabs on one section: the later capture stops its editor, read-only, its unsaved text
    shown as changes against the section as it now stands, with *open this section again*."""
    _, url = tab(BODY)
    open_section(page, 0)
    other = page.context.new_page()
    other.goto(url)
    other.wait_for_function(OFFERED)
    open_section(other, 0)
    type_into(page, 0, " One tab added this.")
    assert page.evaluate(f"{section(0)}.capture.flush()") == "captured"
    type_into(other, 0, " Another tab added this.")
    assert other.evaluate(f"{section(0)}.capture.flush()") == "stale"
    other.wait_for_selector(".stopped-editor")
    stopped = other.text_content(".stopped-editor") or ""
    assert "Another tab added this." in stopped
    # As changes: the unsaved words marked as added against the section as it now stands.
    assert other.locator(".stopped-editor .changes ins").count() >= 1
    assert other.locator(".stopped-editor [data-command=reopen]").count() == 1
    assert other.evaluate(f"{section(0)}.view.editable") is False
    assert "Another tab added this." in other.evaluate(f"{section(0)}.markdown()")


def test_a_heading_makes_a_section(tab: Any, page: Any) -> None:
    """A heading typed into a section editor does not split it; once it is closed, the tab is
    drawn again and the new heading offers its own *edit*."""
    tab(BODY)
    open_section(page, 1)
    page.evaluate(
        f"{section(1)}.replace({section(1)}.markdown() + '\\n# New section\\n\\nA sentence.\\n')"
    )
    assert page.evaluate(f"{section(1)}.capture.flush()") == "captured"
    with page.expect_navigation():
        page.click(".section-editor button[data-command=close-section]")
    page.wait_for_function(
        "() => document.querySelectorAll('button[data-command=edit-section]').length === 3"
    )
    assert "New section" in (page.text_content("[data-draft-view]") or "")


def test_finish_waits_for_editors(tab: Any, page: Any) -> None:
    """*Finish editing* is disabled with its reason while a section editor is open, as is
    *edit whole document*; *finish editing* comes back once it is closed."""
    tab(BODY)
    open_section(page, 0)
    finish = page.locator("button[data-command=finish-all]")
    assert finish.is_disabled()
    assert finish.get_attribute("title")
    assert page.locator("button[data-command=edit-whole]").is_disabled()
    with page.expect_navigation():
        page.click(".section-editor button[data-command=close-section]")
    page.wait_for_function(OFFERED)
    page.wait_for_function(
        "() => !document.querySelector('button[data-command=finish-all]').disabled"
    )


def test_closing_one_editor_keeps_the_others_text(
    tab: Any, page: Any, migrated_tenant: Any
) -> None:
    """Closing a section editor never draws the tab again while another holds text: its place says
    it is closed, the other keeps typing, and the last one closed draws the tab with both texts."""
    from editing.models import Draft

    document, _ = tab(BODY)
    navigations: list[str] = []
    page.on("framenavigated", lambda frame: navigations.append(frame.url))
    open_section(page, 0)
    open_section(page, 1)
    type_into(page, 1, " Text not yet captured.")
    page.click(".section-editor[data-ordinal='0'] button[data-command=close-section]")
    page.wait_for_selector(".section-closed")
    page.wait_for_load_state("networkidle")
    assert navigations == []
    assert "Text not yet captured." in page.evaluate(f"{section(1)}.markdown()")
    with page.expect_navigation():
        page.click(".section-editor[data-ordinal='1'] button[data-command=close-section]")
    page.wait_for_function(
        "() => document.querySelectorAll('button[data-command=edit-section]').length === 2"
    )
    page.wait_for_load_state("networkidle")
    with schema_context(migrated_tenant.number):
        body = Draft.objects.get(hold__document=document).content["document.md"]
    assert "Text not yet captured." in body


def test_a_heading_added_stops_the_other_sections_opening(tab: Any, page: Any) -> None:
    """Once a capture adds a heading, the page's other *edit* buttons count the old headings:
    they are disabled with the reason until the tab is drawn again."""
    tab(BODY)
    open_section(page, 0)
    page.evaluate(
        f"{section(0)}.replace({section(0)}.markdown() + '\\n# Added section\\n\\nA sentence.\\n')"
    )
    assert page.evaluate(f"{section(0)}.capture.flush()") == "captured"
    later = page.locator("button[data-command=edit-section][data-ordinal='1']")
    later.wait_for(state="attached")
    page.wait_for_function(f"() => {LATER}.disabled")
    assert later.get_attribute("title")


def test_text_typed_while_its_heading_goes_is_kept(tab: Any, page: Any) -> None:
    """The server closes a section editor whose capture removed its own heading; text typed while
    that capture was on its way is never lost: the editor stops, read-only, the text shown to carry
    over by hand, and the tab is not drawn again over it."""
    tab(BODY)
    navigations: list[str] = []
    page.on("framenavigated", lambda frame: navigations.append(frame.url))
    open_section(page, 1)
    held: list[Any] = []

    def hold_the_first(route: Any) -> None:
        if held:
            route.continue_()
        else:
            held.append(route)

    page.route("**/edit/capture/", hold_the_first)
    page.evaluate(f"{section(1)}.replace('The first sentence of the second section.\\n')")
    page.evaluate(f"() => {{ window.firstCapture = {section(1)}.capture.flush(); }}")
    while not held:
        page.wait_for_timeout(20)
    page.evaluate(
        f"{section(1)}.replace({section(1)}.markdown() + '\\nTyped during the capture.\\n')"
    )
    held[0].continue_()
    assert page.evaluate("window.firstCapture") == "stale"
    page.wait_for_selector(".stopped-editor")
    assert "Typed during the capture." in (page.text_content(".stopped-editor") or "")
    assert page.locator(".stopped-editor [data-command=reopen]").count() == 1
    page.wait_for_load_state("networkidle")
    assert navigations == []
    assert "Typed during the capture." in page.evaluate(f"{section(1)}.markdown()")


MEASURE = """async ([ordinal, keys]) => {
  const editor = document.querySelector(`.section-editor[data-ordinal="${ordinal}"]`).editor;
  const times = [];
  for (const key of keys) {
    const started = performance.now();
    editor.view.dispatch(editor.view.state.tr.insertText(key));
    await new Promise((resolve) => requestAnimationFrame(() => resolve()));
    times.push(performance.now() - started);
    await new Promise((resolve) => setTimeout(resolve, 150));
  }
  return times;
}"""


@pytest.mark.skipif(
    not os.environ.get("SYNGRAPHE_MEASURE"),
    reason="a measurement, run alone on a quiet machine (ASR-21)",
)
def test_two_editors_keystroke_measurement(tab: Any, page: Any) -> None:
    """Two section editors open on the forty-page corpus: keystroke to the next painted frame at a
    human pace, its 95th percentile printed and held to ASR-21's 50 ms. Run alone, with
    `SYNGRAPHE_MEASURE=1`; never judged while other work loads the machine."""
    # The corpus file carries its own frontmatter, which a draft's body never holds.
    tab(CORPUS.read_text(encoding="utf-8").partition("\n---\n")[2].removeprefix("\n"))
    # The first two `##` sections: the one `#` section spans the whole text (DL-0418).
    open_section(page, 1)
    open_section(page, 5)
    page.evaluate(f"{section(5)}.select(1)")
    times = sorted(page.evaluate(MEASURE, [5, list("abcdefghik" * 6)]))
    p95 = times[int(len(times) * 0.95) - 1]
    print(f"two section editors, forty pages: p95 {p95:.1f} ms over {len(times)} keystrokes")
    assert p95 <= 50


def test_a_declaration_reaches_every_open_picker(tab: Any, page: Any) -> None:
    """A role declared in one section's editor is offered at once by another's picker, open
    while it was declared: the page keeps one list of the draft's declarations."""
    tab(BODY)
    open_section(page, 0)
    open_section(page, 1)
    first = ".section-editor[data-ordinal='0']"
    second = ".section-editor[data-ordinal='1']"
    page.click(f"{second} button[data-command=mark]")
    page.select_option(f"{second} select[data-field=mark-kind]", "role")

    page.evaluate(f"{section(0)}.select(5, 10)")
    page.click(f"{first} button[data-command=mark]")
    page.select_option(f"{first} select[data-field=mark-kind]", "role")
    page.fill(f"{first} input[data-field=mark-label]", "the clerk")
    page.click(f"{first} button[data-field=mark-declare]")
    page.wait_for_function(f"{section(0)}.markdown().includes('#role-1')")

    assert (
        page.locator(f"{second} button[data-entity=role-1]").text_content(timeout=2000)
        == "the clerk"
    )
