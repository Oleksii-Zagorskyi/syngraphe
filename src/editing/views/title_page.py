"""The title page's switch and text in the edit tab (DL-0463, DL-0476): one form, each key whose
value differs from the draft's staged as a draft change; a text past its rule refused with what
was typed kept."""

from __future__ import annotations

from typing import cast

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache

from documents import bundle
from documents.locks import LockTimeout
from editing import holds, parts, title_page
from editing.views.edit_tab import editable, tab_response
from editing.views.parts import _back, _said
from identity.models import User
from shell.views import not_found


@never_cache
@login_required
def switch(request: HttpRequest, number: int) -> HttpResponse:
    """Stage the switch and the text the form sends; the edit tab again, a refusal said there."""
    document = editable(request, number)
    if document is None or request.method != "POST":
        return not_found(request)
    user = cast(User, request.user)
    hold = holds.open_hold(document)
    if hold is None or hold.user_id != user.pk:
        # Refused as the panel's other forms are, whatever was sent: staging decides it again.
        messages.error(request, _said(parts.PartRefused("not_holding")))
        return _back(document)
    typed = request.POST.get("title_page_text", "")
    text = bundle.clean_title_page_text(typed)
    on = request.POST.get("title_page") == "on"
    if not bundle.valid_title_page_text(text):
        refused = {
            "title_page_attempt": typed,
            "title_page_attempt_on": on,
            "title_page_error": _("At most 500 characters and 8 lines, plain text."),
        }
        return tab_response(request, document, extra=refused, status=400)
    current = title_page.state(document, hold)
    try:
        if on != current["title_page"]:
            parts.stage_frontmatter(document, user, "title_page", on)
        if text != current["text"]:
            parts.stage_frontmatter(document, user, "title_page_text", text)
    except parts.PartRefused as refusal:
        messages.error(request, _said(refusal))
    except LockTimeout:
        messages.error(request, _("The document is busy. Try again in a moment."))
    return _back(document)
