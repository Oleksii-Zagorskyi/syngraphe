"""*Export a sample PDF* and *Export a sample Word file* (DL-0466): the built-in invented sample,
in the interface's language, rendered with the stylesheet as it stands in the styles page's box —
checked first, never applied — one at a time per organisation; written before it is queued and
done only when the worker says so; its file kept for a day.

People and stylesheets are synthetic examples."""

from __future__ import annotations

import re
import threading
import zipfile
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from django.utils import timezone

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

PAGE = "/administration/tenant/styles/"
ASK = "/administration/tenant/styles/sample/"
BOX = 'h1 { color: #123456; font-family: "DejaVu Serif" }\n'


@pytest.fixture(autouse=True)
def english(settings: Any) -> None:
    settings.LANGUAGE_CODE = "en"


@pytest.fixture
def admin(migrated_tenant: Any, member_of: Any) -> Any:
    client, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    return client


def _samples(migrated_tenant: Any) -> list[Any]:
    from rendering.models import SampleExport

    with schema_context(migrated_tenant.number):
        return list(SampleExport.objects.order_by("created_at"))


def _run(migrated_tenant: Any, sample: Any) -> Any:
    from rendering import sample as samples

    with schema_context(migrated_tenant.number):
        samples.run(sample.pk, migrated_tenant.number)
        sample.refresh_from_db()
    return sample


def _ask(admin: Any, fmt: str = "pdf", text: str = BOX) -> Any:
    return admin.post(ASK, {"text": text, "format": fmt})


def test_a_sample_pdf_renders_the_box(
    migrated_tenant: Any, admin: Any, exports: Any, queued_samples: list[Any], settings: Any
) -> None:
    import json

    from pypdf import PdfReader

    from audit.models import AuditEvent
    from documents.models import DocumentTemplate
    from rendering.models import Stylesheet

    # The organisation's own layout: the number before the title, the text, the approval.
    layout = {"items": ["number", "title", "text", "approval"], "align": "centre"}
    with schema_context(migrated_tenant.number):
        DocumentTemplate.objects.update(title_page_layout=json.dumps(layout))
    answer = _ask(admin)

    (sample,) = _samples(migrated_tenant)
    assert answer.status_code == 303
    assert answer["Location"] == f"{PAGE}?sample={sample.pk}"
    assert (sample.state, sample.format, sample.stylesheet, sample.language) == (
        "queued",
        "pdf",
        BOX,
        "en",
    )
    assert queued_samples == [(migrated_tenant.number, str(sample.pk))]
    (event,) = AuditEvent.objects.filter(action="stylesheet.sample_requested")
    assert event.after == {"format": "pdf", "language": "en"} and event.object_id == sample.pk
    drawn = admin.get(answer["Location"]).content.decode()
    assert "being made" in drawn
    done = _run(migrated_tenant, sample)
    assert done.state == "done"
    pages = PdfReader(str(Path(settings.EXPORT_ROOT) / done.artifact_ref)).pages
    first = [line.strip() for line in pages[0].extract_text().splitlines() if line.strip()]
    assert first[:4] == [
        "#1",
        "An example policy",
        "Register entry: EX-0 (example)",
        "A second line of its own text",
    ]
    assert first[4].startswith("Approved")
    assert "Attachment list" in pages[-1].extract_text()
    with schema_context(migrated_tenant.number):
        # Never applied: the organisation's row is as it was.
        assert Stylesheet.objects.get().text == ""


def test_a_sample_word_file_uses_the_derived_styles(
    migrated_tenant: Any, admin: Any, exports: Any, queued_samples: list[Any], settings: Any
) -> None:
    _ask(admin, "docx")
    (sample,) = _samples(migrated_tenant)

    done = _run(migrated_tenant, sample)

    assert done.state == "done"
    with zipfile.ZipFile(Path(settings.EXPORT_ROOT) / done.artifact_ref) as produced:
        styles = produced.read("word/styles.xml").decode()
    heading = re.search(r'<w:style\b[^>]*w:styleId="Heading1".*?</w:style>', styles, re.DOTALL)
    assert heading and re.search(r'<w:color w:val="123456" ?/>', heading.group(0))


def test_one_sample_at_a_time(
    migrated_tenant: Any, admin: Any, exports: Any, queued_samples: list[Any]
) -> None:
    from django.db import connection, transaction

    from rendering.models import SampleExport

    assert _ask(admin).status_code == 303
    second = _ask(admin)
    assert second.status_code == 409
    assert "A sample is being made; wait for it." in second.content.decode()
    assert len(_samples(migrated_tenant)) == 1

    # Asked 31 minutes ago and never taken: failed, and the next one queued.
    with schema_context(migrated_tenant.number):
        SampleExport.objects.update(created_at=timezone.now() - timedelta(minutes=31))
    assert _ask(admin).status_code == 303
    old, new = _samples(migrated_tenant)
    assert (old.state, old.failure_reason) == ("failed", "The sample was not made in time.")
    assert new.state == "queued"

    # One a worker holds, however old: left as it is, and the request does not wait for it.
    with schema_context(migrated_tenant.number):
        SampleExport.objects.filter(pk=new.pk).update(
            created_at=timezone.now() - timedelta(minutes=40)
        )
    held, release = threading.Event(), threading.Event()

    def worker() -> None:
        try:
            with schema_context(migrated_tenant.number), transaction.atomic():
                SampleExport.objects.select_for_update().get(pk=new.pk)
                held.set()
                release.wait(15)
        finally:
            connection.close()

    other = threading.Thread(target=worker)
    other.start()
    try:
        assert held.wait(10)
        with connection.cursor() as cursor:
            cursor.execute("SET lock_timeout = '2s'")
        answer = _ask(admin)
    finally:
        release.set()
        other.join(20)
        with connection.cursor() as cursor:
            cursor.execute("SET lock_timeout = 0")

    assert answer.status_code == 409
    with schema_context(migrated_tenant.number):
        new.refresh_from_db()
    assert new.state == "queued"
    assert len(_samples(migrated_tenant)) == 2


def test_a_refused_box_queues_nothing(
    migrated_tenant: Any, admin: Any, exports: Any, queued_samples: list[Any]
) -> None:
    import html

    answer = _ask(admin, text="h1 { color: #123 }\nh2 { background: url(x.png) }\n")
    unknown = _ask(admin, fmt="markdown")

    assert answer.status_code == 400
    assert "Line 2: background fetches from outside the platform." in html.unescape(
        answer.content.decode()
    )
    assert unknown.status_code == 400
    assert _samples(migrated_tenant) == [] and queued_samples == []


def test_a_sample_that_cannot_be_queued_fails(
    migrated_tenant: Any, admin: Any, exports: Any, monkeypatch: Any
) -> None:
    def refused(*args: Any) -> None:
        raise ConnectionError("the broker refused the synthetic task")

    monkeypatch.setattr("rendering.tasks.render_sample.delay", refused)

    answer = _ask(admin)

    (sample,) = _samples(migrated_tenant)
    assert sample.state == "failed" and sample.failure_reason
    assert "The sample could not be made." in admin.get(answer["Location"]).content.decode()


def test_only_the_organisations_administrators_download_it(
    migrated_tenant: Any,
    admin: Any,
    member_of: Any,
    make_tenant_schema: Any,
    exports: Any,
    queued_samples: list[Any],
) -> None:
    from django.test import Client

    from identity.models import Membership, User

    _ask(admin)
    (sample,) = _samples(migrated_tenant)
    _run(migrated_tenant, sample)
    other_admin, _, _ = member_of("another.admin@example.test", is_tenant_admin=True)
    member, _, _ = member_of("a.member@example.test")
    other = make_tenant_schema("Another organisation (synthetic)")
    stranger = User.objects.create_user("a.stranger@example.test", "test-only-not-a-password")
    Membership.objects.create(
        tenant=other, user=stranger, is_tenant_admin=True, actor_kind="system"
    )
    elsewhere = Client(headers={"host": "127.0.0.1"})
    elsewhere.force_login(stranger)
    session = elsewhere.session
    session["tenant_number"] = other.number
    session.save()
    status = f"{ASK}{sample.pk}/"
    download = f"{ASK}{sample.pk}/download/"

    assert "download" in other_admin.get(status).content.decode().lower()
    got = other_admin.get(download)
    assert got.status_code == 200 and got["Content-Type"] == "application/pdf"
    assert b"".join(got.streaming_content).startswith(b"%PDF")
    for client in (member, elsewhere):
        assert client.get(status).status_code == 404
        assert client.get(download).status_code == 404


def test_the_sample_is_in_the_interface_language(
    migrated_tenant: Any, admin: Any, exports: Any, queued_samples: list[Any], settings: Any
) -> None:
    from pypdf import PdfReader

    settings.LANGUAGE_CODE = "uk"
    _ask(admin)
    (sample,) = _samples(migrated_tenant)
    assert sample.language == "uk"

    done = _run(migrated_tenant, sample)

    text = "".join(page.extract_text() for page in PdfReader(
        str(Path(settings.EXPORT_ROOT) / done.artifact_ref)
    ).pages)  # fmt: skip
    assert "Приклад положення" in text and "Затверджено" in text


def test_the_sample_is_composed_as_an_export_is(
    migrated_tenant: Any, admin: Any, exports: Any, queued_samples: list[Any], settings: Any
) -> None:
    from pypdf import PdfReader

    _ask(admin)
    (sample,) = _samples(migrated_tenant)
    done = _run(migrated_tenant, sample)

    pdf = PdfReader(str(Path(settings.EXPORT_ROOT) / done.artifact_ref))
    text = "".join(page.extract_text() for page in pdf.pages)
    # The mention's words, never a link (DL-0438).
    assert "example register" in text
    links = [
        annotation
        for page in pdf.pages
        for annotation in (page.get("/Annots") or [])
        if "/URI" in str(annotation.get_object().get("/A", {}))
        and "/document/" in str(annotation.get_object()["/A"]["/URI"])
    ]
    assert links == []
    # The image embedded as the export embeds it.
    assert [image for page in pdf.pages for image in page.images]
    # The attachment list's two invented rows, and the clause numbers an export carries.
    assert "An example form" in text and "An example schedule" in text
    assert "1-1" in text


def test_a_sample_finished_between_the_reads_stays_done(
    migrated_tenant: Any, admin: Any, exports: Any, queued_samples: list[Any], monkeypatch: Any
) -> None:
    """A long-waiting sample the worker finishes while a second request reads the queue keeps
    its *done*; the request treats it as finished, not as stale."""
    from django.db import connection

    from rendering import styles_views
    from rendering.models import SampleExport

    _ask(admin)
    (first,) = _samples(migrated_tenant)
    with schema_context(migrated_tenant.number):
        SampleExport.objects.update(created_at=timezone.now() - timedelta(minutes=40))
    real = styles_views._unheld

    def finished_meanwhile(ids: list[Any]) -> set[Any]:
        # The worker commits between the request's two reads.
        def worker() -> None:
            try:
                with schema_context(migrated_tenant.number):
                    SampleExport.objects.filter(pk=first.pk).update(
                        state="done", artifact_ref=f"{first.pk}/sample.pdf"
                    )
            finally:
                connection.close()

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(10)
        return real(ids)

    monkeypatch.setattr(styles_views, "_unheld", finished_meanwhile)
    answer = _ask(admin)

    assert answer.status_code == 303
    with schema_context(migrated_tenant.number):
        first.refresh_from_db()
    assert (first.state, first.failure_reason) == ("done", "")
    assert [s.state for s in _samples(migrated_tenant)] == ["done", "queued"]


def test_a_worker_meeting_a_held_sample_tries_again(
    migrated_tenant: Any, admin: Any, exports: Any, queued_samples: list[Any]
) -> None:
    """A delivery that finds its sample held — by a request reading the queue — is retried, never
    dropped with the sample left queued and nothing behind it."""
    from celery.exceptions import Retry
    from django.db import connection, transaction

    from rendering.models import SampleExport
    from rendering.tasks import render_sample

    _ask(admin)
    (sample,) = _samples(migrated_tenant)
    held, release = threading.Event(), threading.Event()

    def request_holds() -> None:
        try:
            with schema_context(migrated_tenant.number), transaction.atomic():
                SampleExport.objects.select_for_update().get(pk=sample.pk)
                held.set()
                release.wait(15)
        finally:
            connection.close()

    other = threading.Thread(target=request_holds)
    other.start()
    try:
        assert held.wait(10)
        with pytest.raises(Retry):
            render_sample(migrated_tenant.number, str(sample.pk))
    finally:
        release.set()
        other.join(20)
    assert render_sample(migrated_tenant.number, str(sample.pk)) == "done"


def test_a_blocked_organisation_reaches_no_sample(
    migrated_tenant: Any, admin: Any, exports: Any, queued_samples: list[Any]
) -> None:
    from tenancy.middleware import invalidate_host_cache

    _ask(admin)
    (sample,) = _samples(migrated_tenant)
    _run(migrated_tenant, sample)
    migrated_tenant.state = "blocked"
    migrated_tenant.save(update_fields=["state"])
    invalidate_host_cache()

    assert _ask(admin).status_code == 404
    assert admin.get(f"{ASK}{sample.pk}/").status_code == 404
    assert admin.get(f"{ASK}{sample.pk}/download/").status_code == 404
