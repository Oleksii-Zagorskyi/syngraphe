"""The page on which the browser tests run the conformance cases through the editor's own code.

Mounted always, and answering *Nothing to show here* unless `EDITING_CONFORMANCE_PAGE` is set, which
only the browser tests do; the setting is read on every request.
"""

from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from shell.views import not_found


def page(request: HttpRequest) -> HttpResponse:
    if not settings.EDITING_CONFORMANCE_PAGE or request.method != "GET":
        return not_found(request)
    return render(request, "editing/conformance.html")
