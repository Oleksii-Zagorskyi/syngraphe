"""The audit log's filters: each refuses what it does not know, never ignores it."""

from __future__ import annotations

from typing import Any, cast

from django import forms
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from syngraphe.provenance import ActorKind

# The organisation filter's value for events that belong to no organisation.
PLATFORM = "platform"


class AuditFilterForm(forms.Form):
    organisation = forms.ChoiceField(label=gettext_lazy("Organisation"), required=False)
    kind = forms.ChoiceField(
        label=gettext_lazy("Kind"),
        required=False,
        choices=[
            ("", "—"),
            (ActorKind.USER, gettext_lazy("person")),
            (ActorKind.SYSTEM, gettext_lazy("system")),
            (ActorKind.AGENT, gettext_lazy("agent")),
        ],
    )
    # Matched as a prefix: `document.` gives every document action.
    action = forms.CharField(label=gettext_lazy("Action"), required=False, max_length=100)
    since = forms.DateField(label=gettext_lazy("Since"), required=False)
    until = forms.DateField(label=gettext_lazy("Until"), required=False)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        from tenancy.models import Tenant

        super().__init__(*args, **kwargs)
        cast(forms.ChoiceField, self.fields["organisation"]).choices = [
            ("", "—"),
            (PLATFORM, _("the platform")),
            *(
                (str(number), f"#{number} {name}")
                for number, name in Tenant.objects.order_by("number").values_list("number", "name")
            ),
        ]

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        since, until = cleaned.get("since"), cleaned.get("until")
        if since and until and since > until:
            self.add_error("until", _("The end of the period comes before its start."))
        return cleaned
