"""Documents in the tenant's schema: the document, its type and folder, the template new documents
start from, its versions, and the caches rebuilt from git (ADR-0007, ADR-0008, DL-0111).

Git holds content; these rows are derived from it or are about it, never a second copy of a text.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import connection, models
from django.db.models.functions import Lower

from syngraphe.provenance import Mutable, Provenanced

# The tenant schema's own sequence: a number taken by a failed creation is never given again
# (ADR-0008).
DOCUMENT_NUMBER_SEQUENCE = "documents_document_number"
ROOT_FOLDER = 1


def next_document_number() -> int:
    """The next document number of the tenant whose schema the connection is set to."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT nextval(%s)", [DOCUMENT_NUMBER_SEQUENCE])
        row = cursor.fetchone()
    assert row is not None
    return int(row[0])


# Epic 10: folder numbers from the tenant's own sequence, after the root's 1, never given again.
FOLDER_NUMBER_SEQUENCE = "documents_folder_number"


def next_folder_number() -> int:
    """The next folder number of the tenant whose schema the connection is set to."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT nextval(%s)", [FOLDER_NUMBER_SEQUENCE])
        row = cursor.fetchone()
    assert row is not None
    return int(row[0])


class DocumentType(Mutable):
    """This organisation's own classification of documents, seeded with `document` (DL-0235)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True)
    label = models.CharField(max_length=100)
    retired_at = models.DateTimeField(null=True, blank=True)

    class Meta(Mutable.Meta):
        abstract = False
        ordering = ["label"]
        # Epic 10: a label is unique among the organisation's types, in any case (DL-10-001).
        constraints = [
            *Mutable.Meta.constraints,
            models.UniqueConstraint(Lower("label"), name="documents_documenttype_label_unique_ci"),
        ]

    def __str__(self) -> str:
        return self.code


class Folder(Mutable):
    """Presentation only; the root is number 1 and its name is the organisation's (ADR-0008,
    DL-0194)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    number = models.PositiveIntegerField(unique=True)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="children"
    )
    name = models.CharField(max_length=200, blank=True)

    class Meta(Mutable.Meta):
        abstract = False
        ordering = ["number"]
        # Epic 10: a folder is known by its path, so siblings never share a name in any case
        # (DL-0453); the root alone has no parent (ADR-0008).
        constraints = [
            *Mutable.Meta.constraints,
            models.UniqueConstraint(
                Lower("name"), "parent", name="documents_folder_name_unique_among_siblings"
            ),
            models.CheckConstraint(
                condition=models.Q(number=1, parent__isnull=True)
                | models.Q(parent__isnull=False, number__gt=1),
                name="documents_folder_only_the_root_has_no_parent",
            ),
        ]

    def __str__(self) -> str:
        return f"folder {self.number}"


class DocumentTemplate(Mutable):
    """What a new document starts from; one row per organisation (DL-0169)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    outline = models.TextField(blank=True)
    title_page = models.BooleanField(default=False)
    title_page_layout = models.TextField(blank=True)

    class Meta(Mutable.Meta):
        abstract = False

    def __str__(self) -> str:
        return "document template"


class DocumentState(models.TextChoices):
    CREATING = "creating", "creating"
    ACTIVE = "active", "active"
    ARCHIVED = "archived", "archived"


class Document(Mutable):
    """A document; its content is its repository at `tenant-N/document-M/`.

    `title` and `language` are caches of `document.md`'s frontmatter. `state` is `creating` from
    the row's first write until the repository holds its first commit (DL-0111).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    number = models.PositiveIntegerField(unique=True)
    title = models.CharField(max_length=500)
    language = models.ForeignKey("identity.Language", on_delete=models.PROTECT, related_name="+")
    document_type = models.ForeignKey(DocumentType, on_delete=models.PROTECT, related_name="+")
    folder = models.ForeignKey(Folder, on_delete=models.PROTECT, related_name="documents")
    author_only = models.BooleanField(default=True)
    copied_from = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="copies"
    )
    state = models.CharField(
        max_length=8, choices=DocumentState.choices, default=DocumentState.CREATING
    )

    class Meta(Mutable.Meta):
        abstract = False
        ordering = ["number"]

    def __str__(self) -> str:
        return f"#{self.number}"


class VersionKind(models.TextChoices):
    """The same values as a commit's `Kind:` trailer (DL-0260, DL-0268)."""

    CREATED = "created", "created"
    EDIT = "edit", "edit"
    REVIEWER_EDIT = "reviewer_edit", "reviewer_edit"
    ACCEPTANCE = "acceptance", "acceptance"
    RETURN = "return", "return"
    APPROVAL = "approval", "approval"


class Version(Provenanced):
    """One commit of a document's repository, derived from it (DL-0111)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, on_delete=models.PROTECT, related_name="versions")
    commit_sha = models.CharField(max_length=40, unique=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    summary = models.CharField(max_length=500)
    kind = models.CharField(max_length=13, choices=VersionKind.choices)
    committed_at = models.DateTimeField()

    class Meta(Provenanced.Meta):
        abstract = False
        ordering = ["committed_at"]

    def __str__(self) -> str:
        return self.commit_sha[:12]


class HeadingIndex(Provenanced):
    """A heading of `document.md` or an appendix at one version; a cache rebuilt from git."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="+")
    version = models.ForeignKey(Version, on_delete=models.CASCADE, related_name="headings")
    file = models.CharField(max_length=100)
    position = models.PositiveIntegerField()
    depth = models.PositiveSmallIntegerField()
    heading = models.CharField(max_length=1000)
    line = models.PositiveIntegerField()

    class Meta(Provenanced.Meta):
        abstract = False
        ordering = ["file", "position"]

    def __str__(self) -> str:
        return f"{self.file}:{self.line}"


class PartKind(models.TextChoices):
    APPENDIX = "appendix", "appendix"
    ATTACHMENT = "attachment", "attachment"


class PartIndex(Provenanced):
    """An appendix or attachment listed in `document.md`'s frontmatter at one version; a cache."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="+")
    version = models.ForeignKey(Version, on_delete=models.CASCADE, related_name="parts")
    kind = models.CharField(max_length=10, choices=PartKind.choices)
    part_number = models.PositiveIntegerField()
    position = models.PositiveIntegerField()
    title = models.CharField(max_length=500)
    file_name = models.CharField(max_length=255, blank=True)
    sha256 = models.CharField(max_length=64, blank=True)
    bytes = models.PositiveBigIntegerField(null=True, blank=True)

    class Meta(Provenanced.Meta):
        abstract = False
        ordering = ["kind", "position"]

    def __str__(self) -> str:
        return f"{self.kind} {self.part_number}"
