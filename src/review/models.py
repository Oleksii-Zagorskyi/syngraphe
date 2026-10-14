"""Acceptances and the correction notices they generate (ADR-0001, ADR-0014, DL-0113).

`ACCEPTANCE` is derived from the passport commit it keys, which is the record; the notice holds
references, never text. The tables carry their own facts under the data model's names — who
reviewed, who was told, when — so they do not take the provenance columns.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class Acceptance(models.Model):
    """One acceptance of a run: its passport commit and the number it gave (DL-0183)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # The passport commit, kind `acceptance`.
    version = models.OneToOneField(
        "documents.Version", on_delete=models.PROTECT, related_name="acceptance"
    )
    # The content version the previous acceptance accepted, or the `created` one.
    accepted_from = models.ForeignKey(
        "documents.Version", on_delete=models.PROTECT, related_name="+"
    )
    number = models.CharField(max_length=21)
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    at = models.DateTimeField()
    # Set when the notices are computed, so an empty result is told from an uncomputed one.
    notices_computed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(number__regex=r"^[0-9]{1,10}\.[0-9]{1,10}$"),
                name="review_acceptance_number_is_n_m",
            )
        ]

    def __str__(self) -> str:
        return f"acceptance {self.number}"


class CorrectionNotice(models.Model):
    """One author's notice for one acceptance: every change of theirs a reviewer's version
    replaced or reversed (ADR-0014)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    acceptance = models.ForeignKey(Acceptance, on_delete=models.PROTECT, related_name="notices")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["acceptance", "author"], name="review_one_notice_per_author"
            )
        ]

    def __str__(self) -> str:
        return f"correction notice {self.pk}"


class Entry(models.TextChoices):
    LINE = "line", "line"
    RESTORED = "restored", "restored"
    PART_OPERATION = "part_operation", "part_operation"


class CorrectionLine(models.Model):
    """One change a notice lists, by reference: the versions and the line ranges, never the text
    (DL-0113). A range is `12` or `12-14`, empty for none."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    notice = models.ForeignKey(CorrectionNotice, on_delete=models.CASCADE, related_name="lines")
    changing_version = models.ForeignKey(
        "documents.Version", on_delete=models.PROTECT, related_name="+"
    )
    entry = models.CharField(max_length=14, choices=Entry.choices)
    # The appendix or attachment, for a part operation; empty otherwise.
    part = models.CharField(max_length=200, blank=True)
    author_version = models.ForeignKey(
        "documents.Version", on_delete=models.PROTECT, related_name="+"
    )
    file = models.CharField(max_length=100)
    range_before = models.CharField(max_length=23, blank=True)
    range_after = models.CharField(max_length=23, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(entry__in=Entry.values), name="review_correctionline_entry_known"
            ),
            *(
                models.CheckConstraint(
                    condition=Q(**{column: ""})
                    | Q(**{f"{column}__regex": r"^[1-9][0-9]{0,9}(-[1-9][0-9]{0,9})?$"}),
                    name=f"review_correctionline_{column}_is_a_range",
                )
                for column in ("range_before", "range_after")
            ),
        ]

    def __str__(self) -> str:
        return f"correction line {self.pk}"


class Return(models.Model):
    """One return of a run without accepting it (DL-0114): its passport commit, which is the
    record, and the reviewer's reason, one line under DL-0378's rule. The run stays pending; the
    returned versions are the run's up to the version the section names."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # The passport commit, kind `return`.
    version = models.OneToOneField(
        "documents.Version", on_delete=models.PROTECT, related_name="returned"
    )
    # The content version the latest acceptance before it accepted, or the `created` one.
    returned_from = models.ForeignKey(
        "documents.Version", on_delete=models.PROTECT, related_name="+"
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    reason = models.CharField(max_length=500)
    at = models.DateTimeField()

    def __str__(self) -> str:
        return f"return {self.pk}"
