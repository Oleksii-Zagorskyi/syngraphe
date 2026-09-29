"""The create dialog's form (`pages.md § Create or copy a document`)."""

from __future__ import annotations

from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _

from documents.bundle import TITLE_MAX, valid_title
from documents.models import ROOT_FOLDER, DocumentType, Folder
from identity.models import Language


class RootFolderField(forms.ModelChoiceField):  # type: ignore[type-arg]
    """The root folder, named after the organisation (DL-0194)."""

    organisation = ""

    def label_from_instance(self, obj: Any) -> str:
        return self.organisation


class CreateForm(forms.Form):
    title = forms.CharField(label=_("Title"), max_length=TITLE_MAX, strip=True)
    language = forms.ModelChoiceField(
        label=_("Language"), queryset=Language.objects.all(), to_field_name="code", empty_label=None
    )
    document_type = forms.ModelChoiceField(
        label=_("Type"),
        queryset=DocumentType.objects.filter(retired_at__isnull=True),
        empty_label=None,
    )
    # The root alone until folders beyond it exist.
    folder = RootFolderField(
        label=_("Folder"), queryset=Folder.objects.filter(number=ROOT_FOLDER), empty_label=None
    )

    def __init__(self, *args: Any, organisation: str, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        folder = self.fields["folder"]
        assert isinstance(folder, RootFolderField)
        folder.organisation = organisation

    def clean_title(self) -> str:
        title = str(self.cleaned_data["title"])
        if not valid_title(title):
            raise forms.ValidationError(_("A title is one line of text."))
        return title
