"""What follows a return (ST-0052, DL-0114, DL-0369, DL-0378): an acceptance ends the *returned*
state; a second return is never derived over a run returned once; a finish completed under a
return tells nobody the returned version awaits them; the reason reaches only those who may read
the pending text; the record is believed over a row that disagrees with it; a returned entry
opens the version returned; a run read across a return still has its notices computed.

People, groups and texts are synthetic examples; every text is invented.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.test import Client

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

FIRST = "# General provisions\n\nAn application is made in writing.\n"
SECOND = FIRST + "\nThe decision is sent the same day.\n"
REASON = "Synthetic reason: the deadlines are still under discussion"


def signed_in(tenant: Any, user: Any, **options: Any) -> Client:
    client = Client(headers={"host": "127.0.0.1"}, **options)
    client.force_login(user)
    session = client.session
    session["tenant_number"] = tenant.number
    session.save()
    return client


def test_an_accepted_run_is_no_longer_returned(
    migrated_tenant: Any, cast: Any, commit_version: Any
) -> None:
    from review import services
    from review.state import State, state, tags

    people = cast(editors=("a",), reviewers=("r",))
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        services.return_run(document, people["r"], REASON)
        assert state(document) is State.RETURNED
        services.accept(document, people["r"])
        assert state(document) is State.ACCEPTED
        shown = tags(people["r"], [document])[document.pk]
        assert not [tag for tag in shown if tag.state is State.RETURNED]


def test_a_second_return_over_a_returned_run_is_not_derived(
    migrated_tenant: Any, cast: Any, commit_version: Any
) -> None:
    from django.utils import timezone

    from documents import bundle, gitstore
    from documents.identity import identity_for
    from documents.locks import document_lock
    from review import services
    from review.models import Return

    people = cast(editors=("a",), reviewers=("r",))
    document = people.document
    last = commit_version(document, people["a"], FIRST, "edit")
    number = migrated_tenant.number
    with schema_context(number):
        services.return_run(document, people["r"], REASON)
        repo = gitstore.open_repository(number, document.number)
        with document_lock(number, document.number):
            # A second section written exactly as the platform writes one, with nothing sent since.
            head = gitstore.head(repo)
            assert head is not None
            now = timezone.now().replace(microsecond=0)
            entry = bundle.PassportEntry(
                kind="return",
                number=None,
                at=now,
                by=str(people["r"].pk),
                version=last.commit_sha,
                reason=REASON,
            )
            passport = gitstore.read(repo, "passport.md", head).decode()
            sha = gitstore.commit(
                repo,
                {"passport.md": bundle.append_passport(passport, entry).encode()},
                identity_for(people["r"], at=now),
                "Returned without accepting",
                gitstore.Kind.RETURN,
            )
            assert isinstance(services.derivable_return(document, repo, sha), str)
            with pytest.raises(services.RecordIncomplete):
                services.settle_head(document)
        assert Return.objects.count() == 1


def test_a_finish_completed_under_a_return_tells_no_reviewer(
    migrated_tenant: Any, cast: Any, commit_version: Any
) -> None:
    from editing import holds
    from editing import services as editing
    from editing.models import Draft, Hold
    from notifications.models import Notification
    from review import services

    people = cast(editors=("a", "b"), reviewers=("r",))
    document = people.document
    commit_version(document, people["b"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        hold = holds.take(document, people["a"])
        draft = Draft.objects.get(hold=hold)
        draft.content = {**draft.content, "document.md": SECOND}
        draft.save()
        with pytest.raises(editing.InjectedFault):
            editing.commit_draft(hold, people["a"], "Synthetic edit", fault_at=1)
        services.return_run(document, people["r"], REASON)
        told_before = Notification.objects.filter(
            user=people["r"], event="version_committed"
        ).count()
        editing.commit_draft(Hold.objects.get(pk=hold.pk), people["a"], "Synthetic edit")
        assert (
            Notification.objects.filter(user=people["r"], event="version_committed").count()
            == told_before
        )


def test_the_reason_is_read_under_the_readers_rights(
    migrated_tenant: Any, cast: Any, commit_version: Any, link_group: Any, settings: Any
) -> None:
    from access.models import AccessGroup
    from access.rights import Right
    from review import services

    settings.LANGUAGE_CODE = "en"
    people = cast(editors=("a",), reviewers=("r",))
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        services.return_run(document, people["r"], REASON)
    author = signed_in(migrated_tenant, people["a"])
    assert REASON in author.get("/notifications/").content.decode()
    # The author keeps reading accepted text, and no longer the pending text a reason may quote.
    link_group(document, [Right.VIEW_ACCEPTED], [people.memberships["a"]], people["r"])
    with schema_context(migrated_tenant.number):
        AccessGroup.objects.get(pk=people.groups["editors"].pk).remove_member(
            people.memberships["a"], by=people["r"]
        )
    page = author.get("/notifications/").content.decode()
    assert "returned without accepting" in page
    assert REASON not in page


def test_the_return_needs_its_csrf_token(
    migrated_tenant: Any, cast: Any, commit_version: Any, repository: Any
) -> None:
    people = cast(editors=("a",), reviewers=("r",))
    document = people.document
    last = commit_version(document, people["a"], FIRST, "edit")
    head = repository.head(document)
    strict = signed_in(migrated_tenant, people["r"], enforce_csrf_checks=True)
    answer = strict.post(
        f"/document/{document.number}/pending/return/",
        {"reason": REASON, "confirmed": last.commit_sha},
    )
    assert answer.status_code == 403
    assert repository.head(document) == head


def test_direction_marks_are_refused(
    migrated_tenant: Any, cast: Any, commit_version: Any, settings: Any
) -> None:
    from editing.reservations import ReasonRefused
    from review import services

    settings.LANGUAGE_CODE = "en"
    people = cast(editors=("a",), reviewers=("r",))
    commit_version(people.document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        for mark in ("‎", "‏", "؜"):
            with pytest.raises(ReasonRefused):
                services.return_run(people.document, people["r"], f"Synthetic{mark} reason")


def test_a_refused_form_keeps_what_was_typed(
    migrated_tenant: Any, cast: Any, commit_version: Any, settings: Any
) -> None:
    settings.LANGUAGE_CODE = "en"
    people = cast(editors=("a",), reviewers=("r",))
    document = people.document
    first = commit_version(document, people["a"], FIRST, "edit")
    second = commit_version(document, people["a"], SECOND, "edit")
    client = signed_in(migrated_tenant, people["r"])
    address = f"/document/{document.number}/pending/return/"
    # Confirmed on an earlier run: the page again, the reason kept, the run as it now stands.
    grown = client.post(address, {"reason": REASON, "confirmed": first.commit_sha})
    assert grown.status_code == 409
    body = grown.content.decode()
    assert f'value="{REASON}"' in body
    assert f'value="{second.commit_sha}"' in body
    # A reason outside the rule: the run listed and the version it names agree.
    refused = client.post(address, {"reason": "x" * 501, "confirmed": first.commit_sha})
    assert refused.status_code == 400
    assert f'value="{second.commit_sha}"' in refused.content.decode()


def test_a_run_returned_already_is_refused_on_the_page(
    migrated_tenant: Any, cast: Any, commit_version: Any, settings: Any
) -> None:
    from review import services

    settings.LANGUAGE_CODE = "en"
    people = cast(editors=("a",), reviewers=("r",))
    document = people.document
    last = commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        services.return_run(document, people["r"], REASON)
    client = signed_in(migrated_tenant, people["r"])
    answer = client.post(
        f"/document/{document.number}/pending/return/",
        {"reason": REASON, "confirmed": last.commit_sha},
        follow=True,
    )
    assert "already returned" in answer.content.decode()
    pending = client.get(f"/document/{document.number}/pending/").content.decode()
    assert 'data-command="return"' not in pending


def test_the_reconciler_believes_the_passport_over_a_return_row(
    migrated_tenant: Any, cast: Any, commit_version: Any
) -> None:
    from documents import reconcile
    from review import services
    from review.models import Return

    people = cast(editors=("a",), reviewers=("r",))
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        services.return_run(document, people["r"], REASON)
        Return.objects.update(reason="Synthetic altered reason")
    found = reconcile.run(tenant=migrated_tenant.number, document=document.number)
    differs = [f for f in found if f.kind == "return_differs"]
    assert differs and "Synthetic altered reason" not in differs[0].detail
    assert REASON not in differs[0].detail
    reconcile.run(tenant=migrated_tenant.number, document=document.number, repair=True)
    with schema_context(migrated_tenant.number):
        assert Return.objects.get().reason == REASON
    again = reconcile.run(tenant=migrated_tenant.number, document=document.number)
    assert not [f for f in again if f.kind == "return_differs"]


def test_a_returns_row_goes_with_its_pruned_version(
    migrated_tenant: Any, cast: Any, commit_version: Any
) -> None:
    from documents import reconcile
    from documents.models import Version
    from review import services
    from review.models import Return

    people = cast(editors=("a",), reviewers=("r",))
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        services.return_run(document, people["r"], REASON)
        returned = Version.objects.get(document=document, kind="return")
        real = returned.commit_sha
        # A row whose commit the repository no longer holds, as after a restore from an older
        # bundle.
        Version.objects.filter(pk=returned.pk).update(commit_sha="f" * 40)
    reconcile.run(
        tenant=migrated_tenant.number, document=document.number, repair=True, prune_rows=True
    )
    with schema_context(migrated_tenant.number):
        assert not Version.objects.filter(commit_sha="f" * 40).exists()
        # The stale row went with its version; the return's own commit was derived again.
        (again,) = Return.objects.select_related("version")
        assert again.version.commit_sha == real


def test_the_return_control_is_disabled_while_reserved(
    migrated_tenant: Any, cast: Any, commit_version: Any, link_group: Any, settings: Any
) -> None:
    from access.rights import Right
    from editing import holds, reservations

    settings.LANGUAGE_CODE = "en"
    people = cast(editors=("a",), reviewers=("r",))
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    link_group(document, [Right.RESERVE_FOR_EDITING], [people.memberships["a"]], people["r"])
    with schema_context(migrated_tenant.number):
        reservations.reserve(holds.take(document, people["a"]), people["a"])
    page = signed_in(migrated_tenant, people["r"]).get(f"/document/{document.number}/pending/")
    body = page.content.decode()
    assert f'href="/document/{document.number}/pending/return/"' not in body
    assert "Return without accepting" in body and "Reserved for editing" in body


def test_a_returned_entry_opens_the_version_returned(
    migrated_tenant: Any, cast: Any, commit_version: Any
) -> None:
    from notifications.models import Notification
    from review import services

    people = cast(editors=("a",), reviewers=("r",))
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    commit_version(document, people["a"], SECOND, "edit")
    with schema_context(migrated_tenant.number):
        services.return_run(document, people["r"], REASON)
        told = Notification.objects.get(user=people["a"], event="returned")
    opened = signed_in(migrated_tenant, people["a"]).get(f"/notifications/{told.pk}/")
    assert opened.status_code == 302
    assert opened["Location"] == f"/document/{document.number}/version/0.0-2/"


def test_an_acceptance_over_a_return_inside_the_run_computes_its_notices(
    migrated_tenant: Any, cast: Any, commit_version: Any
) -> None:
    """Content, a return, content again: the run read across the return commit, and the author
    whose sentence the reviewer's version removed is told at the acceptance."""
    from review import services
    from review.models import CorrectionLine

    people = cast(editors=("a", "b"), reviewers=("r",))
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        services.accept(document, people["r"])
    written = commit_version(document, people["a"], SECOND, "edit")
    with schema_context(migrated_tenant.number):
        services.return_run(document, people["r"], REASON)
    later = SECOND + "\nA copy is kept in the register.\n"
    commit_version(document, people["b"], later, "edit")
    removed = later.replace("The decision is sent the same day.\n\n", "")
    commit_version(document, people["r"], removed, "reviewer_edit")
    with schema_context(migrated_tenant.number):
        services.accept(document, people["r"])
        lines = CorrectionLine.objects.filter(notice__author=people["a"])
        assert lines.exists()
        assert {line.author_version_id for line in lines} == {written.pk}


def test_a_finish_a_release_completes_under_a_return_tells_no_reviewer(
    migrated_tenant: Any, cast: Any, commit_version: Any, member_of: Any
) -> None:
    """The same stop completed by a release that is not the holder's own — an administrator's
    forced release here — rather than by the holder finishing again."""
    from editing import holds, reservations
    from editing import services as editing
    from editing.models import Draft, Hold
    from notifications.models import Notification
    from review import services

    people = cast(editors=("a", "b"), reviewers=("r",))
    document = people.document
    commit_version(document, people["b"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        hold = holds.take(document, people["a"])
        draft = Draft.objects.get(hold=hold)
        draft.content = {**draft.content, "document.md": SECOND}
        draft.save()
        with pytest.raises(editing.InjectedFault):
            editing.commit_draft(hold, people["a"], "Synthetic edit", fault_at=1)
        services.return_run(document, people["r"], REASON)
        told_before = Notification.objects.filter(
            user=people["r"], event="version_committed"
        ).count()
    _client, admin, _membership = member_of("admin.synthetic@example.test", is_tenant_admin=True)
    with schema_context(migrated_tenant.number):
        assert reservations.force_release(Hold.objects.get(pk=hold.pk), admin)
        finished = Hold.objects.get(pk=hold.pk)
        assert finished.release_kind == "finished"
        assert not Draft.objects.filter(hold=hold).exists()
        assert (
            Notification.objects.filter(user=people["r"], event="version_committed").count()
            == told_before
        )


def test_the_reconciler_completes_a_finish_under_a_return_and_tells_no_reviewer(
    migrated_tenant: Any, cast: Any, commit_version: Any
) -> None:
    from documents import reconcile
    from editing import holds
    from editing import services as editing
    from editing.models import Draft, Hold
    from notifications.models import Notification
    from review import services

    people = cast(editors=("a", "b"), reviewers=("r",))
    document = people.document
    commit_version(document, people["b"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        hold = holds.take(document, people["a"])
        draft = Draft.objects.get(hold=hold)
        draft.content = {**draft.content, "document.md": SECOND}
        draft.save()
        with pytest.raises(editing.InjectedFault):
            editing.commit_draft(hold, people["a"], "Synthetic edit", fault_at=1)
        services.return_run(document, people["r"], REASON)
        told_before = Notification.objects.filter(
            user=people["r"], event="version_committed"
        ).count()
    reconcile.run(tenant=migrated_tenant.number, document=document.number, repair=True)
    with schema_context(migrated_tenant.number):
        assert Hold.objects.get(pk=hold.pk).release_kind == "finished"
        assert (
            Notification.objects.filter(user=people["r"], event="version_committed").count()
            == told_before
        )
