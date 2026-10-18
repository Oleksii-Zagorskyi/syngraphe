"""`{% organisation_stylesheet %}`: the link to the organisation's stylesheet, in the read-only
pages that draw document text (DL-0464). A template tag in those pages' own block, never a context
processor, so a page without document text — or without an organisation — never reads the row."""

from __future__ import annotations

from django import template
from django.utils.html import format_html
from django.utils.safestring import SafeString

from rendering.models import Stylesheet
from rendering.stylesheet import applied, digest, served

register = template.Library()


@register.simple_tag
def organisation_stylesheet() -> SafeString | str:
    """The `<link>` to the served stylesheet at the address of what would be served, or nothing
    while no rule of the organisation's applies."""
    text = Stylesheet.objects.get().text
    if not applied(text):
        return ""
    return format_html(
        '<link rel="stylesheet" href="/document-styles/{}.css">', digest(served(text))
    )
