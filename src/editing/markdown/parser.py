"""markdown-it-py configured to recognise everything the whitelist refuses: CommonMark, pipe
tables, raw HTML tokenised so that it can be refused by name, every link tokenised so that a refused
scheme is named, the span and callout rules, and the tidying both sides share (ADR-0010).
`src/editing/js/parser.js` is its twin.

**This instance recognises; it never renders.** It passes raw HTML and any link through, so that
the validator can name them: a page rendered from it would carry whatever a text holds. A renderer
builds its own instance, with raw HTML off and links validated.
"""

from __future__ import annotations

from markdown_it import MarkdownIt

from editing.markdown.rules import attr_span, callout, tidy


def make_parser() -> MarkdownIt:
    """A new recogniser. The specification is applied by the validator's walk, not here."""
    md = MarkdownIt("commonmark", {"html": True}).enable("table")
    md.validateLink = lambda url: True  # type: ignore[method-assign]
    md.inline.ruler.before("link", "attr_span", attr_span)
    md.core.ruler.after("block", "callout", callout)
    md.core.ruler.after("text_join", "tidy", tidy)
    return md


_PARSER: MarkdownIt | None = None


def parser() -> MarkdownIt:
    """The one shared recogniser; markdown-it-py keeps no state between parses."""
    global _PARSER
    if _PARSER is None:
        _PARSER = make_parser()
    return _PARSER
