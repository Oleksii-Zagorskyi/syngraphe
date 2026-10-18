"""The document template's text (DL-0169): checked against the whitelist and its own two rules,
and put in normal form for the language of the document it starts.

Outlines and titles are synthetic examples."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from django.utils import timezone

from tenancy.schemas import schema_context

IMAGE = "images/" + "a" * 64 + ".png"


@pytest.mark.parametrize(
    ("outline", "expected"),
    [
        ("# Purpose\nWhy.\n", []),
        ("# Purpose\n\n<div>raw</div>\n", [(3, "html")]),
        ("Starting text\n# Scope\n", [(1, "first-block")]),
        ("", [(1, "first-block")]),
        (f"# Purpose\n\n![A synthetic picture]({IMAGE})\n", [(3, "image")]),
        ("# Purpose\n\n" + "Synthetic words. " * 25_000, [(1, "too-large")]),
        # Inside the editor's size, past the template's.
        ("# Purpose\n\n" + "Synthetic words. " * 1_200, [(1, "too-large")]),
        # Two images in one paragraph: each refusal named once for its line.
        (
            f"# Purpose\n\n![One]({IMAGE}) ![Two]({IMAGE})\n",
            [(3, "image"), (3, "image-inline")],
        ),
    ],
    ids=[
        "inside",
        "html",
        "text-first",
        "empty",
        "image",
        "too-large",
        "past-the-template-size",
        "two-images",
    ],
)
def test_the_template_is_refused_by_construct_and_line(
    outline: str, expected: list[tuple[int, str]]
) -> None:
    from documents.template import refusals

    assert [(r.line, r.code) for r in refusals(outline)] == expected


def _english() -> Any:
    from identity.models import Language

    return Language(code="en", label="English", never_final="", may_be_final="")


def test_the_starting_body_is_in_normal_form() -> None:
    from documents.template import starting_body

    outline = "# Purpose\nThe first sentence. The second sentence.\n"

    assert starting_body(outline, _english()) == (
        "# Purpose\n\nThe first sentence.\nThe second sentence.\n"
    )


def test_a_template_outside_the_whitelist_has_no_strict_starting_body() -> None:
    from documents.template import TemplateRefused, starting_body

    outline = "# Purpose\n\n<div>raw</div>\n"

    with pytest.raises(TemplateRefused):
        starting_body(outline, _english())
    assert starting_body(outline, _english(), strict=False) == outline


@pytest.mark.integration
@pytest.mark.crash
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_a_resumed_creation_never_sticks(
    migrated_tenant: Any, member_of: Any, repo_root: Path
) -> None:
    from documents import bundle, gitstore, reconcile, services
    from documents.models import Document, DocumentTemplate, DocumentType, Folder
    from identity.models import Language

    Language.objects.get_or_create(code="uk", defaults={"label": "uk", "actor_kind": "system"})
    _, user, _ = member_of("an.author@example.test")
    broken = "# Purpose\n\n<div>raw</div>\n"
    with schema_context(migrated_tenant.number):
        kind = DocumentType.objects.get(code="document")
        root = Folder.objects.get(number=1)
        with pytest.raises(services.InjectedFault):
            services.create_document(user, "Synthetic example", "uk", kind, root, fault_at=2)
        document = Document.objects.get()
        Document.objects.filter(pk=document.pk).update(
            created_at=timezone.now() - timedelta(hours=1)
        )
        # Rewritten outside the page, as no administrator's save could.
        DocumentTemplate.objects.update(outline=broken)

    reconcile.run(tenant=migrated_tenant.number, repair=True)

    with schema_context(migrated_tenant.number):
        document.refresh_from_db()
    assert document.state == "active"
    repo = gitstore.open_repository(migrated_tenant.number, document.number)
    sha = str(next(gitstore.history(repo)).id)
    assert bundle.parse(gitstore.read(repo, "document.md", sha).decode())[1] == broken


def test_an_outline_is_put_in_normal_form_once_per_language(monkeypatch: Any) -> None:
    from documents import template

    calls: list[str] = []
    real = template.normalize

    def counted(previous: bytes, submitted: str, lists: Any) -> bytes:
        calls.append(lists.language)
        return real(previous, submitted, lists)

    monkeypatch.setattr(template, "normalize", counted)
    outline = "# Purpose\nA sentence counted once. Another one.\n"

    # The check before a creation's row and the body its first commit holds: one normalisation.
    first = template.starting_body(outline, _english())
    second = template.starting_body(outline, _english(), strict=False)

    assert first == second
    assert calls == ["en"]
