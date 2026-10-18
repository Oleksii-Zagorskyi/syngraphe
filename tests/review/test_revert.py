"""Reverting a part operation of the pending run (ST-0063, DL-0446, DL-0474): each row the run's
parts show — an attachment added, removed, replaced or renamed, an appendix added, removed or
renamed, a list reordered, a registered frontmatter key changed — has its inverse staged in the
reviewer's draft with *accept* alone; the reviewer finishes with *accept as* and no part right is
asked; a revert is refused while reserved, held by another, with a kept draft, after the head
moved, for an operation the run did not make or the draft already reverted, where the draft
changed the row's own property, or while an editor of the appendix is open — leaving nobody
holding; acceptance waits for a revert as it waits for an undo; a crafted input finds nothing.

People, groups, titles and texts are synthetic examples; every text is invented English and every
file's bytes are placeholders.
"""

from __future__ import annotations

import hashlib
import html
import re
from typing import Any
from urllib.parse import urlsplit

import pytest
from django.db import transaction
from django.test import Client

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

BODY = "# Purpose\n\nThe first synthetic sentence.\n"
FORMS = {
    1: b"synthetic form one",
    2: b"synthetic form two",
    3: b"synthetic form three",
}
FORM_TWO_REPLACED = b"synthetic form two, replaced in the run"
FORM_FOUR = b"synthetic form four, added in the run"
TEXTS = {
    1: "# Appendix one (example)\n\nThe first appendix sentence.\n",
    2: "# Appendix two (example)\n\nThe second appendix sentence.\n",
    3: "# Appendix three (example)\n\nThe third appendix sentence.\n",
}
TEXT_FOUR = "# Appendix four (example)\n\nThe fourth appendix sentence, added in the run.\n"
SUMMARY = "Synthetic revert of the run's parts"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def attachment(
    number: int, title: str, data: bytes, file_name: str | None = None
) -> dict[str, Any]:
    """An attachment entry as the frontmatter lists it."""
    return {
        "number": number,
        "title": title,
        "file_name": file_name or f"form-{number}.xlsx",
        "sha256": sha(data),
        "bytes": len(data),
    }


def appendix(number: int, title: str) -> dict[str, Any]:
    return {"number": number, "title": title}


BASE_APPENDICES = [
    appendix(1, "Appendix one (example)"),
    appendix(2, "Appendix two (example)"),
    appendix(3, "Appendix three (example)"),
]
BASE_ATTACHMENTS = [
    attachment(1, "Form one (example)", FORMS[1]),
    attachment(2, "Form two (example)", FORMS[2]),
    attachment(3, "Form three (example)", FORMS[3]),
]
BASE_FILES: dict[str, bytes | None] = {
    **{f"appendices/{n}.md": text.encode() for n, text in TEXTS.items()},
    **{f"attachments/{n}": data for n, data in FORMS.items()},
}
# The run: appendix 1 and attachment 1 removed, appendix 2 and attachment 3 renamed, attachment 2's
# file replaced (its name too), appendix 4 and attachment 4 added, and both lists reordered — the
# parts on both sides (2 and 3) the other way round.
RUN_APPENDICES = [
    appendix(3, "Appendix three (example)"),
    appendix(2, "Appendix two, renamed (example)"),
    appendix(4, "Appendix four (example)"),
]
RUN_ATTACHMENTS = [
    attachment(3, "Form three, renamed (example)", FORMS[3]),
    attachment(2, "Form two (example)", FORM_TWO_REPLACED, "form-2-revised.xlsx"),
    attachment(4, "Form four (example)", FORM_FOUR),
]
RUN_FILES: dict[str, bytes | None] = {
    "appendices/1.md": None,
    "appendices/4.md": TEXT_FOUR.encode(),
    "attachments/1": None,
    "attachments/2": FORM_TWO_REPLACED,
    "attachments/4": FORM_FOUR,
}


def signed_in(tenant: Any, user: Any) -> Client:
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(user)
    session = client.session
    session["tenant_number"] = tenant.number
    session.save()
    return client


def flat(markup: str) -> str:
    """The page's text: tags removed, entities read, whitespace collapsed."""
    return " ".join(re.sub(r"<[^>]+>", " ", html.unescape(markup)).split())


def head_of(tenant: Any, document: Any) -> str:
    from documents import gitstore

    head = gitstore.head(gitstore.open_repository(tenant.number, document.number))
    assert head is not None
    return head


def open_holds(tenant: Any, document: Any) -> list[Any]:
    from editing.models import Hold

    with schema_context(tenant.number):
        return list(Hold.objects.filter(document=document, released_at__isnull=True))


def draft_of(tenant: Any, document: Any) -> Any:
    """The draft of the one open hold on `document`."""
    from editing.models import Draft

    with schema_context(tenant.number):
        return Draft.objects.select_related("hold").get(
            hold__document=document, hold__released_at__isnull=True
        )


def lists_of(draft: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    frontmatter = draft.content["frontmatter"]
    return list(frontmatter.get("appendices", [])), list(frontmatter.get("attachments", []))


def numbers(entries: list[dict[str, Any]]) -> list[int]:
    return [int(e["number"]) for e in entries]


def entry_of(entries: list[dict[str, Any]], number: int) -> dict[str, Any]:
    return next(e for e in entries if int(e["number"]) == number)


def reverted(draft: Any) -> list[tuple[str, str]]:
    return [(r["part"], r["change"]) for r in draft.content.get("revert", [])]


def rows_of(tenant: Any, draft: Any, number: int) -> list[tuple[str, bytes | None]]:
    """Each staged row of attachment `number`: its operation and its bytes."""
    with schema_context(tenant.number):
        return [
            (row.operation, bytes(row.content) if row.content is not None else None)
            for row in draft.files.filter(kind="attachment", path=f"attachments/{number}")
        ]


def post_revert(client: Client, document: Any, part: str, change: str, head: str) -> Any:
    return client.post(
        f"/document/{document.number}/pending/revert/",
        {"part": part, "change": change, "head": head},
    )


def redirected(response: Any, path: str) -> bool:
    """Whether `response` is a 303 whose target is `path`."""
    return response.status_code == 303 and urlsplit(response["Location"]).path == path


def to_edit_tab(response: Any, document: Any) -> bool:
    return redirected(response, f"/document/{document.number}/edit/")


def to_pending_tab(response: Any, document: Any) -> bool:
    return redirected(response, f"/document/{document.number}/pending/")


def build(
    tenant: Any,
    cast: Any,
    commit_version: Any,
    accepted_directly: Any,
    *,
    base: dict[str, Any],
    run: dict[str, Any],
    editor: str = "a",
    reviewers: tuple[str, ...] = ("r",),
) -> tuple[Any, Any, str]:
    """A document whose base holds `base`'s parts, accepted, then one run version with `run`'s:
    the cast, the document and the head. `base` and `run` carry `files`, `appendices`,
    `attachments` as `commit_version` takes them. A second cast in one test names other
    people: each name is one synthetic address."""
    people = cast(editors=(editor,), reviewers=reviewers)
    document = people.document
    commit_version(document, people[editor], BODY, **base)
    accepted_directly(document, people[reviewers[0]])
    commit_version(document, people[editor], BODY, **run)
    return people, document, head_of(tenant, document)


FULL_BASE = {"files": BASE_FILES, "appendices": BASE_APPENDICES, "attachments": BASE_ATTACHMENTS}
FULL_RUN = {"files": RUN_FILES, "appendices": RUN_APPENDICES, "attachments": RUN_ATTACHMENTS}
# A base with one form, and a run that uploads a second.
ONE_FORM = {"files": {"attachments/1": FORMS[1]}, "attachments": [BASE_ATTACHMENTS[0]]}
SECOND_FORM = {
    "files": {"attachments/2": FORM_FOUR},
    "attachments": [BASE_ATTACHMENTS[0], attachment(2, "Form two (example)", FORM_FOUR)],
}


def test_each_operation_reverts(
    migrated_tenant: Any, cast: Any, commit_version: Any, accepted_directly: Any
) -> None:
    """Every row the run's parts show, reverted through the route into the reviewer's draft: the
    inverse of each as *Pending edits* describes it (ST-0063), each listed in `content["revert"]`,
    each answered with the edit tab. The reviewer holds *accept* and no part right."""
    from documents.parts import lists_at, part_operations
    from review import services

    people, document, head = build(
        migrated_tenant, cast, commit_version, accepted_directly, base=FULL_BASE, run=FULL_RUN
    )
    with schema_context(migrated_tenant.number):
        run = services.run(document)
        plural = {"appendix": "appendices", "attachment": "attachments"}
        found = {
            (f"{op.kind}:{op.number}" if op.number is not None else plural[op.kind], op.change)
            for op in part_operations(lists_at(services.base(document)), lists_at(run[-1]))
        }
    rows = [
        ("attachment:4", "added"),
        ("attachment:1", "removed"),
        ("attachment:2", "replaced"),
        ("attachment:3", "renamed"),
        ("attachments", "reordered"),
        ("appendix:4", "added"),
        ("appendix:1", "removed"),
        ("appendix:2", "renamed"),
        ("appendices", "reordered"),
    ]
    assert found == set(rows)
    client = signed_in(migrated_tenant, people["r"])
    assert open_holds(migrated_tenant, document) == []

    # Attachment added in the run: its entry dropped and a `remove` row.
    assert to_edit_tab(post_revert(client, document, "attachment:4", "added", head), document)
    [hold] = open_holds(migrated_tenant, document)
    assert hold.user_id == people["r"].pk and hold.last_activity_at is not None
    draft = draft_of(migrated_tenant, document)
    assert numbers(lists_of(draft)[1]) == [3, 2]
    assert rows_of(migrated_tenant, draft, 4) == [("remove", None)]

    # Attachment removed in the run: the base's entry back under its own number at its base
    # position, with an `add` row of the base's bytes.
    assert to_edit_tab(post_revert(client, document, "attachment:1", "removed", head), document)
    draft = draft_of(migrated_tenant, document)
    attachments = lists_of(draft)[1]
    assert numbers(attachments) == [1, 3, 2]
    assert entry_of(attachments, 1) == BASE_ATTACHMENTS[0]
    assert rows_of(migrated_tenant, draft, 1) == [("add", FORMS[1])]
    assert [hold.pk for hold in open_holds(migrated_tenant, document)] == [hold.pk]

    # Attachment replaced in the run: a `replace` row with the base's bytes; the entry's file
    # fields the base's, its title the head's.
    assert to_edit_tab(post_revert(client, document, "attachment:2", "replaced", head), document)
    draft = draft_of(migrated_tenant, document)
    two = entry_of(lists_of(draft)[1], 2)
    assert {k: two[k] for k in ("file_name", "sha256", "bytes")} == {
        k: BASE_ATTACHMENTS[1][k] for k in ("file_name", "sha256", "bytes")
    }
    assert two["title"] == "Form two (example)"
    assert rows_of(migrated_tenant, draft, 2) == [("replace", FORMS[2])]

    # Attachment renamed in the run: the base's title, the file as the head has it.
    assert to_edit_tab(post_revert(client, document, "attachment:3", "renamed", head), document)
    draft = draft_of(migrated_tenant, document)
    three = entry_of(lists_of(draft)[1], 3)
    assert three == BASE_ATTACHMENTS[2]
    assert rows_of(migrated_tenant, draft, 3) == []

    # The attachments reordered in the run: the parts on both sides back in the base's order.
    assert to_edit_tab(post_revert(client, document, "attachments", "reordered", head), document)
    draft = draft_of(migrated_tenant, document)
    attachments = lists_of(draft)[1]
    assert numbers(attachments).index(2) < numbers(attachments).index(3)
    assert attachments == BASE_ATTACHMENTS

    # Appendix added in the run: the entry and its key dropped.
    assert to_edit_tab(post_revert(client, document, "appendix:4", "added", head), document)
    draft = draft_of(migrated_tenant, document)
    assert numbers(lists_of(draft)[0]) == [3, 2]
    assert "appendices/4.md" not in draft.content

    # Appendix removed in the run: the base's entry back at its base position, its key holding
    # the base's text.
    assert to_edit_tab(post_revert(client, document, "appendix:1", "removed", head), document)
    draft = draft_of(migrated_tenant, document)
    appendices = lists_of(draft)[0]
    assert numbers(appendices) == [1, 3, 2]
    assert entry_of(appendices, 1) == BASE_APPENDICES[0]
    assert draft.content["appendices/1.md"] == TEXTS[1]

    # Appendix renamed in the run: the base's title.
    assert to_edit_tab(post_revert(client, document, "appendix:2", "renamed", head), document)
    draft = draft_of(migrated_tenant, document)
    assert entry_of(lists_of(draft)[0], 2) == BASE_APPENDICES[1]

    # The appendices reordered in the run.
    assert to_edit_tab(post_revert(client, document, "appendices", "reordered", head), document)
    draft = draft_of(migrated_tenant, document)
    appendices = lists_of(draft)[0]
    assert numbers(appendices).index(2) < numbers(appendices).index(3)
    assert appendices == BASE_APPENDICES
    # Every other key the draft holds for an appendix is the head's text, untouched.
    assert draft.content["appendices/2.md"] == TEXTS[2]
    assert draft.content["appendices/3.md"] == TEXTS[3]

    # Each revert recorded, with the head it was posted against and what it left in the list.
    assert reverted(draft) == rows
    records = {(r["part"], r["change"]): r for r in draft.content["revert"]}
    assert all(r["head"] == head for r in records.values())
    assert records[("attachment:4", "added")]["staged"] is None
    assert records[("appendix:4", "added")]["staged"] is None
    assert records[("attachment:1", "removed")]["staged"] == BASE_ATTACHMENTS[0]
    assert records[("appendix:1", "removed")]["staged"] == BASE_APPENDICES[0]
    assert records[("attachment:2", "replaced")]["staged"] == BASE_ATTACHMENTS[1]
    # Nothing committed: the head stands, and one hold — the reviewer's — is open.
    assert head_of(migrated_tenant, document) == head
    assert [h.user_id for h in open_holds(migrated_tenant, document)] == [people["r"].pk]
    later = open_holds(migrated_tenant, document)[0]
    assert later.last_activity_at >= hold.last_activity_at


def test_a_revert_needs_accept_alone(
    migrated_tenant: Any,
    cast: Any,
    commit_version: Any,
    accepted_directly: Any,
    queued_authorship: list[Any],
) -> None:
    """A staged revert finished with *accept as*: one version without the reverted part, accepted,
    from a reviewer holding *accept* and no part right."""
    from documents import gitstore
    from documents.models import VersionKind
    from documents.parts import lists_at
    from review import services
    from review.models import Acceptance

    people, document, head = build(
        migrated_tenant, cast, commit_version, accepted_directly, base=ONE_FORM, run=SECOND_FORM
    )
    n = document.number
    client = signed_in(migrated_tenant, people["r"])
    assert to_edit_tab(post_revert(client, document, "attachment:2", "added", head), document)
    with schema_context(migrated_tenant.number):
        before = Acceptance.objects.filter(version__document=document).count()

    sent = client.post(
        f"/document/{n}/edit/send/", {"choice": "accept", "summary": SUMMARY, "head": head}
    )

    assert sent.status_code in (302, 303) and urlsplit(sent["Location"]).path == f"/document/{n}/"
    assert open_holds(migrated_tenant, document) == []
    with schema_context(migrated_tenant.number):
        assert Acceptance.objects.filter(version__document=document).count() == before + 1
        acceptance = services.latest_acceptance(document)
        assert acceptance is not None
        accepted = services.accepted_content_version(acceptance)
        assert accepted.commit_sha != head
        assert accepted.kind == VersionKind.REVIEWER_EDIT
        assert accepted.author_id == people["r"].pk
        assert lists_at(accepted)[1] == [BASE_ATTACHMENTS[0]]
        repo = gitstore.open_repository(migrated_tenant.number, n)
        with pytest.raises(KeyError):
            gitstore.read(repo, "attachments/2", accepted.commit_sha)
        assert gitstore.read(repo, "attachments/1", accepted.commit_sha) == FORMS[1]
        assert services.run(document) == []


def test_refusals_leave_nobody_holding(
    migrated_tenant: Any,
    cast: Any,
    commit_version: Any,
    accepted_directly: Any,
    link_group: Any,
    member_of: Any,
    settings: Any,
) -> None:
    """Each refusal by its reason through the service, and through the route as a message on the
    pending tab; none leaves a hold that was not open before."""
    from access.rights import Right
    from editing import holds, parts, reservations
    from editing import services as editing
    from editing.models import Hold
    from review import revert, services

    settings.LANGUAGE_CODE = "en"
    base = {
        "files": {"appendices/1.md": TEXTS[1].encode(), "attachments/1": FORMS[1]},
        "appendices": [BASE_APPENDICES[0]],
        "attachments": [BASE_ATTACHMENTS[0]],
    }
    run = {
        "appendices": [appendix(1, "Appendix one, renamed (example)")],
        "attachments": [attachment(1, "Form one, renamed (example)", FORMS[1])],
    }
    people = cast(editors=("a",), reviewers=("r",))
    document = people.document
    n = document.number
    # Linked before any hold: a group cannot be linked while the document is held.
    link_group(document, [Right.RESERVE_FOR_EDITING], [people.memberships["a"]], people["a"])
    _, admin, _ = member_of("admin.synthetic@example.test", is_tenant_admin=True)
    commit_version(document, people["a"], BODY, **base)
    accepted_directly(document, people["r"])
    commit_version(document, people["a"], BODY, **run)
    head = head_of(migrated_tenant, document)
    client = signed_in(migrated_tenant, people["r"])

    def refused(reason: str, part: str, change: str, at: str = head) -> None:
        """The service answers `reason`; the route answers the pending tab with a message; the
        holds open before are the holds open after."""
        before = {h.pk for h in open_holds(migrated_tenant, document)}
        with schema_context(migrated_tenant.number):
            with pytest.raises(revert.RevertRefused) as caught:
                revert.apply(document, people["r"], part=part, change=change, head=at)
            assert caught.value.reason == reason
        assert {h.pk for h in open_holds(migrated_tenant, document)} == before
        assert to_pending_tab(post_revert(client, document, part, change, at), document), reason
        assert {h.pk for h in open_holds(migrated_tenant, document)} == before
        page = client.get(f"/document/{n}/pending/")
        assert page.status_code == 200
        assert 'class="notice"' in page.content.decode(), reason

    # Held by another.
    with schema_context(migrated_tenant.number):
        theirs = holds.take(document, people["a"])
    refused("held", "attachment:1", "renamed")
    # Reserved — by anyone, the reviewer included.
    with schema_context(migrated_tenant.number):
        reservations.reserve(theirs, people["a"])
    refused("reserved", "attachment:1", "renamed")
    with schema_context(migrated_tenant.number):
        editing.discard(Hold.objects.get(pk=theirs.pk), people["a"])
    assert open_holds(migrated_tenant, document) == []
    # The reviewer's own draft kept from a hold an administrator ended.
    with schema_context(migrated_tenant.number):
        mine = holds.take(document, people["r"])
        assert reservations.force_release(Hold.objects.get(pk=mine.pk), admin) is True
        assert holds.preserved_draft(document, people["r"]) is not None
    assert open_holds(migrated_tenant, document) == []
    refused("draft_kept", "attachment:1", "renamed")
    discarded = client.post(f"/document/{n}/edit/discard-draft/")
    assert discarded.status_code in (302, 303), discarded.status_code
    with schema_context(migrated_tenant.number):
        assert holds.preserved_draft(document, people["r"]) is None
    # The head the page showed is not the head.
    with schema_context(migrated_tenant.number):
        older = services.base(document).commit_sha
    assert older != head
    refused("run_changed", "attachment:1", "renamed", older)
    # Not among the run's operations.
    refused("nothing_to_revert", "attachment:1", "removed")
    refused("nothing_to_revert", "attachments", "reordered")
    assert open_holds(migrated_tenant, document) == []
    # Reverted once, the same row again finds the draft already as the base had it.
    with schema_context(migrated_tenant.number):
        hold = revert.apply(document, people["r"], part="attachment:1", change="renamed", head=head)
        assert hold.user_id == people["r"].pk
    assert [h.pk for h in open_holds(migrated_tenant, document)] == [hold.pk]
    refused("nothing_to_revert", "attachment:1", "renamed")
    # The reviewer's own draft already differs from the head on the row's property.
    with schema_context(migrated_tenant.number):
        parts.rename_appendix(document, people["r"], 1, title="The reviewer's own title (example)")
    refused("changed_in_draft", "appendix:1", "renamed")
    draft = draft_of(migrated_tenant, document)
    assert entry_of(lists_of(draft)[0], 1)["title"] == "The reviewer's own title (example)"
    assert reverted(draft) == [("attachment:1", "renamed")]
    assert [h.pk for h in open_holds(migrated_tenant, document)] == [hold.pk]


def test_acceptance_waits_for_a_revert(
    migrated_tenant: Any,
    cast: Any,
    commit_version: Any,
    accepted_directly: Any,
    settings: Any,
) -> None:
    """A revert waiting in reviewer B's draft: reviewer A's acceptance is refused `revert_waits`,
    A's pending tab draws the button disabled naming B, and A's return proceeds."""
    from identity.models import User
    from review import revert, services
    from review.models import Acceptance, Return

    settings.LANGUAGE_CODE = "en"
    people, document, head = build(
        migrated_tenant,
        cast,
        commit_version,
        accepted_directly,
        base=ONE_FORM,
        run=SECOND_FORM,
        reviewers=("ra", "rb"),
    )
    n = document.number
    User.objects.filter(pk=people["rb"].pk).update(display_name="Synthetic Reviewer B")
    with schema_context(migrated_tenant.number):
        assert services.revert_waiting(document) is None
        waiting = revert.apply(
            document, people["rb"], part="attachment:2", change="added", head=head
        )
        found = services.revert_waiting(document)
        assert found is not None and found.pk == waiting.pk
        assert services.refusal(document, people["ra"]) == "revert_waits"
        with pytest.raises(services.AcceptRefused) as caught:
            services.accept(document, people["ra"])
        assert caught.value.reason == "revert_waits"
        last = services.run(document)[-1].commit_sha
        accepted_before = Acceptance.objects.filter(version__document=document).count()

    client = signed_in(migrated_tenant, people["ra"])
    page = client.get(f"/document/{n}/pending/")
    assert page.status_code == 200
    markup = page.content.decode()
    assert re.search(
        r'<button class="btn primary" type="button" disabled>Accept the run</button>', markup
    )
    assert (
        "A revert of parts waits in Synthetic Reviewer B’s draft: the run is accepted when they "
        "finish it with “Accept as”."
    ) in flat(markup)
    assert f'href="/document/{n}/pending/accept/"' not in markup

    answered = client.post(f"/document/{n}/pending/accept/", {"confirmed": last})
    assert answered.status_code in (302, 303)
    assert urlsplit(answered["Location"]).path == f"/document/{n}/pending/"
    with schema_context(migrated_tenant.number):
        assert Acceptance.objects.filter(version__document=document).count() == accepted_before
        assert services.return_refusal(document, people["ra"]) is None

    returned = client.post(
        f"/document/{n}/pending/return/",
        {"reason": "Synthetic reason: the added form is not the agreed one", "confirmed": last},
    )
    assert returned.status_code in (302, 303)
    assert urlsplit(returned["Location"]).path == f"/document/{n}/pending/"
    with schema_context(migrated_tenant.number):
        assert Return.objects.filter(version__document=document).count() == 1
    # The revert still waits in B's draft; the head moved by the return's commit alone.
    assert [h.pk for h in open_holds(migrated_tenant, document)] == [waiting.pk]
    assert reverted(draft_of(migrated_tenant, document)) == [("attachment:2", "added")]


def test_a_revert_is_audited(
    migrated_tenant: Any, cast: Any, commit_version: Any, accepted_directly: Any
) -> None:
    from audit.models import AuditEvent
    from review import revert

    people, document, head = build(
        migrated_tenant, cast, commit_version, accepted_directly, base=ONE_FORM, run=SECOND_FORM
    )
    assert not AuditEvent.objects.filter(action="part.reverted").exists()
    with schema_context(migrated_tenant.number):
        revert.apply(document, people["r"], part="attachment:2", change="added", head=head)
    [event] = AuditEvent.objects.filter(action="part.reverted")
    assert event.after == {"number": document.number, "part": "attachment:2", "change": "added"}
    assert event.actor_id == people["r"].pk
    assert event.tenant_id == migrated_tenant.pk


def test_a_registered_frontmatter_change_reverts(
    migrated_tenant: Any,
    cast: Any,
    commit_version: Any,
    accepted_directly: Any,
    frontmatter_kinds: dict[str, Any],
) -> None:
    """A kind registered by the test, its key changed in the run: the older value staged in the
    reviewer's draft and the revert listed; a registered key the run left alone has nothing to
    revert."""
    from documents import gitstore
    from editing import holds, parts
    from review import revert

    parts.register_frontmatter_kind(
        parts.FrontmatterKind(
            "title_page",
            lambda value: isinstance(value, bool),
            lambda older, newer: "Synthetic title page switched",
        )
    )
    parts.register_frontmatter_kind(
        parts.FrontmatterKind("language", lambda value: isinstance(value, str), lambda o, n: "")
    )
    people = cast(editors=("a",), reviewers=("r",))
    document = people.document
    commit_version(document, people["a"], BODY)
    accepted_directly(document, people["r"])
    with schema_context(migrated_tenant.number):
        repo = gitstore.open_repository(migrated_tenant.number, document.number)
        frontmatter, body = holds.split(
            gitstore.read(repo, "document.md", head_of(migrated_tenant, document)).decode()
        )
    assert frontmatter["title_page"] is False
    frontmatter["title_page"] = True
    commit_version(
        document, people["a"], body, files={"document.md": holds.join(frontmatter, body).encode()}
    )
    head = head_of(migrated_tenant, document)
    client = signed_in(migrated_tenant, people["r"])

    # The key the run left alone.
    with schema_context(migrated_tenant.number):
        with pytest.raises(revert.RevertRefused) as caught:
            revert.apply(
                document, people["r"], part="frontmatter:language", change="changed", head=head
            )
        assert caught.value.reason == "nothing_to_revert"
    assert open_holds(migrated_tenant, document) == []

    answer = post_revert(client, document, "frontmatter:title_page", "changed", head)

    assert to_edit_tab(answer, document)
    draft = draft_of(migrated_tenant, document)
    assert draft.hold.user_id == people["r"].pk
    assert draft.content["frontmatter"]["title_page"] is False
    assert reverted(draft) == [("frontmatter:title_page", "changed")]
    assert draft.content["revert"][0]["head"] == head
    # Reverted once, the same key finds the draft already as the base had it.
    assert to_pending_tab(
        post_revert(client, document, "frontmatter:title_page", "changed", head), document
    )
    assert reverted(draft_of(migrated_tenant, document)) == [("frontmatter:title_page", "changed")]


@pytest.mark.parametrize(
    "part, change, head_shape",
    [
        ("appendix:x", "added", "as-is"),
        ("appendix:3", "moved", "as-is"),
        ("appendix:3", "added", "short"),
        ("appendix:3", "added", "upper"),
        ("appendix:3", "replaced", "as-is"),
        ("appendix:3", "reordered", "as-is"),
        ("appendix:3", "changed", "as-is"),
        ("appendices", "added", "as-is"),
        ("attachments", "renamed", "as-is"),
        ("frontmatter:title_page", "renamed", "as-is"),
        ("section:3", "added", "as-is"),
        ("", "added", "as-is"),
    ],
)
def test_crafted_inputs_are_missing(
    migrated_tenant: Any,
    cast: Any,
    commit_version: Any,
    accepted_directly: Any,
    part: str,
    change: str,
    head_shape: str,
) -> None:
    """A `part`, `change` or `head` not of the route's forms answers *Nothing to show here*, and
    nothing is held; so does a GET."""
    base = {
        "files": {"appendices/1.md": TEXTS[1].encode()},
        "appendices": [BASE_APPENDICES[0]],
    }
    run = {
        "files": {"appendices/3.md": TEXTS[3].encode()},
        "appendices": [BASE_APPENDICES[0], BASE_APPENDICES[2]],
    }
    people, document, head = build(
        migrated_tenant, cast, commit_version, accepted_directly, base=base, run=run
    )
    n = document.number
    at = {"as-is": head, "short": head[:-1], "upper": head.upper()}[head_shape]
    client = signed_in(migrated_tenant, people["r"])

    answer = post_revert(client, document, part, change, at)

    assert answer.status_code == 404, (part, change, head_shape)
    assert open_holds(migrated_tenant, document) == []
    assert client.get(f"/document/{n}/pending/revert/").status_code == 404
    assert open_holds(migrated_tenant, document) == []
    # The same route with the run's own row and the head it showed is not missing.
    assert to_edit_tab(post_revert(client, document, "appendix:3", "added", head), document)


def test_the_exemption_covers_the_revert_alone(
    migrated_tenant: Any,
    cast: Any,
    commit_version: Any,
    accepted_directly: Any,
    queued_authorship: list[Any],
) -> None:
    """The revert's removal needs no part right at the commit; a new upload staged beside it in the
    same draft needs *upload attachment*, which the reviewer lacks, and is named."""
    from documents.parts import lists_at
    from editing import parts
    from editing import services as editing
    from editing.models import Draft, Hold
    from review import revert

    people, document, head = build(
        migrated_tenant, cast, commit_version, accepted_directly, base=ONE_FORM, run=SECOND_FORM
    )
    with schema_context(migrated_tenant.number):
        hold = revert.apply(document, people["r"], part="attachment:2", change="added", head=head)
        with transaction.atomic():
            locked = Draft.objects.select_for_update().get(hold=hold)
            made = parts.apply_to_draft(
                locked,
                "add_attachment",
                title="Late upload (example)",
                file_name="late.xlsx",
                data=b"a synthetic late upload",
            )
        assert made == 3
        with pytest.raises(editing.PartRightLost) as lost:
            editing.commit_draft(Hold.objects.get(pk=hold.pk), people["r"], SUMMARY)
        assert lost.value.parts == ["Late upload (example)"]
    assert head_of(migrated_tenant, document) == head
    assert [h.pk for h in open_holds(migrated_tenant, document)] == [hold.pk]

    # Without the upload, the revert alone commits with *accept*.
    other, document2, head2 = build(
        migrated_tenant,
        cast,
        commit_version,
        accepted_directly,
        base=ONE_FORM,
        run=SECOND_FORM,
        editor="c",
        reviewers=("s",),
    )
    with schema_context(migrated_tenant.number):
        hold2 = revert.apply(document2, other["s"], part="attachment:2", change="added", head=head2)
        version = editing.commit_draft(Hold.objects.get(pk=hold2.pk), other["s"], SUMMARY)
        assert version.commit_sha == head_of(migrated_tenant, document2) != head2
        assert lists_at(version)[1] == [BASE_ATTACHMENTS[0]]
    assert open_holds(migrated_tenant, document2) == []


def test_rows_of_one_part_revert_in_any_order(
    migrated_tenant: Any, cast: Any, commit_version: Any, accepted_directly: Any
) -> None:
    """Attachment 2 both replaced and renamed in the run: each row's property is its own, so the
    two revert in either order; the list's reorder reverts after the added part was."""
    base = {
        "files": {f"attachments/{k}": v for k, v in FORMS.items()},
        "attachments": BASE_ATTACHMENTS,
    }
    run = {
        "files": {"attachments/2": FORM_TWO_REPLACED, "attachments/4": FORM_FOUR},
        "attachments": [
            BASE_ATTACHMENTS[2],
            attachment(2, "Form two, renamed (example)", FORM_TWO_REPLACED, "form-2-revised.xlsx"),
            BASE_ATTACHMENTS[0],
            attachment(4, "Form four (example)", FORM_FOUR),
        ],
    }
    first, document_a, head_a = build(
        migrated_tenant, cast, commit_version, accepted_directly, base=base, run=run
    )
    second, document_b, head_b = build(
        migrated_tenant,
        cast,
        commit_version,
        accepted_directly,
        base=base,
        run=run,
        editor="c",
        reviewers=("s",),
    )
    client_a = signed_in(migrated_tenant, first["r"])
    client_b = signed_in(migrated_tenant, second["s"])

    # Replaced, then renamed.
    assert to_edit_tab(
        post_revert(client_a, document_a, "attachment:2", "replaced", head_a), document_a
    )
    two = entry_of(lists_of(draft_of(migrated_tenant, document_a))[1], 2)
    assert two["title"] == "Form two, renamed (example)" and two["sha256"] == sha(FORMS[2])
    assert to_edit_tab(
        post_revert(client_a, document_a, "attachment:2", "renamed", head_a), document_a
    )
    draft_a = draft_of(migrated_tenant, document_a)
    assert entry_of(lists_of(draft_a)[1], 2) == BASE_ATTACHMENTS[1]
    assert rows_of(migrated_tenant, draft_a, 2) == [("replace", FORMS[2])]
    assert reverted(draft_a) == [("attachment:2", "replaced"), ("attachment:2", "renamed")]

    # Renamed, then replaced.
    assert to_edit_tab(
        post_revert(client_b, document_b, "attachment:2", "renamed", head_b), document_b
    )
    two = entry_of(lists_of(draft_of(migrated_tenant, document_b))[1], 2)
    assert two["title"] == "Form two (example)" and two["sha256"] == sha(FORM_TWO_REPLACED)
    assert to_edit_tab(
        post_revert(client_b, document_b, "attachment:2", "replaced", head_b), document_b
    )
    draft_b = draft_of(migrated_tenant, document_b)
    assert entry_of(lists_of(draft_b)[1], 2) == BASE_ATTACHMENTS[1]
    assert rows_of(migrated_tenant, draft_b, 2) == [("replace", FORMS[2])]
    assert reverted(draft_b) == [("attachment:2", "renamed"), ("attachment:2", "replaced")]

    # The addition reverted, then the reorder.
    assert to_edit_tab(
        post_revert(client_a, document_a, "attachment:4", "added", head_a), document_a
    )
    assert numbers(lists_of(draft_of(migrated_tenant, document_a))[1]) == [3, 2, 1]
    assert to_edit_tab(
        post_revert(client_a, document_a, "attachments", "reordered", head_a), document_a
    )
    draft_a = draft_of(migrated_tenant, document_a)
    assert lists_of(draft_a)[1] == BASE_ATTACHMENTS
    assert reverted(draft_a) == [
        ("attachment:2", "replaced"),
        ("attachment:2", "renamed"),
        ("attachment:4", "added"),
        ("attachments", "reordered"),
    ]
    assert head_of(migrated_tenant, document_a) == head_a

    # Both drafts commit with *accept* alone, whichever order the rows were reverted in, and
    # leave the base's parts.
    from documents.parts import lists_at
    from editing import holds, services

    for people, reviewer, document in ((first, "r", document_a), (second, "s", document_b)):
        with schema_context(migrated_tenant.number):
            hold = holds.open_hold(document)
            version = services.commit_draft(hold, people[reviewer], "Reverted (example)")
            assert lists_at(version)[1] == (
                BASE_ATTACHMENTS if document is document_a else lists_of(draft_b)[1]
            )


def test_an_open_editor_stops_an_appendix_revert(
    migrated_tenant: Any, cast: Any, commit_version: Any, accepted_directly: Any
) -> None:
    """The reviewer holds with an editor open on appendix 3, which the run added: reverting the
    addition would drop the text under the editor, so it is refused and nothing is staged."""
    from django.utils import timezone

    from editing import holds
    from editing.models import Draft, OpenEditor
    from review import revert

    base = {
        "files": {"appendices/1.md": TEXTS[1].encode()},
        "appendices": [BASE_APPENDICES[0]],
    }
    run = {
        "files": {"appendices/3.md": TEXTS[3].encode()},
        "appendices": [BASE_APPENDICES[0], BASE_APPENDICES[2]],
    }
    people, document, head = build(
        migrated_tenant, cast, commit_version, accepted_directly, base=base, run=run
    )
    with schema_context(migrated_tenant.number):
        hold = holds.take(document, people["r"])
        draft = Draft.objects.get(hold=hold)
        OpenEditor.objects.create(
            draft=draft,
            file="appendices/3.md",
            range="",
            base_hash=sha(TEXTS[3].encode()),
            last_seen_at=timezone.now(),
        )
        with pytest.raises(revert.RevertRefused) as caught:
            revert.apply(document, people["r"], part="appendix:3", change="added", head=head)
        assert caught.value.reason == "editor_open"
    draft = draft_of(migrated_tenant, document)
    assert numbers(lists_of(draft)[0]) == [1, 3]
    assert draft.content["appendices/3.md"] == TEXTS[3]
    assert reverted(draft) == []
    assert [h.pk for h in open_holds(migrated_tenant, document)] == [hold.pk]
    client = signed_in(migrated_tenant, people["r"])
    assert to_pending_tab(post_revert(client, document, "appendix:3", "added", head), document)
    assert reverted(draft_of(migrated_tenant, document)) == []
    # The editor closed, the same revert stages.
    with schema_context(migrated_tenant.number):
        OpenEditor.objects.filter(draft=draft).update(closed_at=timezone.now())
    assert to_edit_tab(post_revert(client, document, "appendix:3", "added", head), document)
    draft = draft_of(migrated_tenant, document)
    assert numbers(lists_of(draft)[0]) == [1]
    assert "appendices/3.md" not in draft.content
    assert reverted(draft) == [("appendix:3", "added")]


def test_the_reviewer_holding_the_revert_is_told_in_the_second_person(
    migrated_tenant: Any,
    cast: Any,
    commit_version: Any,
    accepted_directly: Any,
    settings: Any,
) -> None:
    """The reviewer whose own draft holds the revert reads that it waits in *their* draft, not
    under their own name."""
    from review import revert

    settings.LANGUAGE_CODE = "en"
    people, document, head = build(
        migrated_tenant,
        cast,
        commit_version,
        accepted_directly,
        base=ONE_FORM,
        run=SECOND_FORM,
        reviewers=("ra",),
    )
    with schema_context(migrated_tenant.number):
        revert.apply(document, people["ra"], part="attachment:2", change="added", head=head)
    markup = signed_in(migrated_tenant, people["ra"]).get(f"/document/{document.number}/pending/")
    assert (
        "A revert of parts waits in your draft: the run is accepted when you finish it with "
        "“Accept as”."
    ) in flat(markup.content.decode())
