"""The holder's return to a draft kept by a released hold (ST-0070, DL-0219, DL-0225, DL-0318,
DL-0379, DL-0381): with nobody having committed since the draft was started, the holder takes the
document back and the same draft moves onto the new hold; otherwise the draft opens read-only as
changes against the current text, and may be discarded. The same return follows a hold released
by an administrator, for inactivity or by a block, and it is the holder's alone.

People, organisations, groups and texts are synthetic examples: every address ends in
`@example.test`, and every text is invented."""

from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import pytest
from django.db import transaction

from access.rights import Right
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

REASON = "Synthetic reason: an urgent budget correction is needed"
BODY = "# Synthetic terms\n\nThe first synthetic sentence.\nThe second synthetic sentence.\n"
DRAFT_SENTENCE = "The draft's owner added a wholly new sentence on time limits."
DRAFT = BODY + "\n" + DRAFT_SENTENCE + "\n"
LATER = BODY.replace(
    "The second synthetic sentence.", "The second synthetic sentence, clarified by another editor."
)
LATEST = LATER.replace("The first synthetic sentence.", "The first synthetic sentence, edited too.")
SAME_ORIGIN = {"Sec-Fetch-Site": "same-origin"}


@dataclass
class Scene:
    document: Any
    holder: Any
    holder_client: Any
    other: Any
    other_client: Any
    reviewer: Any
    admin: Any
    admin_client: Any


def redirected_to(response: Any, path: str) -> bool:
    """Whether `response` is a 302 whose target is `path`."""
    return response.status_code == 302 and urlsplit(response["Location"]).path == path


def posts_to(body: str, path: str) -> bool:
    """Whether the page draws a form, or a submit control, posting to `path`."""
    return any(
        re.search(rf'\b(?:action|formaction)="{re.escape(path)}"', tag)
        for tag in re.findall(r"<(?:form|button|input)\b[^>]*>", body)
    )


def text_of(body: str) -> str:
    """The page's text: tags removed, entities read, whitespace collapsed."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", body)))


def against_options(body: str) -> list[tuple[str, str]]:
    """The `(value, label)` of every option of the page's `<select name="against">`."""
    found = re.search(r'<select\b[^>]*\bname="against"[^>]*>(.*?)</select>', body, re.S)
    assert found is not None, "no comparison to choose"
    return [
        (html.unescape(value), text_of(label).strip())
        for value, label in re.findall(
            r'<option\b[^>]*\bvalue="([^"]*)"[^>]*>(.*?)</option>', found.group(1), re.S
        )
    ]


def offers(options: list[tuple[str, str]], number: str) -> bool:
    """Whether an option names version `number` — `0.1` never matching inside `0.1-2`."""
    pattern = rf"(?<![\d.-]){re.escape(number)}(?![\d-])"
    return any(re.search(pattern, f"{value} {label}") for value, label in options)


def commit_version(tenant: Any, document: Any, user: Any, body: str) -> Any:
    """Commit `body` as the body of `document.md` on the head as `user`, kind `edit`, and derive
    its `VERSION` row."""
    from documents import gitstore, services
    from documents.identity import identity_for
    from documents.locks import document_lock
    from editing import holds

    number = tenant.number
    with schema_context(number):
        repo = gitstore.open_repository(number, document.number)
        with document_lock(number, document.number):
            head = gitstore.head(repo)
            assert head is not None
            frontmatter, _ = holds.split(gitstore.read(repo, holds.BODY, head).decode())
            sha = gitstore.commit(
                repo,
                {holds.BODY: holds.join(frontmatter, body).encode("utf-8")},
                identity_for(user),
                "Synthetic edit",
                gitstore.Kind("edit"),
            )
            return services.derive_version(document, gitstore.commit_at(repo, sha), user)


def head_of(tenant: Any, document: Any) -> str:
    from documents import gitstore

    head = gitstore.head(gitstore.open_repository(tenant.number, document.number))
    assert head is not None
    return head


def open_holds(tenant: Any, document: Any) -> list[Any]:
    from editing.models import Hold

    with schema_context(tenant.number):
        return list(Hold.objects.filter(document=document, released_at__isnull=True))


def draft_of(tenant: Any, pk: Any) -> Any:
    from editing.models import Draft

    with schema_context(tenant.number):
        return Draft.objects.filter(pk=pk).first()


@pytest.fixture
def scene(member_of: Any, new_document: Any, link_group: Any) -> Scene:
    """A document whose holder may reserve it, another editor, a reviewer holding *accept*, and a
    tenant administrator; nobody holds it yet."""
    _, author, _ = member_of("author.synthetic@example.test")
    holder_client, holder, holder_membership = member_of("holder.synthetic@example.test")
    holder.display_name = "Synthetic Owner"
    holder.save(update_fields=["display_name"])
    other_client, other, other_membership = member_of("other.synthetic@example.test")
    _, reviewer, reviewer_membership = member_of("reviewer.synthetic@example.test")
    admin_client, admin, _ = member_of("admin.synthetic@example.test", is_tenant_admin=True)
    admin.display_name = "Synthetic Administrator"
    admin.save(update_fields=["display_name"])
    document = new_document(author)
    link_group(document, [Right.EDIT, Right.RESERVE_FOR_EDITING], [holder_membership], author)
    link_group(document, [Right.EDIT], [other_membership], author)
    link_group(document, [Right.ACCEPT], [reviewer_membership], author)
    return Scene(
        document, holder, holder_client, other, other_client, reviewer, admin, admin_client
    )


def take_with_draft(tenant: Any, scene: Scene) -> tuple[Any, Any]:
    """The holder takes the document and writes `DRAFT` into the draft; the hold and the draft."""
    from editing.models import Draft, Hold

    number = scene.document.number
    assert scene.holder_client.post(f"/document/{number}/edit/take/").status_code == 200
    with schema_context(tenant.number):
        draft = Draft.objects.select_related("hold").get(
            hold__document=scene.document, hold__released_at__isnull=True
        )
        draft.content = {**draft.content, "document.md": DRAFT}
        draft.save()
        draft.refresh_from_db()
        hold = Hold.objects.get(pk=draft.hold_id)
    return hold, draft


def ended_reservation(tenant: Any, scene: Scene) -> tuple[Any, Any]:
    """The holder takes, writes the draft and reserves; the administrator ends the reservation
    with `REASON` through the screens. The ended hold and its draft."""
    hold, draft = take_with_draft(tenant, scene)
    number = scene.document.number
    reserved = scene.holder_client.post(f"/document/{number}/edit/reserve/")
    assert redirected_to(reserved, f"/document/{number}/edit/"), reserved.status_code
    ended = scene.admin_client.post(
        f"/document/{number}/edit/end-reservation/", {"reason": REASON, "hold": str(hold.pk)}
    )
    assert redirected_to(ended, f"/document/{number}/"), ended.status_code
    assert open_holds(tenant, scene.document) == []
    return hold, draft


def test_take_back_restores_the_draft(migrated_tenant: Any, scene: Scene, settings: Any) -> None:
    from editing.models import Hold

    settings.LANGUAGE_CODE = "en"
    ended, draft = ended_reservation(migrated_tenant, scene)
    number = scene.document.number

    page = scene.holder_client.get(f"/document/{number}/edit/", headers=SAME_ORIGIN)

    assert page.status_code == 200
    body = page.content.decode()
    assert open_holds(migrated_tenant, scene.document) == []
    assert 'id="editor"' not in body
    shown = text_of(body)
    assert scene.admin.display_name in shown or scene.admin.email in shown
    assert REASON in shown
    # When: the day the reservation was ended, in the display timezone.
    from zoneinfo import ZoneInfo

    from django.conf import settings as django_settings
    from django.utils import formats, timezone

    with schema_context(migrated_tenant.number):
        ended_at = Hold.objects.get(pk=ended.pk).released_at
    local = timezone.localtime(ended_at, ZoneInfo(django_settings.DISPLAY_TIMEZONE))
    assert formats.date_format(local, "DATE_FORMAT") in shown
    assert posts_to(body, f"/document/{number}/edit/take-back/")

    taken = scene.holder_client.post(f"/document/{number}/edit/take-back/")

    assert redirected_to(taken, f"/document/{number}/edit/"), taken.status_code
    [hold] = open_holds(migrated_tenant, scene.document)
    assert hold.user_id == scene.holder.pk
    assert hold.pk != ended.pk
    moved = draft_of(migrated_tenant, draft.pk)
    assert moved is not None and moved.hold_id == hold.pk
    assert moved.base_commit == draft.base_commit
    assert moved.content == draft.content
    with schema_context(migrated_tenant.number):
        before = Hold.objects.get(pk=ended.pk)
    assert before.released_at is not None and before.release_kind == "forced"


def test_moved_head_opens_read_only(migrated_tenant: Any, scene: Scene, settings: Any) -> None:
    from review import services

    settings.LANGUAGE_CODE = "en"
    commit_version(migrated_tenant, scene.document, scene.other, BODY)
    with schema_context(migrated_tenant.number):
        services.accept(scene.document, scene.reviewer)
    ended_reservation(migrated_tenant, scene)
    commit_version(migrated_tenant, scene.document, scene.other, LATER)
    commit_version(migrated_tenant, scene.document, scene.other, LATEST)
    number = scene.document.number

    page = scene.holder_client.get(f"/document/{number}/edit/", headers=SAME_ORIGIN)

    assert page.status_code == 200
    body = page.content.decode()
    assert open_holds(migrated_tenant, scene.document) == []
    assert not posts_to(body, f"/document/{number}/edit/take-back/")
    assert DRAFT_SENTENCE in text_of(body)
    options = against_options(body)
    # The latest accepted version, and every content version after it.
    for wanted in ("0.1", "0.1-1", "0.1-2"):
        assert offers(options, wanted), (wanted, options)
    for value, _ in options:
        if value:
            compared = scene.holder_client.get(f"/document/{number}/edit/", {"against": value})
            assert compared.status_code == 200, value
    assert open_holds(migrated_tenant, scene.document) == []


def test_take_back_refused_once_the_head_moved(
    migrated_tenant: Any, scene: Scene, settings: Any
) -> None:
    settings.LANGUAGE_CODE = "en"
    ended, draft = ended_reservation(migrated_tenant, scene)
    number = scene.document.number
    offered = scene.holder_client.get(f"/document/{number}/edit/", headers=SAME_ORIGIN)
    assert posts_to(offered.content.decode(), f"/document/{number}/edit/take-back/")
    commit_version(migrated_tenant, scene.document, scene.other, LATER)

    taken = scene.holder_client.post(f"/document/{number}/edit/take-back/")

    assert redirected_to(taken, f"/document/{number}/edit/"), taken.status_code
    assert open_holds(migrated_tenant, scene.document) == []
    kept = draft_of(migrated_tenant, draft.pk)
    assert kept is not None and kept.hold_id == ended.pk
    assert kept.content == draft.content


def test_discard_the_preserved_draft(migrated_tenant: Any, scene: Scene, settings: Any) -> None:
    from django.utils import timezone

    from audit.models import AuditEvent
    from editing.models import DraftFile

    settings.LANGUAGE_CODE = "en"
    _, draft = ended_reservation(migrated_tenant, scene)
    image = b"synthetic image bytes"
    with schema_context(migrated_tenant.number):
        upload = DraftFile.objects.create(
            draft_id=draft.pk,
            kind="image",
            path="images/synthetic.png",
            operation="add",
            content=image,
            file_name="synthetic.png",
            sha256=hashlib.sha256(image).hexdigest(),
            at=timezone.now(),
        )
    commit_version(migrated_tenant, scene.document, scene.other, LATER)
    number = scene.document.number
    read_only = scene.holder_client.get(f"/document/{number}/edit/").content.decode()
    assert 'name="against"' in read_only
    assert posts_to(read_only, f"/document/{number}/edit/discard-draft/")

    discarded = scene.holder_client.post(f"/document/{number}/edit/discard-draft/")

    assert redirected_to(discarded, f"/document/{number}/edit/"), discarded.status_code
    assert draft_of(migrated_tenant, draft.pk) is None
    with schema_context(migrated_tenant.number):
        assert not DraftFile.objects.filter(pk=upload.pk).exists()
    assert AuditEvent.objects.filter(action="document.draft_discarded").count() == 1
    body = scene.holder_client.get(f"/document/{number}/edit/").content.decode()
    assert 'id="editor"' in body
    assert 'class="band end"' not in body
    assert 'name="against"' not in body
    assert not posts_to(body, f"/document/{number}/edit/discard-draft/")
    assert not posts_to(body, f"/document/{number}/edit/take-back/")


@pytest.mark.parametrize("kind", ["inactivity", "blocked"])
def test_the_return_follows_any_kept_draft(
    migrated_tenant: Any, scene: Scene, settings: Any, kind: str
) -> None:
    from documents.locks import document_lock
    from editing import holds
    from editing.models import Hold, ReleaseKind
    from identity import blocking

    settings.LANGUAGE_CODE = "en"
    ended, draft = take_with_draft(migrated_tenant, scene)
    number = scene.document.number
    if kind == "inactivity":
        with schema_context(migrated_tenant.number):
            hold = Hold.objects.get(pk=ended.pk)
            with document_lock(migrated_tenant.number, number), transaction.atomic():
                assert holds.release(hold, ReleaseKind.INACTIVITY) is True
    else:
        with transaction.atomic():
            released = blocking.end_holds(
                [migrated_tenant], by=scene.admin, cause=blocking.BLOCKED, user=scene.holder
            )
        assert released == 1
    with schema_context(migrated_tenant.number):
        assert Hold.objects.get(pk=ended.pk).release_kind == kind
    assert open_holds(migrated_tenant, scene.document) == []

    page = scene.holder_client.get(f"/document/{number}/edit/", headers=SAME_ORIGIN)

    body = page.content.decode()
    assert page.status_code == 200
    assert open_holds(migrated_tenant, scene.document) == []
    assert 'id="editor"' not in body
    assert posts_to(body, f"/document/{number}/edit/take-back/")

    taken = scene.holder_client.post(f"/document/{number}/edit/take-back/")

    assert redirected_to(taken, f"/document/{number}/edit/"), taken.status_code
    [hold] = open_holds(migrated_tenant, scene.document)
    assert hold.user_id == scene.holder.pk and hold.pk != ended.pk
    moved = draft_of(migrated_tenant, draft.pk)
    assert moved is not None and moved.hold_id == hold.pk
    assert moved.base_commit == draft.base_commit
    assert moved.content == draft.content


def test_the_return_is_the_holders_alone(migrated_tenant: Any, scene: Scene) -> None:
    from editing.models import Draft

    ended, _ = ended_reservation(migrated_tenant, scene)
    with schema_context(migrated_tenant.number):
        draft = Draft.objects.get(hold=ended)
    number = scene.document.number
    assert head_of(migrated_tenant, scene.document) == draft.base_commit

    for route in ("take-back", "discard-draft"):
        refused = scene.other_client.post(f"/document/{number}/edit/{route}/")
        assert refused.status_code == 404, route

    kept = draft_of(migrated_tenant, draft.pk)
    assert kept is not None
    assert kept.hold_id == ended.pk
    assert kept.base_commit == draft.base_commit
    assert kept.content == draft.content
    assert kept.updated_at == draft.updated_at
    assert open_holds(migrated_tenant, scene.document) == []


def test_the_read_only_view_marks_the_changes_and_escapes_the_draft(
    migrated_tenant: Any, scene: Scene, settings: Any
) -> None:
    """The comparison is drawn as changes; a kept draft the whitelist refuses — it was never
    checked, since a capture takes any text — is shown as plain text, never as markup."""
    from editing.models import Draft

    settings.LANGUAGE_CODE = "en"
    _, draft = ended_reservation(migrated_tenant, scene)
    commit_version(migrated_tenant, scene.document, scene.other, LATER)
    number = scene.document.number
    page = scene.holder_client.get(f"/document/{number}/edit/").content.decode()
    assert "<ins" in page and "&lt;ins" not in page
    assert page.count('class="band') == 1
    with schema_context(migrated_tenant.number):
        Draft.objects.filter(pk=draft.pk).update(
            content={**draft.content, "document.md": DRAFT + "\n<script>alert(1)</script>\n"}
        )
    page = scene.holder_client.get(f"/document/{number}/edit/").content.decode()
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page


def test_a_stopped_finish_is_not_a_kept_draft(migrated_tenant: Any, scene: Scene) -> None:
    """A finish that stopped after releasing its hold and before deleting its draft leaves no work
    at risk: the commit holds it, and the next visit opens the editor as usual."""
    from editing import services
    from editing.models import Hold

    hold, _ = take_with_draft(migrated_tenant, scene)
    with schema_context(migrated_tenant.number), pytest.raises(services.InjectedFault):
        services.commit_draft(
            Hold.objects.get(pk=hold.pk), scene.holder, "Synthetic edit", fault_at=3
        )
    number = scene.document.number
    page = scene.holder_client.get(f"/document/{number}/edit/", headers=SAME_ORIGIN)
    assert 'id="editor"' in page.content.decode()
    assert scene.holder_client.post(f"/document/{number}/edit/take/").status_code == 200


def test_the_operators_release_is_told_without_its_note(
    migrated_tenant: Any, scene: Scene, settings: Any
) -> None:
    """The operator's `release_hold` records its note for the audit trail; the holder reads that
    the platform's operator ended their editing, and nothing of the note."""
    from django.core.management import call_command

    settings.LANGUAGE_CODE = "en"
    take_with_draft(migrated_tenant, scene)
    note = "Synthetic operator's note"
    call_command(
        "release_hold",
        f"--tenant={migrated_tenant.number}",
        f"--document={scene.document.number}",
        f"--reason={note}",
    )
    page = scene.holder_client.get(f"/document/{scene.document.number}/edit/").content.decode()
    assert note not in page
    assert "reservation" not in page.split('class="band end"', 1)[1].split("</p>", 1)[0]
    assert "operator" in page


def test_take_back_closes_the_old_editors_and_needs_a_kept_draft(
    migrated_tenant: Any, scene: Scene
) -> None:
    """The editors left open on the kept draft belonged to the ended hold: taking it back closes
    them, so none keeps the new hold from finishing. A take-back that finds nothing kept — it was
    discarded from another tab — takes nothing."""
    from editing import holds
    from editing.models import OpenEditor

    number = scene.document.number
    hold, draft = take_with_draft(migrated_tenant, scene)
    assert scene.holder_client.post(f"/document/{number}/edit/load/").status_code == 200
    scene.holder_client.post(f"/document/{number}/edit/reserve/")
    ended = scene.admin_client.post(
        f"/document/{number}/edit/end-reservation/", {"reason": REASON, "hold": str(hold.pk)}
    )
    assert redirected_to(ended, f"/document/{number}/")
    assert redirected_to(
        scene.holder_client.post(f"/document/{number}/edit/take-back/"), f"/document/{number}/edit/"
    )
    with schema_context(migrated_tenant.number):
        assert not OpenEditor.objects.filter(draft=draft, closed_at__isnull=True).exists()
    # Nothing kept: a take-back takes nothing.
    assert scene.holder_client.post(f"/document/{number}/edit/discard-draft/").status_code == 404
    with schema_context(migrated_tenant.number):
        from documents.locks import document_lock
        from editing.models import Hold, ReleaseKind

        with document_lock(migrated_tenant.number, number), transaction.atomic():
            holds.release(
                Hold.objects.get(document=scene.document, released_at__isnull=True),
                ReleaseKind.DISCARDED,
            )
        with pytest.raises(holds.NothingKept):
            holds.take(scene.document, scene.other, take_back=True)
        assert not Hold.objects.filter(document=scene.document, released_at__isnull=True).exists()


def test_a_taken_back_draft_keeps_its_files_and_entities(
    migrated_tenant: Any, scene: Scene, queued_authorship: list[Any]
) -> None:
    """A kept draft's staged image and declared entity move with it, and its holder's finish
    commits both."""
    from django.utils import timezone

    from documents import entities, gitstore
    from editing import services
    from editing.models import Draft, DraftFile

    image = b"a synthetic image staged before the release"
    path = f"images/{hashlib.sha256(image).hexdigest()}.png"
    declared = entities.dump([entities.Declared("role", "approver", "the approver")])
    _, draft = ended_reservation(migrated_tenant, scene)
    with schema_context(migrated_tenant.number):
        Draft.objects.filter(pk=draft.pk).update(
            content={
                **draft.content,
                "document.md": DRAFT + f"\n![A synthetic plan]({path})\n",
                "entities.yaml": declared,
            }
        )
        DraftFile.objects.create(
            draft_id=draft.pk,
            kind="image",
            path=path,
            operation="add",
            content=image,
            file_name="plan.png",
            sha256=hashlib.sha256(image).hexdigest(),
            at=timezone.now(),
        )
    number = scene.document.number
    taken = scene.holder_client.post(f"/document/{number}/edit/take-back/")
    assert redirected_to(taken, f"/document/{number}/edit/"), taken.status_code
    [hold] = open_holds(migrated_tenant, scene.document)

    with schema_context(migrated_tenant.number):
        version = services.commit_draft(hold, scene.holder, "Taken back and finished")
        repo = gitstore.open_repository(migrated_tenant.number, number)
        assert gitstore.read(repo, path, version.commit_sha) == image
        assert gitstore.read(repo, "entities.yaml", version.commit_sha).decode() == declared
