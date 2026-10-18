"""Parts in exports (DL-0193, DL-0207, DL-0208, DL-0165, DL-0444): appendices embedded after the
body and before the attachment list, numbered from 1 and never titled, or each a file of its own
in the zip; a marked export marking each appendix; *my edits* exporting the draft's appendices,
attachment list and files; every attachment in a zip checked against its listed hash.

People, groups and titles are synthetic examples; every text is invented English.
"""

from __future__ import annotations

import hashlib
import logging
import zipfile
from pathlib import Path
from typing import Any

import pytest

from access.rights import PARTS, Right
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

BODY = "# General provisions\n\nThe body's own sentence.\n"
ONE = "# Forms\n\nThe first appendix's sentence.\n"
TWO = "# Registers\n\nThe second appendix's sentence.\n"
TITLES = ["Synthetic forms", "Synthetic registers"]
LISTED = [{"number": n, "title": t} for n, t in enumerate(TITLES, 1)]


def entry(number: int, data: bytes, title: str) -> dict[str, Any]:
    return {
        "number": number,
        "title": title,
        "file_name": f"form-{number}.txt",
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }


def _canonical(tenant: int, people: Any, commit_version: Any, **parts: Any) -> Any:
    """`BODY` with `parts` committed, accepted and made canonical."""
    from editions import services as editions
    from review import services as review

    commit_version(people.document, people["a"], BODY, "edit", **parts)
    with schema_context(tenant):
        review.accept(people.document, people["r"])
        editions.freeze(people.document, people["p"], "Synthetic reason")
        return editions.make_canonical(people.document, people["p"])


def _two(tenant: int, people: Any, commit_version: Any, attachment: bool = True) -> Any:
    files: dict[str, bytes | None] = {
        "appendices/1.md": ONE.encode(),
        "appendices/2.md": TWO.encode(),
    }
    attachments = None
    if attachment:
        files["attachments/1"] = b"one"
        attachments = [entry(1, b"one", "Form one (example)")]
    return _canonical(
        tenant, people, commit_version, files=files, appendices=LISTED, attachments=attachments
    )


def _post(client: Any, of: Any, **choice: str) -> Any:
    return client.post(f"/document/{of.number}/export/", {"view": "canonical", **choice})


def _pdf_text(path: Path) -> str:
    from pypdf import PdfReader

    return " ".join(" ".join(page.extract_text() for page in PdfReader(str(path)).pages).split())


def test_embedded_appendices_follow_the_body(
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
    _two(migrated_tenant.number, people, commit_version)
    client, _ = kit.reader(member_of, link_group, people, [Right.VIEW_CANONICAL], "embedded")
    for fmt in ("pdf", "markdown"):
        response = _post(
            client,
            people.document,
            document="on",
            appendices="on",
            appendices_mode="embedded",
            attachments="on",
            format=fmt,
        )
        assert response.status_code == 302
        job = kit.run_job(migrated_tenant.number, exports[-1][1])
        assert job.state == "done", job.failure_reason
        assert job.appendices == "embedded"
        with zipfile.ZipFile(Path(settings.EXPORT_ROOT) / job.artifact_ref) as bundle:
            inner = next(n for n in bundle.namelist() if not n.startswith("вкладений"))
            if fmt == "pdf":
                (Path(settings.EXPORT_ROOT) / "inner.pdf").write_bytes(bundle.read(inner))
                text = _pdf_text(Path(settings.EXPORT_ROOT) / "inner.pdf")
            else:
                text = bundle.read(inner).decode("utf-8")
        at = [
            text.index(s)
            for s in (
                "The body's own sentence.",
                "1 Forms",
                "The first appendix's sentence.",
                "1 Registers",
                "The second appendix's sentence.",
                "Form one (example)",
            )
        ]
        assert at == sorted(at), (fmt, text)
        assert not any(title in text for title in TITLES), (fmt, text)


def test_separate_appendices_are_files_of_their_own(
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
    _two(migrated_tenant.number, people, commit_version, attachment=False)
    client, _ = kit.reader(member_of, link_group, people, [Right.VIEW_CANONICAL], "separate")
    # As the browser posts it: the document unchecked, so the mode's radios are disabled.
    response = _post(client, people.document, appendices="on", format="docx")
    assert response.status_code == 302
    job = kit.run_job(migrated_tenant.number, exports[-1][1])
    assert job.state == "done", job.failure_reason
    assert (job.appendices, job.include_document) == ("separate", False)
    with zipfile.ZipFile(Path(settings.EXPORT_ROOT) / job.artifact_ref) as bundle:
        assert sorted(bundle.namelist()) == [
            "додаток-1_—_Synthetic_forms.docx",
            "додаток-2_—_Synthetic_registers.docx",
        ]


def test_marked_exports_mark_appendices(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
) -> None:
    """Pending edits marked against the acceptance: appendix 1 changed, appendix 2 added since."""
    from rendering.export import compose
    from rendering.models import ExportJob

    people = edition_cast()
    number = migrated_tenant.number
    _canonical(
        number,
        people,
        commit_version,
        files={"appendices/1.md": ONE.encode()},
        appendices=LISTED[:1],
    )
    commit_version(
        people.document,
        people["a"],
        BODY,
        "edit",
        files={
            "appendices/1.md": ONE.replace("first", "reworded").encode(),
            "appendices/2.md": TWO.encode(),
        },
        appendices=LISTED,
    )
    client, _ = kit.reader(member_of, link_group, people, [Right.VIEW_PENDING], "marked")
    response = client.post(
        f"/document/{people.document.number}/export/",
        {
            "document": "on",
            "appendices": "on",
            "appendices_mode": "embedded",
            "format": "pdf",
            "view": "pending_edits",
            "changes-pending_edits": "marked",
        },
    )
    assert response.status_code == 302
    with schema_context(number):
        job = ExportJob.objects.get(pk=exports[-1][1])
        html = compose.compose(job, number, number="1.0-1").html
    first, second = html.split('<section class="appendix">')[1:]
    assert "<del>first</del>" in first and "<ins>reworded</ins>" in first
    assert "<del>" not in second and "<ins>" in second


def test_my_edits_export_the_drafts_appendices(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
    settings: Any,
) -> None:
    from editing import parts
    from editing.models import Draft

    number = migrated_tenant.number
    people = edition_cast()
    kit.canonical(number, people, commit_version, BODY)
    holder, user, membership = member_of("holder.synthetic@example.test")
    link_group(people.document, [Right.EDIT, Right.VIEW_PENDING, *PARTS], [membership], people["a"])
    assert holder.post(f"/document/{people.document.number}/edit/take/").status_code == 200
    with schema_context(number):
        made = parts.create_appendix(people.document, user, title="Synthetic draft appendix")
        draft = Draft.objects.get(hold__document=people.document, hold__released_at__isnull=True)
        draft.content = {
            **draft.content,
            parts.appendix_key(made): "# Draft\n\nOnly the draft holds this sentence.\n",
        }
        draft.save()
    response = holder.post(
        f"/document/{people.document.number}/export/",
        {
            "document": "on",
            "appendices": "on",
            "appendices_mode": "embedded",
            "format": "markdown",
            "view": "my_edits",
            "changes-my_edits": "clean",
        },
    )
    assert response.status_code == 302
    job = kit.run_job(number, exports[-1][1])
    assert job.state == "done", job.failure_reason
    text = (Path(settings.EXPORT_ROOT) / job.artifact_ref).read_text(encoding="utf-8")
    assert "Only the draft holds this sentence." in text


def test_a_missing_part_is_reported(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
) -> None:
    from django.utils.translation import gettext, override

    from rendering.models import ExportJob

    people = edition_cast()
    kit.canonical(migrated_tenant.number, people, commit_version, BODY)
    client, _ = kit.reader(member_of, link_group, people, [Right.VIEW_CANONICAL], "missing")
    body = client.get(f"/document/{people.document.number}/export/").content.decode()
    assert 'name="appendices"' not in body
    response = _post(client, people.document, document="on", appendices="on", format="pdf")
    assert response.status_code == 400
    with override("uk"):
        said = gettext("The chosen version has no appendices; untick them to export the rest.")
    assert said in response.content.decode()
    with schema_context(migrated_tenant.number):
        assert not ExportJob.objects.filter(document=people.document).exists()


def test_a_long_title_is_cut_in_the_file_name(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
    settings: Any,
) -> None:
    from rendering.export import names

    people = edition_cast()
    title = ("Synthetic long title " * 15)[:300]
    _canonical(
        migrated_tenant.number,
        people,
        commit_version,
        files={"appendices/1.md": ONE.encode()},
        appendices=[{"number": 1, "title": title}],
    )
    client, _ = kit.reader(member_of, link_group, people, [Right.VIEW_CANONICAL], "long")
    response = _post(
        client,
        people.document,
        document="on",
        appendices="on",
        appendices_mode="separate",
        format="pdf",
    )
    assert response.status_code == 302
    job = kit.run_job(migrated_tenant.number, exports[-1][1])
    assert job.state == "done", job.failure_reason
    with zipfile.ZipFile(Path(settings.EXPORT_ROOT) / job.artifact_ref) as bundle:
        assert names.part_name("додаток", 1, title[: names.TITLE_MOST]) + ".pdf" in (
            bundle.namelist()
        )


def test_my_edits_export_the_drafts_parts(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
    settings: Any,
) -> None:
    from editing import parts

    number = migrated_tenant.number
    people = edition_cast()
    _canonical(
        number,
        people,
        commit_version,
        files={"attachments/1": b"first", "attachments/2": b"second"},
        attachments=[
            entry(1, b"first", "First (example)"),
            entry(2, b"second", "Second (example)"),
        ],
    )
    holder, user, membership = member_of("holder.synthetic@example.test")
    link_group(people.document, [Right.EDIT, Right.VIEW_PENDING, *PARTS], [membership], people["a"])
    assert holder.post(f"/document/{people.document.number}/edit/take/").status_code == 200
    with schema_context(number):
        parts.delete_attachment(people.document, user, 1)
        new = parts.upload_attachment(
            people.document, user, title="Uploaded (example)", file_name="new.txt", data=b"new"
        )
    response = holder.post(
        f"/document/{people.document.number}/export/",
        {
            "document": "on",
            "attachments": "on",
            "format": "markdown",
            "view": "my_edits",
            "changes-my_edits": "clean",
        },
    )
    assert response.status_code == 302
    job = kit.run_job(number, exports[-1][1])
    assert job.state == "done", job.failure_reason
    with zipfile.ZipFile(Path(settings.EXPORT_ROOT) / job.artifact_ref) as bundle:
        files = {n: bundle.read(n) for n in bundle.namelist()}
    document = next(v.decode() for n, v in files.items() if n.endswith(".md"))
    assert "Uploaded (example)" in document and "Second (example)" in document
    assert "First (example)" not in document
    attached = {n: v for n, v in files.items() if not n.endswith(".md")}
    assert attached == {
        "вкладений_файл-2_—_form-2.txt": b"second",
        f"вкладений_файл-{new}_—_new.txt": b"new",
    }


def test_a_mismatched_attachment_fails_the_zip(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
    settings: Any,
    caplog: Any,
) -> None:
    number = migrated_tenant.number
    people = edition_cast()
    kit.canonical(number, people, commit_version, BODY)
    commit_version(
        people.document,
        people["a"],
        BODY,
        "edit",
        files={"attachments/1": b"altered bytes"},
        attachments=[entry(1, b"the listed bytes", "Form one (example)")],
    )
    client, _ = kit.reader(member_of, link_group, people, [Right.VIEW_PENDING], "tampered")
    response = client.post(
        f"/document/{people.document.number}/export/",
        {
            "document": "on",
            "attachments": "on",
            "format": "pdf",
            "view": "pending_edits",
            "changes-pending_edits": "clean",
        },
    )
    assert response.status_code == 302
    with caplog.at_level(logging.ERROR):
        job = kit.run_job(number, exports[-1][1])
    assert job.state == "failed" and job.failure_reason
    assert any("does not match its listed hash" in r.getMessage() for r in caplog.records)
    assert not (Path(settings.EXPORT_ROOT) / str(job.pk)).exists()


def test_appendices_alone_carry_only_their_own_images(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
    pictures: Any,
    settings: Any,
) -> None:
    """Appendices exported without the document: the body's image is in no exported text, so it
    is neither read nor zipped."""
    people = edition_cast()
    plan = pictures.make(7)
    _canonical(
        migrated_tenant.number,
        people,
        commit_version,
        files={plan.path: plan.data, "appendices/1.md": ONE.encode()},
        appendices=LISTED[:1],
    )
    commit_version(people.document, people["a"], BODY + plan.paragraph, "edit")
    client, _ = kit.reader(member_of, link_group, people, [Right.VIEW_PENDING], "alone")
    response = client.post(
        f"/document/{people.document.number}/export/",
        {"appendices": "on", "format": "markdown", "view": "pending_edits"},
    )
    assert response.status_code == 302
    job = kit.run_job(migrated_tenant.number, exports[-1][1])
    assert job.state == "done", job.failure_reason
    with zipfile.ZipFile(Path(settings.EXPORT_ROOT) / job.artifact_ref) as bundle:
        assert bundle.namelist() == ["додаток-1_—_Synthetic_forms.md"]


def test_a_refusal_without_the_document_names_what_remains(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
) -> None:
    """Appendices asked of a version without them, beside its attachments and without the
    document: the sentence names what is left, not the document."""
    from django.utils.translation import gettext, override

    people = edition_cast()
    _canonical(
        migrated_tenant.number,
        people,
        commit_version,
        files={"attachments/1": b"one"},
        attachments=[entry(1, b"one", "Form one (example)")],
    )
    client, _ = kit.reader(member_of, link_group, people, [Right.VIEW_CANONICAL], "remains")
    response = _post(client, people.document, appendices="on", attachments="on", format="pdf")
    assert response.status_code == 400
    with override("uk"):
        said = gettext("The chosen version has no appendices; untick them to export the rest.")
    assert said in response.content.decode()


def test_a_draft_changed_while_its_export_is_made_fails_it(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
    settings: Any,
    monkeypatch: Any,
) -> None:
    """The holder replaces an attachment between the export's composing and its zip: the zip
    would pair the new file with the old list's name and hash, so the job fails instead."""
    from editing import parts
    from rendering.export import job as export_job

    number = migrated_tenant.number
    people = edition_cast()
    _canonical(
        number,
        people,
        commit_version,
        files={"attachments/1": b"first"},
        attachments=[entry(1, b"first", "First (example)")],
    )
    holder, user, membership = member_of("holder.synthetic@example.test")
    link_group(people.document, [Right.EDIT, Right.VIEW_PENDING, *PARTS], [membership], people["a"])
    assert holder.post(f"/document/{people.document.number}/edit/take/").status_code == 200
    response = holder.post(
        f"/document/{people.document.number}/export/",
        {
            "document": "on",
            "attachments": "on",
            "format": "markdown",
            "view": "my_edits",
            "changes-my_edits": "clean",
        },
    )
    assert response.status_code == 302
    written = export_job._write_document

    def replaced_meanwhile(*args: Any, **kwargs: Any) -> None:
        written(*args, **kwargs)
        parts.replace_attachment(
            people.document, user, 1, file_name="other.txt", data=b"other bytes"
        )

    monkeypatch.setattr(export_job, "_write_document", replaced_meanwhile)
    job = kit.run_job(number, exports[-1][1])
    assert job.state == "failed" and job.failure_reason
    assert not (Path(settings.EXPORT_ROOT) / str(job.pk)).exists()


def test_an_appendices_only_export_without_attachments_names_the_rest(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
) -> None:
    """Attachments asked of a version without them, beside its appendices and without the
    document: the sentence names what is left, not the document."""
    from django.utils.translation import gettext, override

    from editions import services as editions
    from review import services as review

    number = migrated_tenant.number
    people = edition_cast()
    # An edition with an attachment, so the dialog offers attachments at all ...
    _canonical(
        number,
        people,
        commit_version,
        files={"attachments/1": b"one"},
        attachments=[entry(1, b"one", "Form one (example)")],
    )
    # ... and a pending version with appendices and none.
    commit_version(
        people.document,
        people["a"],
        BODY,
        "edit",
        files={"appendices/1.md": ONE.encode(), "attachments/1": None},
        appendices=LISTED[:1],
        attachments=[],
    )
    assert editions and review
    client, _ = kit.reader(
        member_of, link_group, people, [Right.VIEW_CANONICAL, Right.VIEW_PENDING], "rest"
    )
    response = client.post(
        f"/document/{people.document.number}/export/",
        {"appendices": "on", "attachments": "on", "format": "pdf", "view": "pending_edits"},
    )
    assert response.status_code == 400
    with override("uk"):
        said = gettext("The chosen version has no attachments; untick them to export the rest.")
    assert said in response.content.decode()
