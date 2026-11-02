"""What a reader may see (DL-0209, DL-0272, DL-0352, DL-0358): the latest content version to a
holder of *view pending*, the latest accepted to a holder of *view accepted* — the `created` text
before any acceptance — and the canonical edition's version to a holder of *view canonical*, for
whom a document without an edition does not exist. The header names the version shown and the
canonical edition. Carries the six cases of the alpha's stand-in (`review.visible`) over to
`editions.visible`.

People and groups are synthetic examples; the text is invented.
"""

from __future__ import annotations

import dataclasses
import hashlib
import html
import re
from types import SimpleNamespace
from typing import Any

import pytest

from access.rights import Right
from documents.models import Version
from review import services as review
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

FIRST = "# General provisions\n\nA request for approval is made in writing.\n"
SECOND = FIRST + "\nA copy of the decision goes to the applicant that day.\n"
THIRD = SECOND + "\nThe register of requests is kept by the officer in charge.\n"
REASON = "Synthetic reason: waiting for the board to decide"
ROOT = "/folder/1/"
SCHEME = ("Approval scheme", "scheme.txt", b"Synthetic approval scheme.\n")
ORDER = ("Access granting procedure", "order.txt", b"Synthetic order on access.\n")


def _reader(
    member_of: Any, link_group: Any, document: Any, right: Right, by: Any, name: str
) -> tuple[Any, Any]:
    """A member whose only group linked to `document` holds `right` alone: `(client, user)`."""
    client, user, membership = member_of(f"{name}.synthetic@example.test")
    link_group(document, [right], [membership], by)
    return client, user


def _rows(body: str) -> list[str]:
    """The document numbers the list shows."""
    return re.findall(r'<tr class="document"[^>]*data-number="(\d+)"', body)


def _text(body: str) -> str:
    """The page's text as a reader sees it: tags dropped, entities read, spaces collapsed."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", body)))


def _edition(migrated_tenant: Any, people: Any) -> Any:
    """Freeze and make canonical as the approver; the edition."""
    from editions import services as editions

    with schema_context(migrated_tenant.number):
        editions.freeze(people.document, people["p"], REASON)
        return editions.make_canonical(people.document, people["p"])


def _at_edition_accepted_pending(
    migrated_tenant: Any, edition_cast: Any, commit_version: Any
) -> SimpleNamespace:
    """Edition `1.0` over the first version, `1.1` accepted over the second, `1.1-1` pending in the
    third: the cast and the three content versions."""
    people = edition_cast()
    document = people.document
    canonical = commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        assert review.accept(document, people["r"]).number == "0.1"
    assert _edition(migrated_tenant, people).number == "1.0"
    accepted = commit_version(document, people["a"], SECOND, "edit")
    with schema_context(migrated_tenant.number):
        assert review.accept(document, people["r"]).number == "1.1"
    pending = commit_version(document, people["a"], THIRD, "edit")
    return SimpleNamespace(people=people, canonical=canonical, accepted=accepted, pending=pending)


def _three_readers(member_of: Any, link_group: Any, people: Any) -> dict[str, tuple[Any, Any]]:
    by = people["a"]
    return {
        stance: _reader(member_of, link_group, people.document, right, by, stance)
        for stance, right in (
            ("pending", Right.VIEW_PENDING),
            ("accepted", Right.VIEW_ACCEPTED),
            ("canonical", Right.VIEW_CANONICAL),
        )
    }


# --- reading by rights ---------------------------------------------------------------------


def test_visible_by_rights(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
) -> None:
    from editions.visible import latest_visible, visible

    made = _at_edition_accepted_pending(migrated_tenant, edition_cast, commit_version)
    document = made.people.document
    readers = _three_readers(member_of, link_group, made.people)
    expected = {
        "pending": (made.pending, "1.1-1"),
        "accepted": (made.accepted, "1.1"),
        "canonical": (made.canonical, "1.0"),
    }

    with schema_context(migrated_tenant.number):
        for stance, (_, user) in readers.items():
            version, number = expected[stance]
            latest = latest_visible(user, document)
            assert latest is not None, stance
            assert latest.pk == version.pk, stance
            seen = visible(user, document)
            assert seen is not None, stance
            assert seen.version.pk == version.pk, stance
            assert (seen.number, seen.stance, seen.canonical) == (number, stance, "1.0"), stance


def test_no_edition_means_no_document_for_canonical_readers(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
) -> None:
    """Accepted, and never made canonical: to a reader of canonical text alone the document is
    missing everywhere — the list, the page, its tabs, its attachments."""
    from editions.visible import latest_visible, visible

    people = edition_cast()
    document = people.document
    # One attachment, so its route has something to refuse.
    _commit_with_attachments(migrated_tenant, document, people["a"], FIRST, [SCHEME])
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
    client, reader = _reader(
        member_of, link_group, document, Right.VIEW_CANONICAL, people["a"], "canon"
    )

    with schema_context(migrated_tenant.number):
        assert latest_visible(reader, document) is None
        assert visible(reader, document) is None

    assert str(document.number) not in _rows(client.get(ROOT).content.decode())
    for route in (
        f"/document/{document.number}/",
        f"/document/{document.number}/info/",
        f"/document/{document.number}/attachment/1/",
    ):
        assert client.get(route).status_code == 404, route


def test_header_names_the_version(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    settings: Any,
) -> None:
    """DL-0352's wording: *Viewing version 1.1-1 · open canonical 1.0*, *Viewing version
    1.1 · open canonical 1.0*, *Viewing canonical 1.0*."""
    settings.LANGUAGE_CODE = "en"
    made = _at_edition_accepted_pending(migrated_tenant, edition_cast, commit_version)
    document = made.people.document
    readers = _three_readers(member_of, link_group, made.people)
    route = f"/document/{document.number}/"

    pending = _text(readers["pending"][0].get(route).content.decode())
    assert "Viewing version 1.1-1" in pending
    assert "open canonical 1.0" in pending

    accepted = _text(readers["accepted"][0].get(route).content.decode())
    assert "Viewing version 1.1" in accepted
    assert "open canonical 1.0" in accepted
    assert "1.1-1" not in accepted

    canonical = _text(readers["canonical"][0].get(route).content.decode())
    assert "Viewing canonical 1.0" in canonical
    assert "Viewing version" not in canonical
    assert "1.1-1" not in canonical
    # The preview's wording is gone (DL-0352).
    for body in (pending, accepted, canonical):
        assert "Accepted version" not in body


def test_header_before_any_edition(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    settings: Any,
) -> None:
    """Before any edition, *Viewing version 0.1* without the canonical segment; before any
    acceptance with nothing pending, the created text's own number, *Viewing version 0.0*
    (DL-0352, DL-0358)."""
    settings.LANGUAGE_CODE = "en"
    people = edition_cast()
    document = people.document
    client, _ = _reader(member_of, link_group, document, Right.VIEW_ACCEPTED, people["a"], "reader")
    route = f"/document/{document.number}/"

    created_only = _text(client.get(route).content.decode())
    assert "Viewing version 0.0" in created_only

    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
    accepted = _text(client.get(route).content.decode())
    assert "Viewing version 0.1" in accepted
    assert "open canonical" not in accepted


def test_view_accepted_before_the_first_acceptance(
    migrated_tenant: Any, edition_cast: Any, member_of: Any, link_group: Any
) -> None:
    """Only the `created` commit: it stands as the first accepted baseline (DL-0272), so a
    reader of accepted text sees it as version 0.0 (DL-0358); a reader of canonical text sees
    nothing."""
    from editions.visible import latest_visible, visible

    people = edition_cast()
    document = people.document
    _, accepted_reader = _reader(
        member_of, link_group, document, Right.VIEW_ACCEPTED, people["a"], "reader"
    )
    _, canonical_reader = _reader(
        member_of, link_group, document, Right.VIEW_CANONICAL, people["a"], "canon"
    )

    with schema_context(migrated_tenant.number):
        created = Version.objects.get(document=document, kind="created")
        latest = latest_visible(accepted_reader, document)
        assert latest is not None and latest.pk == created.pk
        seen = visible(accepted_reader, document)
        assert seen is not None and seen.version.pk == created.pk
        # The document's first version (DL-0358).
        assert seen.number == "0.0"
        # The `created` text is the accepted baseline (DL-0272).
        assert (seen.stance, seen.canonical) == ("accepted", None)

        assert latest_visible(canonical_reader, document) is None
        assert visible(canonical_reader, document) is None


# --- carried from the preview's reading rule --------------------------------------------


def test_pending_sees_the_newest_content_version(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
) -> None:
    from editions.visible import latest_visible, visible

    people = edition_cast()
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
    newest = commit_version(document, people["a"], SECOND, "edit")
    _, holder = _reader(member_of, link_group, document, Right.VIEW_PENDING, people["a"], "pend")

    with schema_context(migrated_tenant.number):
        latest = latest_visible(holder, document)
        assert latest is not None and latest.pk == newest.pk
        seen = visible(holder, document)
        assert seen is not None and seen.version.pk == newest.pk
        assert (seen.number, seen.stance, seen.canonical) == ("0.1-1", "pending", None)


def test_pending_with_an_empty_run_sees_the_base(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
) -> None:
    from editions.visible import latest_visible, visible

    people = edition_cast()
    document = people.document
    accepted_content = commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
    _, holder = _reader(member_of, link_group, document, Right.VIEW_PENDING, people["a"], "pend")

    with schema_context(migrated_tenant.number):
        latest = latest_visible(holder, document)
        # The content version the acceptance decided on, not the acceptance's own commit.
        assert latest is not None and latest.pk == accepted_content.pk
        seen = visible(holder, document)
        assert seen is not None and seen.version.pk == accepted_content.pk
        assert seen.number == "0.1"
        # With nothing pending, the reader of pending work reads accepted text; the stance names
        # what the text is, not the right that reached it.
        assert (seen.stance, seen.canonical) == ("accepted", None)


def test_accepted_sees_the_latest_accepted_content_version(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
) -> None:
    from editions.visible import latest_visible, visible

    people = edition_cast()
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
    second = commit_version(document, people["a"], SECOND, "edit")
    with schema_context(migrated_tenant.number):
        assert review.accept(document, people["r"]).number == "0.2"
    commit_version(document, people["a"], THIRD, "edit")
    _, reader = _reader(member_of, link_group, document, Right.VIEW_ACCEPTED, people["a"], "reader")

    with schema_context(migrated_tenant.number):
        latest = latest_visible(reader, document)
        # The later acceptance's content version; the pending third is not the reader's.
        assert latest is not None and latest.pk == second.pk
        seen = visible(reader, document)
        assert seen is not None and seen.version.pk == second.pk
        assert (seen.number, seen.stance, seen.canonical) == ("0.2", "accepted", None)


def test_accepted_before_any_acceptance_sees_the_created_version(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
) -> None:
    """A version pending and nothing accepted: the reader of accepted text sees the `created`
    text, version 0.0, never the pending version."""
    from editions.visible import latest_visible, visible

    people = edition_cast()
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    _, reader = _reader(member_of, link_group, document, Right.VIEW_ACCEPTED, people["a"], "reader")

    with schema_context(migrated_tenant.number):
        created = Version.objects.get(document=document, kind="created")
        latest = latest_visible(reader, document)
        assert latest is not None and latest.pk == created.pk
        seen = visible(reader, document)
        assert seen is not None and seen.version.pk == created.pk
        assert seen.number == "0.0"
        assert seen.canonical is None


def test_view_canonical_alone_sees_nothing(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
) -> None:
    from editions.visible import latest_visible, visible

    people = edition_cast()
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
    _, reader = _reader(member_of, link_group, document, Right.VIEW_CANONICAL, people["a"], "canon")

    with schema_context(migrated_tenant.number):
        assert latest_visible(reader, document) is None
        assert visible(reader, document) is None


def test_no_right_sees_nothing(
    migrated_tenant: Any, edition_cast: Any, member_of: Any, commit_version: Any
) -> None:
    from editions.visible import latest_visible, visible

    people = edition_cast()
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
    _ = _edition(migrated_tenant, people)
    _, stranger, _ = member_of("stranger.synthetic@example.test")

    with schema_context(migrated_tenant.number):
        assert latest_visible(stranger, document) is None
        assert visible(stranger, document) is None


# --- the canonical reader's attachments, and the crash window -----------------------------


def _commit_with_attachments(
    migrated_tenant: Any,
    document: Any,
    user: Any,
    body: str,
    attachments: list[tuple[str, str, bytes]],
) -> Any:
    """One `edit` version whose `document.md` holds `body` and lists `attachments` —
    `(title, file_name, data)`, numbered from 1 — each at `attachments/<n>`, as
    `tests/documents/conftest.py::commit_parts` lays them; its row derived."""
    from documents import bundle, gitstore, services
    from documents.identity import identity_for
    from documents.locks import document_lock

    number = migrated_tenant.number
    with schema_context(number):
        repo = gitstore.open_repository(number, document.number)
        with document_lock(number, document.number):
            head = gitstore.head(repo)
            assert head is not None
            frontmatter, _ = bundle.parse(gitstore.read(repo, "document.md", head).decode())
            entries = [
                {
                    "number": n,
                    "title": title,
                    "file_name": file_name,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "bytes": len(data),
                }
                for n, (title, file_name, data) in enumerate(attachments, 1)
            ]
            text = bundle.render(dataclasses.replace(frontmatter, attachments=entries), body)
            files = {"document.md": text.encode("utf-8")}
            for n, (_, _, data) in enumerate(attachments, 1):
                files[f"attachments/{n}"] = data
            sha = gitstore.commit(
                repo, files, identity_for(user), "Synthetic edit", gitstore.Kind.EDIT
            )
            return services.derive_version(document, gitstore.commit_at(repo, sha), user)


def test_canonical_reader_reads_the_edition(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
) -> None:
    """A holder of *view canonical* of a document with an edition gets
    the *View* tab, finds the document in the list, and downloads the edition's attachments — not
    those of the version accepted since."""
    from audit.models import AuditEvent

    people = edition_cast()
    document = people.document
    canonical = _commit_with_attachments(migrated_tenant, document, people["a"], FIRST, [SCHEME])
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
    _edition(migrated_tenant, people)
    # Attachment 2 arrives after the edition, accepted as `1.1`.
    _commit_with_attachments(migrated_tenant, document, people["a"], SECOND, [SCHEME, ORDER])
    with schema_context(migrated_tenant.number):
        assert review.accept(document, people["r"]).number == "1.1"
    client, reader = _reader(
        member_of, link_group, document, Right.VIEW_CANONICAL, people["a"], "canon"
    )
    accepted_client, _ = _reader(
        member_of, link_group, document, Right.VIEW_ACCEPTED, people["a"], "reader"
    )

    assert str(document.number) in _rows(client.get(ROOT).content.decode())
    page = client.get(f"/document/{document.number}/")
    assert page.status_code == 200
    body = page.content.decode()
    assert "A request for approval is made in writing." in body
    assert "A copy of the decision goes to the applicant that day." not in body

    served = client.get(f"/document/{document.number}/attachment/1/")
    assert served.status_code == 200
    assert served.content == SCHEME[2]
    event = AuditEvent.objects.get(action="attachment.downloaded", actor_id=reader.pk)
    assert event.after["commit"] == canonical.commit_sha

    # The attachment the edition does not list is missing to the canonical reader alone.
    assert client.get(f"/document/{document.number}/attachment/2/").status_code == 404
    later = accepted_client.get(f"/document/{document.number}/attachment/2/")
    assert later.status_code == 200 and later.content == ORDER[2]


def test_an_approval_without_its_edition_row_opens_nothing(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
) -> None:
    """Stopped after the tag, before the `EDITION` row: *an edition exists* is read from
    `EDITION`, so the reader of canonical text still finds nothing — the
    list, the page and `visible` agree until the row is derived."""
    from editions import services as editions
    from editions import visible as visibility

    people = edition_cast()
    document = people.document
    commit_version(document, people["a"], FIRST, "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, people["r"])
        editions.freeze(document, people["p"], REASON)
        with pytest.raises(review.InjectedFault):
            editions.make_canonical(document, people["p"], fault_at=2)
    client, reader = _reader(
        member_of, link_group, document, Right.VIEW_CANONICAL, people["a"], "canon"
    )

    with schema_context(migrated_tenant.number):
        assert visibility.visible(reader, document) is None
    assert str(document.number) not in _rows(client.get(ROOT).content.decode())
    assert client.get(f"/document/{document.number}/").status_code == 404
