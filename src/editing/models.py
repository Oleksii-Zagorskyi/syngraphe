"""Holds, drafts, the uploads a draft stages and the editors open on it (ADR-0006, DL-0167).

The tables carry their own facts under the data model's names — who holds, since when, who released
— so they do not take the provenance columns of `syngraphe.provenance`.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class ReleaseKind(models.TextChoices):
    FINISHED = "finished", "finished"
    # Finished by *accept as*, its acceptance still to land: the reconciler's mark (ADR-0014's
    # one act, held across two writes).
    ACCEPTING = "accepting", "accepting"
    DISCARDED = "discarded", "discarded"
    # Let go by its holder with nothing edited: nothing was thrown away (DL-0510), and nothing is
    # kept (DL-0514).
    RELEASED = "released", "released"
    INACTIVITY = "inactivity", "inactivity"
    FORCED = "forced", "forced"
    BLOCKED = "blocked", "blocked"


class Hold(models.Model):
    """One person's exclusive claim to edit a document; open while `released_at` is null."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey("documents.Document", on_delete=models.PROTECT, related_name="+")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    acquired_at = models.DateTimeField()
    last_activity_at = models.DateTimeField()
    reserved_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)
    released_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    release_kind = models.CharField(max_length=10, choices=ReleaseKind.choices, blank=True)
    release_reason = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["document"],
                condition=Q(released_at__isnull=True),
                name="editing_hold_one_open_per_document",
            ),
            models.CheckConstraint(
                condition=Q(released_at__isnull=True, release_kind="")
                | Q(released_at__isnull=False) & ~Q(release_kind=""),
                name="editing_hold_released_with_its_kind",
            ),
            models.CheckConstraint(
                condition=Q(release_kind__in=["", *ReleaseKind.values]),
                name="editing_hold_release_kind_known",
            ),
            # Someone forced or blocked it, or nobody: a finish or a discard is the holder's own.
            models.CheckConstraint(
                condition=Q(released_by__isnull=True)
                | Q(release_kind__in=[ReleaseKind.FORCED, ReleaseKind.BLOCKED]),
                name="editing_hold_released_by_only_when_forced",
            ),
        ]

    def __str__(self) -> str:
        return f"hold {self.pk}"


class Draft(models.Model):
    """The working text of one hold: a body per file, the frontmatter and the declarations, never a
    version."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    hold = models.OneToOneField(Hold, on_delete=models.PROTECT, related_name="draft")
    # The head the draft started from (DL-0318).
    base_commit = models.CharField(max_length=40)
    # `document.md` — the body — `frontmatter` and `entities.yaml`, what the editors and the
    # commit read; and, after an undo, `undo` — `{"version", "author", "undone", "listed":
    # [{"before", "wrote", "after"}]}`: the versions undone so far, which a second undo merges
    # from, and the places left for the holder's hand, a `{"frontmatter": "kept"}` entry for a
    # title or part the undo left standing and an `{"entities": "kept"}` one for the roles,
    # actions and terms — kept beside the text and never in it (DL-0380).
    content = models.JSONField()
    updated_at = models.DateTimeField(auto_now=True)
    # What the edit tab opens with, so that it need not run the normalizer itself (DL-23-001):
    # `{"key", "edited", "declared"}` — whether the draft holds edits, the declarations *Mark*
    # offers, and a hash of every input they were read from. An answer whose key no longer matches
    # is read again; nothing else trusts it.
    opening = models.JSONField(null=True, blank=True)

    def __str__(self) -> str:
        return f"draft {self.pk}"


class DraftFileKind(models.TextChoices):
    IMAGE = "image", "image"
    ATTACHMENT = "attachment", "attachment"


class DraftFileOperation(models.TextChoices):
    ADD = "add", "add"
    REPLACE = "replace", "replace"
    REMOVE = "remove", "remove"


class DraftFile(models.Model):
    """An upload waiting with its draft until the commit that finishes the session (DL-0175)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    draft = models.ForeignKey(Draft, on_delete=models.CASCADE, related_name="files")
    kind = models.CharField(max_length=10, choices=DraftFileKind.choices)
    path = models.CharField(max_length=200)
    operation = models.CharField(max_length=7, choices=DraftFileOperation.choices)
    content = models.BinaryField(null=True, blank=True)
    file_name = models.CharField(max_length=255, blank=True)
    sha256 = models.CharField(max_length=64, blank=True)
    at = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(operation=DraftFileOperation.REMOVE, content__isnull=True)
                | ~Q(operation=DraftFileOperation.REMOVE) & Q(content__isnull=False),
                name="editing_draftfile_content_unless_removed",
            )
        ]

    def __str__(self) -> str:
        return f"draft file {self.pk}"


class OpenEditor(models.Model):
    """An editor open on the draft, known by its heartbeat; open while `closed_at` is null. Its
    captures are taken only while the text still hashes to `base_hash`. `range` is always
    `whole`: an editor opens on the whole text (DL-0517); the column stays so the rows written
    before are read as they stand, and dropping it would be a migration for nothing."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    draft = models.ForeignKey(Draft, on_delete=models.CASCADE, related_name="editors")
    file = models.CharField(max_length=100)
    range = models.CharField(max_length=100)
    base_hash = models.CharField(max_length=64)
    last_seen_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"open editor {self.pk}"


class LineAuthorship(models.Model):
    """Which version introduced each non-blank line of a file at a version, kept for the head and
    the latest accepted version (DL-0135, DL-0266, ADR-0011). A cache of what blame says, never
    the authority."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    version = models.ForeignKey(
        "documents.Version", on_delete=models.CASCADE, related_name="authorship"
    )
    file = models.CharField(max_length=100)
    line = models.PositiveIntegerField()
    introduced_by = models.ForeignKey(
        "documents.Version", on_delete=models.CASCADE, related_name="+"
    )
    # A verbatim line matched more than once by the move rule: recorded, not guessed.
    ambiguous_move = models.BooleanField(default=False)
    # Null for the kept versions; set on rows computed on demand for an older one.
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["version", "file", "line"], name="editing_lineauthorship_one_per_line"
            )
        ]

    def __str__(self) -> str:
        return f"line authorship {self.pk}"
