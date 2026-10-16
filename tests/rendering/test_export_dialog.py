"""The export dialog (DL-0193, DL-0207, DL-0241; `pages.md § Export`): what the person may choose
by the document and their rights, and a request that writes its job, audits it and queues it.

People, groups and titles are synthetic examples; every text is invented.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from access.rights import Right
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]


def _offers(body: str) -> dict[str, str]:
    """Each offered view's block of the dialog, by its view."""
    return dict(
        re.findall(r'<div class="offer" data-view="([a-z_]+)">(.*?)</div>', body, re.DOTALL)
    )


def test_dialog_by_document_and_rights(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
) -> None:
    people = edition_cast()
    kit.canonical(migrated_tenant.number, people, commit_version, kit.FIRST)
    client, _ = kit.reader(member_of, link_group, people, [Right.VIEW_CANONICAL], "canonical")

    body = client.get(f"/document/{people.document.number}/export/").content.decode()

    assert 'name="document"' in body and 'name="attachments"' not in body
    offers = _offers(body)
    assert list(offers) == ["canonical"]
    # A single view is named as text, not offered as a choice.
    assert '<span class="single">' in offers["canonical"] and "1.0" in offers["canonical"]
    assert 'type="radio" name="view"' not in body
    assert "data-changes" not in body
    assert 'data-delivery="file"' in body


def test_views_and_changes(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
) -> None:
    """Two editions, an acceptance beyond them, a pending run and the reader's own draft: four
    views, each with its baseline named — marked by default except the canonical edition."""
    from editing import holds
    from review import services as review

    number = migrated_tenant.number
    people = edition_cast()
    kit.canonical(number, people, commit_version, kit.FIRST)
    kit.canonical(number, people, commit_version, kit.SECOND)
    commit_version(people.document, people["a"], kit.THIRD, "edit")
    with schema_context(number):
        review.accept(people.document, people["r"])
    commit_version(people.document, people["a"], kit.FOURTH, "edit")
    rights = [Right.VIEW_PENDING, Right.VIEW_ALL_HISTORY, Right.EDIT]
    client, user = kit.reader(member_of, link_group, people, rights, "history")
    with schema_context(number):
        holds.take(people.document, user)

    body = client.get(f"/document/{people.document.number}/export/").content.decode()

    offers = _offers(body)
    assert list(offers) == ["canonical", "accepted", "pending_edits", "my_edits"]
    for view, baseline in (
        ("canonical", "1.0"),
        ("accepted", "2.0"),
        ("pending_edits", "2.1"),
        ("my_edits", "2.1-1"),
    ):
        block = offers[view]
        assert f'data-changes="{view}"' in block, view
        # The baseline named in the *changes* line, not in the offer's own label.
        assert f"позначені відносно {baseline}<" in block, view
        marked = re.search(rf'name="changes-{view}" value="marked"( checked)?', block)
        assert marked is not None, view
        assert bool(marked.group(1)) is (view != "canonical"), view


def test_a_request_writes_its_job_audits_and_queues_it(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
) -> None:
    from audit.models import AuditEvent
    from rendering.models import ExportJob

    people = edition_cast()
    edition = kit.canonical(migrated_tenant.number, people, commit_version, kit.FIRST)
    client, user = kit.reader(member_of, link_group, people, [Right.VIEW_CANONICAL], "asker")
    route = f"/document/{people.document.number}/export/"

    response = client.post(route, {"document": "on", "format": "pdf", "view": "canonical"})
    nothing = client.post(route, {"format": "pdf", "view": "canonical"})
    foreign = client.post(route, {"document": "on", "format": "pdf", "view": "pending_edits"})

    assert response.status_code == 302
    with schema_context(migrated_tenant.number):
        job = ExportJob.objects.get()
    assert response["Location"] == f"{route}{job.pk}/"
    assert (job.version_id, job.format, job.view, job.state) == (
        edition.version_id,
        "pdf",
        "canonical",
        "queued",
    )
    assert job.requested_by_id == user.pk
    assert exports == [(migrated_tenant.number, str(job.pk))]
    event = AuditEvent.objects.get(action="document.exported")
    assert event.after["export"] == str(job.pk)
    assert nothing.status_code == 400 and foreign.status_code == 400


def test_a_broker_fault_after_the_commit_leaves_the_job_to_the_reconciler(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The row is written before the call that leaves the process: when the broker refuses the
    job, the person still reaches the job's page, the job stays queued for the reconciler, and
    the fault is logged."""
    import logging

    from rendering import tasks
    from rendering.models import ExportJob

    def refused(*args: Any) -> None:
        raise ConnectionError("the broker is down")

    people = edition_cast()
    kit.canonical(migrated_tenant.number, people, commit_version, kit.FIRST)
    client, _ = kit.reader(member_of, link_group, people, [Right.VIEW_CANONICAL], "broker")
    monkeypatch.setattr(tasks.render_export, "delay", refused)
    caplog.set_level(logging.ERROR)

    response = client.post(
        f"/document/{people.document.number}/export/",
        {"document": "on", "format": "pdf", "view": "canonical"},
    )

    assert response.status_code == 302
    with schema_context(migrated_tenant.number):
        job = ExportJob.objects.get()
    assert job.state == "queued"
    assert response["Location"].endswith(f"/{job.pk}/")
    assert any(record.levelno >= logging.ERROR for record in caplog.records)


def test_only_the_requester_sees_a_job(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
) -> None:
    people = edition_cast()
    kit.canonical(migrated_tenant.number, people, commit_version, kit.FIRST)
    asker, _ = kit.reader(member_of, link_group, people, [Right.VIEW_CANONICAL], "asker")
    other, _ = kit.reader(member_of, link_group, people, [Right.VIEW_CANONICAL], "other")
    route = f"/document/{people.document.number}/export/"
    asker.post(route, {"document": "on", "format": "pdf", "view": "canonical"})
    job_route = f"{route}{exports[0][1]}/"

    assert asker.get(job_route).status_code == 200
    assert other.get(job_route).status_code == 404
    assert other.get(f"{job_route}download/").status_code == 404


def test_markdown_with_images_is_announced_as_a_zip(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
    pictures: Any,
) -> None:
    """Each offer says whether its text shows images — the holder's draft by what it stages, its
    only image in no commit yet — so the dialog can say a Markdown export is one zip."""
    import hashlib

    from django.utils import timezone

    from editing.models import Draft, DraftFile

    people = edition_cast()
    plan = pictures.make(1)
    pictures.canonical_with(
        migrated_tenant.number,
        people,
        commit_version,
        kit.FIRST + plan.paragraph,
        {plan.path: plan.data},
    )
    commit_version(people.document, people["a"], kit.SECOND, "edit", files={plan.path: None})
    holder, _, membership = member_of("holder.synthetic@example.test")
    link_group(
        people.document,
        [Right.VIEW_CANONICAL, Right.VIEW_PENDING, Right.EDIT],
        [membership],
        people["a"],
    )
    assert holder.post(f"/document/{people.document.number}/edit/take/").status_code == 200
    staged = pictures.make(2)
    with schema_context(migrated_tenant.number):
        draft = Draft.objects.get(hold__document=people.document, hold__released_at__isnull=True)
        draft.content = {**draft.content, "document.md": kit.SECOND + staged.paragraph}
        draft.save()
        DraftFile.objects.create(
            draft=draft,
            kind="image",
            path=staged.path,
            operation="add",
            content=staged.data,
            file_name="plan.png",
            sha256=hashlib.sha256(staged.data).hexdigest(),
            at=timezone.now(),
        )

    body = holder.get(f"/document/{people.document.number}/export/").content.decode()

    marks = dict(re.findall(r'name="view" value="([a-z_]+)"[^>]*data-images="(true|false)"', body))
    assert marks == {"canonical": "true", "pending_edits": "false", "my_edits": "true"}
    assert 'data-zip="' in body and 'data-file="' in body


def test_an_image_only_an_appendix_shows_makes_no_zip(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    exports: Any,
    kit: Any,
    pictures: Any,
) -> None:
    """The dialog reads the text the export writes: an image only an appendix shows is in no
    Markdown export yet, and announces no zip."""
    people = edition_cast()
    plan = pictures.make(6)
    pictures.canonical_with(
        migrated_tenant.number,
        people,
        commit_version,
        kit.FIRST,
        {plan.path: plan.data, "appendices/1.md": plan.paragraph.encode()},
    )
    client, _ = kit.reader(member_of, link_group, people, [Right.VIEW_CANONICAL], "appendix")

    body = client.get(f"/document/{people.document.number}/export/").content.decode()

    assert 'data-images="false"' in body and 'data-images="true"' not in body
