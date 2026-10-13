"""The platform's sending address and its outbox (DL-0202, DL-0203): a platform administrator's
page on the platform's host. It reads and writes the shared schema's rows whatever organisation
the session has chosen, through the context manager inside the request (DL-0393), since the
tables exist in every schema; it renders outside that schema, where the shell reads the
session's organisation."""

from __future__ import annotations

from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters

from mail.forms import SenderForm
from mail.models import MailSender
from mail.views import common
from shell.views import frame, not_found
from tenancy.schemas import schema_context
from tenancy.views import _platform_admin

PAGE = "/administration/platform/mail/"
TEST = "/administration/platform/mail/test/"


@sensitive_post_parameters("password")
@never_cache
@login_required
def mail(request: HttpRequest) -> HttpResponse:
    """The platform's sender — the form, *remove*, the last test's steps — and its outbox."""
    if request.method not in ("GET", "POST") or not _platform_admin(request):
        return not_found(request)
    with schema_context(None):
        sender = MailSender.objects.first()
        if request.method == "POST":
            if request.POST.get("action") == "remove":
                if sender is not None:
                    common.remove(request, sender, None)
                return HttpResponseRedirect(PAGE)
            form = SenderForm(request.POST, stored=common.stored(sender))
            if form.is_valid() and common.save(request, form, sender, None):
                return HttpResponseRedirect(PAGE)
        else:
            form = SenderForm(initial=common.initial(sender), stored=common.stored(sender))
    return _page(request, sender, form)


@sensitive_post_parameters("password")
@never_cache
@login_required
def test(request: HttpRequest) -> HttpResponse:
    """*Send a test email*: the form saved as it stands, then the worker's job asked for — one
    test at a time (DL-0392)."""
    from mail.tasks import test_sender

    if request.method != "POST" or not _platform_admin(request):
        return not_found(request)
    with schema_context(None):
        sender = MailSender.objects.first()
        form = SenderForm(request.POST, stored=common.stored(sender))
        running = common.test_running(sender)
        saved = not running and form.is_valid() and common.save(request, form, sender, None)
        if saved:
            sender = MailSender.objects.first()
            assert sender is not None
            common.ask_for_test(sender)
    if not saved:
        return _page(request, sender, form, running=running)
    test_sender.delay(None)
    return common.after_test(PAGE)


def _page(
    request: HttpRequest, sender: MailSender | None, form: SenderForm, *, running: bool = False
) -> HttpResponse:
    def rows() -> Any:
        with schema_context(None):
            return common.outbox()

    return common.page(
        request,
        sender,
        form,
        scope="platform",
        page_url=PAGE,
        test_url=TEST,
        rows=rows,
        frame=frame(request),
        running=running,
    )
