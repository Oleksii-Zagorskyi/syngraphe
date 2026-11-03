"""The historical page (DL-0195, DL-0209, DL-0286, DL-0334, DL-0421, ADR-0007): one version shown
read-only at `/document/<n>/version/<number>/` to a reader whose ceiling reaches it, with its
outline, its export, its attachments as that version lists them and its generated views; every
other number answers as
a missing document does. The links that name a version — the canonical edition in the header and
the folder list, the version a correction notice or a notification concerns — lead to it.

People, organisations, groups and texts are synthetic examples: every address ends in
`@example.test`, and every text is invented.
"""

from __future__ import annotations

import html
import re
from types import SimpleNamespace
from typing import Any

import pytest

from access.rights import Right
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

TOKEN = re.compile(rb'name="csrfmiddlewaretoken" value="[^"]+"')
REASON = "Synthetic reason: waiting for the board's decision"
FIRST = "# General provisions\n\nA request for approval is made in writing.\n"
ONLY_IN_SECOND = "The applicant attaches a synthetic record of service."
SECOND = FIRST + f"\n{ONLY_IN_SECOND}\n"
THIRD = FIRST + "\nA request is considered within ten days.\n"
FOURTH = THIRD + "\nA copy of the decision goes to the applicant that day.\n"
FIFTH = FOURTH + "\nThe register of requests is kept by the officer in charge.\n"
SIXTH = FIFTH + "\nRequests are considered in the order they arrive.\n"
WRITTEN = (
    "# General provisions\n\n"
    "A request for approval is made in writing.\n"
    "A request is considered within ten days.\n"
)
CORRECTED = WRITTEN.replace(
    "A request is considered within ten days.",
    "A request is considered within five working days.",
)
READER_I = [Right.VIEW_ALL_HISTORY, Right.VIEW_PENDING]
READER_II = [Right.VIEW_PREVIOUS_CANONICAL, Right.VIEW_CANONICAL]


def standard_history(tenant: Any, edition_cast: Any, commit_version: Any) -> SimpleNamespace:
    """Created (`0.0`); three edits by `a` (`0.0-1` to `0.0-3`); accepted by `r` as `0.1`; a
    freeze and its unfreeze; one edit (`0.1-1`) accepted as `0.2`; a freeze and *make canonical*
    (`1.0`, approving `0.1-1`); two edits by `a` and `b` (`1.0-1`, `1.0-2`). `0.0-2` alone holds
    `ONLY_IN_SECOND`. `.versions` by pending number."""
    from documents.models import Version
    from editions import services as editions
    from review import services as review

    people = edition_cast(editors=("a", "b"))
    document = people.document
    versions: dict[str, Any] = {}
    with schema_context(tenant.number):
        versions["0.0"] = Version.objects.get(document=document, kind="created")
    versions["0.0-1"] = commit_version(document, people["a"], FIRST, "edit")
    versions["0.0-2"] = commit_version(document, people["a"], SECOND, "edit")
    versions["0.0-3"] = commit_version(document, people["a"], THIRD, "edit")
    with schema_context(tenant.number):
        review.accept(document, people["r"])
        editions.freeze(document, people["p"], REASON)
        editions.end_freeze(document, user=people["p"])
    versions["0.1-1"] = commit_version(document, people["a"], FOURTH, "edit")
    with schema_context(tenant.number):
        review.accept(document, people["r"])
        editions.freeze(document, people["p"], REASON)
        editions.make_canonical(document, people["p"])
    versions["1.0-1"] = commit_version(document, people["a"], FIFTH, "edit")
    versions["1.0-2"] = commit_version(document, people["b"], SIXTH, "edit")
    return SimpleNamespace(people=people, document=document, versions=versions)


def reader(
    member_of: Any, link_group: Any, people: Any, name: str, *groups: list[Any]
) -> SimpleNamespace:
    """A member of one new group per entry of `groups`, each holding those rights on the
    document. `.client`, `.user`, `.membership`, `.groups`."""
    client, user, membership = member_of(f"{name}.synthetic@example.test")
    made = [link_group(people.document, rights, [membership], people["a"]) for rights in groups]
    return SimpleNamespace(client=client, user=user, membership=membership, groups=made)


def text_of(body: str) -> str:
    """The page's text: each tag a space, entities read, whitespace collapsed."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", body)))


def links_to(body: str, path: str) -> bool:
    """Whether the page draws a link, a form or a submit control leading to `path`."""
    return any(
        re.search(rf'\b(?:href|action|formaction)="{re.escape(path)}"', tag)
        for tag in re.findall(r"<(?:a|form|button|input)\b[^>]*>", body)
    )


def offered(body: str) -> dict[str, str]:
    """Each offered view's block of the export dialog, by its view."""
    return dict(
        re.findall(r'<div class="offer" data-view="([a-z_]+)">(.*?)</div>', body, re.DOTALL)
    )


def missing(client: Any) -> bytes:
    """What the client is answered for a document number nobody has, the masked token removed."""
    response = client.get("/document/999999/")
    assert response.status_code == 404
    return TOKEN.sub(b"", response.content)


def test_historical_page(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    member_of: Any,
    link_group: Any,
    settings: Any,
) -> None:
    settings.LANGUAGE_CODE = "en"
    history = standard_history(migrated_tenant, edition_cast, commit_version)
    number = history.document.number
    full = reader(member_of, link_group, history.people, "history-i", READER_I)

    response = full.client.get(f"/document/{number}/version/0.0-2/")

    assert response.status_code == 200
    body = response.content.decode()
    shown = text_of(body)
    assert "Historical version 0.0-2 — read only" in shown
    assert re.search(rf'<a\b[^>]*\bhref="/document/{number}/"', body)
    assert ONLY_IN_SECOND in shown
    # The heading's outline link.
    assert re.search(r'<a\b[^>]*\bhref="#[^"]+"', body)
    assert 'href="#h-1"' in body
    # Read-only: no tabs, nothing to edit; the run's arc on the path is this reader's way to it.
    assert f'href="/document/{number}/edit/"' not in body
    assert 'class="tabs"' not in body
    # History is the heading's icon alone.
    assert body.count(f'href="/document/{number}/history/"') == 1
    assert f'<a class="icon-btn" href="/document/{number}/history/"' in body
    assert links_to(body, f"/document/{number}/version/0.0-2/export/")


def test_export_at_a_version(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    member_of: Any,
    link_group: Any,
    exports: Any,
    settings: Any,
) -> None:
    from audit.models import AuditEvent
    from rendering.models import ExportJob

    settings.LANGUAGE_CODE = "en"
    history = standard_history(migrated_tenant, edition_cast, commit_version)
    number, v = history.document.number, history.versions
    full = reader(member_of, link_group, history.people, "history-i", READER_I)
    # Accepted text is marked against the edition before it: before `0.1` there is none.
    first = offered(full.client.get(f"/document/{number}/version/0.1/export/").content.decode())
    [(accepted, alone)] = first.items()
    assert re.search(r"(?<![\d.-])0\.1(?![\d-])", text_of(alone)), alone
    assert f'data-changes="{accepted}"' not in alone

    route = f"/document/{number}/version/1.0-2/export/"
    dialog = full.client.get(route)

    assert dialog.status_code == 200
    offers = offered(dialog.content.decode())
    assert len(offers) == 1, list(offers)
    [(view, block)] = offers.items()
    assert re.search(r"(?<![\d.-])1\.0-2(?![\d-])", text_of(block)), block
    # Pending work is marked against the edition it counts from (DL-0241, DL-0426).
    assert f'data-changes="{view}"' in block
    assert re.search(r"(?<![\d.-])1\.0(?![\d.-])", text_of(block)), block
    assert f'name="changes-{view}" value="marked"' in block

    full.client.post(
        route,
        {"view": view, "format": "pdf", "document": "on", f"changes-{view}": "marked"},
    )

    with schema_context(migrated_tenant.number):
        job = ExportJob.objects.get()
    assert job.version_id == v["1.0-2"].pk
    assert job.baseline_version_id == v["0.1-1"].pk
    assert job.changes == "marked"
    assert job.requested_by_id == full.user.pk
    assert AuditEvent.objects.filter(action="document.exported").count() == 1


def test_unreachable_versions_are_missing(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    member_of: Any,
    link_group: Any,
    settings: Any,
) -> None:
    settings.LANGUAGE_CODE = "en"
    history = standard_history(migrated_tenant, edition_cast, commit_version)
    number = history.document.number
    previous = reader(member_of, link_group, history.people, "history-ii", READER_II)
    accepted = reader(member_of, link_group, history.people, "accepted", [Right.VIEW_ACCEPTED])

    for client, path, status in (
        (previous.client, "0.0-2", 404),
        (previous.client, "9.9", 404),
        (previous.client, "1.0", 200),
        (accepted.client, "1.0", 200),
        (accepted.client, "0.0-2", 404),
    ):
        response = client.get(f"/document/{number}/version/{path}/")
        assert response.status_code == status, (path, status)
        if status == 404:
            assert TOKEN.sub(b"", response.content) == missing(client), path


def test_an_export_at_a_version_rechecks_the_ceiling(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    member_of: Any,
    link_group: Any,
    exports: Any,
    settings: Any,
) -> None:
    """Reader (i) holds *view pending* in one group and *view all history* in another; removed
    from the second, their export of `0.0-2` — beyond the latest accepted version, below which
    *view pending* alone opens nothing — is no longer permitted."""
    from rendering.export.compose import still_permitted
    from rendering.models import ExportJob

    settings.LANGUAGE_CODE = "en"
    history = standard_history(migrated_tenant, edition_cast, commit_version)
    number, v = history.document.number, history.versions
    full = reader(
        member_of,
        link_group,
        history.people,
        "history-i",
        [Right.VIEW_PENDING],
        [Right.VIEW_ALL_HISTORY],
    )
    route = f"/document/{number}/version/0.0-2/export/"
    offers = offered(full.client.get(route).content.decode())
    assert len(offers) == 1, list(offers)
    [view] = offers
    full.client.post(route, {"view": view, "format": "pdf", "document": "on"})
    with schema_context(migrated_tenant.number):
        job = ExportJob.objects.select_related("document", "requested_by").get()
        assert job.version_id == v["0.0-2"].pk
        assert still_permitted(job) is True
        full.groups[1].remove_member(full.membership, by=history.people["a"])

    with schema_context(migrated_tenant.number):
        job = ExportJob.objects.select_related("document", "requested_by").get(pk=job.pk)
        assert still_permitted(job) is False


def test_attachment_at_a_version(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    kit: Any,
    settings: Any,
) -> None:
    """Attachment 1 is served as each version lists it: bytes A at `v1`, bytes B at `v2` (DL-0421).
    `v2` is then made the edition `1.0`, so reader (ii) opens the document, and `v1` stays beyond
    them."""
    from editions import services as editions
    from review import services as review

    settings.LANGUAGE_CODE = "en"
    tenant = migrated_tenant.number
    people = edition_cast()
    number = people.document.number
    bytes_a = b"Synthetic list of time limits, first revision.\n"
    bytes_b = b"Synthetic list of time limits, second revision.\n"
    kit.attach(tenant, people, FIRST, bytes_a)
    kit.attach(tenant, people, SECOND, bytes_b)
    with schema_context(tenant):
        review.accept(people.document, people["r"])
        editions.freeze(people.document, people["p"], REASON)
        editions.make_canonical(people.document, people["p"])
    full = reader(member_of, link_group, people, "history-i", READER_I)
    previous = reader(member_of, link_group, people, "history-ii", READER_II)

    at_v1 = full.client.get(f"/document/{number}/version/0.0-1/attachment/1/")
    at_v2 = full.client.get(f"/document/{number}/version/0.0-2/attachment/1/")
    beyond = previous.client.get(f"/document/{number}/version/0.0-1/attachment/1/")
    edition = previous.client.get(f"/document/{number}/version/1.0/attachment/1/")

    assert at_v1.status_code == 200
    assert at_v1.content == bytes_a
    assert at_v1["Content-Disposition"].startswith("attachment")
    assert 'filename="time-limits.txt"' in at_v1["Content-Disposition"]
    assert at_v2.status_code == 200 and at_v2.content == bytes_b
    assert beyond.status_code == 404
    assert edition.status_code == 200 and edition.content == bytes_b


def test_links_to_a_version_open_its_page(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    new_document: Any,
    member_of: Any,
    link_group: Any,
    settings: Any,
) -> None:
    from notifications.models import Notification
    from review import services as review

    settings.LANGUAGE_CODE = "en"
    history = standard_history(migrated_tenant, edition_cast, commit_version)
    people, number = history.people, history.document.number
    canonical_page = f"/document/{number}/version/1.0/"
    full = reader(member_of, link_group, people, "history-i", READER_I)
    accepted = reader(member_of, link_group, people, "accepted", [Right.VIEW_ACCEPTED])

    # The view tab's header, its text beyond the edition: *open canonical 1.0* is a link.
    view = full.client.get(f"/document/{number}/").content.decode()
    assert re.search(rf'<a\b[^>]*\bhref="{re.escape(canonical_page)}"', view), (
        "no link to the canonical edition in the header"
    )
    # The folder list's *Canonical* cell.
    listing = full.client.get("/folder/1/").content.decode()
    assert f'href="{canonical_page}"' in listing

    # A correction notice of the acceptance `0.1`, on a document of its own.
    noticed = new_document(people["a"], "Synthetic reporting procedure")
    link_group(noticed, [Right.EDIT], [people.memberships["a"]], people["a"])
    link_group(noticed, [Right.ACCEPT], [people.memberships["r"]], people["a"])
    commit_version(noticed, people["a"], WRITTEN, "edit")
    commit_version(noticed, people["r"], CORRECTED, "reviewer_edit")
    with schema_context(migrated_tenant.number):
        review.accept(noticed, people["r"])
        notice = Notification.objects.get(user=people["a"], event="correction_notice")
    page = people.clients["a"].get(f"/notifications/{notice.pk}/")
    assert page.status_code == 200
    assert re.search(
        rf'href="/document/{noticed.number}/version/0\.1/#[^"]+"', page.content.decode()
    )

    # A version committed, told to a reader who may open it and to one who may not.
    with schema_context(migrated_tenant.number):
        told = {
            key: Notification.objects.create(
                user=person.user,
                document=history.document,
                category="document",
                event="version_committed",
                version=history.versions["0.0-2"],
            )
            for key, person in (("may", full), ("may_not", accepted))
        }
    opened = full.client.get(f"/notifications/{told['may'].pk}/")
    assert opened.status_code == 302
    assert opened["Location"] == f"/document/{number}/version/0.0-2/"
    refused = accepted.client.get(f"/notifications/{told['may_not'].pk}/")
    assert refused.status_code == 302
    assert refused["Location"] == f"/document/{number}/"


def test_canonical_reader_opens_the_edition(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    member_of: Any,
    link_group: Any,
    kit: Any,
    settings: Any,
) -> None:
    settings.LANGUAGE_CODE = "en"
    people = edition_cast()
    kit.canonical(migrated_tenant.number, people, commit_version, kit.FIRST)
    number = people.document.number
    canonical = reader(member_of, link_group, people, "canonical", [Right.VIEW_CANONICAL])

    view = canonical.client.get(f"/document/{number}/")

    assert view.status_code == 200
    # The reader views the edition itself, *Viewing canonical 1.0*, with no *open canonical*
    # segment to link (DL-0352); the edition's own page opens for them all the same.
    assert "Viewing canonical 1.0" in view.content.decode()
    assert canonical.client.get(f"/document/{number}/version/1.0/").status_code == 200


def test_generated_views_at_a_version(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    settings: Any,
) -> None:
    """The directory and *see also* of the version shown, not of the latest."""
    from access.rights import Right

    settings.LANGUAGE_CODE = "en"
    client, author, membership = member_of("the.author@example.test")
    document = new_document(author)
    link_group(document, [Right.EDIT, Right.VIEW_ALL_HISTORY], [membership], author)
    roles = '- kind: "role"\n  key: "clerk"\n  label: "the clerk"\n'
    commit_version(
        document,
        author,
        "The [clerk]{.role #clerk} files it, as [the old rules]{.document #4096} say.\n",
        files={"entities.yaml": roles.encode()},
    )
    commit_version(document, author, "Nobody files it.\n", files={"entities.yaml": b"[]\n"})

    earlier = client.get(f"/document/{document.number}/version/0.0-1/").content.decode()
    latest = client.get(f"/document/{document.number}/").content.decode()

    assert "the clerk" in earlier[earlier.index('class="role-directory"') :]
    assert "the old rules" in earlier[earlier.index('class="see-also"') :]
    assert 'class="role-directory"' not in latest and "the old rules" not in latest
