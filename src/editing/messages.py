"""The interface's words for the editor: the name of every construct the whitelist refuses, by its
stable code, and the editor's labels and notices. Kept here, not in the specification, so the
catalogue finds them; `tests/editing/test_messages.py` holds the codes to the specification's."""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

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
    "table-merged": _("a table cell spanning several"),
    "image-missing": _("an image the document does not hold"),
    "mention-id": _("a mention without a document number"),
}

# A draft's limits outside the whitelist, refused as its constructs are: the declarations a commit
# derives from the spans pass the size the platform holds them to.
DRAFT_LIMITS = {
    "entities-full": _("more roles, actions and terms than the platform accepts"),
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
    "edit_whole": _("Edit the whole document"),
    "edit_section": pgettext_lazy("open a section's editor", "Edit"),
    "close_section": _("Close this editor"),
    "image": _("Image"),
    "mention": _("Mention"),
    "mention_number": _("Document number"),
    "mark": _("Mark"),
    "mark_kind": _("Kind"),
    "mark_role": pgettext_lazy("an entity", "Role"),
    "mark_action": pgettext_lazy("an entity", "Action"),
    "mark_term": pgettext_lazy("an entity", "Term"),
    "mark_declare": _("Declare a new one"),
    "mark_label": _("Label"),
    "declare": _("Declare"),
}

NOTICES = {
    "refused": _("Not pasted: it holds %(constructs)s."),
    "help": _("What the editor accepts"),
    "images": _(
        "An image that is only a web address was not pasted; copy the image itself and paste it."
    ),
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
    "released": _("This editor stopped: your editing of the document was ended."),
    "take_back": _("Take the document back"),
    "still_working": _("Are you still working? Your editing will soon end for inactivity."),
    "still_working_answer": _("I am still working"),
    "too_large": _("Not captured — the text is over the size allowed; shorten it to go on."),
    "others": _("Finishing waits until the other tabs editing this document are closed."),
    "sections_open": _("Close the section editors first to edit the whole document."),
    "whole_open": _("Close the whole-document editor first to edit a section."),
    "close_sections": _("Finishing waits until every section editor is closed."),
    "overlaps": _("Another editor is open on part of this section; close it first."),
    "too_many": _("Close a section editor first: five are open."),
    "sections_changed": _(
        "The sections changed since the tab was drawn; close your editors to see them again."
    ),
    "section_closed": _("Closed. The section is drawn again once the other editors are closed."),
    "stopped_open": _(
        "A stopped editor still holds your text; carry it over before the tab is drawn again."
    ),
    "line": _("line %(line)s: %(construct)s"),
    "line_in_appendix": _("appendix «%(title)s», line %(line)s: %(construct)s"),
    "uploading": _("Uploading the image…"),
    "image_refused_one": _("Choose one image file."),
    "image_refused_too_large": _(
        "The image is larger than %(limit_mb)s MB, the most the platform accepts."
    ),
    "image_refused_heic": _(
        "HEIC images are not accepted; convert the photograph to JPEG or PNG and add it again."
    ),
    "image_refused_type": _("Only PNG, JPEG and GIF images are accepted."),
    "image_refused_dimensions": _(
        "The image is %(width)s × %(height)s pixels; at most %(max_side)s pixels a side and "
        "%(megapixels)s megapixels are accepted."
    ),
    "image_refused_dimensions_unknown": _(
        "The image is too large in pixels; at most %(max_side)s pixels a side and "
        "%(megapixels)s megapixels are accepted."
    ),
    "image_refused_unreadable": _("The file could not be read as an image."),
    "image_failed": _("The image was not added. Try again."),
    "mention_refused": _("A mention needs a document number."),
    "mention_select": _("Select the words to mention first."),
    "entity_kind": _("Only a role, an action or a term can be declared."),
    "entity_label": _("A label is one line of 1 to 200 characters."),
    "mark_select": _("Select the words to mark first."),
    "mark_moved": _("The text changed meanwhile; select the words again and pick the new one."),
    "joined": _(
        "Lines %(first)s–%(last)s are one paragraph and will be joined; leave a blank line to "
        "start a new one."
    ),
    "joined_more": _("Paragraphs after it to be joined too: %(count)s."),
    "entities_full": _(
        "This document declares as many roles, actions and terms as the platform accepts."
    ),
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
    "document": _("Mention of a document"),
}

# The help pages shipped with the application, by address, in their order.
HELP_PAGES = {
    "moves": _("How a document moves"),
    "versions": _("Versions and their numbers"),
    "review": _("Reviewing and accepting"),
    "editions": _("Freezing and editions"),
    "history": _("History, comparing and undoing"),
    "editing": _("Editing"),
    "editing-together": _("Editing together"),
    "markdown": _("What the editor accepts"),
    "reading": _("Reading a document"),
    "exporting": _("Exporting"),
    "template-and-styles": _("Template and styles"),
    "parts": _("Appendices and attachments"),
    "notifications": _("Notifications"),
    "mail": _("Mail"),
    "people": _("People and access"),
    "corpus": _("Finding and organising documents"),
    "accountability": _("Settings, access history and the audit log"),
}


def for_the_editor() -> dict[str, Any]:
    """Every word the editor shows, translated, as the page hands it to the browser."""
    return {
        "constructs": {code: str(name) for code, name in CONSTRUCTS.items()},
        "labels": {key: str(label) for key, label in LABELS.items()},
        "notices": {key: str(notice) for key, notice in NOTICES.items()},
    }
