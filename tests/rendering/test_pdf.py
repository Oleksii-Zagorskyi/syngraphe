"""The PDF export (ADR-0013, DL-0182): the conformance sample with its outline, every label, the
header and the page numbers; a remote reference failing the job by name and writing nothing; the
writer refusing every fetch but the document's own images; a marked export.

People, groups and titles are synthetic examples; every text is invented.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from access.rights import Right
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]


def _body(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _export(client: Any, number: int, **choice: str) -> None:
    response = client.post(f"/document/{number}/export/", {"document": "on", **choice})
    assert response.status_code == 302, response.content[:400]


def _pdf_text(path: Path) -> tuple[str, list[str]]:
    from pypdf import PdfReader

    pdf = PdfReader(str(path))
    titles: list[str] = []

    def walk(entries: list[Any]) -> None:
        for entry in entries:
            if isinstance(entry, list):
                walk(entry)
            else:
                titles.append(entry.title)

    walk(pdf.outline)
    return "\n".join(page.extract_text() for page in pdf.pages), titles


def test_pdf_has_outline_labels_and_furniture(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
    monkeypatch: pytest.MonkeyPatch,
    settings: Any,
) -> None:
    from rendering.export import compose, pdf
    from rendering.models import ExportView
    from rendering.numbering import labels
    from rendering.renderer import RENDERER

    fetched: list[str] = []
    real = pdf.fetcher

    def recording(read_image: Any) -> Any:
        inner = real(read_image)

        def fetch(url: str, *args: Any, **kwargs: Any) -> Any:
            fetched.append(url)
            return inner(url, *args, **kwargs)

        fetch._fail_on_errors = True  # type: ignore[attr-defined]
        return fetch

    monkeypatch.setattr(pdf, "fetcher", recording)
    sample = _body(kit.FIXTURES / "conformance.md")
    people = edition_cast()
    kit.canonical(migrated_tenant.number, people, commit_version, sample)
    client, _ = kit.reader(member_of, link_group, people, [Right.VIEW_CANONICAL], "pdf")

    _export(client, people.document.number, format="pdf", view="canonical")
    job = kit.run_job(migrated_tenant.number, exports[0][1])

    assert job.state == "done", job.failure_reason
    text, outline = _pdf_text(Path(settings.EXPORT_ROOT) / job.artifact_ref)
    tokens = RENDERER.parse(sample)
    found = labels(tokens)
    headings = [found[i] for i in sorted(found) if tokens[i].type == "heading_open"]
    assert len(outline) == len(headings)
    for label in found.values():
        assert label in text, label
    with schema_context(migrated_tenant.number):
        stance = compose.stance(ExportView.CANONICAL)
    title = people.document.title
    from pypdf import PdfReader

    pages = PdfReader(str(Path(settings.EXPORT_ROOT) / job.artifact_ref)).pages
    assert len(pages) > 1
    for n, page in enumerate(pages, 1):
        # Every page carries the header — title, number, stance — and its own page number.
        lines = [line.strip() for line in page.extract_text().splitlines()]
        flat = re.sub(r"\s+", " ", " ".join(lines))
        assert f"{title} 1.0 — {stance}" in flat, n
        assert str(n) in lines, n
    # Images reach an export as their descriptions: nothing is fetched.
    assert fetched == []


def test_remote_reference_fails_loudly(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
    settings: Any,
) -> None:
    people = edition_cast()
    kit.canonical(
        migrated_tenant.number, people, commit_version, _body(kit.FIXTURES / "negative.md")
    )
    client, _ = kit.reader(member_of, link_group, people, [Right.VIEW_CANONICAL], "negative")

    _export(client, people.document.number, format="pdf", view="canonical")
    job = kit.run_job(migrated_tenant.number, exports[0][1])

    assert job.state == "failed"
    assert "image-src" in job.failure_reason
    assert not (Path(settings.EXPORT_ROOT) / str(job.pk)).exists()


def test_writer_raises_on_unreachable_reference(tmp_path: Path) -> None:
    """The writer alone, no validator in front: a remote image, a missing image, an address
    outside the images — each stops the render, and no file is written."""
    from rendering.export import pdf

    def missing(path: str) -> bytes:
        raise KeyError(path)

    for html in (
        '<p>Текст <img src="https://example.org/remote.png"></p>',
        '<p>Текст <img src="images/missing.png"></p>',
        '<p>Текст <img src="attachments/1"></p>',
    ):
        target = tmp_path / "out.pdf"
        with pytest.raises(BaseException):  # noqa: B017, PT011 — weasyprint's fatal error
            pdf.write(html, target, stylesheets=[], read_image=missing)
        assert not target.exists()
        assert not list(tmp_path.iterdir())


def test_marked_export(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
    settings: Any,
) -> None:
    """Pending edits, marked against the last acceptance: an inserted sentence and a removed one
    marked in the HTML the PDF is made from, and the file's name carrying the marks."""
    from rendering.export import compose
    from rendering.models import ExportJob

    people = edition_cast()
    kit.canonical(migrated_tenant.number, people, commit_version, kit.THIRD)
    removed = "Реєстр заяв веде відповідальний виконавець."
    commit_version(people.document, people["a"], kit.FOURTH.replace(removed + "\n\n", ""), "edit")
    client, _ = kit.reader(member_of, link_group, people, [Right.VIEW_PENDING], "marked")

    _export(
        client,
        people.document.number,
        format="pdf",
        view="pending_edits",
        **{"changes-pending_edits": "marked"},
    )
    job = kit.run_job(migrated_tenant.number, exports[0][1])

    assert job.state == "done", job.failure_reason
    with schema_context(migrated_tenant.number):
        stored = ExportJob.objects.select_related("document", "version", "baseline_version").get(
            pk=job.pk
        )
        composed = compose.compose(stored, migrated_tenant.number, number="1.0-1")
    assert "<ins>Строк розгляду заяви становить десять днів.</ins>" in composed.html
    assert f"<del>{removed}</del>" in composed.html
    produced = Path(settings.EXPORT_ROOT) / job.artifact_ref
    assert produced.is_file()
    assert produced.name.endswith("_—_1.0-1_—_всі_неприйняті_правки-позначено.pdf"), produced.name


def test_the_writer_fetches_the_documents_own_images(tmp_path: Path) -> None:
    """An image under `images/` is fetched through the writer's fetcher, and only through it."""
    import base64

    from rendering.export import pdf

    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )
    asked: list[str] = []

    def read_image(path: str) -> bytes:
        asked.append(path)
        return png

    pdf.write('<p>Схема <img src="images/a.png" alt="Схема"></p>', tmp_path / "a.pdf",
              stylesheets=[], read_image=read_image)  # fmt: skip

    assert asked == ["images/a.png"]
    assert (tmp_path / "a.pdf").read_bytes().startswith(b"%PDF")


def test_title_page_says_what_the_text_is(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any, kit: Any
) -> None:
    """The canonical view carries its approval; any other view says it is not approved, to the
    edition it departs from (DL-0360)."""
    from types import SimpleNamespace

    from rendering.export.compose import _title_page

    people = edition_cast()
    kit.canonical(migrated_tenant.number, people, commit_version, kit.FIRST)
    with schema_context(migrated_tenant.number):
        canonical = _title_page(SimpleNamespace(document=people.document, view="canonical"), "T")
        pending = _title_page(SimpleNamespace(document=people.document, view="pending_edits"), "T")

    assert "Затверджено:" in canonical and "редакція 1.0" in canonical
    assert "@" not in canonical
    assert "Не затверджено — всі неприйняті правки до редакції 1.0" in pending


def test_a_formatting_change_prints_once(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
    settings: Any,
) -> None:
    """A sentence whose formatting alone changed prints as it now reads, never beside its earlier
    form."""
    from pypdf import PdfReader

    sentence = "Заяву на погодження подають письмово."
    people = edition_cast()
    kit.canonical(migrated_tenant.number, people, commit_version, kit.FIRST)
    bold = kit.FIRST.replace("подають письмово", "подають **письмово**")
    commit_version(people.document, people["a"], bold, "edit")
    client, _ = kit.reader(member_of, link_group, people, [Right.VIEW_PENDING], "style")
    _export(
        client,
        people.document.number,
        format="pdf",
        view="pending_edits",
        **{"changes-pending_edits": "marked"},
    )
    job = kit.run_job(migrated_tenant.number, exports[0][1])

    assert job.state == "done", job.failure_reason
    pages = PdfReader(str(Path(settings.EXPORT_ROOT) / job.artifact_ref)).pages
    text = re.sub(r"\s+", " ", " ".join(page.extract_text() for page in pages))
    assert text.count(sentence) == 1
