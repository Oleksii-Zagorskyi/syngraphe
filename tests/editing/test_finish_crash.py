"""A finish stopped after each of its steps ends, once the reconciler has repaired it, where an
uninterrupted finish ends: the version derived, the hold released as finished, the draft gone, the
authorship asked for. Invented text; people are synthetic examples."""

from __future__ import annotations

from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.crash,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]


@pytest.mark.parametrize("step", [1, 2, 3, 4])
def test_each_crash_state_repaired(
    step: int,
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    queued_authorship: list[Any],
) -> None:
    from documents import gitstore, reconcile
    from documents.models import Version
    from editing import services
    from editing.models import Draft, Hold

    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    client.post(f"/document/{document.number}/edit/take/")
    with schema_context(migrated_tenant.number):
        hold = Hold.objects.get(document=document)
        draft = Draft.objects.get(hold=hold)
        draft.content = {
            **draft.content,
            "document.md": draft.content["document.md"] + "\nA new sentence.\n",
        }
        draft.save()
        with pytest.raises(services.InjectedFault):
            services.commit_draft(hold, author, "Extended", fault_at=step)

    reconcile.run(tenant=migrated_tenant.number, repair=True)

    with schema_context(migrated_tenant.number):
        repo = gitstore.open_repository(migrated_tenant.number, document.number)
        head = gitstore.head(repo)
        hold.refresh_from_db()
        assert Version.objects.filter(commit_sha=head, kind="edit").exists()
        assert hold.release_kind == "finished"
        assert not Draft.objects.filter(hold=hold).exists()
    assert (migrated_tenant.number, document.number, head) in queued_authorship
    assert [f.kind for f in reconcile.run(tenant=migrated_tenant.number)] in (
        [],
        ["authorship_missing"],
    )


def stopped_at_the_commit(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> tuple[Any, Any, Any]:
    """A finish stopped right after its git commit: the hold open, its draft behind the head."""
    from editing import services
    from editing.models import Draft, Hold

    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    client.post(f"/document/{document.number}/edit/take/")
    with schema_context(migrated_tenant.number):
        hold = Hold.objects.get(document=document)
        draft = Draft.objects.get(hold=hold)
        draft.content = {
            **draft.content,
            "document.md": draft.content["document.md"] + "\nA new sentence.\n",
        }
        draft.save()
        with pytest.raises(services.InjectedFault):
            services.commit_draft(hold, author, "Extended", fault_at=1)
    return author, document, hold


def add_to_draft(migrated_tenant: Any, hold: Any, text: str) -> None:
    from editing.models import Draft

    with schema_context(migrated_tenant.number):
        draft = Draft.objects.get(hold=hold)
        draft.content = {**draft.content, "document.md": draft.content["document.md"] + text}
        draft.save()


def test_a_second_send_resumes_a_stopped_finish(
    migrated_tenant: Any, member_of: Any, new_document: Any, queued_authorship: list[Any]
) -> None:
    """Sent again with nothing typed since: the stopped version finished, not *nothing changed*."""
    from documents import gitstore
    from documents.models import Version
    from editing import services
    from editing.models import Draft

    author, document, hold = stopped_at_the_commit(migrated_tenant, member_of, new_document)
    with schema_context(migrated_tenant.number):
        version = services.commit_draft(hold, author, "Extended")
        head = gitstore.head(gitstore.open_repository(migrated_tenant.number, document.number))
        hold.refresh_from_db()
        assert version.commit_sha == head
        assert Version.objects.filter(document=document, kind="edit").count() == 1
        assert hold.release_kind == "finished"
        assert not Draft.objects.filter(hold=hold).exists()


def test_a_second_send_commits_what_was_typed_after_the_stop(
    migrated_tenant: Any, member_of: Any, new_document: Any, queued_authorship: list[Any]
) -> None:
    from documents import bundle, gitstore
    from documents.models import Version
    from editing import services

    author, document, hold = stopped_at_the_commit(migrated_tenant, member_of, new_document)
    add_to_draft(migrated_tenant, hold, "\nA later sentence.\n")
    with schema_context(migrated_tenant.number):
        version = services.commit_draft(hold, author, "Extended again")
        repo = gitstore.open_repository(migrated_tenant.number, document.number)
        _, body = bundle.parse(gitstore.read(repo, "document.md", version.commit_sha).decode())
        assert "A new sentence." in body and "A later sentence." in body
        assert Version.objects.filter(document=document, kind="edit").count() == 2


def test_the_repair_leaves_text_typed_after_the_stop(
    migrated_tenant: Any, member_of: Any, new_document: Any, queued_authorship: list[Any]
) -> None:
    from documents import reconcile
    from editing.models import Draft

    _, document, hold = stopped_at_the_commit(migrated_tenant, member_of, new_document)
    add_to_draft(migrated_tenant, hold, "\nA later sentence.\n")

    findings = reconcile.run(tenant=migrated_tenant.number, repair=True)

    stopped = [f for f in findings if f.kind == "finish_stopped"]
    assert stopped and not stopped[0].repaired and "later work" in stopped[0].detail
    with schema_context(migrated_tenant.number):
        hold.refresh_from_db()
        assert hold.released_at is None
        assert "A later sentence." in Draft.objects.get(hold=hold).content["document.md"]


def test_the_repair_leaves_a_holder_no_longer_a_member(
    migrated_tenant: Any, member_of: Any, new_document: Any, queued_authorship: list[Any]
) -> None:
    from documents import reconcile
    from editing.models import Draft
    from identity.models import Membership

    author, _, hold = stopped_at_the_commit(migrated_tenant, member_of, new_document)
    with schema_context(migrated_tenant.number):
        Membership.objects.filter(user=author).delete()

    findings = reconcile.run(tenant=migrated_tenant.number, repair=True)

    stopped = [f for f in findings if f.kind == "finish_stopped"]
    assert stopped and not stopped[0].repaired
    with schema_context(migrated_tenant.number):
        hold.refresh_from_db()
        assert hold.released_at is None
        assert Draft.objects.filter(hold=hold).exists()


def test_the_screen_numbers_the_version_after_a_stopped_one(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    """Inside the stopped-finish window, before the reconciler derives the stopped commit's row:
    with nothing typed since, the screen shows the stopped version's number; with more typed, the
    one after it."""
    from editing import services

    _, _, hold = stopped_at_the_commit(migrated_tenant, member_of, new_document)
    with schema_context(migrated_tenant.number):
        assert services.finish(hold).number == "0.0-1"
    add_to_draft(migrated_tenant, hold, "\nA later sentence.\n")
    with schema_context(migrated_tenant.number):
        assert services.finish(hold).number == "0.0-2"


def image_paragraph(data: bytes) -> str:
    import hashlib

    return f"\n![A synthetic plan](images/{hashlib.sha256(data).hexdigest()}.png)\n"


def stopped_with_an_image(
    migrated_tenant: Any, member_of: Any, new_document: Any, data: bytes
) -> tuple[Any, Any, Any]:
    """A finish stopped right after its git commit, which wrote a staged image."""
    import hashlib

    from django.utils import timezone

    from editing import services
    from editing.models import Draft, DraftFile, Hold

    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    client.post(f"/document/{document.number}/edit/take/")
    path = f"images/{hashlib.sha256(data).hexdigest()}.png"
    with schema_context(migrated_tenant.number):
        hold = Hold.objects.get(document=document)
        draft = Draft.objects.get(hold=hold)
        draft.content = {
            **draft.content,
            "document.md": draft.content["document.md"] + image_paragraph(data),
        }
        draft.save()
        DraftFile.objects.create(
            draft=draft,
            kind="image",
            path=path,
            operation="add",
            content=data,
            file_name="plan.png",
            sha256=hashlib.sha256(data).hexdigest(),
            at=timezone.now(),
        )
        with pytest.raises(services.InjectedFault):
            services.commit_draft(hold, author, "An image", fault_at=1)
    return author, document, hold


def test_a_stopped_finish_with_files_resumes(
    migrated_tenant: Any, member_of: Any, new_document: Any, queued_authorship: list[Any]
) -> None:
    """The image the stop committed is the head's now: sent again, the stopped version is the
    finish's, and nothing is committed twice."""
    from documents import gitstore
    from documents.models import Version
    from editing import services

    data = b"a synthetic image committed by the stop"
    author, document, hold = stopped_with_an_image(migrated_tenant, member_of, new_document, data)
    with schema_context(migrated_tenant.number):
        repo = gitstore.open_repository(migrated_tenant.number, document.number)
        stopped = gitstore.head(repo)
        version = services.commit_draft(hold, author, "An image")
        assert version.commit_sha == stopped == gitstore.head(repo)
        assert Version.objects.filter(document=document, kind="edit").count() == 1
        hold.refresh_from_db()
        assert hold.release_kind == "finished"


def test_a_stop_with_later_entities_is_unfinishable(
    migrated_tenant: Any, member_of: Any, new_document: Any, queued_authorship: list[Any]
) -> None:
    """An entity declared in the draft after the stop is later work: the reconciler names the
    stop and leaves the hold and the draft to their holder."""
    from documents import entities, reconcile
    from editing.models import Draft

    data = b"a synthetic image committed by the stop"
    _, document, hold = stopped_with_an_image(migrated_tenant, member_of, new_document, data)
    declared = entities.dump([entities.Declared("term", "record", "the record")])
    with schema_context(migrated_tenant.number):
        draft = Draft.objects.get(hold=hold)
        draft.content = {**draft.content, "entities.yaml": declared}
        draft.save()

    findings = reconcile.run(tenant=migrated_tenant.number, repair=True)

    stopped = [f for f in findings if f.kind == "finish_stopped"]
    assert stopped and not stopped[0].repaired and "later work" in stopped[0].detail
    with schema_context(migrated_tenant.number):
        hold.refresh_from_db()
        assert hold.released_at is None
        assert Draft.objects.get(hold=hold).content["entities.yaml"] == declared


def test_a_file_staged_after_the_stop_is_the_next_version(
    migrated_tenant: Any, member_of: Any, new_document: Any, queued_authorship: list[Any]
) -> None:
    """An attachment staged after the stop is later work: sent again, the stopped version is
    derived and the attachment committed as the version after it."""
    import hashlib

    from django.utils import timezone

    from documents import gitstore
    from documents.models import Version
    from editing import services
    from editing.models import Draft, DraftFile

    author, document, hold = stopped_at_the_commit(migrated_tenant, member_of, new_document)
    data = b"an attachment staged after the stop"
    with schema_context(migrated_tenant.number):
        repo = gitstore.open_repository(migrated_tenant.number, document.number)
        stopped = gitstore.head(repo)
        draft = Draft.objects.get(hold=hold)
        # Listed by the draft as the parts services list an upload, so row and entry agree.
        draft.content["frontmatter"]["attachments"] = [
            {
                "number": 1,
                "title": "Synthetic form (example)",
                "file_name": "form.txt",
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
            }
        ]
        draft.save()
        DraftFile.objects.create(
            draft=draft,
            kind="attachment",
            path="attachments/1",
            operation="add",
            content=data,
            file_name="form.txt",
            sha256=hashlib.sha256(data).hexdigest(),
            at=timezone.now(),
        )
        version = services.commit_draft(hold, author, "An attachment")
        assert [str(p.id) for p in gitstore.commit_at(repo, version.commit_sha).parents] == [
            stopped
        ]
        assert gitstore.read(repo, "attachments/1", version.commit_sha) == data
        assert Version.objects.filter(document=document, kind="edit").count() == 2


def test_a_part_staged_after_a_stop_is_kept(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    commit_version: Any,
    queued_authorship: list[Any],
) -> None:
    """Only an attachment renamed after the stop is later work all the same: the reconciler names
    the stop and deletes nothing, and the next send commits the rename as the version after it."""
    import hashlib

    from documents import bundle, gitstore, reconcile
    from documents.models import Version
    from editing import parts, services
    from editing.models import Draft, Hold

    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    data = b"a synthetic form"
    entry = {
        "number": 1,
        "title": "Request form (example)",
        "file_name": "form.txt",
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }
    commit_version(
        document,
        author,
        "A synthetic sentence.\n",
        files={"attachments/1": data},
        attachments=[entry],
    )
    client.post(f"/document/{document.number}/edit/take/")
    with schema_context(migrated_tenant.number):
        hold = Hold.objects.get(document=document, released_at__isnull=True)
        draft = Draft.objects.get(hold=hold)
        draft.content = {**draft.content, "document.md": "A synthetic sentence, extended.\n"}
        draft.save()
        with pytest.raises(services.InjectedFault):
            services.commit_draft(hold, author, "Extended", fault_at=1)
        repo = gitstore.open_repository(migrated_tenant.number, document.number)
        stopped = gitstore.head(repo)
        parts.rename_attachment(document, author, 1, title="Renamed form (example)")

    findings = reconcile.run(tenant=migrated_tenant.number, repair=True)

    stop = [f for f in findings if f.kind == "finish_stopped"]
    assert stop and not stop[0].repaired and "later work" in stop[0].detail
    with schema_context(migrated_tenant.number):
        assert Draft.objects.filter(pk=draft.pk).exists()
        version = services.commit_draft(Hold.objects.get(pk=hold.pk), author, "Renamed")
        assert [str(p.id) for p in gitstore.commit_at(repo, version.commit_sha).parents] == [
            stopped
        ]
        text = gitstore.read(repo, "document.md", version.commit_sha).decode()
        assert bundle.parse(text)[0].attachments[0]["title"] == "Renamed form (example)"
        assert Version.objects.filter(document=document, commit_sha=stopped).exists()


def test_the_screens_heading_names_the_number_its_form_gives(
    migrated_tenant: Any, member_of: Any, new_document: Any, settings: Any
) -> None:
    """A finish stopped past its commit, the commit's row derived since: the screen's form gives
    the stopped version's own number, and the heading names the same draft number."""
    from documents import gitstore
    from documents import services as documents
    from editing import services
    from editing.models import Draft, Hold

    settings.LANGUAGE_CODE = "en"
    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    client.post(f"/document/{document.number}/edit/take/")
    with schema_context(migrated_tenant.number):
        hold = Hold.objects.get(document=document)
        draft = Draft.objects.get(hold=hold)
        draft.content = {
            **draft.content,
            "document.md": draft.content["document.md"] + "\nA new sentence.\n",
        }
        draft.save()
        with pytest.raises(services.InjectedFault):
            services.commit_draft(hold, author, "Extended", fault_at=1)
        repo = gitstore.open_repository(migrated_tenant.number, document.number)
        head = gitstore.head(repo)
        assert head is not None
        documents.derive_version(document, gitstore.commit_at(repo, head), author)
        assert services.finish(hold).number == "0.0-1"

    body = client.get(f"/document/{document.number}/edit/finish/").content.decode()

    assert '<span class="version-number">0.0-1 — draft</span>' in body
