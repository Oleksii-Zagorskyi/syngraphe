"""Administration › template (ST-0058, DL-0169): the outline every new document starts from and
the title-page switch, for the organisation's administrators; anyone else is answered as for a
missing page. The template is not a document: it has no review cycle, and the audit trail is its
only history."""

from __future__ import annotations

from typing import Any, cast

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.cache import never_cache

from access.views import administers
from audit.record import record
from documents.forms import TemplateForm, TitlePageLayoutForm
from documents.models import DocumentTemplate
from documents.template import TemplateRefusal, checked
from identity.models import Language, User
from shell.views import frame, not_found

PAGE = "/administration/tenant/template/"

# The template's own refusals, beside the whitelist's constructs.
OWN_REFUSALS = {
    "first-block": gettext_lazy("The template must begin with a # heading"),
    "image": gettext_lazy("A template cannot hold an image"),
}


def refusal_text(refusal: TemplateRefusal) -> str:
    """One refusal as the page shows it: *Line N:* and the construct as the editor names it, or
    the sentence for an outline that does not normalise."""
    from editing.messages import CONSTRUCTS

    if refusal.code == "normal-form":
        # About the whole outline, so it names no line.
        language = Language.objects.filter(code=refusal.language).first()
        return _("The platform could not prepare the template for a document in %(language)s") % {
            "language": language.label if language else refusal.language
        }
    named = OWN_REFUSALS.get(refusal.code) or CONSTRUCTS.get(refusal.code)
    what = str(named) if named else refusal.code
    return _("Line %(line)s: %(what)s") % {"line": refusal.line, "what": what}


def _state(template: DocumentTemplate) -> dict[str, Any]:
    return {
        "outline": template.outline,
        "title_page": template.title_page,
        "title_page_layout": template.title_page_layout,
    }


@never_cache
@login_required
def template(request: HttpRequest) -> HttpResponse:
    """The page; `POST` saves the outline and the switch when the outline passes, audited as
    `template.changed` with both states in full, or draws the page again with every refusal and
    `400`, nothing saved."""
    if request.method not in ("GET", "POST") or not administers(request):
        return not_found(request)
    if request.method == "GET":
        current = DocumentTemplate.objects.select_related("updated_by").get()
        form = TemplateForm(initial={"outline": current.outline, "title_page": current.title_page})
        return _page(request, current, form)
    form = TemplateForm(request.POST)
    form.is_valid()
    outline = form.cleaned_data.get("outline", "")
    found = checked(outline, list(Language.objects.all()))
    if found:
        current = DocumentTemplate.objects.select_related("updated_by").get()
        return _page(request, current, form, refusals=found, status=400)
    with transaction.atomic():
        row = DocumentTemplate.objects.select_for_update(of=("self",)).get()
        before = _state(row)
        row.outline = outline
        row.title_page = bool(form.cleaned_data.get("title_page"))
        row.updated_by = cast(User, request.user)
        row.save(update_fields=["outline", "title_page", "updated_by", "updated_at"])
        record(
            actor=cast(User, request.user),
            action="template.changed",
            obj=row,
            before=before,
            after=_state(row),
            tenant=getattr(request, "tenant", None),
        )
    response = HttpResponse(status=303)
    response["Location"] = PAGE
    return response


def _page(
    request: HttpRequest,
    current: DocumentTemplate,
    form: TemplateForm,
    *,
    refusals: list[TemplateRefusal] | None = None,
    status: int = 200,
) -> HttpResponse:
    context = {
        **frame(request),
        "form": form,
        "refusals": [refusal_text(r) for r in refusals or []],
        # By address, as every administration page names a person (DL-0434).
        "changed_by": current.updated_by.email if current.updated_by is not None else "",
        "changed_at": current.updated_at if current.updated_by_id else current.created_at,
        "page_url": PAGE,
    }
    return render(request, "documents/template.html", context, status=status)


LAYOUT_PAGE = "/administration/tenant/template/title-page/"


@never_cache
@login_required
def title_page_layout(request: HttpRequest) -> HttpResponse:
    """The title page's layout (DL-0462): `POST` saves the details shown, their order and the
    alignment, or with `action=reset` the default form; audited as `template.changed`. Two details
    at one position are refused with `400`, nothing saved."""
    from rendering import title_page

    if request.method not in ("GET", "POST") or not administers(request):
        return not_found(request)
    if request.method == "GET":
        layout = title_page.layout_of(DocumentTemplate.objects.get().title_page_layout)
        initial: dict[str, Any] = {"align": layout.align}
        for position, item in enumerate(layout.items, 1):
            initial[f"position_{item}"] = str(position)
            initial[f"show_{item}"] = True
        return _layout_page(request, TitlePageLayoutForm(initial=initial))
    if request.POST.get("action") == "reset":
        stored = ""
    else:
        form = TitlePageLayoutForm(request.POST)
        if not form.is_valid():
            return _layout_page(request, form, status=400)
        layout = title_page.Layout(form.cleaned_data["items"], form.cleaned_data["align"])
        stored = title_page.dump(layout)
    with transaction.atomic():
        row = DocumentTemplate.objects.select_for_update(of=("self",)).get()
        before = _state(row)
        row.title_page_layout = stored
        row.updated_by = cast(User, request.user)
        row.save(update_fields=["title_page_layout", "updated_by", "updated_at"])
        record(
            actor=cast(User, request.user),
            action="template.changed",
            obj=row,
            before=before,
            after=_state(row),
            tenant=getattr(request, "tenant", None),
        )
    response = HttpResponse(status=303)
    response["Location"] = LAYOUT_PAGE
    return response


def _layout_page(
    request: HttpRequest, form: TitlePageLayoutForm, *, status: int = 200
) -> HttpResponse:
    context = {**frame(request), "form": form, "page_url": LAYOUT_PAGE, "template_url": PAGE}
    return render(request, "documents/title_page_layout.html", context, status=status)
