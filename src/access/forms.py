from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _

from access.rights import Right


class GroupForm(forms.Form):
    name = forms.CharField(label=_("Name"), max_length=100)

    def clean_name(self) -> str:
        from access.models import AccessGroup

        name = str(self.cleaned_data["name"]).strip()
        if AccessGroup.objects.filter(name=name).exists():
            raise forms.ValidationError(_("A group with this name exists."))
        return name


class RightForm(forms.Form):
    right = forms.ChoiceField(choices=[(r.value, r.value) for r in Right])
    action = forms.ChoiceField(choices=[("grant", "grant"), ("revoke", "revoke")])


class MemberForm(forms.Form):
    membership = forms.UUIDField()
    action = forms.ChoiceField(
        choices=[("add", "add"), ("remove", "remove")], required=False, initial="add"
    )


class LinkForm(forms.Form):
    group = forms.UUIDField()
    action = forms.ChoiceField(choices=[("link", "link"), ("unlink", "unlink")])
