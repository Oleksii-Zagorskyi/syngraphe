"""The PDF export (ADR-0013, DL-0182): the conformance sample with its outline, every label, the
header and the page numbers; a remote reference failing the job by name and writing nothing; the
writer refusing every fetch but the document's own images; a marked export; the images a version
shows embedded, an oriented photograph upright.

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
        # No page carries a header (DL-0362): the page number at its foot alone.
        lines = [line.strip() for line in page.extract_text().splitlines()]
        flat = re.sub(r"\s+", " ", " ".join(lines))
        assert f"{title} 1.0 — {stance}" not in flat, n
        assert str(n) in lines, n
    # The sample's image is no name the platform gives, so it stays its description: nothing is
    # fetched.
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
    removed = "The register of requests is kept by the officer in charge."
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
    assert "<ins>A request is considered within ten days.</ins>" in composed.html
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
        canonical = _title_page(
            SimpleNamespace(document=people.document, view="canonical"),
            "T",
            "1.0",
        )
        pending = _title_page(
            SimpleNamespace(document=people.document, view="pending_edits"),
            "T",
            "1.0-1",
        )

    assert "Затверджено:" in canonical and "редакція 1.0" in canonical
    assert "@" not in canonical
    assert "Не затверджено — всі неприйняті правки до редакції 1.0" in pending


def test_the_title_page_names_the_exported_edition(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any, kit: Any
) -> None:
    """A canonical export of edition 1.0 run after edition 2.0 exists — queued before it, and still
    permitted — names 1.0 on its title page, as its header and file name do; a view departing from
    1.0 names 1.0."""
    from types import SimpleNamespace

    from rendering.export.compose import _title_page

    people = edition_cast()
    kit.canonical(migrated_tenant.number, people, commit_version, kit.FIRST)
    kit.canonical(migrated_tenant.number, people, commit_version, kit.SECOND)
    with schema_context(migrated_tenant.number):
        canonical = _title_page(
            SimpleNamespace(document=people.document, view="canonical"), "T", "1.0"
        )
        accepted = _title_page(
            SimpleNamespace(document=people.document, view="accepted"), "T", "1.1"
        )

    assert "редакція 1.0" in canonical and "2.0" not in canonical
    assert "редакції 1.0" in accepted and "2.0" not in accepted


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
    form, and marked as a change of formatting."""
    from pypdf import PdfReader

    sentence = "A request for approval is made in writing."
    people = edition_cast()
    kit.canonical(migrated_tenant.number, people, commit_version, kit.FIRST)
    bold = kit.FIRST.replace("made in writing", "made in **writing**")
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
    # Marked by its colour alone: the words that name the change are the screen's (DL-0363).
    assert "лише форматування" not in text


def exported(
    tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
    pictures: Any,
    shown: list[Any],
    fmt: str,
) -> Path:
    """A canonical version showing `shown`, exported in `fmt` by a reader of it; the file."""
    from django.conf import settings

    people = edition_cast()
    body = kit.FIRST + "".join(p.paragraph for p in shown)
    pictures.canonical_with(
        tenant.number, people, commit_version, body, {p.path: p.data for p in shown}
    )
    client, _ = kit.reader(member_of, link_group, people, [Right.VIEW_CANONICAL], fmt)
    response = client.post(
        f"/document/{people.document.number}/export/",
        {"document": "on", "format": fmt, "view": "canonical"},
    )
    assert response.status_code == 302
    job = kit.run_job(tenant.number, exports[-1][1])
    assert job.state == "done", job.failure_reason
    return Path(settings.EXPORT_ROOT) / job.artifact_ref


def placed_images(path: Path) -> list[tuple[float, float]]:
    """Each image the PDF draws, as the width and height it is laid out at."""
    from pypdf import PdfReader

    found: list[tuple[float, float]] = []

    def drawn(names: set[str]) -> Any:
        matrix: list[float] = []

        def visit(operator: bytes, operands: Any, *_: Any) -> None:
            nonlocal matrix
            if operator == b"cm":
                matrix = [float(v) for v in operands]
            elif operator == b"Do" and operands and operands[0] in names and matrix:
                found.append((abs(matrix[0]) + abs(matrix[2]), abs(matrix[1]) + abs(matrix[3])))

        return visit

    for page in PdfReader(str(path)).pages:
        names = set((page.get("/Resources") or {}).get("/XObject", {}).keys())
        page.extract_text(visitor_operand_before=drawn(names))
    return found


def test_pdf_embeds_the_images(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
    pictures: Any,
) -> None:
    shown = [pictures.make(1), pictures.make(2)]
    path = exported(
        migrated_tenant,
        edition_cast,
        member_of,
        link_group,
        commit_version,
        exports,
        kit,
        pictures,
        shown,
        "pdf",
    )
    assert len(placed_images(path)) == 2


def test_an_oriented_photograph_in_a_pdf(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
    pictures: Any,
) -> None:
    """A JPEG keeps its orientation alone (DL-0472), and the PDF stands it upright."""
    photo = pictures.make(3, "jpeg", width=40, height=20, orientation=6)
    path = exported(
        migrated_tenant,
        edition_cast,
        member_of,
        link_group,
        commit_version,
        exports,
        kit,
        pictures,
        [photo],
        "pdf",
    )
    [(width, height)] = placed_images(path)
    assert height > width


def marked_with_a_changed_image(
    tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
    pictures: Any,
    fmt: str,
) -> Path:
    """An edition showing one image, pending edits replacing it — the old one gone from the
    version's tree — exported marked; the file."""
    from django.conf import settings

    people = edition_cast()
    old, new = pictures.make(7), pictures.make(8)
    pictures.canonical_with(
        tenant.number, people, commit_version, kit.FIRST + old.paragraph, {old.path: old.data}
    )
    commit_version(
        people.document,
        people["a"],
        kit.FIRST + new.paragraph,
        "edit",
        files={old.path: None, new.path: new.data},
    )
    client, _ = kit.reader(member_of, link_group, people, [Right.VIEW_PENDING], "marked-image")
    response = client.post(
        f"/document/{people.document.number}/export/",
        {
            "document": "on",
            "format": fmt,
            "view": "pending_edits",
            "changes-pending_edits": "marked",
        },
    )
    assert response.status_code == 302
    job = kit.run_job(tenant.number, exports[-1][1])
    assert job.state == "done", job.failure_reason
    return Path(settings.EXPORT_ROOT) / job.artifact_ref


def test_a_marked_pdf_carries_both_images(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
    pictures: Any,
) -> None:
    """The pair's before side read at the baseline, the image the version no longer holds; no
    full-size copy in a file."""
    path = marked_with_a_changed_image(
        migrated_tenant,
        edition_cast,
        member_of,
        link_group,
        commit_version,
        exports,
        kit,
        pictures,
        "pdf",
    )
    assert len(placed_images(path)) == 2
