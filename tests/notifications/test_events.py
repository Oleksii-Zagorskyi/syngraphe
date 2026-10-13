"""Who each built act tells (ST-0047, ST-0051): a version committed to the holders of
*accept*, an acceptance to the run's authors, a freeze, its end and an edition to the document's
readers and the organisation's administrators, a group joined to its new member, a document
created to the administrators — never to the person who acted, and never to anyone blocked.

People, groups and texts are synthetic examples."""

from __future__ import annotations

from typing import Any

import pytest
from django.utils import translation

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

BODY = "# Умови\n\nПерше синтетичне речення.\nДруге синтетичне речення.\n"
CHANGED = BODY.replace("Друге синтетичне речення.", "Друге синтетичне речення, уточнене.")
REASON = "Синтетична причина: чекаємо рішення"


def events_of(tenant: Any, user: Any) -> list[str]:
    from notifications.models import Notification

    with schema_context(tenant.number):
        return sorted(Notification.objects.filter(user=user).values_list("event", flat=True))


def acts(tenant: Any, user: Any, event: str) -> list[Any]:
    from notifications.models import Notification

    with schema_context(tenant.number):
        return list(Notification.objects.filter(user=user, event=event).select_related("document"))


def send_for_review(
    tenant: Any, client: Any, document: Any, body: str, choice: str = "send"
) -> None:
    """Take the document, type `body`, and send it for review — or, for a holder of *accept*,
    create the version — as the editor's screens do."""
    from editing.models import Draft

    assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
    with schema_context(tenant.number):
        draft = Draft.objects.get(hold__document=document, hold__released_at__isnull=True)
        draft.content = {**draft.content, "document.md": body}
        draft.save()
    sent = client.post(
        f"/document/{document.number}/edit/send/",
        {"summary": "Синтетична правка", "choice": choice},
    )
    assert sent.status_code == 302, sent.content[:300]


def test_version_committed_goes_to_reviewers_not_the_author(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    from access.rights import Right

    _, editor, editor_membership = member_of("the.editor@example.test")
    _, first, first_membership = member_of("first.reviewer@example.test")
    second_client, second, second_membership = member_of("second.reviewer@example.test")
    document = new_document(editor)
    link_group(document, [Right.EDIT], [editor_membership], editor)
    link_group(document, [Right.ACCEPT], [first_membership, second_membership], editor)

    send_for_review(migrated_tenant, second_client, document, BODY, choice="create")

    [told] = acts(migrated_tenant, first, "version_committed")
    assert told.document_id == document.pk and told.version_id is not None
    assert told.facts == {"version": "0.0-1"}
    assert acts(migrated_tenant, second, "version_committed") == []
    assert acts(migrated_tenant, editor, "version_committed") == []


def test_accepted_goes_to_the_runs_authors(
    migrated_tenant: Any, cast: Any, commit_version: Any
) -> None:
    from review import services

    people = cast(editors=("a", "b"), reviewers=("r",))
    document = people.document
    commit_version(document, people["a"], BODY, "edit")
    commit_version(document, people["b"], CHANGED, "edit")
    with schema_context(migrated_tenant.number):
        services.accept(document, people["r"])

    for author in ("a", "b"):
        [told] = acts(migrated_tenant, people[author], "accepted")
        assert told.facts == {"accepted": "0.1"}
    assert acts(migrated_tenant, people["r"], "accepted") == []
    assert acts(migrated_tenant, people["a"], "correction_notice") == []


def test_frozen_unfrozen_and_canonical_go_to_the_documents_readers(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
) -> None:
    from access.rights import Right
    from editions import services as editions
    from review import services

    _, creator, _ = member_of("the.creator@example.test")
    _, reader, reader_membership = member_of("the.reader@example.test")
    _, editor, editor_membership = member_of("the.editor@example.test")
    _, reviewer, reviewer_membership = member_of("the.reviewer@example.test")
    _, approver, approver_membership = member_of("the.approver@example.test")
    _, admin, _ = member_of("the.admin@example.test", is_tenant_admin=True)
    _, platform, _ = member_of("p.admin@example.test", is_platform_admin=True)
    _, elsewhere, elsewhere_membership = member_of("elsewhere@example.test")
    document = new_document(creator)
    other = new_document(creator, "Інший синтетичний документ")
    link_group(document, [Right.VIEW_CANONICAL], [reader_membership], creator)
    link_group(document, [Right.EDIT], [editor_membership], creator)
    link_group(document, [Right.ACCEPT], [reviewer_membership], creator)
    link_group(document, [Right.FREEZE, Right.MAKE_CANONICAL], [approver_membership], creator)
    link_group(other, [Right.VIEW_ACCEPTED], [elsewhere_membership], creator)
    commit_version(document, editor, BODY, "edit")
    with schema_context(migrated_tenant.number):
        services.accept(document, reviewer)
        editions.freeze(document, approver, REASON)
        editions.make_canonical(document, approver)
        editions.freeze(document, approver, REASON)
        editions.end_freeze(document, REASON)

    for person in (editor, reviewer, admin):
        told = [
            e
            for e in events_of(migrated_tenant, person)
            if e in ("frozen", "made_canonical", "unfrozen")
        ]
        assert told == ["frozen", "frozen", "made_canonical", "unfrozen"], person.email
    # Canonical text alone opens nothing before the first edition (DL-0209): the first freeze
    # is not the canonical reader's to hear of.
    told = [
        e
        for e in events_of(migrated_tenant, reader)
        if e in ("frozen", "made_canonical", "unfrozen")
    ]
    assert told == ["frozen", "made_canonical", "unfrozen"]
    [canonical] = acts(migrated_tenant, reader, "made_canonical")
    assert canonical.facts == {"edition": "1.0"}
    # The approver acted on all but the end of the freeze, which an operator made.
    approver_told = [
        e
        for e in events_of(migrated_tenant, approver)
        if e in ("frozen", "made_canonical", "unfrozen")
    ]
    assert approver_told == ["unfrozen"]
    assert events_of(migrated_tenant, platform) == []
    assert [e for e in events_of(migrated_tenant, elsewhere) if e != "access_granted"] == []


def test_access_granted_to_the_member(migrated_tenant: Any, member_of: Any) -> None:
    from access.models import AccessGroup

    _, admin, _ = member_of("the.admin@example.test", is_tenant_admin=True)
    _, member, membership = member_of("a.member@example.test")
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(
            name="Синтетична група", created_by=admin, actor_kind="user"
        )
        group.add_member(membership, by=admin)
        group.add_member(membership, by=admin)

    [told] = acts(migrated_tenant, member, "access_granted")
    assert told.facts == {"group": str(group.pk)}
    assert events_of(migrated_tenant, admin) == []


def test_document_created_to_administrators(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    from access.rights import Right
    from notifications.events import describe, tag

    _, first, _ = member_of("first.admin@example.test", is_tenant_admin=True)
    _, second, _ = member_of("second.admin@example.test", is_tenant_admin=True)
    _, creator, creator_membership = member_of("the.creator@example.test")
    document = new_document(creator)

    [told] = acts(migrated_tenant, first, "document_created")
    assert told.document_id == document.pk
    assert len(acts(migrated_tenant, second, "document_created")) == 1
    assert acts(migrated_tenant, creator, "document_created") == []
    with schema_context(migrated_tenant.number), translation.override("en"):
        before = tag(told)
        assert "no reviewer assigned" not in describe(told)
    link_group(document, [Right.ACCEPT], [creator_membership], creator)
    with schema_context(migrated_tenant.number), translation.override("en"):
        after = tag(told)
    assert before == "no reviewer assigned"
    assert after is None


def test_a_blocked_member_is_not_notified(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    from access.rights import Right

    editor_client, editor, editor_membership = member_of("the.editor@example.test")
    _, blocked, blocked_membership = member_of("blocked.reviewer@example.test")
    _, active, active_membership = member_of("active.reviewer@example.test")
    document = new_document(editor)
    link_group(document, [Right.EDIT], [editor_membership], editor)
    link_group(document, [Right.ACCEPT], [blocked_membership, active_membership], editor)
    blocked_membership.change("state", "blocked", by=editor)

    send_for_review(migrated_tenant, editor_client, document, BODY)

    assert acts(migrated_tenant, blocked, "version_committed") == []
    assert len(acts(migrated_tenant, active, "version_committed")) == 1


def a_review(member_of: Any, new_document: Any, link_group: Any) -> tuple[Any, ...]:
    """An editor and two reviewers of one document, each in a group of their own role."""
    from access.rights import Right

    editor_client, editor, editor_membership = member_of("the.editor@example.test")
    first_client, first, first_membership = member_of("first.reviewer@example.test")
    _, second, second_membership = member_of("second.reviewer@example.test")
    document = new_document(editor)
    link_group(document, [Right.EDIT], [editor_membership], editor)
    link_group(document, [Right.ACCEPT], [first_membership, second_membership], editor)
    return editor_client, editor, first_client, first, second, document


def stopped_finish(tenant: Any, client: Any, editor: Any, document: Any, step: int) -> Any:
    """The editor's finish, stopped after `step`: the commit made, the hold still open."""
    from editing import services
    from editing.models import Draft, Hold

    assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
    with schema_context(tenant.number):
        hold = Hold.objects.get(document=document, released_at__isnull=True)
        draft = Draft.objects.get(hold=hold)
        draft.content = {**draft.content, "document.md": BODY}
        draft.save()
        with pytest.raises(services.InjectedFault):
            services.commit_draft(hold, editor, "Синтетична правка", fault_at=step)
    return hold


@pytest.mark.parametrize("step", [1, 2])
def test_a_finish_the_reconciler_repairs_tells_the_reviewers_once(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, step: int
) -> None:
    from documents import reconcile

    client, editor, _, first, second, document = a_review(member_of, new_document, link_group)
    stopped_finish(migrated_tenant, client, editor, document, step)

    reconcile.run(tenant=migrated_tenant.number, repair=True)
    reconcile.run(tenant=migrated_tenant.number, repair=True)

    for reviewer in (first, second):
        [told] = acts(migrated_tenant, reviewer, "version_committed")
        assert told.facts == {"version": "0.0-1"}
    assert acts(migrated_tenant, editor, "version_committed") == []


def test_a_finish_resumed_after_its_version_was_accepted_tells_nobody(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    from editing import services as editing
    from review import services

    client, editor, _, first, second, document = a_review(member_of, new_document, link_group)
    hold = stopped_finish(migrated_tenant, client, editor, document, 1)
    with schema_context(migrated_tenant.number):
        services.accept(document, first)
        editing.commit_draft(hold, editor, "Синтетична правка")

    for reviewer in (first, second):
        assert acts(migrated_tenant, reviewer, "version_committed") == []


def test_accept_as_tells_no_other_reviewer_that_a_version_awaits(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    from editing.models import Draft, Hold
    from review import services

    _, _, first_client, first, second, document = a_review(member_of, new_document, link_group)
    assert first_client.post(f"/document/{document.number}/edit/take/").status_code == 200
    with schema_context(migrated_tenant.number):
        hold = Hold.objects.get(document=document, released_at__isnull=True)
        draft = Draft.objects.get(hold=hold)
        draft.content = {**draft.content, "document.md": BODY}
        draft.save()
        services.accept_as(hold, first, "Синтетична правка")

    assert acts(migrated_tenant, second, "version_committed") == []


def test_accepted_reaches_only_authors_who_can_open_the_document(
    migrated_tenant: Any, cast: Any, commit_version: Any
) -> None:
    from access.models import GroupMember
    from review import services

    people = cast(editors=("a", "b", "c", "d"), reviewers=("r",))
    document = people.document
    texts = [BODY, CHANGED, CHANGED + "\nТретє синтетичне речення.\n"]
    texts.append(texts[-1] + "\nЧетверте синтетичне речення.\n")
    for author, text in zip(("a", "b", "c", "d"), texts, strict=True):
        commit_version(document, people[author], text, "edit")
    people["a"].self_blocked = True
    people["a"].save(update_fields=["self_blocked"])
    people.memberships["b"].change("state", "blocked", by=people["r"])
    with schema_context(migrated_tenant.number):
        GroupMember.objects.filter(membership=people.memberships["c"]).delete()
        services.accept(document, people["r"])

    for author in ("a", "b", "c"):
        assert acts(migrated_tenant, people[author], "accepted") == [], author
    assert len(acts(migrated_tenant, people["d"], "accepted")) == 1


def test_people_who_hold_no_viewing_right_are_never_told(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
) -> None:
    from access.rights import Right
    from editions import services as editions
    from identity.models import User
    from review import services

    _, creator, creator_membership = member_of("the.creator@example.test")
    _, historian, historian_membership = member_of("the.historian@example.test")
    _, appender, appender_membership = member_of("the.appender@example.test")
    _, gone, gone_membership = member_of("gone.reviewer@example.test")
    _, absent_admin, _ = member_of("absent.admin@example.test", is_tenant_admin=True)
    User.objects.filter(pk=absent_admin.pk).update(self_blocked=True)
    document = new_document(creator)
    link_group(
        document, [Right.ACCEPT, Right.FREEZE], [creator_membership, gone_membership], creator
    )
    link_group(document, [Right.VIEW_ALL_HISTORY], [historian_membership], creator)
    link_group(document, [Right.CREATE_APPENDIX], [appender_membership], creator)
    User.objects.filter(pk=gone.pk).update(is_tombstoned=True)
    commit_version(document, creator, BODY, "edit")
    with schema_context(migrated_tenant.number):
        services.accept(document, creator)
        editions.freeze(document, creator, REASON)
    new_document(creator, "Ще один синтетичний документ")

    for person in (historian, appender, gone, absent_admin):
        assert [e for e in events_of(migrated_tenant, person) if e != "access_granted"] == [], (
            person.email
        )


def test_a_member_who_adds_themselves_is_not_told(migrated_tenant: Any, member_of: Any) -> None:
    from access.models import AccessGroup

    _, admin, membership = member_of("the.admin@example.test", is_tenant_admin=True)
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(
            name="Синтетична група", created_by=admin, actor_kind="user"
        )
        group.add_member(membership, by=admin)

    assert events_of(migrated_tenant, admin) == []


def test_the_holders_are_the_organisations_members_of_an_active_document(
    migrated_tenant: Any,
    member_of: Any,
    make_tenant_schema: Any,
    new_document: Any,
    link_group: Any,
) -> None:
    from access.models import AccessGroup, GroupMember
    from access.rights import ACTS, LADDER, Right, holders_of
    from documents.models import Document
    from identity.models import Membership

    _, creator, creator_membership = member_of("the.creator@example.test")
    document = new_document(creator)
    group = link_group(document, [Right.VIEW_ACCEPTED], [creator_membership], creator)
    elsewhere = make_tenant_schema("Інша синтетична організація")
    stranger = Membership.objects.create(
        tenant=elsewhere, user=member_of("a.stranger@example.test")[1], actor_kind="system"
    )
    with schema_context(migrated_tenant.number):
        # A row no act writes: a member of another organisation in this one's group.
        GroupMember.objects.create(group=group, membership=stranger, actor_kind="system")
        assert holders_of(LADDER, [document.pk])[document.pk] == {creator.pk}
        Document.objects.filter(pk=document.pk).update(state="archived")
        assert holders_of((*LADDER, *ACTS), [document.pk])[document.pk] == set()
        assert AccessGroup.objects.filter(pk=group.pk).exists()


def test_a_finish_resumed_with_new_text_tells_both_versions(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    """The stopped version is told when its finish is completed, though the holder typed more
    since: both versions await review."""
    from editing import services as editing
    from editing.models import Draft

    client, editor, _, first, second, document = a_review(member_of, new_document, link_group)
    hold = stopped_finish(migrated_tenant, client, editor, document, 1)
    with schema_context(migrated_tenant.number):
        draft = Draft.objects.get(hold=hold)
        draft.content = {**draft.content, "document.md": CHANGED}
        draft.save()
        editing.commit_draft(hold, editor, "Синтетична правка")

    for reviewer in (first, second):
        told = sorted(
            row.facts["version"] for row in acts(migrated_tenant, reviewer, "version_committed")
        )
        assert told == ["0.0-1", "0.0-2"]


def test_accept_as_failing_after_its_version_tells_the_reviewers(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, monkeypatch: Any
) -> None:
    """The version committed and the acceptance failed for any reason: it awaits review, and the
    other reviewers are told so."""
    from editing.models import Draft, Hold
    from review import services

    _, _, first_client, first, second, document = a_review(member_of, new_document, link_group)
    assert first_client.post(f"/document/{document.number}/edit/take/").status_code == 200

    def failing(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("the acceptance could not be written")

    monkeypatch.setattr(services, "accept_locked", failing)
    with schema_context(migrated_tenant.number):
        hold = Hold.objects.get(document=document, released_at__isnull=True)
        draft = Draft.objects.get(hold=hold)
        draft.content = {**draft.content, "document.md": BODY}
        draft.save()
        with pytest.raises(RuntimeError):
            services.accept_as(hold, first, "Синтетична правка")

    [told] = acts(migrated_tenant, second, "version_committed")
    assert told.facts == {"version": "0.0-1"}


def test_an_accept_as_stopped_before_its_acceptance_is_told_by_the_reconciler(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, monkeypatch: Any
) -> None:
    """A process that dies between the version and its acceptance leaves the hold *accepting*:
    the reconciler tells the other reviewers once, and finishes the hold."""
    from documents import reconcile
    from editing.models import Draft, Hold, ReleaseKind
    from review import services

    _, _, first_client, first, second, document = a_review(member_of, new_document, link_group)
    assert first_client.post(f"/document/{document.number}/edit/take/").status_code == 200

    def dies(*args: Any, **kwargs: Any) -> Any:
        raise SystemExit("the process stops")

    monkeypatch.setattr(services, "accept_locked", dies)
    with schema_context(migrated_tenant.number):
        hold = Hold.objects.get(document=document, released_at__isnull=True)
        draft = Draft.objects.get(hold=hold)
        draft.content = {**draft.content, "document.md": BODY}
        draft.save()
        with pytest.raises(SystemExit):
            services.accept_as(hold, first, "Синтетична правка")
        hold.refresh_from_db()
    assert hold.release_kind == ReleaseKind.ACCEPTING
    assert acts(migrated_tenant, second, "version_committed") == []

    monkeypatch.undo()
    reconcile.run(tenant=migrated_tenant.number, repair=True)
    reconcile.run(tenant=migrated_tenant.number, repair=True)

    [told] = acts(migrated_tenant, second, "version_committed")
    assert told.facts == {"version": "0.0-1"}
    with schema_context(migrated_tenant.number):
        hold.refresh_from_db()
        assert not Draft.objects.filter(hold=hold).exists()
    assert hold.release_kind == ReleaseKind.FINISHED


def test_a_completed_accept_as_leaves_its_hold_finished(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    from documents import reconcile
    from editing.models import Draft, Hold, ReleaseKind
    from review import services

    _, _, first_client, first, second, document = a_review(member_of, new_document, link_group)
    assert first_client.post(f"/document/{document.number}/edit/take/").status_code == 200
    with schema_context(migrated_tenant.number):
        hold = Hold.objects.get(document=document, released_at__isnull=True)
        draft = Draft.objects.get(hold=hold)
        draft.content = {**draft.content, "document.md": BODY}
        draft.save()
        services.accept_as(hold, first, "Синтетична правка")
        hold.refresh_from_db()
    assert hold.release_kind == ReleaseKind.FINISHED
    reconcile.run(tenant=migrated_tenant.number, repair=True)
    assert acts(migrated_tenant, second, "version_committed") == []
