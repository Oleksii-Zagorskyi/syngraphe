"""An export asked from a version's historical page is held to the reader's ceiling, not to the
view's rights (DL-0195, DL-0421, DL-0423): a version reached through a history right exports to
the end; the same job fails once the ceiling no longer reaches it; an ordinary export keeps its
own rule.

People, groups and texts are synthetic examples; every text is invented.
"""

from __future__ import annotations

from typing import Any

import pytest

from access.rights import Right
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

FIRST = "# General provisions\n\nAn application is made in writing.\n"
SECOND = FIRST + "\nThe decision is sent the same day.\n"


def _ask(client: Any, tenant: int, number: int, version: str) -> Any:
    """The job a reader asks from a version's page, read in its tenant."""
    from rendering.models import ExportJob

    dialog = client.get(f"/document/{number}/version/{version}/export/")
    assert dialog.status_code == 200
    view = dialog.context["offers"][0].view.value
    client.post(
        f"/document/{number}/version/{version}/export/",
        {"view": view, "format": "pdf", "document": "on", f"changes-{view}": "clean"},
    )
    with schema_context(tenant):
        return ExportJob.objects.order_by("-created_at").first()


def test_a_version_a_history_right_reaches_exports(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    member_of: Any,
    link_group: Any,
    exports: Any,
    kit: Any,
) -> None:
    from review import services

    people = edition_cast()
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    commit_version(document, people["a"], SECOND, "edit")
    with schema_context(migrated_tenant.number):
        services.accept(document, people["r"])
    client, _user, membership = member_of("acc.synthetic@example.test")
    link_group(document, [Right.VIEW_ACCEPTED, Right.VIEW_ALL_HISTORY], [membership], people["a"])
    # `0.0-1`: pending once, superseded by the acceptance; the reader's ladder stops at 0.1.
    job = _ask(client, migrated_tenant.number, document.number, "0.0-1")
    assert job is not None and job.at_version
    done = kit.run_job(migrated_tenant.number, job.pk)
    assert done.state == "done", done.failure
    assert client.get(f"/document/{document.number}/export/{job.pk}/").status_code == 200


def test_the_job_fails_once_the_ceiling_no_longer_reaches_it(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    member_of: Any,
    link_group: Any,
    exports: Any,
) -> None:
    from access.models import AccessGroup
    from rendering.export.compose import still_permitted
    from review import services

    people = edition_cast()
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        services.accept(document, people["r"])
    client, _user, membership = member_of("acc.synthetic@example.test")
    link_group(document, [Right.VIEW_ACCEPTED], [membership], people["a"])
    history = link_group(document, [Right.VIEW_ALL_HISTORY], [membership], people["a"])
    job = _ask(client, migrated_tenant.number, document.number, "0.0")
    with schema_context(migrated_tenant.number):
        assert job is not None and still_permitted(job)
        AccessGroup.objects.get(pk=history.pk).remove_member(membership, by=people["a"])
        assert not still_permitted(job)


def test_an_ordinary_export_keeps_its_rule(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    member_of: Any,
    link_group: Any,
    exports: Any,
) -> None:
    from rendering.models import ExportJob

    people = edition_cast()
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    client = people.clients["a"]
    view = client.get(f"/document/{document.number}/export/").context["offers"][-1].view.value
    client.post(
        f"/document/{document.number}/export/",
        {"view": view, "format": "pdf", "document": "on", f"changes-{view}": "clean"},
    )
    with schema_context(migrated_tenant.number):
        job = ExportJob.objects.get()
        assert not job.at_version


def test_the_file_names_the_number_the_page_shows(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    member_of: Any,
    link_group: Any,
    exports: Any,
    kit: Any,
) -> None:
    """The version's number from git and the passport, as its page names it — even while an
    acceptance's rows wait to be derived (DL-0183, DL-0267)."""
    from rendering.export.job import artifact
    from review import services

    people = edition_cast()
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        with pytest.raises(services.InjectedFault):
            services.accept(document, people["r"], fault_at=1)
    client, _user, membership = member_of("all.synthetic@example.test")
    link_group(document, [Right.VIEW_PENDING, Right.VIEW_ALL_HISTORY], [membership], people["a"])
    job = _ask(client, migrated_tenant.number, document.number, "0.1")
    done = kit.run_job(migrated_tenant.number, job.pk)
    path = artifact(done)
    assert path is not None and "0.1" in path.name, done.failure_reason


def test_marks_follow_the_chain_of_the_versions_stance(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    member_of: Any,
    link_group: Any,
    exports: Any,
) -> None:
    """Pending work is marked against the acceptance it counts from, by default; accepted text
    against the edition before it — none here, so no marks (DL-0241, DL-0426)."""
    from review import services

    people = edition_cast()
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        services.accept(document, people["r"])
    commit_version(document, people["a"], SECOND, "edit")
    commit_version(document, people["a"], SECOND + "\nA third sentence.\n", "edit")
    client, _user, membership = member_of("all.synthetic@example.test")
    link_group(document, [Right.VIEW_PENDING, Right.VIEW_ALL_HISTORY], [membership], people["a"])
    n = document.number
    pending = client.get(f"/document/{n}/version/0.1-2/export/").context["offers"][0]
    assert pending.baseline_number == "0.1" and pending.marked_by_default
    accepted = client.get(f"/document/{n}/version/0.1/export/").context["offers"][0]
    assert accepted.baseline is None


def test_the_historical_page_offers_its_comparisons_and_files(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    member_of: Any,
    link_group: Any,
    kit: Any,
) -> None:
    from review import services

    people = edition_cast()
    document = people.document
    kit.attach(migrated_tenant.number, people, FIRST, b"one table\n")
    with schema_context(migrated_tenant.number):
        services.accept(document, people["r"])
    commit_version(document, people["a"], SECOND, "edit")
    client, _user, membership = member_of("all.synthetic@example.test")
    link_group(document, [Right.VIEW_PENDING, Right.VIEW_ALL_HISTORY], [membership], people["a"])
    n = document.number
    page = client.get(f"/document/{n}/version/0.1/").content.decode()
    chooser = page[page.index('class="compare-with"') :]
    assert 'name="from" value="0.1"' in chooser
    assert '<option value="0.1-1">' in chooser and '<option value="0.0">' in chooser
    assert '<option value="0.1">' not in chooser
    assert f'href="/document/{n}/version/0.1/attachment/1/"' in page
