"""The create and copy dialogs' forms (`pages.md § Create or copy a document`)."""

from __future__ import annotations

from typing import Any, cast

from django import forms
from django.db.models import Case, Value, When
from django.http import QueryDict
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

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


class TemplateForm(forms.Form):
    """The document template's page: the outline and the title-page switch (ST-0058)."""

    # Checked by `documents.template`, not here: an empty outline is refused there, by its line.
    outline = forms.CharField(
        label=_("Section headings and starting text"),
        required=False,
        strip=False,
        widget=forms.Textarea(attrs={"rows": 16, "class": "outline", "spellcheck": "false"}),
    )
    title_page = forms.BooleanField(label=_("New documents get a title page"), required=False)

    def clean_outline(self) -> str:
        # A browser sends a text box's line breaks as CR LF; the stored text is the editor's.
        return str(self.cleaned_data["outline"]).replace("\r\n", "\n").replace("\r", "\n")


class TitlePageLayoutForm(forms.Form):
    """The title page's layout (DL-0462, DL-0476): each detail shown or not, with a position; the
    approval line's position, never hidden; the alignment."""

    POSITIONS = [("", "—"), *((str(n), str(n)) for n in range(1, 9))]
    LABELS = {
        "title": _("Title"),
        "number": _("Document number"),
        "type": _("Type"),
        "edition": _("Edition"),
        "approver": _("Approved by"),
        "approval_date": _("Approval date"),
        "text": _("The document's own title-page text"),
    }

    position_approval = forms.ChoiceField(label=_("Approval"), choices=POSITIONS[1:])
    align = forms.ChoiceField(
        label=_("Alignment"),
        choices=[
            ("left", pgettext_lazy("alignment", "left")),
            ("centre", pgettext_lazy("alignment", "centred")),
        ],
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for item, label in self.LABELS.items():
            self.fields[f"show_{item}"] = forms.BooleanField(label=label, required=False)
            self.fields[f"position_{item}"] = forms.ChoiceField(
                label=label, choices=self.POSITIONS, required=False
            )

    def rows(self) -> list[tuple[Any, Any]]:
        """Each detail's two fields, in the details' order."""
        return [(self[f"show_{item}"], self[f"position_{item}"]) for item in self.LABELS]

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        placed: dict[int, str] = {}
        shown = [item for item in self.LABELS if cleaned.get(f"show_{item}")]
        if not cleaned.get("position_approval"):
            raise forms.ValidationError(_("Give the approval line a position."))
        for item in [*shown, "approval"]:
            raw = cleaned.get(f"position_{item}") or ""
            if not raw:
                raise forms.ValidationError(_("Give each shown detail a position."))
            position = int(raw)
            if position in placed:
                raise forms.ValidationError(
                    _("Two details are at position %(position)s.") % {"position": position}
                )
            placed[position] = item
        cleaned["items"] = tuple(placed[p] for p in sorted(placed))
        return cleaned
