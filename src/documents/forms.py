"""The create and copy dialogs' forms (`pages.md § Create or copy a document`)."""

from __future__ import annotations

from typing import Any, cast

from django import forms
from django.db.models import Case, Value, When
from django.http import QueryDict
from django.utils.translation import gettext_lazy as _

from documents.bundle import TITLE_MAX, valid_title
from documents.models import DocumentType, Folder
from identity.models import Language

# A new document's language when the organisation names none (DL-0366).
DEFAULT_DOCUMENT_LANGUAGE = "en"


class FolderField(forms.ModelChoiceField):  # type: ignore[type-arg]
    """A folder the person sees, labelled by its path; the root named after the organisation
    (DL-0194, DL-0206)."""

    paths: dict[Any, str] = {}

    def label_from_instance(self, obj: Any) -> str:
        return self.paths.get(obj.pk, "")


class LabelledField(forms.ModelChoiceField):  # type: ignore[type-arg]
    """A choice of seeded rows named by their labels, never by their codes."""

    def label_from_instance(self, obj: Any) -> str:
        return str(obj.label)


class CreateForm(forms.Form):
    title = forms.CharField(label=_("Title"), max_length=TITLE_MAX, strip=True)
    language = LabelledField(
        label=_("Language"), queryset=Language.objects.all(), to_field_name="code", empty_label=None
    )
    document_type = LabelledField(
        label=_("Type"),
        queryset=DocumentType.objects.filter(retired_at__isnull=True),
        empty_label=None,
    )
    # The folders the person sees, by path, the root first — a person never chooses, or
    # learns, a folder they cannot see; one posted outside them is refused as an unknown one.
    folder = FolderField(label=_("Folder"), queryset=Folder.objects.none(), empty_label=None)

    def __init__(
        self, *args: Any, organisation: str, user: Any, administrator: bool, **kwargs: Any
    ) -> None:
        from documents.tree import Tree, visible_folders

        super().__init__(*args, **kwargs)
        tree = Tree(organisation, visible_folders(user, administrator=administrator))
        listed = [node.folder for node in tree.flat()]
        folder = self.fields["folder"]
        assert isinstance(folder, FolderField)
        # In path order, root first, as the tree lists them.
        order = Case(*(When(pk=f.pk, then=Value(i)) for i, f in enumerate(listed)))
        folder.queryset = Folder.objects.filter(pk__in=[f.pk for f in listed]).order_by(order)
        folder.paths = {f.pk: tree.path_of(f) for f in listed}
        # English until an organisation has a language of its own (DL-0366).
        self.fields["language"].initial = DEFAULT_DOCUMENT_LANGUAGE

    def clean_title(self) -> str:
        title = str(self.cleaned_data["title"])
        if not valid_title(title):
            raise forms.ValidationError(_("A title is one line of text."))
        return title


class CopyForm(CreateForm):
    """The copy dialog's fields beside the version and the appendices it draws itself: the title
    prefilled with the source's, the type and folder as in create, the language the source's and
    never a choice (`pages.md § Create or copy a document`)."""

    APPENDICES = ("none", "all", "chosen")

    def __init__(self, *args: Any, source: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        del self.fields["language"]
        self.fields["title"].initial = source.title
        kind = self.fields["document_type"]
        assert isinstance(kind, LabelledField)
        # Posted by code and number, as every other page names a type and a folder.
        kind.to_field_name = "code"
        if source.document_type.retired_at is None:
            kind.initial = source.document_type.code
        folder = self.fields["folder"]
        assert isinstance(folder, FolderField)
        folder.to_field_name = "number"
        if source.folder_id in folder.paths:
            folder.initial = source.folder.number

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        view, colon, number = str(self.data.get("version", "")).partition(":")
        if not view or not colon or not number:
            raise forms.ValidationError(_("Choose a version."))
        cleaned["view"], cleaned["number"] = view, number
        mode = self.data.get("appendices", "none")
        if mode not in self.APPENDICES:
            raise forms.ValidationError(_("Choose the appendices to copy."))
        posted = cast(QueryDict, self.data).getlist("appendix")
        # An appendix number as the dialog posts it: ASCII digits, a few of them.
        if any(not (n.isascii() and n.isdigit() and len(n) <= 6) for n in posted):
            raise forms.ValidationError(_("Choose the appendices to copy."))
        chosen = [int(n) for n in posted]
        cleaned["appendices"] = {"none": [], "all": None, "chosen": chosen}[mode]
        return cleaned
