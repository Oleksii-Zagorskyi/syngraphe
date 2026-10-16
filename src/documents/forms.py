"""The create dialog's form (`pages.md § Create or copy a document`)."""

from __future__ import annotations

from typing import Any

from django import forms
from django.db.models import Case, Value, When
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
    # Epic 10: the folders the person sees, by path, the root first — a person never chooses, or
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
