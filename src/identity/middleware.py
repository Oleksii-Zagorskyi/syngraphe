"""The request's interface language (DL-0501), and the framework's own administration interface,
confined (DL-0210)."""

from __future__ import annotations

from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.utils import translation

from audit.record import record
from identity.language import language_of
from shell.views import not_found
from tenancy.middleware import EXEMPT_PATHS


class LanguageMiddleware:
    """Each request in its person's interface language, the default before sign-in. The thread's
    language is set back on the way out, whatever happens, so the next request served on it
    never inherits this one's."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # The health probe answers whatever state the database is in; it reads no person.
        if request.path in EXEMPT_PATHS:
            return self.get_response(request)
        language = language_of(getattr(request, "user", None))
        translation.activate(language)
        # What the `i18n` context processor reads: the page's `lang` follows.
        request.LANGUAGE_CODE = language
        try:
            return self.get_response(request)
        finally:
            translation.deactivate()


class FrameworkAdminMiddleware:
    """Refuses the admin path on an organisation's domain and to anyone but a signed-in operator,
    with the uniform not-found answer; records every request an operator makes to it."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        self.prefix = f"/{settings.DJANGO_ADMIN_PATH}"

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # The bare path too: the framework would otherwise redirect it to the slashed one for
        # anyone, telling them the interface is there.
        path = request.path_info
        if not (path.startswith(self.prefix) or path == self.prefix[:-1]):
            return self.get_response(request)
        user = getattr(request, "user", None)
        if (
            getattr(request, "tenant_from_domain", True)
            or user is None
            or not user.is_authenticated
            or not getattr(user, "is_superuser", False)
        ):
            return not_found(request)
        record(
            actor=user,
            action="framework_admin.request",
            obj=None,
            before=None,
            after={"method": request.method, "path": request.path},
        )
        return self.get_response(request)
