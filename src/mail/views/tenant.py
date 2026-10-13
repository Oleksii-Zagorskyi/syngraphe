"""The organisation's own sending address and its outbox (DL-0202, DL-0385): for its
administrators, and for a platform administrator who has chosen it, in the organisation's own
schema as every organisation page reads."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters

from access.views import administers
from mail.forms import SenderForm
from mail.models import MailSender
from mail.views import common
from shell.views import frame, not_found

PAGE = "/administration/tenant/sending-address/"
TEST = "/administration/tenant/sending-address/test/"


@sensitive_post_parameters("password")
@never_cache
@login_required
def sending_address(request: HttpRequest) -> HttpResponse:
    """The organisation's sender — the form, *remove*, the last test's steps — and its outbox."""
    if request.method not in ("GET", "POST") or not administers(request):
        return not_found(request)
    tenant = getattr(request, "tenant", None)
    sender = MailSender.objects.first()
    if request.method == "POST":
        if request.POST.get("action") == "remove":
            if sender is not None:
                common.remove(request, sender, tenant)
            return HttpResponseRedirect(PAGE)
        form = SenderForm(request.POST, stored=common.stored(sender))
        if form.is_valid() and common.save(request, form, sender, tenant):
            return HttpResponseRedirect(PAGE)
    else:
        form = SenderForm(initial=common.initial(sender), stored=common.stored(sender))
    return _page(request, sender, form)


@sensitive_post_parameters("password")
@never_cache
@login_required
def test(request: HttpRequest) -> HttpResponse:
    """*Send a test email* for the organisation's sender, saved first as the form stands — one
    test at a time (DL-0392)."""
    from mail.tasks import test_sender

    if request.method != "POST" or not administers(request):
        return not_found(request)
    tenant = getattr(request, "tenant", None)
    assert tenant is not None
    sender = MailSender.objects.first()
    form = SenderForm(request.POST, stored=common.stored(sender))
    running = common.test_running(sender)
    if running or not form.is_valid() or not common.save(request, form, sender, tenant):
        return _page(request, sender, form, running=running)
    sender = MailSender.objects.first()
    assert sender is not None
    if not common.claim_test(sender):
        return _page(request, sender, form, running=True)
    test_sender.delay(tenant.number)
    return common.after_test(PAGE)


def _page(
    request: HttpRequest, sender: MailSender | None, form: SenderForm, *, running: bool = False
) -> HttpResponse:
    return common.page(
        request,
        sender,
        form,
        scope="organisation",
        page_url=PAGE,
        test_url=TEST,
        rows=common.outbox,
        frame=frame(request),
        running=running,
    )
