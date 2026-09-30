"""The interface's words for the editor: the name of every construct the whitelist refuses, by its
stable code, and the editor's labels and notices. Kept here, not in the specification, so the
catalogue finds them; `tests/editing/test_messages.py` holds the codes to the specification's."""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _

CONSTRUCTS = {
    "heading-depth": _("a heading below depth four"),
    "heading-nested": _("a heading inside a list, quote or callout"),
    "code": _("a code block"),
    "inline-code": _("inline code"),
    "html": _("HTML"),
    "hr": _("a horizontal rule"),
    "hard-break": _("a line break inside a paragraph"),
    "footnote": _("a footnote"),
    "link-reference": _("a link defined elsewhere in the text"),
    "task-list": _("a task list"),
    "list-depth": _("a list deeper than three levels"),
    "list-item-empty": _("a list item that does not begin with text"),
    "table-nested": _("a table inside a list, quote or callout"),
    "nested-quote": _("a quote or callout inside a list, quote or callout"),
    "callout-type": _("an unknown callout type"),
    "table-row-cells": _("a table row wider than its header"),
    "image-src": _("an image from outside the document"),
    "image-inline": _("an image beside other content"),
    "title": _("a title on a link or an image"),
    "link-scheme": _("a link of a kind not allowed"),
    "link-empty": _("a link with no text"),
    "span-attrs": _("an unknown entity"),
    "span-type": _("an unknown entity"),
    "span-id": _("an identifier on an entity that takes none"),
    "span-empty": _("an empty entity"),
    "span-nested": _("an entity inside an entity"),
    "unsupported": _("a construct outside the allowed Markdown"),
    "control-character": _("an invisible control character"),
    "too-large": _("a text longer than the platform accepts"),
    "table-merged": _("a merged table cell"),
}

LABELS = {
    "paragraph": _("Paragraph"),
    # One label for every level the specification allows; the toolbar fills in the level.
    "heading": _("Heading %(level)s"),
    "bullet_list": _("Bulleted list"),
    "ordered_list": _("Numbered list"),
    "strong": _("Bold"),
    "em": _("Italic"),
    "underline": _("Underline"),
    "quote": _("Quote"),
    "note": _("Note callout"),
    "warning": _("Warning callout"),
    "example": _("Example callout"),
    "table": _("Table"),
    "add_row": _("Add a row"),
    "link": _("Link"),
    "link_address": _("Link address"),
    "undo": _("Undo"),
    "redo": _("Redo"),
    "source": _("Source view"),
    "rich": _("Rich text"),
    "paste_converted": _("Paste converted"),
    "finish": _("Finish editing"),
    "start": _("Start editing"),
}

NOTICES = {
    "refused": _("Not pasted: it holds %(constructs)s."),
    "help": _("What the editor accepts"),
    "images": _("Images were left out of the paste."),
    "link_refused": _("A link of this kind is not allowed."),
    "busy": _("The document is busy. Try again in a moment."),
    "lines": _("Not accepted — %(lines)s."),
    "capturing": _("Capturing…"),
    "captured": _("Captured"),
    "failed": _("Not captured — retrying"),
    "signed_out": _(
        "Signed out — sign in again in another tab; your text stays here while this tab is open."
    ),
    "stale": _("This editor stopped: the draft changed elsewhere."),
    "too_large": _("Not captured — the text is over the size allowed; shorten it to go on."),
    "others": _("Finishing waits until the other tabs editing this document are closed."),
    "line": _("line %(line)s: %(construct)s"),
}


# What the source view's conversion does to each refused construct (DL-0171), for the help page.
CONVERSIONS = {
    "drop-extra-cells": _("cells beyond the header row dropped"),
    "drop-id": _("the identifier dropped"),
    "drop-title": _("the title dropped"),
    "drop-with-notice": _("left out, with a notice"),
    "footnote-inline": _("its text in brackets where it was referred to"),
    "heading-to-max-depth": _("a heading of the deepest level allowed"),
    "image-own-paragraph": _("the image moved to a line of its own"),
    "inline-link": _("a link written where it is used"),
    "lift-after-parent": _("moved after the block that held it"),
    "lift-to-max-depth": _("lifted to the deepest level allowed"),
    "none": _("not converted"),
    "plain-list": _("a plain list"),
    "plain-quote": _("a plain quote"),
    "remove": _("removed"),
    "space": _("a space"),
    "strip-tags-keep-text": _("its text, the tags removed"),
    "unlink-keep-text": _("its text, the link removed"),
    "unwrap-text": _("its text"),
}

# The kinds of entity, as the interface names them (the glossary's *entity*).
SPAN_NAMES = {
    "role": _("Entity: role"),
    "action": _("Entity: action"),
    "term": _("Entity: term"),
}

# The help pages shipped with the application, by address, in their order.
HELP_PAGES = {
    "moves": _("How a document moves"),
    "versions": _("Versions and their numbers"),
    "review": _("Reviewing and accepting"),
    "editions": _("Freezing and editions"),
    "editing": _("Editing"),
    "markdown": _("What the editor accepts"),
    "exporting": _("Exporting"),
}


def for_the_editor() -> dict[str, Any]:
    """Every word the editor shows, translated, as the page hands it to the browser."""
    return {
        "constructs": {code: str(name) for code, name in CONSTRUCTS.items()},
        "labels": {key: str(label) for key, label in LABELS.items()},
        "notices": {key: str(notice) for key, notice in NOTICES.items()},
    }
