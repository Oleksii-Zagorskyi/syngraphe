"""The frame every page of a document draws (DL-0518, DL-0522): the heading with the version
shown, the icons, the path of versions, and no tabs. The path's rules reader by reader are
`test_path.py`'s; this file reads the markup.

Group names, people and titles are synthetic examples; every text is invented English."""

from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

FIRST = "# General provisions\n\nA request for approval is made in writing.\n"
SECOND = FIRST + "\nA copy of the decision goes to the applicant that day.\n"
THIRD = SECOND + "\nThe register of requests is kept by the officer in charge.\n"
FOURTH = THIRD + "\nA request is considered within ten days.\n"

# A path item as the partial draws it: its link and its key, in the order drawn.
GO = re.compile(r'<a class="go" href="([^"]*)" data-go="([^"]*)"( aria-current="location")?>')


def _linked(tenant: int, document: Any, rights: list[Any], memberships: list[Any], by: Any) -> None:
    from access.models import AccessGroup, DocumentGroup

    with schema_context(tenant):
        group = AccessGroup.objects.create(
            name=f"Synthetic group {AccessGroup.objects.count() + 1}",
            created_by=by,
            actor_kind="user",
        )
        for right in rights:
            group.grant(right, by=by)
        for membership in memberships:
            group.add_member(membership, by=by)
        DocumentGroup.link(document, group, by=by)


@pytest.fixture(autouse=True)
def in_english(settings: Any) -> None:
    settings.LANGUAGE_CODE = "en"


def _along_the_path(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> Any:
    """A document made canonical as 1.0, accepted since as 1.1, with a run of two after it:
    1.1-1 and 1.1-2. The author holds *edit*; the reviewer *accept*, *freeze* and *make
    canonical*; the reader *view canonical* alone."""
    from access.rights import Right
    from editions import services as editions
    from review import services as review

    tenant = migrated_tenant.number
    author_client, author, author_membership = member_of("the.author@example.test")
    reviewer_client, reviewer, reviewer_membership = member_of("the.reviewer@example.test")
    reader_client, _, reader_membership = member_of("a.reader@example.test")
    document = new_document(author)
    _linked(tenant, document, [Right.EDIT], [author_membership], author)
    _linked(
        tenant,
        document,
        [Right.ACCEPT, Right.FREEZE, Right.MAKE_CANONICAL],
        [reviewer_membership],
        author,
    )
    _linked(tenant, document, [Right.VIEW_CANONICAL], [reader_membership], author)
    commit_version(document, author, FIRST)
    with schema_context(tenant):
        review.accept(document, reviewer)
        editions.make_canonical(document, reviewer)
    commit_version(document, author, SECOND)
    with schema_context(tenant):
        review.accept(document, reviewer)
    commit_version(document, author, THIRD)
    commit_version(document, author, FOURTH)
    return SimpleNamespace(
        document=document,
        n=document.number,
        author=author_client,
        author_user=author,
        reviewer=reviewer_client,
        reviewer_user=reviewer,
        reader=reader_client,
    )


def _heading(body: str) -> str:
    found = re.search(r"<h1>(.*?)</h1>", body, re.S)
    assert found is not None, body
    return found.group(1)


def _shown(body: str) -> str | None:
    found = re.search(r'<span class="version-number">([^<]*)</span>', _heading(body))
    return found.group(1) if found is not None else None


def _icons(body: str) -> list[tuple[str, str]]:
    return re.findall(r'<a class="icon-btn" href="([^"]*)" aria-label="([^"]*)"', body)


def test_the_path_is_drawn(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    built = _along_the_path(migrated_tenant, member_of, new_document, commit_version)
    n = built.n

    body = built.reviewer.get(f"/document/{n}/").content.decode()

    assert _shown(body) == "1.1-2"
    assert '<nav class="path" aria-label="' in body
    assert GO.findall(body) == [
        (f"/document/{n}/version/1.0/", "canonical", ""),
        (f"/document/{n}/compare/?from=1.0&amp;to=1.1", "history-arc", ""),
        (f"/document/{n}/version/1.1/", "accepted", ""),
        (f"/document/{n}/pending/", "run-arc", ""),
        (f"/document/{n}/", "latest", ' aria-current="location"'),
    ]
    points = re.findall(r'data-go="([^"]*)"[^>]*>([^<]*)</a><span class="sub">([^<]*)', body)
    # A point's link reads its number, an arc's its caption; the second line the rest.
    assert points == [
        ("canonical", "1.0", "canonical version"),
        ("history-arc", "edits between versions", ""),
        ("accepted", "1.1", "latest accepted"),
        ("run-arc", "edits between versions", "2 versions"),
        ("latest", "1.1-2", "latest version · awaiting review"),
    ]
    assert 'class="tabs"' not in body


def test_history_and_info_show_no_version(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    built = _along_the_path(migrated_tenant, member_of, new_document, commit_version)

    for page in ("history/", "info/"):
        body = built.reviewer.get(f"/document/{built.n}/{page}").content.decode()
        assert _shown(body) is None, page
        assert '<nav class="path"' in body, page
        assert "aria-current" not in "".join(m[2] for m in GO.findall(body)), page


def test_every_page_draws_the_frame(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    """The six former tabs' addresses answer the reader with the right and nobody else; every
    page of the family draws the frame with its icons and no tabs; a reader of canonical text
    alone sees the heading and the icons, and no path."""
    from editing import holds

    built = _along_the_path(migrated_tenant, member_of, new_document, commit_version)
    n = built.n
    with schema_context(migrated_tenant.number):
        holds.take(built.document, built.reviewer_user)
    every = ["", "info/", "edit/", "my-edits/", "pending/", "history/"]
    every += ["pending/accept/", "pending/return/", "edit/finish/"]

    for page in every:
        response = built.reviewer.get(f"/document/{n}/{page}")
        body = response.content.decode()
        assert response.status_code == 200, page
        assert '<nav class="path"' in body, page
        assert 'class="tabs"' not in body, page
        assert [label for _, label in _icons(body)] == ["Export", "History", "Info"], page

    for page in ("edit/", "my-edits/", "pending/", "history/"):
        assert built.reader.get(f"/document/{n}/{page}").status_code == 404, page
    for page in ("", "info/"):
        body = built.reader.get(f"/document/{n}/{page}")
        text = body.content.decode()
        assert body.status_code == 200, page
        assert '<nav class="path"' not in text, page
        assert [label for _, label in _icons(text)] == ["Export", "Info"], page
    assert _shown(built.reader.get(f"/document/{n}/").content.decode()) == "1.0"


def test_the_end_reservation_page_draws_the_frame(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    from access.rights import Right

    built = _along_the_path(migrated_tenant, member_of, new_document, commit_version)
    administrator, _, _ = member_of("an.administrator@example.test", is_tenant_admin=True)
    _, keeper, keeper_membership = member_of("the.keeper@example.test")
    _linked(
        migrated_tenant.number,
        built.document,
        [Right.RESERVE_FOR_EDITING],
        [keeper_membership],
        built.author_user,
    )
    from editing import holds, reservations

    with schema_context(migrated_tenant.number):
        reservations.reserve(holds.take(built.document, keeper), keeper)

    response = administrator.get(f"/document/{built.n}/edit/end-reservation/")
    body = response.content.decode()

    assert response.status_code == 200
    assert '<nav class="path"' in body
    assert _shown(body) is None


def test_an_unreadable_record_costs_the_path_never_the_page(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    """A document row with no repository behind it: Info answers, with the icons and no path
    or version, as the heading did before the frame."""
    client, creator, _ = member_of("the.creator@example.test")
    document = make_document(created_by=creator)

    response = client.get(f"/document/{document.number}/info/")
    body = response.content.decode()

    assert response.status_code == 200
    assert '<nav class="path"' not in body
    assert _shown(body) is None
    assert [label for _, label in _icons(body)][-1] == "Info"


def test_no_draft_point_once_edit_is_withdrawn(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    """A holder whose *edit* was withdrawn while they held the document, *view accepted* left:
    the draft point and its pending number are not drawn, and its `edit/` would answer
    not-found."""
    from access.models import AccessGroup
    from access.rights import Right
    from editing import holds
    from identity.models import Membership

    built = _along_the_path(migrated_tenant, member_of, new_document, commit_version)
    membership = Membership.objects.get(user=built.author_user)
    _linked(
        migrated_tenant.number,
        built.document,
        [Right.VIEW_ACCEPTED],
        [membership],
        built.author_user,
    )
    with schema_context(migrated_tenant.number):
        holds.take(built.document, built.author_user)
        for group in AccessGroup.objects.filter(
            granted__right=Right.EDIT, members__membership=membership
        ):
            group.revoke(Right.EDIT, by=built.author_user)

    body = built.author.get(f"/document/{built.n}/").content.decode()

    assert '<nav class="path"' in body
    assert 'data-go="draft"' not in body


def test_a_returned_run_reads_returned_under_a_freeze(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    """A run returned, then the document frozen: the state reads *frozen*, and the path still
    marks the run *returned*."""
    from editions import services as editions
    from review import services as review

    built = _along_the_path(migrated_tenant, member_of, new_document, commit_version)
    with schema_context(migrated_tenant.number):
        review.return_run(built.document, built.reviewer_user, "Synthetic reason to return")
        editions.freeze(built.document, built.reviewer_user)

    body = built.reviewer.get(f"/document/{built.n}/").content.decode()
    points = re.findall(r'data-go="([^"]*)"[^>]*>([^<]*)</a><span class="sub">([^<]*)', body)

    assert ("run-arc", "edits between versions", "returned") in points
    assert ("latest", "1.1-2", "latest version · returned") in points


def test_an_empty_review_page_names_the_latest(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    """Nothing pending: the review page names the version it stands over, as the document's
    address does."""
    from review import services as review

    built = _along_the_path(migrated_tenant, member_of, new_document, commit_version)
    with schema_context(migrated_tenant.number):
        review.accept(built.document, built.reviewer_user)

    body = built.reviewer.get(f"/document/{built.n}/pending/").content.decode()

    assert _shown(body) == "1.2"


def test_a_holder_on_a_frozen_document_stands_on_the_draft(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    """A holder of a frozen document loses *accept* — the one way a holder may stand on a frozen
    document without it: `edit/` says it is frozen and stands on their draft point."""
    from access.models import AccessGroup
    from access.rights import Right
    from editing import holds
    from editions import services as editions
    from identity.models import Membership

    built = _along_the_path(migrated_tenant, member_of, new_document, commit_version)
    membership = Membership.objects.get(user=built.author_user)
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.get(members__membership=membership)
        group.grant(Right.ACCEPT, by=built.author_user)
        editions.freeze(built.document, built.reviewer_user)
        holds.take(built.document, built.author_user)
        group.revoke(Right.ACCEPT, by=built.author_user)

    body = built.author.get(f"/document/{built.n}/edit/").content.decode()

    assert 'data-go="draft" aria-current="location"' in body


def test_more_to_administrators(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    """*Більше* (⋯) to administrators alone (DL-0522): *Groups* locked with the holder's name
    while the document is reserved or held, *End the reservation…* on a reservation, *Force
    release* with the hold's own number on an ordinary hold, *Archive*; on a free document
    *Groups* links to the document's row of the links page."""
    from access.rights import Right
    from editing import holds, reservations
    from editing.models import Hold

    built = _along_the_path(migrated_tenant, member_of, new_document, commit_version)
    administrator, _, _ = member_of("an.administrator@example.test", is_tenant_admin=True)
    _, keeper, keeper_membership = member_of("the.keeper@example.test")
    keeper.display_name = "Synthetic Keeper K"
    keeper.save(update_fields=["display_name"])
    _linked(
        migrated_tenant.number,
        built.document,
        [Right.RESERVE_FOR_EDITING],
        [keeper_membership],
        built.author_user,
    )
    n = built.n

    def more(client: Any) -> str | None:
        body = client.get(f"/document/{n}/").content.decode()
        if '<details class="more">' not in body:
            return None
        return body.split('<details class="more">', 1)[1].split("</details>", 1)[0]

    with schema_context(migrated_tenant.number):
        reservations.reserve(holds.take(built.document, keeper), keeper)
    reserved = more(administrator)
    assert reserved is not None
    assert 'data-command="groups" disabled title="Synthetic Keeper K has reserved it."' in reserved
    assert f'href="/document/{n}/edit/end-reservation/"' in reserved
    assert f'action="/document/{n}/archive/"' in reserved
    assert more(built.reviewer) is None and more(built.reader) is None

    with schema_context(migrated_tenant.number):
        hold = Hold.objects.get(document=built.document, released_at__isnull=True)
        Hold.objects.filter(pk=hold.pk).update(reserved_at=None)
    held = more(administrator)
    assert held is not None
    assert 'disabled title="Synthetic Keeper K is editing."' in held
    assert f'action="/document/{n}/edit/force-release/"' in held
    assert f'name="hold" value="{hold.pk}"' in held

    from django.db import transaction

    with schema_context(migrated_tenant.number), transaction.atomic():
        holds.release(Hold.objects.get(pk=hold.pk), holds.ReleaseKind.FINISHED)
    free = more(administrator)
    assert free is not None
    assert f'href="/administration/tenant/document-links/#link-{n}"' in free
    assert "force-release" not in free and "end-reservation" not in free


def _historian(migrated_tenant: Any, member_of: Any, built: Any) -> Any:
    """A reader of every version: *view all history* and *view pending*."""
    from access.rights import Right
    from identity.models import Membership

    client, user, membership = member_of("a.historian@example.test")
    _linked(
        migrated_tenant.number,
        built.document,
        [Right.VIEW_ALL_HISTORY, Right.VIEW_PENDING],
        [membership],
        built.author_user,
    )
    assert Membership.objects.filter(user=user).exists()
    return client


def test_the_point_is_outlined(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    """A version's page stands on the point that names it, or on none; the banner stays; it
    exports that version from the icon (DL-0518, DL-0519)."""
    built = _along_the_path(migrated_tenant, member_of, new_document, commit_version)
    client = _historian(migrated_tenant, member_of, built)
    n = built.n

    canonical = client.get(f"/document/{n}/version/1.0/").content.decode()
    between = client.get(f"/document/{n}/version/1.1-1/").content.decode()

    outlined = [m[1] for m in GO.findall(canonical) if m[2]]
    assert outlined == ["canonical"]
    assert _shown(canonical) == "1.0"
    assert "Historical version 1.0 — read only" in canonical
    assert (f"/document/{n}/version/1.0/export/", "Export") in _icons(canonical)
    assert 'class="button" href' not in canonical.split('class="document-actions"', 1)[-1][:200]
    assert [m for m in GO.findall(between) if m[2]] == []
    assert _shown(between) == "1.1-1"


def test_the_arc_is_outlined(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    """A comparison stands on the arc that is its pair, or on none; the heading names the pair."""
    built = _along_the_path(migrated_tenant, member_of, new_document, commit_version)
    client = _historian(migrated_tenant, member_of, built)
    n = built.n

    arc = client.get(f"/document/{n}/compare/?from=1.0&to=1.1").content.decode()
    other = client.get(f"/document/{n}/compare/?from=1.0&to=1.1-1").content.decode()

    assert [m[1] for m in GO.findall(arc) if m[2]] == ["history-arc"]
    assert _shown(arc) == "1.0 → 1.1"
    assert [m for m in GO.findall(other) if m[2]] == []
    assert _shown(other) == "1.0 → 1.1-1"


def test_the_export_page_carries_the_frame(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    """The export page draws the document's frame, its heading the first view offered; each view
    carries its number for the heading to follow (DL-0519)."""
    built = _along_the_path(migrated_tenant, member_of, new_document, commit_version)

    body = built.reviewer.get(f"/document/{built.n}/export/").content.decode()
    views = re.findall(r'name="view" value="([a-z_]+)" data-number="([^"]*)"', body)

    assert '<nav class="path"' in body
    assert len(views) >= 2
    assert _shown(body) == views[0][1]
    assert all(number for _, number in views if _ != "my_edits")


def test_appendix_mode(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    """An appendix the canonical version does not list: its point is drawn without a link; the
    versions that list it open the appendix at that version (DL-0522)."""
    from documents.path import frame
    from identity.models import Membership

    built = _along_the_path(migrated_tenant, member_of, new_document, commit_version)
    commit_version(
        built.document,
        built.author_user,
        FOURTH,
        files={"appendices/2.md": b"# A synthetic form\n\nThe form is filled in by hand.\n"},
        appendices=[{"number": 2, "title": "A synthetic form (example)"}],
    )
    from django.test import RequestFactory

    request = RequestFactory().get(f"/document/{built.n}/appendix/2/")
    request.user = built.reviewer_user
    request.tenant = migrated_tenant
    request.membership = Membership.objects.get(user=built.reviewer_user)
    with schema_context(migrated_tenant.number):
        drawn = frame(request, built.document, here="latest", appendix=2, subtitle="A form")

    assert drawn.path is not None
    points = {i.key: i.href for i in drawn.path if i.kind == "point"}
    n = built.n
    assert points == {"canonical": "", "accepted": "", "latest": f"/document/{n}/appendix/2/"}
    acts = [a.command for i in drawn.path for a in i.acts]
    assert acts == ["edit"]
    assert drawn.more is None


def test_the_export_job_names_the_version_exported(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    commit_version: Any,
    queued_exports: Any,
) -> None:
    """The job's page names the version that is being exported, not the latest."""
    built = _along_the_path(migrated_tenant, member_of, new_document, commit_version)

    asked = built.reviewer.post(
        f"/document/{built.n}/export/", {"document": "on", "format": "pdf", "view": "canonical"}
    )
    page = built.reviewer.get(asked["Location"]).content.decode()

    assert asked.status_code == 302
    assert _shown(page) == "1.0"


def test_an_export_at_an_aliased_number_stands_on_its_point(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    """A version accepted keeps its pending number as an alias: exported at the alias, the page
    names and stands on the point by its number, as the version's own page does."""
    built = _along_the_path(migrated_tenant, member_of, new_document, commit_version)
    client = _historian(migrated_tenant, member_of, built)

    page = client.get(f"/document/{built.n}/version/1.0-1/export/").content.decode()

    assert _shown(page) == "1.1"
    assert [m[1] for m in GO.findall(page) if m[2]] == ["accepted"]
