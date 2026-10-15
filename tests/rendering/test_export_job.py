"""An export job's life (DL-0172, DL-0193, `data-model.md` `EXPORT_JOB`): a done job's file
downloaded under its name, then swept after a day with its row kept; the Markdown export's file;
a zip with the attachments; a job delivered twice running once; a job left queued queued again by
the reconciler; a right lost failing the job.

People, groups and titles are synthetic examples; every text is invented.
"""

from __future__ import annotations

import os
import zipfile
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from django.utils import timezone

from access.rights import Right
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]


def _asked(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    kit: Any,
    body: str,
    **choice: str,
) -> tuple[Any, Any]:
    people = edition_cast()
    kit.canonical(migrated_tenant.number, people, commit_version, body)
    client, _ = kit.reader(member_of, link_group, people, [Right.VIEW_CANONICAL], "job")
    response = client.post(
        f"/document/{people.document.number}/export/",
        {"document": "on", "view": "canonical", **choice},
    )
    assert response.status_code == 302
    return people, client


def test_download_and_expiry(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
    settings: Any,
) -> None:
    from rendering.export.job import sweep
    from rendering.models import ExportJob

    people, client = _asked(
        migrated_tenant, edition_cast, member_of, link_group, commit_version, kit, kit.FIRST,
        format="pdf",
    )  # fmt: skip
    job = kit.run_job(migrated_tenant.number, exports[0][1])
    route = f"/document/{people.document.number}/export/{job.pk}/"

    status = client.get(route).content.decode()
    download = client.get(f"{route}download/")

    assert f"{route}download/" in status
    assert download.status_code == 200
    name = Path(job.artifact_ref).name
    assert name.endswith(".pdf") and "1.0" in name
    assert download["Content-Disposition"].startswith("attachment;")
    assert b"".join(download.streaming_content).startswith(b"%PDF")  # type: ignore[attr-defined]

    folder = Path(settings.EXPORT_ROOT) / str(job.pk)
    old = (timezone.now() - timedelta(hours=25)).timestamp()
    os.utime(folder, (old, old))
    assert sweep() == 1

    assert not folder.exists()
    assert client.get(f"{route}download/").status_code == 404
    with schema_context(migrated_tenant.number):
        assert ExportJob.objects.filter(pk=job.pk, state="done").exists()


def test_markdown_export_is_the_source_view(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
    settings: Any,
) -> None:
    sample = (kit.FIXTURES / "conformance.md").read_text(encoding="utf-8")
    _asked(
        migrated_tenant, edition_cast, member_of, link_group, commit_version, kit, sample,
        format="markdown",
    )  # fmt: skip
    job = kit.run_job(migrated_tenant.number, exports[0][1])

    assert job.state == "done", job.failure_reason
    produced = (Path(settings.EXPORT_ROOT) / job.artifact_ref).read_text(encoding="utf-8")
    from rendering.export.markdown import number_headings

    # The source view with its headings numbered (DL-0363); `number_headings` has its own cases.
    expected = (kit.FIXTURES / "conformance.export.md").read_text(encoding="utf-8")
    assert produced == number_headings(expected)
    assert not produced.startswith("---")


def test_a_job_runs_once(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
) -> None:
    from rendering.export import job as jobs

    _asked(
        migrated_tenant, edition_cast, member_of, link_group, commit_version, kit, kit.FIRST,
        format="markdown",
    )  # fmt: skip
    first = kit.run_job(migrated_tenant.number, exports[0][1])
    with schema_context(migrated_tenant.number):
        again = jobs.run(exports[0][1], migrated_tenant.number)

    assert first.state == "done" and again == "done"


def test_the_reconciler_queues_a_stuck_export_again(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
) -> None:
    from documents import reconcile
    from rendering.models import ExportJob

    _asked(
        migrated_tenant, edition_cast, member_of, link_group, commit_version, kit, kit.FIRST,
        format="pdf",
    )  # fmt: skip
    with schema_context(migrated_tenant.number):
        ExportJob.objects.update(created_at=timezone.now() - timedelta(minutes=30))
    exports.clear()

    reported = reconcile.run(tenant=migrated_tenant.number)
    repaired = reconcile.run(tenant=migrated_tenant.number, repair=True)

    assert [f.kind for f in reported if f.kind == reconcile.EXPORT_STUCK] == ["export_stuck"]
    assert exports and exports[0][0] == migrated_tenant.number
    assert any(f.kind == reconcile.EXPORT_STUCK and f.repaired for f in repaired)


def test_attachments_go_in_one_zip(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
    settings: Any,
) -> None:
    """A document whose canonical version lists an attachment: the export is one zip holding the
    document and the file as stored, the attachment list at the document's end."""
    from documents import bundle, gitstore, services
    from documents.identity import identity_for
    from documents.locks import document_lock
    from editions import services as editions
    from review import services as review

    number = migrated_tenant.number
    people = edition_cast()
    document = people.document
    commit_version(document, people["a"], kit.FIRST, "edit")
    data = b"Synthetic list of time limits.\n"
    import hashlib

    with schema_context(number):
        repo = gitstore.open_repository(number, document.number)
        with document_lock(number, document.number):
            head = gitstore.head(repo)
            assert head is not None
            frontmatter, body = bundle.parse(gitstore.read(repo, "document.md", head).decode())
            frontmatter.attachments = [
                {
                    "number": 1,
                    "title": "List of time limits",
                    "file_name": "time-limits.txt",
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "bytes": len(data),
                }
            ]
            sha = gitstore.commit(
                repo,
                {
                    "document.md": bundle.render(frontmatter, body).encode(),
                    "attachments/1": data,
                },
                identity_for(people["a"]),
                "Synthetic edit with a file",
                gitstore.Kind.EDIT,
            )
            services.derive_version(document, gitstore.commit_at(repo, sha), people["a"])
        review.accept(document, people["r"])
        editions.freeze(document, people["p"], "Synthetic reason")
        editions.make_canonical(document, people["p"])
    client, _ = kit.reader(member_of, link_group, people, [Right.VIEW_CANONICAL], "zip")

    response = client.post(
        f"/document/{document.number}/export/",
        {"document": "on", "attachments": "on", "format": "markdown", "view": "canonical"},
    )
    assert response.status_code == 302
    job = kit.run_job(number, exports[0][1])

    assert job.state == "done", job.failure_reason
    path = Path(settings.EXPORT_ROOT) / job.artifact_ref
    assert path.name.endswith("_—_1.0_—_канонічна_версія.zip"), path.name
    with zipfile.ZipFile(path) as bundle_file:
        assert sorted(bundle_file.namelist()) == [
            "вкладений_файл-1_—_time-limits.txt",
            "документ.md",
        ]
        assert bundle_file.read("вкладений_файл-1_—_time-limits.txt") == data
        assert "time-limits.txt" in bundle_file.read("документ.md").decode()


def test_a_right_lost_before_the_run_fails_the_job(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
) -> None:
    """A reader of pending work who loses the right after asking: the job fails and serves
    nothing."""
    from access.models import DocumentGroup

    people = edition_cast()
    kit.canonical(migrated_tenant.number, people, commit_version, kit.FIRST)
    commit_version(people.document, people["a"], kit.SECOND, "edit")
    client, leaver = kit.reader(member_of, link_group, people, [Right.VIEW_PENDING], "leaver")
    client.post(
        f"/document/{people.document.number}/export/",
        {"document": "on", "format": "markdown", "view": "pending_edits"},
    )
    with schema_context(migrated_tenant.number):
        links = DocumentGroup.objects.filter(
            document=people.document, group__members__membership__user=leaver
        )
        assert links.exists()
        links.delete()

    job = kit.run_job(migrated_tenant.number, exports[0][1])

    assert job.state == "failed"


def test_one_queued_export_per_person_and_document(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
) -> None:
    people, client = _asked(
        migrated_tenant, edition_cast, member_of, link_group, commit_version, kit, kit.FIRST,
        format="pdf",
    )  # fmt: skip

    again = client.post(
        f"/document/{people.document.number}/export/",
        {"document": "on", "format": "pdf", "view": "canonical"},
    )

    assert again.status_code == 400
    assert len(exports) == 1


def test_a_job_delivered_twice_at_once_runs_once(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
) -> None:
    """A second delivery while the first holds the job leaves it alone."""
    import threading

    from django.db import connection

    from rendering.export import job as jobs
    from rendering.models import ExportJob

    _asked(
        migrated_tenant, edition_cast, member_of, link_group, commit_version, kit, kit.FIRST,
        format="markdown",
    )  # fmt: skip
    job_id = exports[0][1]
    second: list[Any] = []
    held = threading.Event()
    release = threading.Event()
    real = jobs.compose.compose

    def slow(*args: Any, **kwargs: Any) -> Any:
        held.set()
        release.wait(10)
        return real(*args, **kwargs)

    def deliver_again() -> None:
        held.wait(10)
        try:
            with schema_context(migrated_tenant.number):
                second.append(jobs.run(job_id, migrated_tenant.number))
        finally:
            connection.close()
            release.set()

    jobs.compose.compose = slow  # type: ignore[assignment]
    try:
        other = threading.Thread(target=deliver_again)
        other.start()
        first = kit.run_job(migrated_tenant.number, job_id)
        other.join(20)
    finally:
        jobs.compose.compose = real  # type: ignore[assignment]

    assert first.state == "done"
    assert second == ["queued"]
    with schema_context(migrated_tenant.number):
        assert ExportJob.objects.get(pk=job_id).state == "done"


def test_the_attachment_list_goes_with_the_document_even_without_the_files(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
    settings: Any,
) -> None:
    """The list of a version's attachments is generated into the document whenever the version
    has any (DL-0172); the checkbox adds the files, as one zip."""
    from editions import services as editions
    from review import services as review

    number = migrated_tenant.number
    people = edition_cast()
    kit.attach(number, people, kit.FIRST, b"Synthetic list.\n")
    with schema_context(number):
        review.accept(people.document, people["r"])
        editions.freeze(people.document, people["p"], "Synthetic reason")
        editions.make_canonical(people.document, people["p"])
    client, _ = kit.reader(member_of, link_group, people, [Right.VIEW_CANONICAL], "list")

    client.post(
        f"/document/{people.document.number}/export/",
        {"document": "on", "format": "markdown", "view": "canonical"},
    )
    job = kit.run_job(number, exports[0][1])

    assert job.state == "done", job.failure_reason
    produced = Path(settings.EXPORT_ROOT) / job.artifact_ref
    assert produced.suffix == ".md"
    assert "time-limits.txt" in produced.read_text(encoding="utf-8")


def test_attachments_asked_of_a_version_without_them_are_refused(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
) -> None:
    """Canonical 1.0 has no attachment, accepted 1.1 has one: attachments with the canonical view
    are reported as not in that version (DL-0208), never dropped silently."""
    from review import services as review

    number = migrated_tenant.number
    people = edition_cast()
    kit.canonical(number, people, commit_version, kit.FIRST)
    kit.attach(number, people, kit.SECOND, b"x")
    with schema_context(number):
        review.accept(people.document, people["r"])
    client, _ = kit.reader(member_of, link_group, people, [Right.VIEW_ACCEPTED], "parts")

    refused = client.post(
        f"/document/{people.document.number}/export/",
        {"document": "on", "attachments": "on", "format": "pdf", "view": "canonical"},
    )

    assert refused.status_code == 400 and exports == []


def test_a_done_export_stays_after_its_run_is_accepted(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
) -> None:
    """Pending edits exported, then accepted: the right still held, the file still served."""
    from review import services as review

    people = edition_cast()
    kit.canonical(migrated_tenant.number, people, commit_version, kit.FIRST)
    commit_version(people.document, people["a"], kit.SECOND, "edit")
    client, _ = kit.reader(member_of, link_group, people, [Right.VIEW_PENDING], "stays")
    client.post(
        f"/document/{people.document.number}/export/",
        {"document": "on", "format": "markdown", "view": "pending_edits"},
    )
    job = kit.run_job(migrated_tenant.number, exports[0][1])
    with schema_context(migrated_tenant.number):
        review.accept(people.document, people["r"])

    download = client.get(f"/document/{people.document.number}/export/{job.pk}/download/")

    assert job.state == "done" and download.status_code == 200


def test_an_abandoned_export_is_failed_and_its_person_may_ask_again(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
) -> None:
    from audit.models import AuditEvent
    from documents import reconcile
    from rendering.models import ExportJob

    people, client = _asked(
        migrated_tenant, edition_cast, member_of, link_group, commit_version, kit, kit.FIRST,
        format="pdf",
    )  # fmt: skip
    with schema_context(migrated_tenant.number):
        ExportJob.objects.update(created_at=timezone.now() - timedelta(hours=2))
    exports.clear()

    found = reconcile.run(tenant=migrated_tenant.number, repair=True)
    again = client.post(
        f"/document/{people.document.number}/export/",
        {"document": "on", "format": "pdf", "view": "canonical"},
    )

    assert [f.kind for f in found if f.kind.startswith("export")] == ["export_abandoned"]
    with schema_context(migrated_tenant.number):
        assert ExportJob.objects.filter(state="failed").count() == 1
    assert AuditEvent.objects.filter(action="reconcile.export_abandoned").exists()
    assert again.status_code == 302


def test_a_one_document_reconcile_touches_its_exports_only(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
) -> None:
    from documents import reconcile
    from rendering.models import ExportJob

    people, _ = _asked(
        migrated_tenant, edition_cast, member_of, link_group, commit_version, kit, kit.FIRST,
        format="pdf",
    )  # fmt: skip
    with schema_context(migrated_tenant.number):
        ExportJob.objects.update(created_at=timezone.now() - timedelta(minutes=30))

    other = reconcile.run(tenant=migrated_tenant.number, document=people.document.number + 100)
    own = reconcile.run(tenant=migrated_tenant.number, document=people.document.number)

    assert not [f for f in other if f.kind == reconcile.EXPORT_STUCK]
    assert [f.kind for f in own if f.kind == reconcile.EXPORT_STUCK] == ["export_stuck"]


def test_attachments_alone_are_exported_as_the_dialog_posts_them(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
    settings: Any,
) -> None:
    """With *Document* unticked the dialog's script disables *Format*, and a disabled control is
    not posted: the request carries no format, and the attachments are exported all the same."""
    number = migrated_tenant.number
    people = edition_cast()
    kit.canonical(number, people, commit_version, kit.FIRST)
    data = b"A synthetic row of the list.\n"
    kit.attach(number, people, kit.SECOND, data)

    response = people.clients["r"].post(
        f"/document/{people.document.number}/export/",
        {"attachments": "on", "view": "pending_edits"},
    )

    assert response.status_code == 302
    job = kit.run_job(number, exports[0][1])
    assert job.state == "done", job.failure_reason
    with zipfile.ZipFile(Path(settings.EXPORT_ROOT) / job.artifact_ref) as bundle_file:
        assert bundle_file.namelist() == ["вкладений_файл-1_—_time-limits.txt"]
        assert bundle_file.read("вкладений_файл-1_—_time-limits.txt") == data


@pytest.mark.budget
def test_the_reconciler_passes_over_an_abandoned_job_a_render_holds(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
) -> None:
    """A job an hour old that a render holds is being made, not abandoned: the repair leaves it
    at once rather than wait for the render's lock."""
    import threading
    import time

    from django.db import connection, transaction

    from documents import reconcile
    from rendering.models import ExportJob

    _asked(
        migrated_tenant, edition_cast, member_of, link_group, commit_version, kit, kit.FIRST,
        format="pdf",
    )  # fmt: skip
    job_id = exports[0][1]
    with schema_context(migrated_tenant.number):
        ExportJob.objects.update(created_at=timezone.now() - timedelta(hours=2))
    held = threading.Event()
    release = threading.Event()

    def render_holds() -> None:
        try:
            with schema_context(migrated_tenant.number), transaction.atomic():
                ExportJob.objects.select_for_update().get(pk=job_id)
                held.set()
                release.wait(15)
        finally:
            connection.close()

    other = threading.Thread(target=render_holds)
    other.start()
    try:
        assert held.wait(10)
        started = time.monotonic()
        found = reconcile.run(tenant=migrated_tenant.number, repair=True)
        took = time.monotonic() - started
    finally:
        release.set()
        other.join(20)

    assert took < 5
    assert [f.kind for f in found if f.kind.startswith("export")] == []
    with schema_context(migrated_tenant.number):
        assert ExportJob.objects.get(pk=job_id).state == "queued"
