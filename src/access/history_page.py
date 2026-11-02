"""Administration › Access history (ST-0006): a document and a day, or one of its editions, answered
as the groups that could read it then, their rights and members, and the changes that led there;
*any document*, the changes alone (DL-0460, DL-0461). For the organisation's administrators and
a platform administrator who has chosen it; people are named by address (DL-0434)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, cast
from zoneinfo import ZoneInfo

from django import forms
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.cache import never_cache

from access import history
from access.rights import LABELS, Right
from access.views import administers
from identity.naming import by_address
from shell.views import frame, not_found

ANY = "any"


def today() -> date:
    """Today in the installation's display timezone, the day the administrator is living."""
    return timezone.localdate(timezone=ZoneInfo(settings.DISPLAY_TIMEZONE))


class HistoryForm(forms.Form):
    document = forms.ChoiceField(label=gettext_lazy("Document"))
    on = forms.DateField(label=gettext_lazy("On"), required=False)
    # The chosen document's editions; one of them takes the place of the day (DL-0461).
    edition = forms.ChoiceField(label=gettext_lazy("Or at the edition"), required=False)

    def __init__(self, *args: Any, documents: list[Any], **kwargs: Any) -> None:
        from editions.models import Edition

        super().__init__(*args, **kwargs)
        self.documents = {str(d.number): d for d in documents}
        cast(forms.ChoiceField, self.fields["document"]).choices = [
            (ANY, _("any document")),
            *((str(d.number), f"#{d.number} {d.title}") for d in documents),
        ]
        self.chosen = self.documents.get(str(self.data.get("document", "")))
        self.editions = (
            {
                e.number: e
                for e in Edition.objects.filter(version__document=self.chosen).order_by(
                    "approved_at"
                )
            }
            if self.chosen is not None
            else {}
        )
        cast(forms.ChoiceField, self.fields["edition"]).choices = [
            ("", "—"),
            *((number, number) for number in self.editions),
        ]

    def clean_on(self) -> Any:
        day = self.cleaned_data.get("on") or today()
        if day > today():
            raise forms.ValidationError(_("Choose today or an earlier day."))
        return day

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        cleaned["found_edition"] = self.editions.get(cleaned.get("edition") or "")
        return cleaned


@never_cache
@login_required
def access_history(request: HttpRequest) -> HttpResponse:
    """The form; asked a question, the answer below it, or the form's errors and `400`."""
    if request.method != "GET" or not administers(request):
        return not_found(request)
    from documents.models import Document, DocumentState

    documents = list(
        Document.objects.exclude(state=DocumentState.CREATING)
        .only("pk", "number", "title", "state", "created_at")
        .order_by("number")
    )
    if "document" not in request.GET:
        form = HistoryForm(initial={"on": today()}, documents=documents)
        return _page(request, {"form": form})
    form = HistoryForm(request.GET, documents=documents)
    if not form.is_valid():
        return _page(request, {"form": form, "document": form.chosen}, status=400)
    chosen = form.cleaned_data["document"]
    edition = form.cleaned_data.get("found_edition")
    moment = edition.approved_at if edition is not None else _moment(form.cleaned_data["on"])
    if chosen == ANY:
        changes = history.changes_until(moment)
        return _page(request, {"form": form, "changes": _rows(changes), "asked": True})
    document = form.documents[chosen]
    answer = history.readers_at(document, moment)
    changes = history.changes_until(moment, document=document)
    context = {
        "form": form,
        "asked": True,
        "document": document,
        "answer": answer,
        "edition": edition,
        "day": form.cleaned_data["on"],
        "groups": [_group(g) for g in answer.groups],
        "changes": _rows(changes),
    }
    return _page(request, context)


def _moment(day: Any) -> datetime:
    return history.moment_of_day(day)


def _grant(grant: history.Grant) -> dict[str, Any]:
    return {"at": grant.at, "who": by_address(grant.by, grant.actor_kind)}


def _group(then: history.GroupThen) -> dict[str, Any]:
    return {
        "name": then.group.name,
        "linked": _grant(then.linked),
        "rights": [{"label": LABELS[right], **_grant(grant)} for right, grant in then.rights],
        "active": sum(1 for m in then.members if m.state == "active"),
        "members": [
            {"address": m.address, "blocked": m.state != "active", **_grant(m.added)}
            for m in then.members
        ],
    }


def _rows(changes: list[history.Change]) -> dict[str, Any]:
    return {
        "rows": [
            {"at": c.at, "who": by_address(c.by, c.actor_kind), "change": change_line(c)}
            for c in changes
        ],
        "bounded": len(changes) >= history.CHANGES_SHOWN,
    }


def change_line(change: history.Change) -> str:
    """One change as the page states it, one sentence per kind and action."""
    values = {
        "group": change.group_name,
        "number": change.document_number,
        "address": change.member_address,
    }
    if change.kind == "link":
        if change.action == "added":
            return _("%(group)s linked to #%(number)s") % values
        return _("%(group)s unlinked from #%(number)s") % values
    if change.kind == "right":
        right = str(LABELS[Right(change.right)]) if change.right in Right else change.right
        if change.action == "added":
            return _("%(group)s granted %(right)s") % {**values, "right": right}
        return _("%(group)s: %(right)s withdrawn") % {**values, "right": right}
    if change.kind == "member":
        if change.action == "added":
            return _("%(address)s added to %(group)s") % values
        return _("%(address)s removed from %(group)s") % values
    if change.kind == "membership":
        if change.field == "state":
            if change.after == "blocked":
                return _("%(address)s's membership blocked") % values
            return _("%(address)s's membership active again") % values
        if change.after == "True":
            return _("%(address)s made an administrator") % values
        return _("%(address)s no longer an administrator") % values
    if change.action == "archived":
        return _("#%(number)s archived") % values
    return _("#%(number)s restored") % values


def _page(request: HttpRequest, context: dict[str, Any], *, status: int = 200) -> HttpResponse:
    return render(
        request,
        "access/access_history.html",
        {**frame(request), **context, "shown": history.CHANGES_SHOWN},
        status=status,
    )
