"""An archived document's gate (DL-0084, DL-0233, DL-0449, DL-0450): to an administrator — of the
organisation, or the platform's acting in it — every read-only page of an archived document opens
with the *archived* tag, as its active twin's opens without it, and an export asked for there is
made and served; every act on it is refused and writes nothing, though the same act by the same
person on the twin succeeds; and its group links stay open to change.

Each act's twin is a document set up the same way, linked to the same group, put in the state the
act needs; the act runs there first, and must succeed, before the archived document is archived and
the act is tried on it.

People, groups, titles and texts are synthetic examples; every text is invented."""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
from django.contrib.messages import constants, get_messages
from django.test import Client

from access.rights import Right
from tenancy.schemas import schema_context

_spec = importlib.util.spec_from_file_location(
    "archive_gate_review_fixtures", Path(__file__).resolve().parents[1] / "review" / "conftest.py"
)
assert _spec is not None and _spec.loader is not None
_review = importlib.util.module_from_spec(_spec)
# Registered before it runs: its dataclass looks its own module up by name.
sys.modules[_spec.name] = _review
_spec.loader.exec_module(_review)
commit_version = _review.commit_version

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

COLLEAGUE = "colleague.synthetic@example.test"
ADMINISTRATOR = "administrator.synthetic@example.test"
BODY = "# Synthetic terms\n\nThe first synthetic sentence.\nThe second synthetic sentence.\n"
LATER = BODY + "\nA later synthetic sentence by the colleague.\n"
DRAFTED = "\nThe administrator's synthetic draft sentence.\n"
SCHEDULE = ("Synthetic schedule", "schedule.txt", b"Synthetic attachment bytes.\n")
REASON = "Synthetic reason: the terms need another look"
# The state tags' own markup (`review/templates/review/state_tag.html`): never the word, which
# the page may give in Ukrainian.
ARCHIVED_TAG = 'data-state="archived"'


# --- the two documents ---------------------------------------------------------------------------


@dataclass
class Pair:
    """Two documents set up alike — created by the colleague, a tenant administrator, both linked
    to one group holding every right, each with one version carrying `SCHEDULE` accepted as `0.1`
    by the colleague: `archived`, the one that will be archived, and `twin`, which stays active."""

    tenant: Any
    colleague: Any
    colleague_client: Client
    group: Any
    commit: Callable[..., Any]
    archived: Any
    twin: Any
    made: dict[str, Any] = field(default_factory=dict)

    def join(self, membership: Any) -> None:
        """`membership` made a member of the group of every right."""
        with schema_context(self.tenant.number):
            self.group.add_member(membership, by=self.colleague)

    def once(self, name: str, make: Callable[[], Any]) -> Any:
        """What `make` returns, made once for both documents."""
        if name not in self.made:
            self.made[name] = make()
        return self.made[name]


@pytest.fixture
def pair(
    migrated_tenant: Any, member_of: Any, repo_root: Path, commit_parts: Any, commit_version: Any
) -> Pair:
    from access.models import AccessGroup, DocumentGroup
    from documents import services
    from documents.models import DocumentType, Folder
    from identity.models import Language
    from review import services as review

    colleague_client, colleague, membership = member_of(COLLEAGUE, is_tenant_admin=True)
    Language.objects.get_or_create(code="uk", defaults={"label": "uk", "actor_kind": "system"})
    documents = []
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(
            name="Every right (synthetic example)", created_by=colleague, actor_kind="user"
        )
        for right in Right:
            group.grant(right, by=colleague)
        group.add_member(membership, by=colleague)
        for title in ("Synthetic procedure to archive", "Synthetic procedure kept active"):
            document = services.create_document(
                colleague,
                title,
                "uk",
                DocumentType.objects.get(code="document"),
                Folder.objects.get(number=1),
            )
            DocumentGroup.link(document, group, by=colleague)
            documents.append(document)
    for document in documents:
        commit_parts(document, colleague, BODY, [SCHEDULE])
        with schema_context(migrated_tenant.number):
            assert review.accept(document, colleague).number == "0.1"
    archived, twin = documents
    return Pair(migrated_tenant, colleague, colleague_client, group, commit_version, archived, twin)


def archive_it(pair: Pair, by: Any) -> None:
    """Archive `pair.archived` as `by`, through the archiving service."""
    from documents import archive
    from documents.models import Document

    with schema_context(pair.tenant.number):
        document = Document.objects.get(pk=pair.archived.pk)
        assert archive.archive(document, by) is True
        assert Document.objects.get(pk=pair.archived.pk).state == "archived"


def administrator(member_of: Any, kind: str) -> tuple[Client, Any, Any]:
    """A tenant administrator, or a platform administrator acting in the organisation."""
    made: tuple[Client, Any, Any] = member_of(
        ADMINISTRATOR, is_tenant_admin=kind == "tenant", is_platform_admin=kind == "platform"
    )
    return made


# --- what must not change ------------------------------------------------------------------------


def _rows(queryset: Any) -> list[dict[str, Any]]:
    return list(queryset.order_by("pk").values())


def footprint(tenant: Any, document: Any) -> dict[str, Any]:
    """Everything a refused act must leave as it was: the audit trail's length; the document's row,
    its holds, drafts, their files and open editors, versions, acceptances, returns, freezes,
    editions and links; and every reference of its repository."""
    from access.models import DocumentGroup
    from audit.models import AuditEvent
    from documents import gitstore
    from documents.models import Document, Version
    from editing.models import Draft, DraftFile, Hold, OpenEditor
    from editions.models import Edition, Freeze
    from review.models import Acceptance, Return

    with schema_context(tenant.number):
        repo = gitstore.open_repository(tenant.number, document.number)
        references = {name: str(repo.references[name].resolve().target) for name in repo.references}
        return {
            "audit events": AuditEvent.objects.count(),
            "document": _rows(Document.objects.filter(pk=document.pk)),
            "holds": _rows(Hold.objects.filter(document=document)),
            "drafts": _rows(Draft.objects.filter(hold__document=document)),
            "draft files": _rows(DraftFile.objects.filter(draft__hold__document=document)),
            "open editors": _rows(OpenEditor.objects.filter(draft__hold__document=document)),
            "versions": _rows(Version.objects.filter(document=document)),
            "acceptances": _rows(Acceptance.objects.filter(version__document=document)),
            "returns": _rows(Return.objects.filter(version__document=document)),
            "freezes": _rows(Freeze.objects.filter(document=document)),
            "editions": _rows(Edition.objects.filter(version__document=document)),
            "links": _rows(DocumentGroup.objects.filter(document=document)),
            "references": references,
        }


def errors_in(response: Any) -> list[str]:
    """The error messages the request left for the next page."""
    return [str(m) for m in get_messages(response.wsgi_request) if m.level == constants.ERROR]


def assert_refused(response: Any) -> None:
    """`404`, or the act's own refusal: a `4xx` page, or a redirect carrying an error message."""
    if response.status_code == 302:
        assert errors_in(response), "redirected without a refusal"
    else:
        assert 400 <= response.status_code < 500, response.status_code


def redirected_to(response: Any, path: str) -> bool:
    return bool(response.status_code == 302 and urlsplit(response["Location"]).path == path)


# --- the read-only pages -------------------------------------------------------------------------


def read_only_pages(number: int) -> list[str]:
    return [
        f"/document/{number}/",
        f"/document/{number}/info/",
        f"/document/{number}/history/",
        f"/document/{number}/pending/",
        f"/document/{number}/version/0.1/",
        f"/document/{number}/compare/?from=0.1&to=0.1-1",
        f"/document/{number}/export/",
        f"/document/{number}/version/0.1/export/",
    ]


def attachments(number: int) -> list[str]:
    return [
        f"/document/{number}/attachment/1/",
        f"/document/{number}/version/0.1/attachment/1/",
    ]


def with_a_pending_run(pair: Pair) -> None:
    """`LATER` committed on both documents by the colleague: a run waiting as `0.1-1`."""
    for document in (pair.archived, pair.twin):
        pair.commit(document, pair.colleague, LATER, "edit")


@pytest.mark.parametrize("kind", ["tenant", "platform"])
def test_administrators_open_every_read_only_page(kind: str, member_of: Any, pair: Pair) -> None:
    client, _, _ = administrator(member_of, kind)
    with_a_pending_run(pair)

    for path in read_only_pages(pair.twin.number):
        response = client.get(path)
        assert response.status_code == 200, path
        assert ARCHIVED_TAG not in response.content.decode(), path
    for path in attachments(pair.twin.number):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.content == SCHEDULE[2], path

    archive_it(pair, pair.colleague)

    for path in read_only_pages(pair.archived.number):
        response = client.get(path)
        assert response.status_code == 200, path
        assert ARCHIVED_TAG in response.content.decode(), path
    for path in attachments(pair.archived.number):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.content == SCHEDULE[2], path


@pytest.mark.parametrize("kind", ["tenant", "platform"])
def test_administrators_export_an_archived_document(
    kind: str, member_of: Any, pair: Pair, queued_exports: list[tuple[Any, ...]]
) -> None:
    """The dialog's `POST` on the archived document makes a job whose status and download answer
    as they do on the active twin."""
    from rendering.export import job as jobs

    client, _, _ = administrator(member_of, kind)
    with_a_pending_run(pair)

    def exported(document: Any) -> None:
        number = document.number
        asked = client.post(
            f"/document/{number}/export/",
            {"document": "on", "format": "markdown", "view": "accepted"},
        )
        assert asked.status_code == 302, asked.status_code
        job_id = queued_exports[-1][1]
        assert urlsplit(asked["Location"]).path == f"/document/{number}/export/{job_id}/"
        with schema_context(pair.tenant.number):
            jobs.run(job_id, pair.tenant.number)
        status = client.get(f"/document/{number}/export/{job_id}/")
        assert status.status_code == 200
        assert f"/document/{number}/export/{job_id}/download/" in status.content.decode()
        download = client.get(f"/document/{number}/export/{job_id}/download/")
        assert download.status_code == 200
        assert b"".join(download.streaming_content)  # type: ignore[attr-defined]

    exported(pair.twin)
    archive_it(pair, pair.colleague)
    exported(pair.archived)


# --- the acts ------------------------------------------------------------------------------------


@dataclass
class Scene:
    """The pair, the administrator acting — a tenant administrator and a member of the group of
    every right — and the colleague, who holds where an act ends someone else's hold."""

    pair: Pair
    client: Client
    user: Any

    @property
    def tenant(self) -> Any:
        return self.pair.tenant


@pytest.fixture
def scene(member_of: Any, pair: Pair) -> Scene:
    client, user, membership = administrator(member_of, "tenant")
    pair.join(membership)
    return Scene(pair, client, user)


def _json(client: Client, path: str, **body: Any) -> Any:
    return client.post(path, data=json.dumps(body), content_type="application/json")


def _open_hold(scene: Scene, document: Any) -> Any:
    from editing.models import Hold

    with schema_context(scene.tenant.number):
        return Hold.objects.filter(document=document, released_at__isnull=True).first()


def _taken(scene: Scene, document: Any) -> Any:
    """The administrator's hold on `document`, taken as the edit tab takes it."""
    taken = scene.client.post(f"/document/{document.number}/edit/take/")
    assert taken.status_code == 200, taken.status_code
    hold = _open_hold(scene, document)
    assert hold is not None and hold.user_id == scene.user.pk
    return hold


def _with_changes(scene: Scene, document: Any) -> dict[str, Any]:
    """The administrator holds `document`, `DRAFTED` added to the draft."""
    from editing.models import Draft

    hold = _taken(scene, document)
    with schema_context(scene.tenant.number):
        draft = Draft.objects.get(hold=hold)
        draft.content = {**draft.content, "document.md": draft.content["document.md"] + DRAFTED}
        draft.save()
    return {"hold": str(hold.pk)}


def _with_an_editor(scene: Scene, document: Any) -> dict[str, Any]:
    """The administrator holds `document` with an editor open on the whole draft."""
    _taken(scene, document)
    loaded = _json(scene.client, f"/document/{document.number}/edit/load/")
    assert loaded.status_code == 200, loaded.status_code
    answer: dict[str, Any] = loaded.json()
    return answer


def _reserved(scene: Scene, document: Any) -> dict[str, Any]:
    """The administrator holds `document` and has reserved it."""
    _taken(scene, document)
    reserved = scene.client.post(f"/document/{document.number}/edit/reserve/")
    assert redirected_to(reserved, f"/document/{document.number}/edit/"), reserved.status_code
    hold = _open_hold(scene, document)
    assert hold.reserved_at is not None
    return {"hold": str(hold.pk)}


def _held_by_the_colleague(scene: Scene, document: Any, *, reserve: bool) -> dict[str, Any]:
    client = scene.pair.colleague_client
    assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
    if reserve:
        reserved = client.post(f"/document/{document.number}/edit/reserve/")
        assert redirected_to(reserved, f"/document/{document.number}/edit/"), reserved.status_code
    hold = _open_hold(scene, document)
    assert hold is not None and hold.user_id == scene.pair.colleague.pk
    assert (hold.reserved_at is not None) == reserve
    return {"hold": str(hold.pk)}


def _kept_draft(scene: Scene, document: Any) -> dict[str, Any]:
    """The administrator's hold, with changes, forced released by the colleague: the draft kept."""
    from editing import holds

    data = _with_changes(scene, document)
    forced = scene.pair.colleague_client.post(
        f"/document/{document.number}/edit/force-release/", {"hold": data["hold"]}
    )
    assert redirected_to(forced, f"/document/{document.number}/"), forced.status_code
    with schema_context(scene.tenant.number):
        assert holds.open_hold(document) is None
        assert holds.preserved_draft(document, scene.user) is not None
    return data


def _pending(scene: Scene, document: Any) -> dict[str, Any]:
    """`LATER` waiting as `0.1-1`, by the colleague."""
    version = scene.pair.commit(document, scene.pair.colleague, LATER, "edit")
    return {"confirmed": version.commit_sha}


def _frozen(scene: Scene, document: Any) -> dict[str, Any]:
    """Frozen by the colleague, `0.1` accepted and nothing waiting: ready to be made canonical by
    the administrator, who accepted nothing it would carry."""
    from editions import services as editions

    with schema_context(scene.tenant.number):
        editions.freeze(document, scene.pair.colleague, "Synthetic reason: the board decides")
        target = editions.canonical_target(document)
    assert target is not None
    return {"confirmed": target[0].commit_sha}


def _policy(scene: Scene) -> Any:
    from documents import types

    def make() -> Any:
        with schema_context(scene.tenant.number):
            return types.add_type("Policy (synthetic example)", by=scene.user)

    return scene.pair.once("policy", make)


def _target(scene: Scene) -> Any:
    from documents import folders
    from documents.models import Folder

    def make() -> Any:
        with schema_context(scene.tenant.number):
            return folders.create_folder(
                Folder.objects.get(number=1), "Target (synthetic example)", by=scene.user
            )

    return scene.pair.once("target", make)


def _nothing(scene: Scene, document: Any) -> dict[str, Any]:
    return {}


Arrange = Callable[[Scene, Any], dict[str, Any]]
Request = Callable[[Scene, Any, dict[str, Any]], Any]
Done = Callable[[Scene, Any, dict[str, Any], Any], None]


@dataclass
class Act:
    name: str
    arrange: Arrange
    request: Request
    done: Done


def _ok(scene: Scene, document: Any, data: dict[str, Any], response: Any) -> None:
    assert response.status_code == 200, response.status_code


def _post(route: str, **fields: Any) -> Request:
    """A form `POST` to `/document/<n>/<route>/`, with `fields` and the arrangement's values
    named in them as `"{key}"`."""

    def request(scene: Scene, document: Any, data: dict[str, Any]) -> Any:
        body = {k: v.format(**data) if isinstance(v, str) else v for k, v in fields.items()}
        return scene.client.post(f"/document/{document.number}/{route}/", body)

    return request


def _get(route: str) -> Request:
    def request(scene: Scene, document: Any, data: dict[str, Any]) -> Any:
        return scene.client.get(f"/document/{document.number}/{route}")

    return request


def _editor_post(route: str, *, with_body: bool = False) -> Request:
    def request(scene: Scene, document: Any, data: dict[str, Any]) -> Any:
        body: dict[str, Any] = {"editor": data["editor"]}
        if with_body:
            body |= {"base_hash": data["base_hash"], "body": data["body"] + DRAFTED}
        return _json(scene.client, f"/document/{document.number}/edit/{route}/", **body)

    return request


def _answered_with(key: str) -> Done:
    def done(scene: Scene, document: Any, data: dict[str, Any], response: Any) -> None:
        assert response.status_code == 200, response.status_code
        assert key in response.json(), response.json()

    return done


def _took(scene: Scene, document: Any, data: dict[str, Any], response: Any) -> None:
    assert response.status_code == 200, response.status_code
    hold = _open_hold(scene, document)
    assert hold is not None and hold.user_id == scene.user.pk


def _loaded(scene: Scene, document: Any, data: dict[str, Any], response: Any) -> None:
    from editing.models import OpenEditor

    assert response.status_code == 200, response.status_code
    with schema_context(scene.tenant.number):
        assert OpenEditor.objects.filter(pk=response.json()["editor"]).exists()


def _captured(scene: Scene, document: Any, data: dict[str, Any], response: Any) -> None:
    from editing.models import Draft

    assert response.status_code == 200, response.status_code
    with schema_context(scene.tenant.number):
        draft = Draft.objects.get(hold__document=document, hold__released_at__isnull=True)
        assert draft.content["document.md"] == data["body"] + DRAFTED


def _closed(scene: Scene, document: Any, data: dict[str, Any], response: Any) -> None:
    from editing.models import OpenEditor

    assert response.status_code == 200, response.status_code
    with schema_context(scene.tenant.number):
        assert OpenEditor.objects.get(pk=data["editor"]).closed_at is not None


def _versions(scene: Scene, document: Any) -> int:
    from documents.models import Version

    with schema_context(scene.tenant.number):
        return Version.objects.filter(document=document).count()


def _counting_versions(arrange: Arrange) -> Arrange:
    def counted(scene: Scene, document: Any) -> dict[str, Any]:
        data = arrange(scene, document)
        return data | {"versions": _versions(scene, document)}

    return counted


def _sent(scene: Scene, document: Any, data: dict[str, Any], response: Any) -> None:
    assert redirected_to(response, f"/document/{document.number}/"), response.status_code
    assert _versions(scene, document) == data["versions"] + 1
    assert _open_hold(scene, document) is None


def _discarded(scene: Scene, document: Any, data: dict[str, Any], response: Any) -> None:
    from editing.models import Draft

    assert redirected_to(response, f"/document/{document.number}/"), response.status_code
    assert _open_hold(scene, document) is None
    with schema_context(scene.tenant.number):
        assert not Draft.objects.filter(hold_id=data["hold"]).exists()


def _to_the_tab(check: Callable[[Scene, Any, dict[str, Any]], None]) -> Done:
    def done(scene: Scene, document: Any, data: dict[str, Any], response: Any) -> None:
        assert redirected_to(response, f"/document/{document.number}/edit/"), response.status_code
        check(scene, document, data)

    return done


def _is_reserved(scene: Scene, document: Any, data: dict[str, Any]) -> None:
    hold = _open_hold(scene, document)
    assert hold is not None and hold.reserved_at is not None


def _is_not_reserved(scene: Scene, document: Any, data: dict[str, Any]) -> None:
    hold = _open_hold(scene, document)
    assert hold is not None and hold.reserved_at is None


def _held_again(scene: Scene, document: Any, data: dict[str, Any]) -> None:
    hold = _open_hold(scene, document)
    assert hold is not None and hold.user_id == scene.user.pk


def _nothing_kept(scene: Scene, document: Any, data: dict[str, Any]) -> None:
    from editing import holds

    with schema_context(scene.tenant.number):
        assert holds.preserved_draft(document, scene.user) is None


def _released(kind: str) -> Done:
    def done(scene: Scene, document: Any, data: dict[str, Any], response: Any) -> None:
        from editing.models import Hold

        assert redirected_to(response, f"/document/{document.number}/"), response.status_code
        with schema_context(scene.tenant.number):
            assert Hold.objects.get(pk=data["hold"]).release_kind == kind

    return done


def _accepted(scene: Scene, document: Any, data: dict[str, Any], response: Any) -> None:
    from review.models import Acceptance

    assert redirected_to(response, f"/document/{document.number}/"), response.status_code
    with schema_context(scene.tenant.number):
        assert Acceptance.objects.filter(version__document=document).count() == 2


def _returned(scene: Scene, document: Any, data: dict[str, Any], response: Any) -> None:
    from review.models import Return

    assert redirected_to(response, f"/document/{document.number}/pending/"), response.status_code
    with schema_context(scene.tenant.number):
        assert Return.objects.filter(version__document=document).exists()


def _undone(scene: Scene, document: Any, data: dict[str, Any], response: Any) -> None:
    from editing.models import Draft

    assert redirected_to(response, f"/document/{document.number}/edit/"), response.status_code
    with schema_context(scene.tenant.number):
        draft = Draft.objects.get(hold__document=document, hold__released_at__isnull=True)
        assert draft.hold.user_id == scene.user.pk
        assert "undo" in draft.content


def _on_the_page(check: Callable[[Scene, Any], bool]) -> Done:
    def done(scene: Scene, document: Any, data: dict[str, Any], response: Any) -> None:
        assert redirected_to(response, f"/document/{document.number}/"), response.status_code
        assert errors_in(response) == []
        with schema_context(scene.tenant.number):
            assert check(scene, document)

    return done


def _is_frozen(scene: Scene, document: Any) -> bool:
    from editions.models import open_freeze

    return open_freeze(document) is not None


def _is_unfrozen(scene: Scene, document: Any) -> bool:
    from editions.models import open_freeze

    return open_freeze(document) is None


def _is_canonical(scene: Scene, document: Any) -> bool:
    from editions.models import Edition

    return Edition.objects.filter(version__document=document).exists()


def _retyped(scene: Scene, document: Any, data: dict[str, Any], response: Any) -> None:
    from documents.models import Document

    assert redirected_to(response, f"/document/{document.number}/info/"), response.status_code
    with schema_context(scene.tenant.number):
        assert Document.objects.get(pk=document.pk).document_type_id == _policy(scene).pk


def _moved(scene: Scene, document: Any, data: dict[str, Any], response: Any) -> None:
    from documents.models import Document

    assert response.status_code == 302, response.status_code
    with schema_context(scene.tenant.number):
        assert Document.objects.get(pk=document.pk).folder_id == _target(scene).pk


def _type_arranged(scene: Scene, document: Any) -> dict[str, Any]:
    return {"code": _policy(scene).code}


def _move_arranged(scene: Scene, document: Any) -> dict[str, Any]:
    return {"target": str(_target(scene).number)}


def _move(scene: Scene, document: Any, data: dict[str, Any]) -> Any:
    return scene.client.post(
        "/administration/tenant/folders/1/move/",
        {"document": [str(document.number)], "to": data["target"]},
    )


def _undo_arranged(scene: Scene, document: Any) -> dict[str, Any]:
    return _pending(scene, document)


ACTS = [
    Act("open the edit tab", _nothing, _get("edit/"), _ok),
    Act("take the document", _nothing, _post("edit/take"), _took),
    Act(
        "load",
        lambda scene, document: {"hold": str(_taken(scene, document).pk)},
        lambda scene, document, data: _json(
            scene.client, f"/document/{document.number}/edit/load/"
        ),
        _loaded,
    ),
    Act("capture", _with_an_editor, _editor_post("capture", with_body=True), _captured),
    Act("heartbeat", _with_an_editor, _editor_post("heartbeat"), _answered_with("others")),
    Act("close", _with_an_editor, _editor_post("close"), _closed),
    Act(
        "changes",
        _with_an_editor,
        lambda scene, document, data: _json(
            scene.client,
            f"/document/{document.number}/edit/changes/",
            editor=data["editor"],
            body=data["body"] + DRAFTED,
        ),
        _answered_with("html"),
    ),
    # The finishing screen is a `GET`: the code's method for the route.
    Act("finish", _with_changes, _get("edit/finish/"), _ok),
    Act(
        "send",
        _counting_versions(_with_changes),
        _post("edit/send", choice="create", summary="Synthetic summary of the change"),
        _sent,
    ),
    Act("discard", _with_changes, _post("edit/discard"), _discarded),
    Act("my edits", _with_changes, _get("my-edits/"), _ok),
    Act(
        "reserve",
        lambda scene, document: {"hold": str(_taken(scene, document).pk)},
        _post("edit/reserve"),
        _to_the_tab(_is_reserved),
    ),
    Act(
        "cancel the reservation",
        _reserved,
        _post("edit/cancel-reservation"),
        _to_the_tab(_is_not_reserved),
    ),
    Act(
        "open the end of a reservation",
        lambda scene, document: _held_by_the_colleague(scene, document, reserve=True),
        _get("edit/end-reservation/"),
        _ok,
    ),
    Act(
        "end a reservation",
        lambda scene, document: _held_by_the_colleague(scene, document, reserve=True),
        _post("edit/end-reservation", reason=REASON, hold="{hold}"),
        _released("forced"),
    ),
    Act(
        "force the release",
        lambda scene, document: _held_by_the_colleague(scene, document, reserve=False),
        _post("edit/force-release", hold="{hold}"),
        _released("forced"),
    ),
    Act("take back", _kept_draft, _post("edit/take-back"), _to_the_tab(_held_again)),
    Act("discard the draft", _kept_draft, _post("edit/discard-draft"), _to_the_tab(_nothing_kept)),
    Act("accept", _pending, _post("pending/accept", confirmed="{confirmed}"), _accepted),
    Act(
        "return",
        _pending,
        _post("pending/return", reason=REASON, confirmed="{confirmed}"),
        _returned,
    ),
    Act("undo", _undo_arranged, _post("history/undo", version="0.1-1"), _undone),
    Act(
        "freeze",
        _nothing,
        _post("freeze", reason="Synthetic reason: the board decides"),
        _on_the_page(_is_frozen),
    ),
    Act("unfreeze", _frozen, _post("unfreeze"), _on_the_page(_is_unfrozen)),
    Act(
        "make canonical",
        _frozen,
        _post("make-canonical", confirmed="{confirmed}"),
        _on_the_page(_is_canonical),
    ),
    Act("change the type", _type_arranged, _post("info/type", document_type="{code}"), _retyped),
    Act("move it to another folder", _move_arranged, _move, _moved),
]


@pytest.mark.parametrize("act", ACTS, ids=[act.name for act in ACTS])
def test_every_act_is_refused(scene: Scene, act: Act) -> None:
    """The act succeeds on the active twin; on the archived document, set up the same way, it is
    refused and nothing is written."""
    pair = scene.pair
    on_archived = act.arrange(scene, pair.archived)
    on_twin = act.arrange(scene, pair.twin)

    act.done(scene, pair.twin, on_twin, act.request(scene, pair.twin, on_twin))

    archive_it(pair, scene.user)
    before = footprint(scene.tenant, pair.archived)
    refused = act.request(scene, pair.archived, on_archived)

    assert_refused(refused)
    assert footprint(scene.tenant, pair.archived) == before


def test_links_stay_open_on_an_archived_document(scene: Scene) -> None:
    """Linking and unlinking a group are not refused on an archived document: they take effect on
    restore."""
    from access.models import AccessGroup, DocumentGroup

    pair = scene.pair
    with schema_context(scene.tenant.number):
        readers = AccessGroup.objects.create(
            name="Readers (synthetic example)", created_by=scene.user, actor_kind="user"
        )
        readers.grant(Right.VIEW_ACCEPTED, by=scene.user)

    def linked(document: Any) -> bool:
        with schema_context(scene.tenant.number):
            return DocumentGroup.objects.filter(document=document, group=readers).exists()

    def link_and_unlink(document: Any) -> None:
        path = f"/administration/tenant/document-links/{document.number}/"
        link = scene.client.post(path, {"group": str(readers.pk), "action": "link"})
        assert link.status_code == 302, link.status_code
        assert linked(document)
        unlink = scene.client.post(path, {"group": str(readers.pk), "action": "unlink"})
        assert unlink.status_code == 302, unlink.status_code
        assert not linked(document)

    link_and_unlink(pair.twin)
    archive_it(pair, scene.user)
    link_and_unlink(pair.archived)
